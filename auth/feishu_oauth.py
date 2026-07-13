from __future__ import annotations

from urllib.parse import quote, urlencode

import requests


AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"


class FeishuAPIError(RuntimeError):
    """A diagnostics-safe Feishu failure that never stores request payloads."""

    def __init__(self, operation: str, http_status: int, code: object = None, request_id: str = ""):
        self.operation = operation
        self.http_status = int(http_status or 0)
        self.code = code if code not in (None, "") else "unknown"
        self.request_id = str(request_id or "")[:128]
        super().__init__(f"{operation} failed (HTTP {self.http_status}, code {self.code})")


def _checked_payload(response: requests.Response, operation: str) -> dict:
    """Parse a Feishu response and raise only payload-free diagnostic fields."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    code = payload.get("code") if isinstance(payload, dict) else None
    if response.ok and code in (None, 0):
        return payload
    request_id = response.headers.get("X-Request-Id") or response.headers.get("X-Tt-Logid") or ""
    raise FeishuAPIError(operation, response.status_code, code, request_id)


def build_authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    return f"{AUTHORIZE_URL}?{urlencode({'app_id': app_id, 'redirect_uri': redirect_uri, 'state': state})}"


def exchange_code_for_token(host: str, app_id: str, app_secret: str, code: str, redirect_uri: str) -> dict:
    response = requests.post(
        f"{host}/open-apis/authen/v2/oauth/token",
        headers={"Content-Type": "application/json; charset=utf-8"},
        json={
            "grant_type": "authorization_code",
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (None, 0):
        raise RuntimeError(payload.get("msg") or "飞书 OAuth 换取 token 失败")
    return payload.get("data", payload)


def get_user_info(host: str, access_token: str) -> dict:
    response = requests.get(
        f"{host}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (None, 0):
        raise RuntimeError(payload.get("msg") or "获取飞书用户信息失败")
    return payload.get("data", payload)


def _tenant_access_token(host: str, app_id: str, app_secret: str) -> str:
    response = requests.post(
        f"{host}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=8,
    )
    payload = _checked_payload(response, "tenant_access_token")
    return payload["tenant_access_token"]


def lookup_open_id_by_mobile(host: str, app_id: str, app_secret: str, mobile: str) -> dict:
    """Resolve one tenant member's Open ID without persisting the mobile number."""
    token = _tenant_access_token(host, app_id, app_secret)
    response = requests.post(
        f"{host}/open-apis/contact/v3/users/batch_get_id",
        params={"user_id_type": "open_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={"mobiles": [mobile], "include_resigned": False},
        timeout=8,
    )
    payload = _checked_payload(response, "contact.batch_get_id")
    data = payload.get("data", {}) or {}
    users = data.get("user_list") or data.get("items") or []
    if not users:
        raise LookupError("未找到该手机号对应的可用飞书成员；请检查号码和应用通讯录范围")
    item = users[0]
    # 新版接口会把 user_id 字段按 user_id_type 返回；兼容可能直接给出 open_id 的响应。
    open_id = item.get("open_id") or item.get("user_id") or ""
    if not str(open_id).startswith("ou_"):
        raise LookupError("飞书接口未返回有效 Open ID，请确认 user_id_type=open_id")
    return {
        "open_id": open_id,
        "user_id": item.get("user_id", ""),
        "status": item.get("status", {}),
    }


def enrich_with_contact_profile(host: str, app_id: str, app_secret: str, user_info: dict) -> dict:
    """Use the Contact API to add job title and department names when permitted."""
    open_id = user_info.get("open_id", "")
    if not open_id:
        return user_info
    token = _tenant_access_token(host, app_id, app_secret)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{host}/open-apis/contact/v3/users/{quote(open_id, safe='')}",
        params={"user_id_type": "open_id", "department_id_type": "open_department_id"},
        headers=headers,
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or "读取飞书通讯录用户失败")
    contact_user = payload.get("data", {}).get("user", {})
    department_names = []
    for department_id in contact_user.get("department_ids", [])[:8]:
        department_response = requests.get(
            f"{host}/open-apis/contact/v3/departments/{quote(department_id, safe='')}",
            params={"department_id_type": "open_department_id"},
            headers=headers,
            timeout=8,
        )
        department_payload = department_response.json() if department_response.ok else {}
        department = department_payload.get("data", {}).get("department", {})
        if department.get("name"):
            department_names.append(department["name"])
    avatar = contact_user.get("avatar", {}) or {}
    return {
        **user_info,
        "name": contact_user.get("name") or user_info.get("name"),
        "mobile": contact_user.get("mobile") or user_info.get("mobile", ""),
        "job_title": contact_user.get("job_title", ""),
        "departments": department_names,
        "avatar_url": avatar.get("avatar_240") or avatar.get("avatar_origin") or user_info.get("avatar_url", ""),
    }
