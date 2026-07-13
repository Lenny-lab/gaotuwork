#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
飞书机器人事件处理
- url_verification challenge
- 加密/签名校验
- 消息事件分发(目前只处理 im.message.receive_v1)
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Callable

import requests

from . import feishu_card


# ---------------------------------------------------------------------------
# 加密/签名相关(飞书事件订阅 v2)
# ---------------------------------------------------------------------------

def _decrypt_aes_cbc(encrypt: str, key_b64: str) -> str:
    """飞书事件加密用 AES-128-CBC,key = base64decode(encrypt_key 的 sha1)."""
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    key_bytes = hashlib.sha1(key_b64.encode("utf-8")).digest()  # 16 字节
    raw = base64.b64decode(encrypt)
    iv = raw[:16]
    ciphertext = raw[16:]
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    # PKCS#7 unpadding
    pad = padded[-1]
    if isinstance(pad, int):
        pad_len = pad
    else:
        pad_len = pad[0]
    if pad_len < 1 or pad_len > 16:
        return padded.decode("utf-8", errors="ignore")
    return (padded[:-pad_len]).decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def handle(
    body: str,
    encrypt_key: str,
    verification_token: str,
    problem_loader: Callable,
    feishu_host: str,
    app_id: str,
    app_secret: str,
) -> Any:
    """处理飞书机器人 POST /feishu/event 入口。

    1. 尝试 url_verification(GET 测试 / POST 第一次握手)
    2. 尝试解密
    3. 校验 verification_token
    4. 分发事件
    """
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {"error": "invalid json"}, 400

    # 1) 加密事件优先
    if "encrypt" in payload and encrypt_key:
        try:
            decrypted_text = _decrypt_aes_cbc(payload["encrypt"], encrypt_key)
            payload = json.loads(decrypted_text)
        except Exception as exc:
            return {"error": f"decrypt failed: {exc}"}, 400

    # 2) url_verification
    if payload.get("type") == "url_verification" or "challenge" in payload:
        return {"challenge": payload.get("challenge", "")}

    # 3) 校验 verification_token
    header = payload.get("header", {})
    token = header.get("token", "")
    if verification_token and token and token != verification_token:
        return {"error": "invalid verification token"}, 401

    # 4) 分发
    event_type = header.get("event_type", "")
    if event_type == "im.message.receive_v1":
        event = payload.get("event", {})
        return _on_message(
            event=event,
            problem_loader=problem_loader,
            feishu_host=feishu_host,
            app_id=app_id,
            app_secret=app_secret,
        )

    # 其他事件类型先 ACK,后续扩展
    return {"code": 0, "msg": "ok"}


# ---------------------------------------------------------------------------
# 消息事件处理
# ---------------------------------------------------------------------------

def _get_tenant_token(feishu_host: str, app_id: str, app_secret: str) -> str:
    url = f"{feishu_host}/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def _send_card(chat_id: str, card: dict, feishu_host: str, token: str) -> None:
    """向 chat_id 发送一张 interactive 消息卡片。"""
    url = f"{feishu_host}/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    requests.post(url, params=params, headers=headers, json=body, timeout=5).raise_for_status()


def _on_message(event, problem_loader, feishu_host, app_id, app_secret):
    """处理 im.message.receive_v1 事件。

    触发条件:消息中 @了机器人 且 包含"排课"或"课表"等关键词。
    """
    sender = event.get("sender", {})
    sender_id = sender.get("sender_id", {}).get("open_id", "")
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")
    message_id = message.get("message_id", "")
    content_raw = message.get("content", "{}")
    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        content = {"text": content_raw}

    text = content.get("text", "").strip()
    mentioned = bool(message.get("mentions"))

    # 根据飞书 Open ID 查询本地角色映射；未映射用户按教务处理，便于比赛演示。
    from classmind.users import find_by_feishu_id
    user = find_by_feishu_id(sender_id) if sender_id else None
    role = user.role if user else "academic_affairs"

    # 简单关键词触发
    triggers = ["排课", "课表", "排一下", "排个", "请假", "我的"]
    if not any(k in text for k in triggers):
        # 静默 ACK
        return {"code": 0, "msg": "ignored"}

    if role == "teacher" and "请假" in text:
        try:
            token = _get_tenant_token(feishu_host, app_id, app_secret)
            _send_card(chat_id, feishu_card.teacher_leave_card(user.name), feishu_host, token)
        except Exception as exc:
            print(f"[feishu_event] 发送请假卡片失败: {exc}")
        return {"code": 0, "msg": "ok"}

    # 跑排课
    try:
        problem = problem_loader()
        from classmind.solver import solve_schedule
        result = solve_schedule(problem, strategy="balanced")
    except Exception as exc:
        # 失败时回一张错误卡
        try:
            token = _get_tenant_token(feishu_host, app_id, app_secret)
            _send_card(
                chat_id,
                feishu_card.error_card(f"排课失败: {exc}"),
                feishu_host,
                token,
            )
        except Exception:
            pass
        return {"code": 0, "msg": "error sent"}

    # 成功,出卡片
    try:
        token = _get_tenant_token(feishu_host, app_id, app_secret)
        if role == "student":
            schedule = [item.to_dict() for item in result.schedule if item.class_id == user.class_id]
            card = feishu_card.student_schedule_card(user.name, schedule, text)
        elif role == "teacher":
            schedule = [item.to_dict() for item in result.schedule if item.teacher_id == user.teacher_id]
            card = feishu_card.teacher_schedule_card(user.name, schedule, text)
        else:
            card = feishu_card.schedule_card(
                title="ClassMind 教务决策课表",
                result=result,
                query=text,
                template="orange",
            )
        _send_card(chat_id, card, feishu_host, token)
    except Exception as exc:
        print(f"[feishu_event] 发送卡片失败: {exc}")

    return {"code": 0, "msg": "ok"}
