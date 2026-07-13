from __future__ import annotations

from .solver import solve_schedule


def student_schedule(problem, class_id: str) -> list[dict]:
    result = solve_schedule(problem, strategy="student")
    return [lesson.to_dict() for lesson in result.schedule if lesson.class_id == class_id]


def student_exams(problem, class_id: str) -> list[dict]:
    lessons = student_schedule(problem, class_id)
    return [
        {
            "id": f"EXAM_{lesson['course_id']}",
            "course_name": lesson["course_name"],
            "day": lesson["day"],
            "period": lesson["period"],
            "room_name": lesson["room_name"],
            "type": "阶段测评",
        }
        for lesson in lessons[:3]
    ]
