from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
USERS_PATH = ROOT / "data" / "users.json"
VALID_ROLES = {"student", "teacher", "academic_affairs"}
_BINDING_LOCK = threading.Lock()


@dataclass(frozen=True)
class User:
    id: str
    feishu_open_id: str
    name: str
    role: str
    avatar: str = ""
    mobile: str = ""
    class_id: str = ""
    teacher_id: str = ""
    subjects: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_session(self) -> dict:
        return {
            "id": self.id,
            "open_id": self.feishu_open_id,
            "name": self.name,
            "role": self.role,
            "avatar": self.avatar,
            "class_id": self.class_id,
            "teacher_id": self.teacher_id,
            "grade": self.metadata.get("grade", ""),
            "age": self.metadata.get("age"),
            "teaching_grades": self.metadata.get("teaching_grades", []),
            "years_experience": self.metadata.get("years_experience"),
        }

    def to_dict(self) -> dict:
        return {
            **self.to_session(),
            "subjects": list(self.subjects),
            "permissions": list(self.permissions),
            **self.metadata,
        }


def _user_from_dict(raw: dict) -> User:
    known = {"id", "feishu_open_id", "name", "role", "avatar", "mobile", "class_id", "teacher_id", "subjects", "permissions"}
    role = raw.get("role", "")
    if role not in VALID_ROLES:
        raise ValueError(f"无效用户角色: {role}")
    return User(
        id=raw["id"],
        feishu_open_id=raw.get("feishu_open_id", ""),
        name=raw["name"],
        role=role,
        avatar=raw.get("avatar", ""),
        mobile=_normalize_mobile(raw.get("mobile", "")),
        class_id=raw.get("class_id", ""),
        teacher_id=raw.get("teacher_id", ""),
        subjects=tuple(raw.get("subjects", [])),
        permissions=tuple(raw.get("permissions", [])),
        metadata={key: value for key, value in raw.items() if key not in known},
    )


def load_users(path: Path = USERS_PATH) -> list[User]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [_user_from_dict(item) for item in payload.get("users", [])]


def find_by_feishu_id(open_id: str) -> User | None:
    if not open_id:
        return None
    return next((user for user in load_users() if user.feishu_open_id and user.feishu_open_id == open_id), None)


def _normalize_mobile(mobile: str) -> str:
    """Canonicalize Chinese mobile numbers while accepting Feishu's +86 form."""
    digits = re.sub(r"\D", "", str(mobile or ""))
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits


def find_by_mobile(mobile: str) -> User | None:
    normalized = _normalize_mobile(mobile)
    if not normalized:
        return None
    return next((user for user in load_users() if user.mobile and user.mobile == normalized), None)


def find_by_role(role: str) -> list[User]:
    return [user for user in load_users() if user.role == role]


def find_by_id(user_id: str) -> User | None:
    return next((user for user in load_users() if user.id == user_id), None)


def bind_feishu_open_id(user_id: str, open_id: str, path: Path = USERS_PATH) -> User:
    """Atomically bind a resolved Feishu Open ID to one existing business user."""
    if not open_id.startswith("ou_"):
        raise ValueError("无效飞书 Open ID")
    with _BINDING_LOCK:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("users", [])
        target = next((item for item in records if item.get("id") == user_id), None)
        if not target:
            raise KeyError(f"未找到业务用户: {user_id}")
        collision = next(
            (item for item in records if item.get("feishu_open_id") == open_id and item.get("id") != user_id),
            None,
        )
        if collision:
            raise ValueError(f"该飞书账号已绑定到 {collision.get('name') or collision.get('id')}")
        target["feishu_open_id"] = open_id
        target["mapping_status"] = "bound_by_mobile_lookup"
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
        return _user_from_dict(target)
