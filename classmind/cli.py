from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .io import dump_json, load_problem
from .solver import solve_schedule


def main() -> int:
    parser = argparse.ArgumentParser(description="高途排课脑 ClassMind CP-SAT MVP")
    parser.add_argument("--input", default="data/demo.json", help="输入 JSON 数据文件")
    parser.add_argument("--output", default="output/schedule.json", help="输出课表 JSON 文件")
    parser.add_argument("--time-limit", type=float, default=15.0, help="求解时限（秒）")
    args = parser.parse_args()

    result = solve_schedule(load_problem(args.input), args.time_limit)
    dump_json(result.to_dict(), args.output)
    print(f"求解状态: {result.status}")
    print(f"课次数量: {result.metrics.get('lesson_count', 0)}")
    print(f"硬冲突数: {len(result.conflicts)}")
    print(f"结果文件: {Path(args.output).resolve()}")
    if result.conflicts:
        for message in result.conflicts:
            print(f"- {message}")
    return 0 if result.status in {"OPTIMAL", "FEASIBLE"} and not result.conflicts else 1


if __name__ == "__main__":
    sys.exit(main())

