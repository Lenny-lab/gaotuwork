#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
ClassMind + Feishu 统一后端入口

合并原来的:
  - classmind/api.py   (排课引擎 REST API)
  - feishuapi/python/server.py (飞书网页应用鉴权)

新增(本文件):
  - 飞书机器人事件回调 /feishu/event
  - 飞书多维表格自动化回调 /bitable/webhook
  - 飞书 JSSDK 鉴权代理 /feishu/jssdk_config

部署到 Render / Railway / 任意 Python WSGI 平台。
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import secrets
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv, find_dotenv
except ImportError:  # 允许仅安装 Flask 的轻量测试环境启动
    def find_dotenv():
        return ""

    def load_dotenv(*_args, **_kwargs):
        return False
from flask import Flask, g, request, jsonify, redirect, send_from_directory, session, url_for

from auth.decorator import login_required, require_role
from auth.feishu_oauth import (
    FeishuAPIError,
    build_authorize_url,
    enrich_with_contact_profile,
    exchange_code_for_token,
    get_user_info,
    lookup_open_id_by_mobile,
)
from auth.role import user_from_feishu
from auth.session import current_user, login_user, logout_user

# classmind 内部模块
from classmind.io import load_problem, problem_from_dict
from classmind.service import portfolio_payload, simulate_teacher_leave, teacher_load
from classmind.solver import solve_schedule
from classmind.student_api import student_exams, student_schedule
from classmind.teacher_api import submit_leave, teacher_schedule, teacher_students, teacher_workload
from classmind.users import bind_feishu_open_id, find_by_feishu_id, find_by_id, find_by_role, load_users

# 飞书鉴权(原 feishuapi/python/auth.py)
from feishuapi.python.auth import Auth

# 飞书事件处理 + 消息卡片
from feishuapi.python import feishu_event, feishu_card, bitable

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

load_dotenv(find_dotenv())

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
FEISHU_WEB = ROOT / "feishuapi" / "python"

# 飞书侧常量
NONCE_STR = "13oEviLbrTo458A3NjrOwS70oTOXVOAm"
APP_ID = os.getenv("APP_ID", "")
APP_SECRET = os.getenv("APP_SECRET", "")
FEISHU_HOST = os.getenv("FEISHU_HOST", "https://open.feishu.cn")

# 事件订阅相关(机器人)
ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")

# 多维表格相关
BITABLE_APP_TOKEN = os.getenv("BITABLE_APP_TOKEN", "")
BITABLE_TABLE_ID = os.getenv("BITABLE_TABLE_ID", "")

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    static_folder=str(WEB),
    static_url_path="/static",
)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "classmind-demo-change-me"
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # 本地 HTTP 默认可登录；Render/生产环境显式设置 SESSION_COOKIE_SECURE=1。
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    # 线上必须关闭，避免用户绕过飞书账号映射自行切换角色。
    # 安全默认值为关闭；只有本地显式设置为 1 才允许手动体验角色。
    DEMO_LOGIN_ENABLED=os.getenv("DEMO_LOGIN_ENABLED", "0") == "1",
)
# 让 feishuapi 自己的 public 资源也走 /public/*
app.static_folder = str(WEB)  # 主静态目录为 web
app.add_url_rule(
    "/public/<path:filename>",
    endpoint="feishu_public",
    view_func=lambda filename: send_from_directory(FEISHU_WEB / "public", filename),
)


@app.before_request
def load_request_user():
    g.user = current_user()


def _role_home(role: str) -> str:
    return {
        "student": "/student/dashboard",
        "teacher": "/teacher/dashboard",
        "academic_affairs": "/admin/dashboard",
    }.get(role, "/login")


def _safe_next(default: str) -> str:
    candidate = request.args.get("next", "")
    parsed = urlparse(candidate)
    return candidate if candidate.startswith("/") and not parsed.netloc else default


def _configured_mobile_bindings() -> dict[str, str]:
    """Read private business-user-to-mobile bindings from a server secret.

    The value is a JSON object, for example ``{"U_S001":"..."}``.  Mobile
    numbers intentionally stay out of the repository, API responses and logs.
    """
    raw = os.getenv("FEISHU_MOBILE_BINDINGS", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("FEISHU_MOBILE_BINDINGS 必须是 JSON 对象") from exc
    if not isinstance(payload, dict):
        raise ValueError("FEISHU_MOBILE_BINDINGS 必须是业务用户 ID 到手机号的 JSON 对象")

    bindings: dict[str, str] = {}
    for raw_user_id, raw_mobile in payload.items():
        user_id = str(raw_user_id).strip()
        mobile = re.sub(r"[\s-]", "", str(raw_mobile))
        if not find_by_id(user_id):
            raise ValueError(f"手机号映射引用了不存在的业务用户: {user_id}")
        if not re.fullmatch(r"\+?\d{8,15}", mobile):
            raise ValueError(f"业务用户 {user_id} 的手机号格式无效")
        bindings[user_id] = mobile
    return bindings


def _resolve_registered_mobile_user(open_id: str):
    """Match the OAuth identity against configured mobiles via Feishu OpenAPI.

    ``contact.user.id:readonly`` supports phone -> Open ID, not Open ID ->
    phone.  For an unmapped OAuth identity we therefore resolve each small,
    private bootstrap record and compare its Open ID with the login identity.
    """
    if not open_id or not APP_ID or not APP_SECRET:
        return None
    for user_id, mobile in _configured_mobile_bindings().items():
        try:
            resolved = lookup_open_id_by_mobile(FEISHU_HOST, APP_ID, APP_SECRET, mobile)
        except LookupError:
            continue
        resolved_open_id = str(resolved.get("open_id", ""))
        if resolved_open_id and secrets.compare_digest(resolved_open_id, open_id):
            user = find_by_id(user_id)
            return replace(user, feishu_open_id=open_id) if user else None
    return None

# ---------------------------------------------------------------------------
# 全局异常处理
# ---------------------------------------------------------------------------

@app.errorhandler(Exception)
def handle_exception(ex):
    import traceback
    traceback.print_exc()
    code = getattr(ex, "code", 500)
    return jsonify({"error": str(ex), "type": type(ex).__name__}), code


# ---------------------------------------------------------------------------
# 路由:根 + 静态页面(classmind 的 web/)
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    # 飞书应用中心通常直接打开根 URL。根页必须始终展示三角色门户，不能
    # 因为浏览器残留了教务 Session 就跳过学生端和教师端入口。
    identity = request.args.get("login_identity", "")
    mapped = find_by_feishu_id(identity) if identity else None
    if mapped:
        login_user(mapped)
        return redirect(_role_home(mapped.role))
    return send_from_directory(WEB, "login.html")


@app.route("/portal", methods=["GET"])
def role_portal():
    return send_from_directory(WEB, "login.html")


@app.route("/login", methods=["GET"])
def login_page():
    return send_from_directory(WEB, "login.html")


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return "", 204


@app.route("/auth/demo", methods=["GET"])
def auth_demo():
    if not app.config["DEMO_LOGIN_ENABLED"]:
        return jsonify({"error": "线上环境已关闭演示角色切换，请使用飞书账号登录"}), 403
    role = request.args.get("role", "")
    users = find_by_role(role)
    if not users:
        return jsonify({"error": "无效演示角色"}), 400
    payload = login_user(users[0])
    return redirect(_safe_next(_role_home(payload["role"])))


@app.route("/auth/logout", methods=["GET", "POST"])
def auth_logout():
    logout_user()
    return redirect(url_for("home"))


@app.route("/auth/feishu", methods=["GET"])
def auth_feishu():
    if not APP_ID or not APP_SECRET:
        return redirect(url_for("login_page", oauth_error="飞书 OAuth 尚未配置，请先使用演示账号"))
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    redirect_uri = url_for("auth_callback", _external=True, _scheme="https")
    return redirect(build_authorize_url(APP_ID, redirect_uri, state))


@app.route("/auth/callback", methods=["GET"])
def auth_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", "")
    if not code or not state or not secrets.compare_digest(state, expected_state):
        return jsonify({"error": "飞书 OAuth 回调参数或 state 无效"}), 400
    redirect_uri = url_for("auth_callback", _external=True, _scheme="https")
    token_data = exchange_code_for_token(FEISHU_HOST, APP_ID, APP_SECRET, code, redirect_uri)
    user_info = get_user_info(FEISHU_HOST, token_data["access_token"])
    try:
        user_info = enrich_with_contact_profile(FEISHU_HOST, APP_ID, APP_SECRET, user_info)
    except Exception as exc:
        # 通讯录权限未开时仍允许 OAuth 登录，并退回本地 Open ID 映射。
        print(f"[auth] 通讯录资料读取失败，使用基础 OAuth 身份: {exc}")
    resolved_user = user_from_feishu(user_info)
    mobile_mapping_state = "not_needed"
    if resolved_user.role not in {"student", "teacher", "academic_affairs"}:
        try:
            bindings_configured = bool(_configured_mobile_bindings())
            mobile_mapping_state = "no_server_bindings" if not bindings_configured else "no_match"
            if bindings_configured:
                mobile_user = _resolve_registered_mobile_user(resolved_user.feishu_open_id)
                if mobile_user:
                    resolved_user = mobile_user
                    mobile_mapping_state = "matched"
        except FeishuAPIError as exc:
            mobile_mapping_state = "lookup_failed"
            # Safe diagnostics: status/code/request-id only. Never log the
            # configured mobile, request body, bearer token or response text.
            request_id = exc.request_id or "none"
            print(
                "[auth] 注册手机号自动识别失败: "
                f"operation={exc.operation} http={exc.http_status} "
                f"code={exc.code} request_id={request_id}"
            )
        except Exception as exc:
            mobile_mapping_state = "lookup_failed"
            # Upstream exception messages can echo request data.  Log only the
            # exception class so a registered mobile never reaches logs.
            print(f"[auth] 注册手机号自动识别失败: {type(exc).__name__}")
    if resolved_user.role not in {"student", "teacher", "academic_affairs"}:
        logout_user()
        reason = {
            "no_server_bindings": "服务端尚未配置注册手机号映射",
            "no_match": "已自动核验登记手机号，但当前飞书账号未匹配",
            "lookup_failed": "注册手机号自动核验暂时失败，请管理员检查飞书接口权限和服务端配置",
        }.get(mobile_mapping_state, "该飞书账号尚未分配角色")
        return redirect(url_for(
            "home",
            oauth_error=(
                f"{reason}。系统不会允许手动选择角色；请使用已登记手机号对应的飞书账号重试。"
            ),
        ))
    payload = login_user(resolved_user)
    return redirect(_role_home(payload["role"]))


@app.route("/student/dashboard", methods=["GET"])
@require_role("student")
def student_dashboard_page():
    return send_from_directory(WEB / "student", "dashboard.html")


@app.route("/student/schedule", methods=["GET"])
@require_role("student")
def student_schedule_page():
    return send_from_directory(WEB / "student", "my-schedule.html")


@app.route("/student/exams", methods=["GET"])
@require_role("student")
def student_exams_page():
    return send_from_directory(WEB / "student", "exams.html")


@app.route("/teacher/dashboard", methods=["GET"])
@require_role("teacher")
def teacher_dashboard_page():
    return send_from_directory(WEB / "teacher", "dashboard.html")


@app.route("/teacher/schedule", methods=["GET"])
@require_role("teacher")
def teacher_schedule_page():
    return send_from_directory(WEB / "teacher", "my-schedule.html")


@app.route("/teacher/leave", methods=["GET"])
@require_role("teacher")
def teacher_leave_page():
    return send_from_directory(WEB / "teacher", "leave.html")


@app.route("/admin/dashboard", methods=["GET"])
@require_role("academic_affairs")
def admin_dashboard_page():
    return send_from_directory(WEB, "index.html")


@app.route("/admin/users", methods=["GET"])
@require_role("academic_affairs")
def admin_users_page():
    return send_from_directory(WEB / "admin", "users.html")


@app.route("/<path:filename>")
def static_file(filename: str):
    """serve web/ 下的静态资源(html/css/js)。"""
    admin_pages = {"index.html", "schedule.html", "reschedule.html", "resources.html", "bitable.html"}
    if filename in admin_pages:
        if not g.user:
            return redirect(url_for("login_page", next=f"/{filename}"))
        if g.user.get("role") != "academic_affairs":
            return jsonify({"error": "权限不足", "role": g.user.get("role")}), 403
    try:
        return send_from_directory(WEB, filename)
    except Exception:
        return jsonify({"error": "not found"}), 404


# ---------------------------------------------------------------------------
# 路由:classmind 排课 API
# ---------------------------------------------------------------------------

def _problem():
    return load_problem(ROOT / "data" / "demo.json")


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "ok",
        "service": "ClassMind",
        "solver": "OR-Tools CP-SAT",
        "feishu": {
            "app_id_configured": bool(APP_ID),
            "host": FEISHU_HOST,
        },
    })


@app.route("/api/plans", methods=["GET"])
@require_role("academic_affairs")
def api_plans():
    return jsonify(portfolio_payload(_problem()))


@app.route("/api/dashboard", methods=["GET"])
@require_role("academic_affairs")
def api_dashboard():
    result = solve_schedule(_problem())
    return jsonify({**result.to_dict(), "teacher_load": teacher_load(result)})


@app.route("/api/demo", methods=["GET"])
@require_role("academic_affairs")
def api_demo():
    return jsonify(json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8")))


@app.route("/api/solve", methods=["POST"])
@require_role("academic_affairs")
def api_solve():
    try:
        raw = request.get_json(force=True, silent=False)
        if not isinstance(raw, dict):
            return jsonify({"error": "请求体必须是 JSON 对象"}), 400
        strategy = raw.pop("strategy", "balanced")
        result = solve_schedule(problem_from_dict(raw), strategy=strategy)
        status = 200 if result.status not in {"INVALID_DATA"} else 400
        return jsonify(result.to_dict()), status
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"无效排课数据: {exc}"}), 400


@app.route("/api/reschedule", methods=["POST"])
@require_role("academic_affairs")
def api_reschedule():
    try:
        raw = request.get_json(force=True, silent=False)
        teacher_id = raw["teacher_id"]
        slot_id = raw["slot_id"]
        return jsonify(simulate_teacher_leave(_problem(), teacher_id, slot_id))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"无效调课数据: {exc}"}), 400


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    return jsonify(g.user)


@app.route("/api/session", methods=["GET"])
def api_session():
    """Portal-safe session probe; unauthenticated visitors receive HTTP 200."""
    return jsonify({
        "authenticated": bool(g.user),
        "user": g.user,
        "demo_login_enabled": bool(app.config["DEMO_LOGIN_ENABLED"]),
    })


@app.route("/api/student/<student_id>/schedule", methods=["GET"])
@require_role("student")
def api_student_schedule(student_id: str):
    if student_id not in {g.user["id"], "me"}:
        return jsonify({"error": "只能查看自己的课表"}), 403
    return jsonify({"student": g.user, "schedule": student_schedule(_problem(), g.user["class_id"])})


@app.route("/api/student/<student_id>/exams", methods=["GET"])
@require_role("student")
def api_student_exams(student_id: str):
    if student_id not in {g.user["id"], "me"}:
        return jsonify({"error": "只能查看自己的考试"}), 403
    return jsonify({"student": g.user, "exams": student_exams(_problem(), g.user["class_id"])})


@app.route("/api/teacher/<teacher_id>/schedule", methods=["GET"])
@require_role("teacher")
def api_teacher_schedule(teacher_id: str):
    if teacher_id not in {g.user["teacher_id"], "me"}:
        return jsonify({"error": "只能查看自己的课表"}), 403
    return jsonify({"teacher": g.user, "schedule": teacher_schedule(_problem(), g.user["teacher_id"])})


@app.route("/api/teacher/<teacher_id>/students", methods=["GET"])
@require_role("teacher")
def api_teacher_students(teacher_id: str):
    if teacher_id not in {g.user["teacher_id"], "me"}:
        return jsonify({"error": "只能查看自己的学生"}), 403
    return jsonify({"teacher": g.user, "students": teacher_students(_problem(), g.user["teacher_id"])})


@app.route("/api/teacher/<teacher_id>/workload", methods=["GET"])
@require_role("teacher")
def api_teacher_workload(teacher_id: str):
    if teacher_id not in {g.user["teacher_id"], "me"}:
        return jsonify({"error": "只能查看自己的工作量"}), 403
    return jsonify(teacher_workload(_problem(), g.user["teacher_id"]))


@app.route("/api/teacher/leave", methods=["POST"])
@require_role("teacher")
def api_teacher_leave():
    raw = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(submit_leave(_problem(), g.user["teacher_id"], raw["slot_id"], raw.get("reason", "")))
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"无效请假申请: {exc}"}), 400


@app.route("/api/admin/users", methods=["GET"])
@require_role("academic_affairs")
def api_admin_users():
    return jsonify({"users": [user.to_dict() for user in load_users()]})


@app.route("/api/admin/statistics", methods=["GET"])
@require_role("academic_affairs")
def api_admin_statistics():
    """Global operational statistics reserved for academic-affairs accounts."""
    problem = _problem()
    users = load_users()
    result = solve_schedule(problem)
    role_counts = {
        role: sum(user.role == role for user in users)
        for role in ("student", "teacher", "academic_affairs")
    }
    return jsonify({
        "scope": "global",
        "permission": "academic_affairs_only",
        "users": {
            "total": len(users),
            "students": role_counts["student"],
            "teachers": role_counts["teacher"],
            "academic_affairs": role_counts["academic_affairs"],
            "bound": sum(bool(user.feishu_open_id) for user in users),
            "pending": sum(not user.feishu_open_id for user in users),
        },
        "resources": {
            "teachers": len(problem.teachers),
            "rooms": len(problem.rooms),
            "classes": len(problem.classes),
            "students": sum(item.size for item in problem.classes),
            "courses": len(problem.courses),
            "requested_lessons": sum(item.sessions for item in problem.courses),
        },
        "schedule": {
            "status": result.status,
            "scheduled_lessons": len(result.schedule),
            "hard_conflicts": len(result.conflicts),
        },
    })


@app.route("/api/admin/users/bind-by-mobile", methods=["POST"])
@require_role("academic_affairs")
def api_admin_bind_user_by_mobile():
    raw = request.get_json(force=True, silent=True) or {}
    mobile = re.sub(r"[\s-]", "", str(raw.get("mobile", "")))
    user_id = str(raw.get("user_id", "")).strip()
    if not re.fullmatch(r"\+?\d{8,15}", mobile):
        return jsonify({"error": "请输入 8--15 位有效手机号；境外号码需包含国家/地区代码"}), 400
    if not user_id:
        return jsonify({"error": "请选择要绑定的 ClassMind 业务用户"}), 400
    if not APP_ID or not APP_SECRET:
        return jsonify({"error": "服务端尚未配置飞书 APP_ID / APP_SECRET"}), 503
    try:
        resolved = lookup_open_id_by_mobile(FEISHU_HOST, APP_ID, APP_SECRET, mobile)
        user = bind_feishu_open_id(user_id, resolved["open_id"])
        return jsonify({
            "message": f"{user.name} 已绑定飞书账号",
            "user": user.to_dict(),
        })
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"飞书用户查询失败: {exc}"}), 502


# ---------------------------------------------------------------------------
# 路由:飞书网页应用鉴权(JSSDK config)
# ---------------------------------------------------------------------------

# 用懒初始化(每次请求都刷 ticket,缓存太麻烦)
_auth_singleton: Auth | None = None


def _get_auth() -> Auth:
    global _auth_singleton
    if _auth_singleton is None:
        _auth_singleton = Auth(FEISHU_HOST, APP_ID, APP_SECRET)
    return _auth_singleton


@app.route("/feishu/jssdk_config", methods=["GET"])
@login_required
def jssdk_config():
    """前端(feishuapi 的 index.html)调这个拿鉴权参数。"""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "缺少 url 参数"}), 400
    if not APP_ID or not APP_SECRET:
        return jsonify({"error": "APP_ID / APP_SECRET 未配置"}), 500
    try:
        ticket = _get_auth().get_ticket()
    except Exception as exc:
        return jsonify({"error": f"获取 jsapi_ticket 失败: {exc}"}), 500
    timestamp = int(time.time()) * 1000
    verify_str = f"jsapi_ticket={ticket}&noncestr={NONCE_STR}&timestamp={timestamp}&url={url}"
    signature = hashlib.sha1(verify_str.encode("utf-8")).hexdigest()
    return jsonify({
        "appid": APP_ID,
        "signature": signature,
        "noncestr": NONCE_STR,
        "timestamp": timestamp,
    })


# ---------------------------------------------------------------------------
# 路由:飞书机器人事件回调
# ---------------------------------------------------------------------------

@app.route("/feishu/event", methods=["POST"])
def feishu_event_callback():
    """飞书机器人事件订阅入口。
    必须做两件事:
      1. url_verification: 直接 echo challenge
      2. encrypt + signature 校验后处理事件
    """
    body = request.get_data(as_text=True)
    return feishu_event.handle(
        body=body,
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        problem_loader=_problem,
        feishu_host=FEISHU_HOST,
        app_id=APP_ID,
        app_secret=APP_SECRET,
    )


# ---------------------------------------------------------------------------
# 路由:多维表格自动化
# ---------------------------------------------------------------------------

@app.route("/bitable/webhook", methods=["POST"])
def bitable_webhook():
    """多维表格自动化按钮触发入口。"""
    return bitable.handle(
        request_json=request.get_json(force=True, silent=True) or {},
        problem_loader=_problem,
        feishu_host=FEISHU_HOST,
        app_id=APP_ID,
        app_secret=APP_SECRET,
        app_token=BITABLE_APP_TOKEN,
        table_id=BITABLE_TABLE_ID,
    )


# ---------------------------------------------------------------------------
# 路由:健康检查(Render 探针用)
# ---------------------------------------------------------------------------

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # 飞书事件回调要求 HTTPS,本地用 HTTP 即可
    app.run(host="0.0.0.0", port=port, debug=False)
