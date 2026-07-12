from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from .models import Problem, ScheduledLesson, SolveResult
from .solver import solve_portfolio, solve_schedule


STRATEGY_NAMES = {"student": "学生体验优先", "teacher": "教师稳定优先", "efficiency": "校区效率优先"}


def score_result(problem: Problem, result: SolveResult) -> dict[str, Any]:
    teachers = {x.id: x for x in problem.teachers}
    groups = {x.id: x for x in problem.classes}
    rooms = {x.id: x for x in problem.rooms}
    student_hits = sum(not groups[x.class_id].preferred_slots or x.slot_id in groups[x.class_id].preferred_slots for x in result.schedule)
    teacher_hits = sum(not teachers[x.teacher_id].preferred_slots or x.slot_id in teachers[x.teacher_id].preferred_slots for x in result.schedule)
    capacity_used = sum(groups[x.class_id].size for x in result.schedule)
    capacity_total = sum(rooms[x.room_id].capacity for x in result.schedule) or 1
    lesson_count = len(result.schedule) or 1

    # 教师日均方差：每位教师每天课次数的总体方差。越低表示老师课表越均匀。
    slots_by_id = {x.id: x for x in problem.time_slots}
    daily_counts: list[int] = []
    for teacher in problem.teachers:
        for day in {s.day for s in problem.time_slots}:
            daily_counts.append(sum(
                1 for x in result.schedule
                if x.teacher_id == teacher.id and slots_by_id[x.slot_id].day == day
            ))
    if daily_counts:
        mean = sum(daily_counts) / len(daily_counts)
        stability_variance = round(sum((c - mean) ** 2 for c in daily_counts) / len(daily_counts), 2)
    else:
        stability_variance = 0.0

    return {
        "hard_conflicts": len(result.conflicts),
        "student_preference_rate": round(student_hits / lesson_count * 100, 1),
        "teacher_preference_rate": round(teacher_hits / lesson_count * 100, 1),
        "capacity_fit_rate": round(capacity_used / capacity_total * 100, 1),
        "stability_variance": stability_variance,
        "overall_score": round((student_hits / lesson_count * 35) + (teacher_hits / lesson_count * 35) + (capacity_used / capacity_total * 30), 1),
        "soft_objective": {
            "student_miss": lesson_count - student_hits,
            "teacher_miss": lesson_count - teacher_hits,
            "stability_variance": stability_variance,
        },
    }


def portfolio_payload(problem: Problem) -> dict[str, Any]:
    results = solve_portfolio(problem)
    return {
        "plans": [
            {
                "id": key,
                "name": STRATEGY_NAMES[key],
                **result.to_dict(),
                "scorecard": score_result(problem, result),
            }
            for key, result in results.items()
        ]
    }


def diff_schedules(before: list[ScheduledLesson], after: list[ScheduledLesson]) -> dict[str, Any]:
    old, new = {x.lesson_id: x for x in before}, {x.lesson_id: x for x in after}
    changes = []
    for lesson_id in sorted(set(old) | set(new)):
        a, b = old.get(lesson_id), new.get(lesson_id)
        if a and b and (a.teacher_id, a.room_id, a.slot_id) == (b.teacher_id, b.room_id, b.slot_id):
            continue
        changes.append({"lesson_id": lesson_id, "before": a.to_dict() if a else None, "after": b.to_dict() if b else None})
    return {"change_count": len(changes), "changes": changes}


def teacher_load(result: SolveResult) -> dict[str, int]:
    return dict(Counter(x.teacher_name for x in result.schedule))


def simulate_teacher_leave(problem: Problem, teacher_id: str, slot_id: str) -> dict[str, Any]:
    teacher_ids = {x.id for x in problem.teachers}
    slot_ids = {x.id for x in problem.time_slots}
    if teacher_id not in teacher_ids:
        raise ValueError(f"未知教师: {teacher_id}")
    if slot_id not in slot_ids:
        raise ValueError(f"未知时间槽: {slot_id}")

    before = solve_schedule(problem, strategy="balanced")
    changed_teachers = tuple(
        replace(x, unavailable=tuple(sorted(set(x.unavailable) | {slot_id}))) if x.id == teacher_id else x
        for x in problem.teachers
    )
    changed_problem = replace(problem, teachers=changed_teachers)
    after = solve_schedule(changed_problem, strategy="reschedule", baseline=before.schedule)
    difference = diff_schedules(before.schedule, after.schedule)
    affected_classes = sorted({
        item["after"]["class_name"] if item["after"] else item["before"]["class_name"]
        for item in difference["changes"]
    })
    return {
        "request": {"type": "teacher_leave", "teacher_id": teacher_id, "slot_id": slot_id},
        "before": before.to_dict(),
        "after": after.to_dict(),
        "diff": difference,
        "impact": {
            "changed_lessons": difference["change_count"],
            "affected_classes": affected_classes,
            "affected_class_count": len(affected_classes),
        },
    }
