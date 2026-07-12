from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ClassGroup, CourseRequest, Problem, Room, Teacher, TimeSlot


def _tuple(value: list[str] | None) -> tuple[str, ...]:
    return tuple(value or [])


def problem_from_dict(raw: dict[str, Any]) -> Problem:
    return Problem(
        time_slots=tuple(TimeSlot(**x) for x in raw["time_slots"]),
        teachers=tuple(
            Teacher(
                id=x["id"], name=x["name"],
                qualifications=_tuple(x.get("qualifications")),
                unavailable=_tuple(x.get("unavailable")),
                preferred_slots=_tuple(x.get("preferred_slots")),
            ) for x in raw["teachers"]
        ),
        rooms=tuple(
            Room(
                id=x["id"], name=x["name"], campus=x["campus"],
                capacity=x["capacity"], equipment=_tuple(x.get("equipment")),
                unavailable=_tuple(x.get("unavailable")),
            ) for x in raw["rooms"]
        ),
        classes=tuple(
            ClassGroup(
                id=x["id"], name=x["name"], size=x["size"],
                unavailable=_tuple(x.get("unavailable")),
                preferred_slots=_tuple(x.get("preferred_slots")),
            ) for x in raw["classes"]
        ),
        courses=tuple(
            CourseRequest(
                id=x["id"], name=x["name"], subject=x["subject"],
                class_id=x["class_id"], sessions=x["sessions"],
                qualified_teacher_ids=_tuple(x.get("qualified_teacher_ids")),
                required_equipment=_tuple(x.get("required_equipment")),
                allowed_slots=_tuple(x.get("allowed_slots")),
            ) for x in raw["courses"]
        ),
    )


def load_problem(path: str | Path) -> Problem:
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return problem_from_dict(raw)


def dump_json(data: Any, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
