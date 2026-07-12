from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .io import load_problem, problem_from_dict
from .service import portfolio_payload, simulate_teacher_leave, teacher_load
from .solver import solve_schedule


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        problem = load_problem(ROOT / "data" / "demo.json")
        if path == "/api/health":
            return self._json({"status": "ok", "service": "ClassMind", "solver": "OR-Tools CP-SAT"})
        if path == "/api/plans":
            return self._json(portfolio_payload(problem))
        if path == "/api/dashboard":
            result = solve_schedule(problem)
            return self._json({**result.to_dict(), "teacher_load": teacher_load(result)})
        if path == "/api/demo":
            return self._json(json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8")))
        target = WEB / ("index.html" if path == "/" else path.lstrip("/"))
        try:
            target = target.resolve()
            if WEB.resolve() not in target.parents and target != WEB.resolve():
                raise FileNotFoundError
            content = target.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            return self._json({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(target.name)[0] or "application/octet-stream") + ("; charset=utf-8" if target.suffix in {".html", ".css", ".js"} else ""))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/solve", "/api/reschedule"}:
            return self._json({"error": "not found"}, 404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2_000_000:
                return self._json({"error": "请求体为空或超过 2MB"}, 400)
            raw = json.loads(self.rfile.read(size).decode("utf-8"))
            if path == "/api/reschedule":
                problem = load_problem(ROOT / "data" / "demo.json")
                return self._json(simulate_teacher_leave(problem, raw["teacher_id"], raw["slot_id"]))
            strategy = raw.pop("strategy", "balanced")
            result = solve_schedule(problem_from_dict(raw), strategy=strategy)
            return self._json(result.to_dict(), 200 if result.status not in {"INVALID_DATA"} else 400)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return self._json({"error": f"无效排课数据: {exc}"}, 400)

    def log_message(self, format, *args):
        print("[ClassMind]", format % args)


def main():
    parser = argparse.ArgumentParser(description="ClassMind 演示服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ClassMind 已启动: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
