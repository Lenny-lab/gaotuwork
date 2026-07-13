import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from classmind.api import Handler, ROOT


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as response:
            return response.status, response.headers.get_content_type(), response.read()

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_four_navigation_items_open_independent_pages(self):
        pages = {
            "/": ("dashboard", "决策驾驶舱", "decision-summary"),
            "/schedule.html": ("schedule", "智能排课", "calendar"),
            "/reschedule.html": ("reschedule", "调课中心", "simulate"),
            "/resources.html": ("resources", "资源概览", "resource-body"),
        }
        expected_links = ('href="/admin/dashboard"', 'href="/schedule.html"', 'href="/reschedule.html"', 'href="/resources.html"', 'href="/portal"')
        exclusive_ids = {item[2] for item in pages.values()}
        for path, (page_id, title, exclusive_id) in pages.items():
            status, content_type, body = self.get(path)
            html = body.decode("utf-8")
            self.assertEqual(200, status)
            self.assertEqual("text/html", content_type)
            self.assertIn(f'data-page="{page_id}"', html)
            self.assertIn(title, html)
            self.assertIn(f'id="{exclusive_id}"', html)
            for other_id in exclusive_ids - {exclusive_id}:
                self.assertNotIn(f'id="{other_id}"', html)
            for link in expected_links:
                self.assertIn(link, html)
        _, _, reschedule_body = self.get("/reschedule.html")
        self.assertIn('id="simulate" disabled', reschedule_body.decode("utf-8"))

    def test_schedule_page_uses_full_day_calendar_without_strategy_sidebar(self):
        _, _, body = self.get("/schedule.html")
        html = body.decode("utf-8")
        self.assertIn("08:00—17:30", html)
        self.assertIn("午休 12:00—13:30", html)
        self.assertIn('id="calendar"', html)
        self.assertNotIn('id="plans"', html)
        _, _, script_body = self.get("/app.js")
        _, _, css_body = self.get("/features.css")
        self.assertIn('class="calendar-scroll"', script_body.decode("utf-8"))
        self.assertIn(".calendar-scroll{overflow-x:auto", css_body.decode("utf-8"))

    def test_health_and_demo_endpoints(self):
        _, _, health_body = self.get("/api/health")
        _, _, demo_body = self.get("/api/demo")
        health = json.loads(health_body.decode("utf-8"))
        demo = json.loads(demo_body.decode("utf-8"))
        self.assertEqual("ok", health["status"])
        self.assertEqual(4, len(demo["teachers"]))
        self.assertEqual(4, len(demo["courses"]))

    def test_plans_endpoint_returns_three_zero_conflict_plans(self):
        _, _, body = self.get("/api/plans")
        plans = json.loads(body.decode("utf-8"))["plans"]
        self.assertEqual(3, len(plans))
        self.assertTrue(all(not plan["conflicts"] for plan in plans))
        self.assertTrue(all(len(plan["schedule"]) == 8 for plan in plans))

    def test_solve_accepts_full_problem_payload(self):
        problem = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        problem["strategy"] = "teacher"
        status, result = self.post("/api/solve", problem)
        self.assertEqual(200, status)
        self.assertEqual([], result["conflicts"])
        self.assertEqual("teacher", result["metrics"]["strategy"])

    def test_reschedule_endpoint_returns_minimum_change_diff(self):
        _, result = self.post("/api/reschedule", {"teacher_id": "T01", "slot_id": "MON_0800"})
        self.assertEqual([], result["after"]["conflicts"])
        self.assertLess(result["diff"]["change_count"], 8)
        self.assertEqual("teacher_leave", result["request"]["type"])

    def test_invalid_request_returns_400(self):
        request = Request(
            f"http://127.0.0.1:{self.port}/api/reschedule",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(400, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
