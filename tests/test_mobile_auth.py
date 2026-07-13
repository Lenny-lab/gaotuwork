import json
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import app as app_module
from app import app
from classmind.users import User, _mobile_fingerprint, find_by_id, find_by_mobile


class RegisteredMobileOAuthTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SESSION_COOKIE_SECURE=False,
            SECRET_KEY="mobile-auth-test-secret",
            DEMO_LOGIN_ENABLED=False,
        )
        # Use the two registered business accounts supplied for the live
        # acceptance test.  Construct the values in parts so a test runner or
        # assertion traceback never has to print a complete mobile number.
        self.student_mobile = "".join(("183", "6149", "3617"))
        self.teacher_mobile = "".join(("131", "4079", "2797"))
        self.bindings = json.dumps(
            {
                "U_S001": self.student_mobile,
                "U_T001": self.teacher_mobile,
            }
        )

    def _lookup(self, _host, _app_id, _app_secret, mobile):
        open_ids = {
            self.student_mobile: "ou_student_registered",
            self.teacher_mobile: "ou_teacher_registered",
        }
        return {"open_id": open_ids[mobile], "user_id": ""}

    def _contains_registered_mobile(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return self.student_mobile in text or self.teacher_mobile in text

    def _oauth_login(self, open_id, lookup=None):
        client = app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["oauth_state"] = "expected-state"
        captured_log = io.StringIO()
        with redirect_stdout(captured_log), patch.dict(
            os.environ, {"FEISHU_MOBILE_BINDINGS": self.bindings}
        ), patch.object(app_module, "APP_ID", "cli_test"), patch.object(
            app_module, "APP_SECRET", "secret"
        ), patch.object(
            app_module, "exchange_code_for_token", return_value={"access_token": "user-token"}
        ), patch.object(
            app_module, "get_user_info", return_value={"open_id": open_id, "name": "飞书成员"}
        ), patch.object(
            app_module,
            "enrich_with_contact_profile",
            side_effect=lambda _host, _app_id, _app_secret, identity: identity,
        ), patch.object(app_module, "lookup_open_id_by_mobile", side_effect=lookup or self._lookup):
            response = client.get("/auth/callback?code=oauth-code&state=expected-state")
        return client, response, captured_log.getvalue()

    def test_registered_student_first_login_enters_student_workspace(self):
        client, response, captured_log = self._oauth_login("ou_student_registered")
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/student/dashboard"))
        session_payload = client.get("/api/session").get_json()
        self.assertEqual("U_S001", session_payload["user"]["id"])
        self.assertEqual("student", session_payload["user"]["role"])
        self.assertNotIn("mobile", session_payload["user"])
        self.assertFalse(self._contains_registered_mobile(session_payload), "session API leaked a registered mobile")
        self.assertFalse(self._contains_registered_mobile(captured_log), "authentication log leaked a registered mobile")

    def test_registered_teacher_first_login_enters_teacher_workspace(self):
        client, response, captured_log = self._oauth_login("ou_teacher_registered")
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/teacher/dashboard"))
        session_payload = client.get("/api/session").get_json()
        self.assertEqual("U_T001", session_payload["user"]["id"])
        self.assertEqual("teacher", session_payload["user"]["role"])
        self.assertNotIn("mobile", session_payload["user"])
        self.assertFalse(self._contains_registered_mobile(session_payload), "session API leaked a registered mobile")
        self.assertFalse(self._contains_registered_mobile(captured_log), "authentication log leaked a registered mobile")

    def test_secret_mapping_does_not_modify_repository_user_records(self):
        with patch.dict(os.environ, {"FEISHU_MOBILE_BINDINGS": self.bindings}), patch.object(
            app_module, "APP_ID", "cli_test"
        ), patch.object(app_module, "APP_SECRET", "secret"), patch.object(
            app_module, "lookup_open_id_by_mobile", side_effect=self._lookup
        ):
            resolved = app_module._resolve_registered_mobile_user("ou_student_registered")
        self.assertEqual("student", resolved.role)
        self.assertEqual("", find_by_id("U_S001").feishu_open_id)

    def test_returned_mobile_matches_repository_fingerprint(self):
        mobile = "13800000009"
        private_user = User(
            id="U_PRIVATE",
            feishu_open_id="",
            name="测试用户",
            role="student",
            mobile_fingerprint=_mobile_fingerprint(mobile),
        )
        with patch("classmind.users.load_users", return_value=[private_user]):
            resolved = find_by_mobile("+86 138-0000-0009")
        self.assertEqual("U_PRIVATE", resolved.id)
        self.assertNotIn("mobile", resolved.to_session())

    def test_unknown_open_id_remains_unauthenticated(self):
        client, response, captured_log = self._oauth_login("ou_unknown_member")
        self.assertEqual(302, response.status_code)
        self.assertIn("oauth_error=", response.headers["Location"])
        self.assertFalse(client.get("/api/session").get_json()["authenticated"])
        self.assertFalse(self._contains_registered_mobile(captured_log), "authentication log leaked a registered mobile")

    def test_lookup_failure_never_echoes_registered_mobile_to_log(self):
        def failing_lookup(_host, _app_id, _app_secret, mobile):
            # Simulate a poorly behaved upstream exception that echoes request
            # data.  The application boundary must sanitize it before logging.
            raise RuntimeError("upstream rejected private lookup value=" + mobile)

        client, response, captured_log = self._oauth_login("ou_unknown_member", lookup=failing_lookup)
        self.assertEqual(302, response.status_code)
        self.assertFalse(client.get("/api/session").get_json()["authenticated"])
        self.assertFalse(self._contains_registered_mobile(captured_log), "authentication log leaked a registered mobile")


if __name__ == "__main__":
    unittest.main()
