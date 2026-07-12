from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TimeSlot:
    id: str
    day: str
    period: str
    order: int


@dataclass(frozen=True)
class Teacher:
    id: str
    name: str
    qualifications: tuple[str, ...]
    unavailable: tuple[str, ...] = ()
    preferred_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    campus: str
    capacity: int
    equipment: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClassGroup:
    id: str
    name: str
    size: int
    unavailable: tuple[str, ...] = ()
    preferred_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class CourseRequest:
    id: str
    name: str
    subject: str
    class_id: str
    sessions: int
    qualified_teacher_ids: tuple[str, ...]
    required_equipment: tuple[str, ...] = ()
    allowed_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class Problem:
    time_slots: tuple[TimeSlot, ...]
    teachers: tuple[Teacher, ...]
    rooms: tuple[Room, ...]
    classes: tuple[ClassGroup, ...]
    courses: tuple[CourseRequest, ...]


@dataclass(frozen=True)
class ScheduledLesson:
    lesson_id: str
    course_id: str
    course_name: str
    class_id: str
    class_name: str
    teacher_id: str
    teacher_name: str
    room_id: str
    room_name: str
    slot_id: str
    day: str
    period: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SolveResult:
    status: str
    schedule: list[ScheduledLesson] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "metrics": self.metrics,
            "conflicts": self.conflicts,
            "schedule": [item.to_dict() for item in self.schedule],
        }
