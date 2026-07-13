from __future__ import annotations

from functools import wraps

from flask import g, jsonify, redirect, request, url_for


def _is_api_request() -> bool:
    return request.path.startswith("/api/") or request.is_json


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not getattr(g, "user", None):
            if _is_api_request():
                return jsonify({"error": "未登录", "login_url": "/login"}), 401
            return redirect(url_for("login_page", next=request.full_path.rstrip("?")))
        return view_func(*args, **kwargs)

    return wrapper


def require_role(*roles: str):
    allowed = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if not user:
                if _is_api_request():
                    return jsonify({"error": "未登录", "login_url": "/login"}), 401
                return redirect(url_for("login_page", next=request.full_path.rstrip("?")))
            role = user.get("role")
            if role not in allowed:
                return jsonify({"error": "权限不足", "role": role, "allowed_roles": sorted(allowed)}), 403
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
