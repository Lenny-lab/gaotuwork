import json
import unittest
from unittest.mock import Mock, patch

from app import app
from auth.feishu_oauth import build_authorize_url, lookup_open_id_by_mobile
from auth.role import infer_role
from classmind.users import find_by_feishu_id, find_by_id, find_by_role, load_users
from feishuapi.python import feishu_card


class RoleAccessTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, SECRET_KEY="test-secret", DEMO_LOGIN_ENABLED=True)
        self.client = app.test_client()

    def login(self, role):
        return self.client.get(f"/auth/demo?role={role}")

    def test_root_is_always_three_role_portal_and_api_is_401(self):
        response = self.client.get("/")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("请选择你的 ClassMind 工作台", html)
        self.assertIn("体验学生工作台", html)
        self.assertIn("体验教师工作台", html)
        self.assertIn("体验教务工作台", html)
        self.assertEqual(
            {"authenticated": False, "user": None, "demo_login_enabled": True},
            self.client.get("/api/session").get_json(),
        )
        response.close()
        response = self.client.get("/api/plans")
        self.assertEqual(401, response.status_code)

    def test_student_sees_only_student_surface_and_own_data(self):
        response = self.login("student")
        self.assertTrue(response.headers["Location"].endswith("/student/dashboard"))
        page = self.client.get("/student/dashboard")
        self.assertEqual(200, page.status_code)
        page.close()
        schedule = self.client.get("/api/student/me/schedule").get_json()["schedule"]
        self.assertTrue(schedule)
        self.assertTrue(all(item["class_id"] == "C01" for item in schedule))
        self.assertEqual(403, self.client.get("/api/student/U_S002/schedule").status_code)
        self.assertEqual(403, self.client.post("/api/solve", json={}).status_code)
        self.assertEqual(403, self.client.get("/teacher/dashboard").status_code)

    def test_teacher_can_view_own_data_and_simulate_leave(self):
        self.login("teacher")
        schedule = self.client.get("/api/teacher/me/schedule").get_json()["schedule"]
        self.assertTrue(schedule)
        self.assertTrue(all(item["teacher_id"] == "T01" for item in schedule))
        workload = self.client.get("/api/teacher/me/workload").get_json()
        self.assertEqual(len(schedule), workload["lesson_count"])
        response = self.client.post("/api/teacher/leave", json={"slot_id": schedule[0]["slot_id"], "reason": "教研"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("simulated", response.get_json()["request"]["status"])
        self.assertEqual(403, self.client.get("/api/admin/users").status_code)

    def test_admin_keeps_existing_surface_and_user_directory(self):
        response = self.login("academic_affairs")
        self.assertTrue(response.headers["Location"].endswith("/admin/dashboard"))
        page = self.client.get("/admin/dashboard")
        self.assertEqual(200, page.status_code)
        page.close()
        portal = self.client.get("/")
        self.assertIn("三角色", portal.get_data(as_text=True))
        self.assertEqual(200, self.client.get("/api/plans").status_code)
        users = self.client.get("/api/admin/users").get_json()["users"]
        self.assertEqual(len(load_users()), len(users))

        statistics = self.client.get("/api/admin/statistics")
        self.assertEqual(200, statistics.status_code)
        data = statistics.get_json()
        self.assertEqual("global", data["scope"])
        self.assertEqual("academic_affairs_only", data["permission"])
        self.assertGreater(data["resources"]["students"], 0)

    def test_global_statistics_are_denied_to_students_and_teachers(self):
        self.login("student")
        self.assertEqual(403, self.client.get("/api/admin/statistics").status_code)
        self.client.get("/auth/logout")
        self.login("teacher")
        self.assertEqual(403, self.client.get("/api/admin/statistics").status_code)

    def test_admin_can_bind_existing_user_by_mobile_lookup(self):
        self.login("academic_affairs")
        bound_user = find_by_id("U_S001")
        with patch("app.APP_ID", "cli_test"), patch("app.APP_SECRET", "secret"), patch(
            "app.lookup_open_id_by_mobile", return_value={"open_id": "ou_resolved", "user_id": ""}
        ), patch("app.bind_feishu_open_id", return_value=bound_user):
            response = self.client.post(
                "/api/admin/users/bind-by-mobile",
                json={"mobile": "13800000000", "user_id": "U_S001"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual("U_S001", response.get_json()["user"]["id"])

    def test_unconfigured_feishu_identity_does_not_gain_a_role(self):
        response = self.client.get("/?login_identity=ou_not_configured")
        self.assertEqual(200, response.status_code)
        self.assertIn("请选择你的 ClassMind 工作台", response.get_data(as_text=True))
        self.assertFalse(self.client.get("/api/session").get_json()["authenticated"])


class UserAndCardTests(unittest.TestCase):
    def test_user_mapping_helpers(self):
        self.assertIsNone(find_by_feishu_id(""))
        self.assertIsNone(find_by_feishu_id("ou_not_configured"))
        self.assertGreaterEqual(len(find_by_role("student")), 1)

    def test_oauth_url_contains_state_and_redirect(self):
        url = build_authorize_url("cli_demo", "https://example.com/auth/callback", "csrf-state")
        self.assertIn("app_id=cli_demo", url)
        self.assertIn("state=csrf-state", url)
        self.assertIn("redirect_uri=", url)

    def test_mobile_lookup_requests_open_id_and_parses_new_api_response(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "data": {"user_list": [{"user_id": "ou_resolved"}]}}
        with patch("auth.feishu_oauth._tenant_access_token", return_value="tenant-token"), patch(
            "auth.feishu_oauth.requests.post", return_value=response
        ) as post:
            result = lookup_open_id_by_mobile("https://open.feishu.cn", "cli_test", "secret", "13800000000")
        self.assertEqual("ou_resolved", result["open_id"])
        self.assertEqual("open_id", post.call_args.kwargs["params"]["user_id_type"])
        self.assertEqual(["13800000000"], post.call_args.kwargs["json"]["mobiles"])

    def test_department_names_infer_student_and_teacher_roles(self):
        self.assertEqual("student", infer_role({"open_id": "unknown", "departments": ["高中学生部"]}))
        self.assertEqual("teacher", infer_role({"open_id": "unknown", "departments": ["教师发展中心"]}))
        self.assertEqual("academic_affairs", infer_role({"open_id": "unknown", "job_title": "教务排课专员"}))
        self.assertEqual("", infer_role({"open_id": "unknown", "departments": ["未知部门"]}))

    def test_demo_role_switch_is_disabled_in_production_mode(self):
        app.config["DEMO_LOGIN_ENABLED"] = False
        client = app.test_client()
        self.assertEqual(403, client.get("/auth/demo?role=student").status_code)

    def test_role_cards_have_distinct_visual_identity(self):
        lesson = {"day": "周一", "period": "08:00-09:30", "course_name": "数学", "teacher_name": "张老师", "room_name": "思源教室"}
        student = feishu_card.student_schedule_card("陈晨", [lesson])
        teacher = feishu_card.teacher_schedule_card("张老师", [lesson])
        self.assertEqual("blue", student["header"]["template"])
        self.assertEqual("green", teacher["header"]["template"])


if __name__ == "__main__":
    unittest.main()
