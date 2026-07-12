#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
飞书消息卡片 JSON 构造

参考:https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-structure
"""
from __future__ import annotations

from typing import Any


def schedule_card(title: str, result, query: str) -> dict[str, Any]:
    """排课结果卡片。"""
    schedule = result.schedule if hasattr(result, "schedule") else result.get("schedule", [])
    status = result.status if hasattr(result, "status") else result.get("status", "UNKNOWN")
    hard_conflicts = (
        result.hard_conflict_count
        if hasattr(result, "hard_conflict_count")
        else result.get("hard_conflict_count", 0)
    )
    scorecard = (
        result.scorecard
        if hasattr(result, "scorecard")
        else result.get("scorecard", {})
    )

    # 按天分组,取前 5 天 + 每日前 6 条
    by_day: dict[str, list[dict]] = {}
    for item in schedule:
        day = item.get("day") if isinstance(item, dict) else item.day
        by_day.setdefault(day, []).append(item)

    day_order = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**查询**: {query or '(空)'}  \\n**状态**: `{status}`  \\n**硬冲突**: {hard_conflicts}",
            },
        },
        {"tag": "hr"},
    ]

    for day in day_order:
        lessons = by_day.get(day, [])
        if not lessons:
            continue
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**📅 {day}**"},
        })
        for item in lessons[:6]:
            if isinstance(item, dict):
                line = f"• {item.get('period','')} · **{item.get('course_name','')}** · {item.get('teacher_name','')} @ {item.get('room_name','')}"
            else:
                line = f"• {item.period} · **{item.course_name}** · {item.teacher_name} @ {item.room_name}"
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": line},
            })
        if len(lessons) > 6:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"_…还有 {len(lessons) - 6} 节课_"},
            })
        elements.append({"tag": "hr"})

    # 评分卡
    if isinstance(scorecard, dict) and scorecard:
        score_text = "  \n".join(
            f"• **{k}**: {v}" for k, v in scorecard.items() if k != "hard_conflicts"
        )
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**评分卡**\n{score_text}"},
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue" if hard_conflicts == 0 else "red",
        },
        "elements": elements,
    }


def error_card(message: str) -> dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "ClassMind 错误"},
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**错误**: {message}"},
            },
        ],
    }


def pending_card(query: str) -> dict[str, Any]:
    """正在处理中的占位卡片。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "ClassMind 处理中..."},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"正在为查询 **{query}** 排课,请稍候…"},
            },
        ],
    }
