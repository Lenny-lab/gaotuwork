from __future__ import annotations

from typing import Any

from flask import session


SESSION_KEY = "classmind_user"


def login_user(user: Any) -> dict:
    payload = user.to_session() if hasattr(user, "to_session") else dict(user)
    session.clear()
    session[SESSION_KEY] = payload
    session.permanent = True
    return payload


def logout_user() -> None:
    session.clear()


def current_user() -> dict | None:
    user = session.get(SESSION_KEY)
    return dict(user) if isinstance(user, dict) else None
