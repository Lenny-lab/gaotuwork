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
import time
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from flask import Flask, request, jsonify, render_template, send_from_directory

# classmind 内部模块
from classmind.io import load_problem, problem_from_dict
from classmind.service import portfolio_payload, simulate_teacher_leave, teacher_load
from classmind.solver import solve_schedule

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
# 让 feishuapi 自己的 public 资源也走 /public/*
app.static_folder = str(WEB)  # 主静态目录为 web
app.add_url_rule(
    "/public/<path:filename>",
    endpoint="feishu_public",
    view_func=lambda filename: send_from_directory(FEISHU_WEB / "public", filename),
)

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
    return send_from_directory(WEB, "index.html")


@app.route("/<path:filename>")
def static_file(filename: str):
    """serve web/ 下的静态资源(html/css/js)。"""
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
def api_plans():
    return jsonify(portfolio_payload(_problem()))


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    result = solve_schedule(_problem())
    return jsonify({**result.to_dict(), "teacher_load": teacher_load(result)})


@app.route("/api/demo", methods=["GET"])
def api_demo():
    return jsonify(json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8")))


@app.route("/api/solve", methods=["POST"])
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
def api_reschedule():
    try:
        raw = request.get_json(force=True, silent=False)
        teacher_id = raw["teacher_id"]
        slot_id = raw["slot_id"]
        return jsonify(simulate_teacher_leave(_problem(), teacher_id, slot_id))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"无效调课数据: {exc}"}), 400


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
