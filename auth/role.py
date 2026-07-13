from __future__ import annotations

from classmind.users import User, bind_feishu_open_id, find_by_feishu_id, find_by_mobile


def infer_role(user_info: dict) -> str:
    """Infer a least-privilege role from mapping, department and job title."""
    open_id = user_info.get("open_id") or user_info.get("user_id") or ""
    local = find_by_feishu_id(open_id) if open_id else None
    if local:
        return local.role
    local = find_by_mobile(user_info.get("mobile", ""))
    if local:
        return local.role

    labels = [
        str(user_info.get("department_name", "")),
        str(user_info.get("job_title", "")),
        " ".join(str(x) for x in user_info.get("departments", []) or []),
    ]
    text = " ".join(labels)
    if any(keyword in text for keyword in ("学生", "学员")):
        return "student"
    if any(keyword in text for keyword in ("教师", "老师", "讲师")):
        return "teacher"
    if any(keyword in text for keyword in ("教务", "排课", "教学运营", "校区运营")):
        return "academic_affairs"
    # 未识别账号绝不能默认获得教务最高权限。
    return ""


def user_from_feishu(user_info: dict) -> User:
    open_id = user_info.get("open_id") or user_info.get("user_id") or ""
    local = find_by_feishu_id(open_id) if open_id else None
    if local:
        return local
    local = find_by_mobile(user_info.get("mobile", ""))
    if local:
        if open_id and not local.feishu_open_id:
            return bind_feishu_open_id(local.id, open_id)
        return local
    return User(
        id=open_id or "FEISHU_USER",
        feishu_open_id=open_id,
        name=user_info.get("name") or user_info.get("en_name") or "飞书用户",
        role=infer_role(user_info),
        avatar=(user_info.get("avatar_url") or user_info.get("avatar_big") or ""),
    )
