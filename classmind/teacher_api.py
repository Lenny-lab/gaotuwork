from __future__ import annotations

from collections import Counter

from .service import simulate_teacher_leave
from .solver import solve_schedule
from .users import load_users


def teacher_schedule(problem, teacher_id: str) -> list[dict]:
    result = solve_schedule(problem, strategy="teacher")
    return [lesson.to_dict() for lesson in result.schedule if lesson.teacher_id == teacher_id]


def teacher_students(problem, teacher_id: str) -> list[dict]:
    class_ids = {lesson["class_id"] for lesson in teacher_schedule(problem, teacher_id)}
    return [user.to_dict() for user in load_users() if user.role == "student" and user.class_id in class_ids]


def teacher_workload(problem, teacher_id: str) -> dict:
    schedule = teacher_schedule(problem, teacher_id)
    by_day = Counter(item["day"] for item in schedule)
    return {"teacher_id": teacher_id, "lesson_count": len(schedule), "class_count": len({x['class_id'] for x in schedule}), "by_day": dict(by_day)}


def submit_leave(problem, teacher_id: str, slot_id: str, reason: str) -> dict:
    result = simulate_teacher_leave(problem, teacher_id, slot_id)
    result["request"]["reason"] = reason
    result["request"]["status"] = "simulated"
    return result
