import copy
import json
import unittest
from pathlib import Path

from classmind.io import load_problem, problem_from_dict
from classmind.solver import solve_schedule
from classmind.solver import solve_portfolio
from classmind.service import portfolio_payload, score_result, simulate_teacher_leave
from classmind.validator import validate_schedule


ROOT = Path(__file__).resolve().parents[1]


class SolverTests(unittest.TestCase):
    def test_demo_produces_zero_conflict_schedule(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        result = solve_schedule(problem)
        self.assertIn(result.status, {"OPTIMAL", "FEASIBLE"})
        self.assertEqual(8, len(result.schedule))
        self.assertEqual([], result.conflicts)
        self.assertEqual([], validate_schedule(problem, result.schedule))

    def test_all_hard_constraints_hold(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        result = solve_schedule(problem)
        teacher_slots = {(x.teacher_id, x.slot_id) for x in result.schedule}
        room_slots = {(x.room_id, x.slot_id) for x in result.schedule}
        class_slots = {(x.class_id, x.slot_id) for x in result.schedule}
        self.assertEqual(len(result.schedule), len(teacher_slots))
        self.assertEqual(len(result.schedule), len(room_slots))
        self.assertEqual(len(result.schedule), len(class_slots))

    def test_impossible_capacity_is_reported(self):
        source = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        broken = copy.deepcopy(source)
        for room in broken["rooms"]:
            room["capacity"] = 1
        path = ROOT / "output" / "test-impossible.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        try:
            result = solve_schedule(load_problem(path))
            self.assertEqual("INFEASIBLE", result.status)
            self.assertTrue(result.conflicts)
        finally:
            path.unlink(missing_ok=True)

    def test_three_strategy_portfolio(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        plans = solve_portfolio(problem)
        self.assertEqual({"student", "teacher", "efficiency"}, set(plans))
        for result in plans.values():
            self.assertEqual([], result.conflicts)
            self.assertEqual(8, len(result.schedule))

    def test_scorecard_range(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        result = solve_schedule(problem, strategy="student")
        score = score_result(problem, result)
        self.assertGreaterEqual(score["overall_score"], 0)
        self.assertLessEqual(score["overall_score"], 100)
        self.assertEqual(3, len(portfolio_payload(problem)["plans"]))

    def test_problem_can_be_created_from_api_payload(self):
        raw = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        result = solve_schedule(problem_from_dict(raw), strategy="balanced")
        self.assertEqual([], result.conflicts)

    def test_demo_slots_stay_inside_business_hours_and_avoid_lunch(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        def minute(value):
            hour, minute_value = map(int, value.split(":"))
            return hour * 60 + minute_value
        for slot in problem.time_slots:
            start, end = map(minute, slot.period.split("-"))
            self.assertGreaterEqual(start, minute("08:00"))
            self.assertLessEqual(end, minute("17:30"))
            self.assertTrue(end <= minute("12:00") or start >= minute("13:30"))

    def test_teacher_leave_uses_minimum_change_reschedule(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        before = solve_schedule(problem, strategy="balanced")
        target = before.schedule[0]
        result = simulate_teacher_leave(problem, target.teacher_id, target.slot_id)
        self.assertIn(result["after"]["status"], {"OPTIMAL", "FEASIBLE"})
        self.assertEqual([], result["after"]["conflicts"])
        self.assertGreaterEqual(result["diff"]["change_count"], 1)
        self.assertLess(result["diff"]["change_count"], len(before.schedule))

    def test_strategy_weights_change_soft_objective_ranking(self):
        """三套独立策略的偏好满足率必须能反映策略意图。

        student 应比 teacher 拿到更高的 student_preference_rate，
        teacher 应比 student 拿到更高的 teacher_preference_rate。
        同时任意两套都仍是零硬冲突的完整课表。
        """
        problem = load_problem(ROOT / "data" / "demo.json")
        student = score_result(problem, solve_schedule(problem, strategy="student"))
        teacher = score_result(problem, solve_schedule(problem, strategy="teacher"))
        self.assertEqual([], solve_schedule(problem, strategy="student").conflicts)
        self.assertEqual([], solve_schedule(problem, strategy="teacher").conflicts)
        self.assertGreaterEqual(student["student_preference_rate"], teacher["student_preference_rate"])
        self.assertGreaterEqual(teacher["teacher_preference_rate"], student["teacher_preference_rate"])

    def test_stability_score_present_and_non_negative(self):
        """决策评分卡必须暴露教师日均方差，用于在 UI 上呈现稳定性。"""
        problem = load_problem(ROOT / "data" / "demo.json")
        score = score_result(problem, solve_schedule(problem, strategy="balanced"))
        self.assertIn("stability_variance", score)
        self.assertGreaterEqual(score["stability_variance"], 0)

    def test_reschedule_minimizes_change_count(self):
        """reschedule 策略下，变更数 ≤ 同教师/同时段只换老师/教室的退化方案。"""
        problem = load_problem(ROOT / "data" / "demo.json")
        before = solve_schedule(problem, strategy="balanced")
        target = before.schedule[0]
        result = simulate_teacher_leave(problem, target.teacher_id, target.slot_id)
        # reschedule 应当只改 1~3 节课，而不是把所有课全换
        self.assertLessEqual(result["diff"]["change_count"], 4)
        # 影响班级数应该小于班级总数
        self.assertLessEqual(result["impact"]["affected_class_count"], len(problem.classes))

    def test_invalid_strategy_rejected(self):
        problem = load_problem(ROOT / "data" / "demo.json")
        result = solve_schedule(problem, strategy="nonsense")
        self.assertEqual("INVALID_DATA", result.status)
        self.assertTrue(any("未知策略" in msg for msg in result.conflicts))


if __name__ == "__main__":
    unittest.main()
