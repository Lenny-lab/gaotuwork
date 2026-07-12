from __future__ import annotations

from collections import defaultdict
from time import perf_counter

from ortools.sat.python import cp_model

from .models import Problem, ScheduledLesson, SolveResult
from .validator import validate_problem, validate_schedule


# 策略权重表：每个值是"对应软目标在总目标中的相对重要性"（0-10）。
# 设计原则：学生/教师/效率三个独立目标各占一组，balanced 居中，
# reschedule 几乎完全压制其它软目标，把"变更数"作为最高优先级。
STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "student":    {"preference": 10, "stability": 2,  "efficiency": 1, "change": 0,   "compactness": 3},
    "teacher":    {"preference": 2,  "stability": 10, "efficiency": 1, "change": 0,   "compactness": 3},
    "efficiency": {"preference": 1,  "stability": 2,  "efficiency": 10,"change": 0,   "compactness": 3},
    "balanced":   {"preference": 5,  "stability": 5,  "efficiency": 5, "change": 0,   "compactness": 3},
    "reschedule": {"preference": 1,  "stability": 1,  "efficiency": 1, "change": 100, "compactness": 0},
}


def _per_lesson_soft_costs(
    problem: Problem,
    variables: dict[tuple[str, str, str, str], cp_model.IntVar],
    weights: dict[str, float],
    baseline_by_lesson: dict[str, tuple[str, str, str]],
    strategy: str,
) -> list[tuple[cp_model.LinearExpr, cp_model.IntVar]]:
    """为每条 (lesson, teacher, room, slot) 计算一个 0-1 量级的软目标值。

    返回 [(expression, variable), ...]，调用方按 (weight * expression * variable) 求和。
    拆成两条目的是：让目标函数可解释（各项可单独求值），并隔离量纲。
    """
    teachers = {x.id: x for x in problem.teachers}
    rooms = {x.id: x for x in problem.rooms}
    classes = {x.id: x for x in problem.classes}
    slots = {x.id: x for x in problem.time_slots}

    costs: list[tuple[cp_model.LinearExpr, cp_model.IntVar]] = []
    for (lesson_id, teacher_id, room_id, slot_id), variable in variables.items():
        course = next(x for x in problem.courses if x.id == lesson_id.rsplit("-", 1)[0])
        group = classes[course.class_id]

        # 偏好满足：1 表示未命中偏好，0 表示命中。空偏好 = 全部命中。
        group_hit = int(bool(group.preferred_slots) and slot_id not in group.preferred_slots)
        teacher_hit = int(bool(teachers[teacher_id].preferred_slots) and slot_id not in teachers[teacher_id].preferred_slots)
        preference_cost = group_hit + teacher_hit

        # 容量适配：浪费座位数 / 教室容量，归一化到 [0, 1]。0 = 容量正好。
        capacity = max(1, rooms[room_id].capacity)
        capacity_waste = max(0, capacity - group.size) / capacity

        # 紧凑度：希望课次尽量排在周内靠前的时段（admin/老师都不喜欢周五最后一节）。
        # 把 order 归一化到 [0, 1]：order=1 -> 0，最后一个 -> 1。
        max_order = max(1, max(s.order for s in problem.time_slots))
        compactness_cost = (slots[slot_id].order - 1) / max_order

        # 变更惩罚：reschedule 专用。每变一条 = 1。
        baseline = baseline_by_lesson.get(lesson_id)
        change_cost = 1 if strategy == "reschedule" and baseline != (teacher_id, room_id, slot_id) else 0

        cost_expr = (
            weights["preference"] * preference_cost
            + weights["efficiency"] * capacity_waste
            + weights["compactness"] * compactness_cost
            + weights["change"] * change_cost
        )
        costs.append((cost_expr, variable))
    return costs


def _stability_cost(
    problem: Problem,
    variables: dict[tuple[str, str, str, str], cp_model.IntVar],
    weights: dict[str, float],
    n_slots: int,
    model: cp_model.CpModel,
) -> tuple[int, cp_model.LinearExpr]:
    """教师日均课次方差软目标。

    思路：每位教师每天的课次计数 c_{t,d} 写为线性表达式（用变量加和），
    然后用 (c - mean)^2 的一阶泰勒近似 ∝ |c - mean| 引入线性代价。
    对每位教师每天，构造辅助变量 u_{t,d} >= c_{t,d} - mean、u_{t,d} >= mean - c_{t,d}。
    这样整个稳定度目标保持线性，可被 CP-SAT 求解。

    返回 (active, expression)：
    - active=0 表示未构造任何辅助变量（无需计入目标）
    - active=1 + expression 表示存在要最小化的稳定性目标
    """
    if weights["stability"] == 0 or n_slots == 0:
        return 0, 0  # type: ignore[return-value]

    teachers = list(problem.teachers)
    days = sorted({s.day for s in problem.time_slots})
    per_day_teacher_count: dict[tuple[str, str], list[cp_model.IntVar]] = defaultdict(list)
    for (lesson_id, teacher_id, room_id, slot_id), variable in variables.items():
        # 用 schedule 里的 day 字段需要从 slot 反查；这里直接根据 slot_id 拿到 day
        day = next(s.day for s in problem.time_slots if s.id == slot_id)
        per_day_teacher_count[(teacher_id, day)].append(variable)

    penalty_expr: list[cp_model.LinearExpr] = []
    # 期望日均 = lesson_count / (teachers * days)，做软目标
    expected_per_day = max(1, n_slots // max(1, len(teachers) * len(days)))

    for teacher in teachers:
        for day in days:
            exprs = per_day_teacher_count.get((teacher.id, day), [])
            if not exprs:
                continue
            daily_count = sum(exprs)  # LinearExpr
            dev_pos = model.new_int_var(0, len(exprs), f"dev_pos_{teacher.id}_{day}")
            dev_neg = model.new_int_var(0, len(exprs), f"dev_neg_{teacher.id}_{day}")
            # dev_pos >= daily - expected
            model.add(dev_pos >= daily_count - expected_per_day)
            # dev_neg >= expected - daily
            model.add(dev_neg >= expected_per_day - daily_count)
            penalty_expr.append((dev_pos + dev_neg))

    if not penalty_expr:
        return 0, 0  # type: ignore[return-value]
    # 直接线性加权和。CP-SAT 不支持浮点系数/LinearExpr 除法，所以把
    # "归一化到期望值" 隐式通过 weight 体现（balanced=5 / reschedule=1）。
    return 1, weights["stability"] * sum(penalty_expr)


def solve_schedule(
    problem: Problem,
    time_limit_seconds: float = 15.0,
    strategy: str = "balanced",
    baseline: list[ScheduledLesson] | None = None,
) -> SolveResult:
    data_errors = validate_problem(problem)
    if data_errors:
        return SolveResult(status="INVALID_DATA", conflicts=data_errors)

    if strategy not in STRATEGY_WEIGHTS:
        return SolveResult(status="INVALID_DATA", conflicts=[f"未知策略: {strategy}"])
    weights = STRATEGY_WEIGHTS[strategy]

    teachers = {x.id: x for x in problem.teachers}
    rooms = {x.id: x for x in problem.rooms}
    classes = {x.id: x for x in problem.classes}
    slots = {x.id: x for x in problem.time_slots}
    slot_ids = [x.id for x in sorted(problem.time_slots, key=lambda s: s.order)]

    lesson_specs = [
        (f"{course.id}-{session + 1}", course)
        for course in problem.courses
        for session in range(course.sessions)
    ]
    model = cp_model.CpModel()
    variables: dict[tuple[str, str, str, str], cp_model.IntVar] = {}
    lesson_vars: dict[str, list[cp_model.IntVar]] = defaultdict(list)

    for lesson_id, course in lesson_specs:
        group = classes[course.class_id]
        allowed = set(course.allowed_slots or slot_ids)
        for teacher_id in course.qualified_teacher_ids:
            teacher = teachers[teacher_id]
            if course.subject not in teacher.qualifications:
                continue
            for room in problem.rooms:
                if room.capacity < group.size or not set(course.required_equipment).issubset(room.equipment):
                    continue
                for slot_id in slot_ids:
                    if slot_id not in allowed or slot_id in teacher.unavailable or slot_id in room.unavailable or slot_id in group.unavailable:
                        continue
                    key = (lesson_id, teacher_id, room.id, slot_id)
                    variables[key] = model.new_bool_var("x_" + "_".join(key))
                    lesson_vars[lesson_id].append(variables[key])

    impossible = [lesson_id for lesson_id, _ in lesson_specs if not lesson_vars[lesson_id]]
    if impossible:
        return SolveResult(status="INFEASIBLE", conflicts=[f"课次无任何可行教师/教室/时段: {x}" for x in impossible])

    for lesson_id, _ in lesson_specs:
        model.add_exactly_one(lesson_vars[lesson_id])

    for teacher_id in teachers:
        for slot_id in slot_ids:
            model.add_at_most_one([v for (lesson, teacher, room, slot), v in variables.items() if teacher == teacher_id and slot == slot_id])
    for room_id in rooms:
        for slot_id in slot_ids:
            model.add_at_most_one([v for (lesson, teacher, room, slot), v in variables.items() if room == room_id and slot == slot_id])
    for class_id in classes:
        course_ids = {x.id for x in problem.courses if x.class_id == class_id}
        for slot_id in slot_ids:
            model.add_at_most_one([v for (lesson, teacher, room, slot), v in variables.items() if lesson.rsplit("-", 1)[0] in course_ids and slot == slot_id])

    # 同一课程的多次课不能落在同一时间。
    for course in problem.courses:
        lesson_ids = [f"{course.id}-{i + 1}" for i in range(course.sessions)]
        for slot_id in slot_ids:
            model.add_at_most_one([v for (lesson, teacher, room, slot), v in variables.items() if lesson in lesson_ids and slot == slot_id])

    baseline_by_lesson = {x.lesson_id: (x.teacher_id, x.room_id, x.slot_id) for x in (baseline or [])}

    # 目标 = Σ_v ( per_lesson_cost * v ) + stability_cost
    per_lesson = _per_lesson_soft_costs(problem, variables, weights, baseline_by_lesson, strategy)
    objective_terms: list[cp_model.LinearExpr] = [expr * var for expr, var in per_lesson]
    stability_active, stability_expr = _stability_cost(problem, variables, weights, len(lesson_specs), model)
    if stability_active:
        objective_terms.append(stability_expr)
    model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    started = perf_counter()
    status_code = solver.solve(model)
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(status="INFEASIBLE", conflicts=["当前硬约束组合无可行课表"], metrics={"solve_time_ms": elapsed_ms})

    courses = {x.id: x for x in problem.courses}
    schedule: list[ScheduledLesson] = []
    for (lesson_id, teacher_id, room_id, slot_id), variable in variables.items():
        if solver.value(variable) != 1:
            continue
        course = courses[lesson_id.rsplit("-", 1)[0]]
        teacher, room, slot, group = teachers[teacher_id], rooms[room_id], slots[slot_id], classes[course.class_id]
        schedule.append(ScheduledLesson(
            lesson_id=lesson_id, course_id=course.id, course_name=course.name,
            class_id=group.id, class_name=group.name,
            teacher_id=teacher.id, teacher_name=teacher.name,
            room_id=room.id, room_name=room.name,
            slot_id=slot.id, day=slot.day, period=slot.period,
        ))
    schedule.sort(key=lambda x: (slots[x.slot_id].order, x.room_id, x.lesson_id))
    conflicts = validate_schedule(problem, schedule)
    return SolveResult(
        status="OPTIMAL" if status_code == cp_model.OPTIMAL else "FEASIBLE",
        schedule=schedule,
        conflicts=conflicts,
        metrics={
            "solve_time_ms": elapsed_ms,
            "lesson_count": len(schedule),
            "hard_conflict_count": len(conflicts),
            "teacher_count": len({x.teacher_id for x in schedule}),
            "room_count": len({x.room_id for x in schedule}),
            "strategy": strategy,
            "objective_value": round(solver.objective_value, 2),
        },
    )


def solve_portfolio(problem: Problem, time_limit_seconds: float = 15.0) -> dict[str, SolveResult]:
    """生成学生、教师、运营三种可比较候选方案。"""
    return {
        strategy: solve_schedule(problem, time_limit_seconds, strategy)
        for strategy in ("student", "teacher", "efficiency")
    }
