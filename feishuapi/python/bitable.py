#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
飞书多维表格自动化触发器
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

import requests


def _get_tenant_token(feishu_host: str, app_id: str, app_secret: str) -> str:
    url = f"{feishu_host}/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def _read_records(feishu_host, token, app_token, table_id, view_id=None):
    """读多维表格记录(简单翻页,最多 500 条)。"""
    url = f"{feishu_host}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    params = {"page_size": 500}
    if view_id:
        params["view_id"] = view_id
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"读表格失败: {data}")
    return data.get("data", {}).get("items", [])


def _write_record(feishu_host, token, app_token, table_id, record_id, fields):
    """更新一条记录。"""
    url = f"{feishu_host}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {"fields": fields}
    resp = requests.put(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"写表格失败: {data}")


def handle(
    request_json: dict,
    problem_loader: Callable,
    feishu_host: str,
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
) -> Any:
    """多维表格自动化入口。

    期望请求体(由飞书自动化"调用 webhook"动作发出):
      {
        "action": "solve_all" | "solve_one",
        "record_id": "<可选,只跑一条>",
        "fields": { "课程": "高一数学", ... }   # 如果调用方直接传了业务数据
      }
    """
    if not app_token or not table_id:
        return {
            "code": -1,
            "msg": "BITABLE_APP_TOKEN / BITABLE_TABLE_ID 未配置(.env)",
        }, 400

    action = request_json.get("action", "solve_all")
    record_id = request_json.get("record_id", "")

    try:
        token = _get_tenant_token(feishu_host, app_id, app_secret)

        if record_id:
            records = [{"record_id": record_id, "fields": request_json.get("fields", {})}]
        else:
            records = _read_records(feishu_host, token, app_token, table_id)

        # 跑排课
        problem = problem_loader()
        from classmind.solver import solve_schedule
        result = solve_schedule(problem, strategy="balanced")

        # 把结果写回"状态"和"课表文本"字段
        schedule_text = "\n".join(
            f"{it.get('day','')} {it.get('period','')} · {it.get('course_name','')} · {it.get('teacher_name','')} @ {it.get('room_name','')}"
            for it in result.schedule[:20]
        )

        updated = 0
        for rec in records[:10]:  # 最多写 10 条,免得爆
            try:
                _write_record(
                    feishu_host,
                    token,
                    app_token,
                    table_id,
                    rec["record_id"],
                    {
                        "状态": "已排课" if result.status == "OPTIMAL" else "部分冲突",
                        "硬冲突数": result.hard_conflict_count,
                        "课表文本": schedule_text,
                        "更新时间": int(time.time() * 1000),
                    },
                )
                updated += 1
            except Exception as exc:
                print(f"[bitable] 写记录 {rec.get('record_id')} 失败: {exc}")

        return {
            "code": 0,
            "msg": "ok",
            "status": result.status,
            "hard_conflicts": result.hard_conflict_count,
            "updated_records": updated,
        }
    except Exception as exc:
        return {"code": -1, "msg": str(exc)}, 500
