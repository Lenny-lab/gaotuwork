from __future__ import annotations

from collections import Counter

from .models import Problem, ScheduledLesson


def validate_problem(problem: Problem) -> list[str]:
    errors: list[str] = []
    ids = {
        "教师": [x.id for x in problem.teachers],
        "教室": [x.id for x in problem.rooms],
        "班级": [x.id for x in problem.classes],
        "时间槽": [x.id for x in problem.time_slots],
        "课程": [x.id for x in problem.courses],
    }
    for label, values in ids.items():
        duplicates = [key for key, count in Counter(values).items() if count > 1]
        if duplicates:
            errors.append(f"{label} ID 重复: {', '.join(duplicates)}")

    teacher_ids, class_ids, slot_ids = set(ids["教师"]), set(ids["班级"]), set(ids["时间槽"])
    for course in problem.courses:
        if course.class_id not in class_ids:
            errors.append(f"课程 {course.id} 引用了不存在的班级 {course.class_id}")
        if course.sessions <= 0:
            errors.append(f"课程 {course.id} 的课次数必须为正数")
        unknown_teachers = set(course.qualified_teacher_ids) - teacher_ids
        if unknown_teachers:
            errors.append(f"课程 {course.id} 引用了不存在的教师 {sorted(unknown_teachers)}")
        unknown_slots = set(course.allowed_slots) - slot_ids
        if unknown_slots:
            errors.append(f"课程 {course.id} 引用了不存在的时间槽 {sorted(unknown_slots)}")
    return errors


def validate_schedule(problem: Problem, lessons: list[ScheduledLesson]) -> list[str]:
    conflicts: list[str] = []
    teachers = {x.id: x for x in problem.teachers}
    rooms = {x.id: x for x in problem.rooms}
    classes = {x.id: x for x in problem.classes}
    courses = {x.id: x for x in problem.courses}

    for label, pairs in {
        "教师": [(x.teacher_id, x.slot_id) for x in lessons],
        "教室": [(x.room_id, x.slot_id) for x in lessons],
        "班级": [(x.class_id, x.slot_id) for x in lessons],
    }.items():
        for key, count in Counter(pairs).items():
            if count > 1:
                conflicts.append(f"{label}冲突: {key[0]} 在 {key[1]} 同时有 {count} 节课")

    for item in lessons:
        teacher, room, group, course = teachers[item.teacher_id], rooms[item.room_id], classes[item.class_id], courses[item.course_id]
        if item.slot_id in teacher.unavailable:
            conflicts.append(f"教师不可用: {teacher.name} / {item.slot_id}")
        if item.slot_id in room.unavailable:
            conflicts.append(f"教室不可用: {room.name} / {item.slot_id}")
        if item.slot_id in group.unavailable:
            conflicts.append(f"班级不可用: {group.name} / {item.slot_id}")
        if room.capacity < group.size:
            conflicts.append(f"教室容量不足: {room.name} < {group.size}")
        if not set(course.required_equipment).issubset(room.equipment):
            conflicts.append(f"教室设备不符: {room.name} / {course.name}")
        if course.subject not in teacher.qualifications or teacher.id not in course.qualified_teacher_ids:
            conflicts.append(f"教师资质不符: {teacher.name} / {course.name}")

    expected = {x.id: x.sessions for x in problem.courses}
    actual = Counter(x.course_id for x in lessons)
    for course_id, count in expected.items():
        if actual[course_id] != count:
            conflicts.append(f"课次数不符: {course_id} 需要 {count}，实际 {actual[course_id]}")
    return conflicts

