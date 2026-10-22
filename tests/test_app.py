import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app as course_app


VALID_COURSE = {
    "name": "Flask Fundamentals",
    "description": "Learn to build a REST API",
    "target_date": "2026-12-31",
    "status": "Not Started",
}


class CourseApiTests(unittest.TestCase):
    """Test the course API without changing the project's real data file."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_data_dir = course_app.DATA_DIR
        self.original_data_file = course_app.DATA_FILE
        self.addCleanup(self.restore_data_paths)

        course_app.DATA_DIR = Path(self.temp_dir.name) / "data"
        course_app.DATA_FILE = course_app.DATA_DIR / "courses.json"
        course_app.ensure_data_file()

        self.client = course_app.app.test_client()
        self.courses_url = "/api/courses"

    def restore_data_paths(self):
        course_app.DATA_DIR = self.original_data_dir
        course_app.DATA_FILE = self.original_data_file

    def create_course(self):
        return self.client.post(self.courses_url, json=VALID_COURSE)

    def test_home_returns_api_overview(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("GET /api/courses", response.get_json()["endpoints"])

    def test_missing_data_file_is_created_automatically(self):
        course_app.DATA_FILE.unlink()

        course_app.ensure_data_file()

        self.assertTrue(course_app.DATA_FILE.exists())
        self.assertEqual(json.loads(course_app.DATA_FILE.read_text(encoding="utf-8")), [])

    def test_get_all_courses_returns_empty_list(self):
        response = self.client.get(self.courses_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"total": 0, "courses": []})

    def test_post_creates_course_with_generated_id_and_timestamp(self):
        response = self.create_course()

        self.assertEqual(response.status_code, 201)
        course = response.get_json()
        self.assertEqual(course["id"], 1)
        self.assertEqual(course["name"], VALID_COURSE["name"])
        self.assertTrue(course["created_at"])
        self.assertEqual(
            set(course),
            {"id", "name", "description", "target_date", "status", "created_at"},
        )
        saved_courses = json.loads(course_app.DATA_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved_courses, [course])

    def test_get_course_returns_existing_course(self):
        created = self.create_course().get_json()

        response = self.client.get(f"{self.courses_url}/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), created)

    def test_put_replaces_course_and_preserves_created_at(self):
        original = self.create_course().get_json()
        updated_fields = {
            **VALID_COURSE,
            "name": "Flask REST API",
            "description": "Build and test a course API",
            "target_date": "2027-01-15",
            "status": "In Progress",
        }

        response = self.client.put(
            f"{self.courses_url}/{original['id']}", json=updated_fields
        )

        self.assertEqual(response.status_code, 200)
        updated = response.get_json()
        self.assertEqual(updated["name"], "Flask REST API")
        self.assertEqual(updated["status"], "In Progress")
        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["created_at"], original["created_at"])

    def test_patch_updates_course_status(self):
        created = self.create_course().get_json()

        response = self.client.patch(
            f"{self.courses_url}/{created['id']}/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "Completed")

    def test_patch_rejects_fields_other_than_status(self):
        created = self.create_course().get_json()

        response = self.client.patch(
            f"{self.courses_url}/{created['id']}/status",
            json={"name": "Not allowed here"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("only the status field", response.get_json()["error"])

    def test_delete_removes_course(self):
        created = self.create_course().get_json()

        response = self.client.delete(f"{self.courses_url}/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"message": f"Course with ID {created['id']} deleted"},
        )
        self.assertEqual(self.client.get(self.courses_url).get_json()["total"], 0)

    def test_post_rejects_missing_required_fields(self):
        response = self.client.post(
            self.courses_url, json={"name": "Incomplete course"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing required field(s)", response.get_json()["error"])

    def test_put_rejects_missing_required_fields(self):
        response = self.client.put(
            f"{self.courses_url}/1", json={"name": "Incomplete replacement"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing required field(s)", response.get_json()["error"])

    def test_post_rejects_empty_required_text(self):
        response = self.client.post(
            self.courses_url, json={**VALID_COURSE, "description": " "}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("description field cannot be empty", response.get_json()["error"])

    def test_post_rejects_invalid_target_date(self):
        response = self.client.post(
            self.courses_url, json={**VALID_COURSE, "target_date": "12/31/2026"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("YYYY-MM-DD", response.get_json()["error"])

    def test_post_rejects_invalid_status(self):
        response = self.client.post(
            self.courses_url, json={**VALID_COURSE, "status": "Paused"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Status must be one of", response.get_json()["error"])

    def test_post_rejects_non_json_body(self):
        response = self.client.post(
            self.courses_url,
            data="not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Request body must be a JSON object"},
        )

    def test_get_returns_not_found_for_missing_course(self):
        response = self.client.get(f"{self.courses_url}/999999")

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"])

    def test_put_returns_not_found_for_missing_course(self):
        response = self.client.put(
            f"{self.courses_url}/999999", json=VALID_COURSE
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"])

    def test_patch_returns_not_found_for_missing_course(self):
        response = self.client.patch(
            f"{self.courses_url}/999999/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"])

    def test_delete_returns_not_found_for_missing_course(self):
        response = self.client.delete(f"{self.courses_url}/999999")

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"])

    def test_read_storage_error_returns_server_error(self):
        with patch.object(
            course_app,
            "load_courses",
            side_effect=course_app.CourseDataError("read failed"),
        ):
            response = self.client.get(self.courses_url)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "read failed"})

    def test_write_storage_error_returns_server_error(self):
        with patch.object(
            course_app,
            "save_courses",
            side_effect=course_app.CourseDataError("write failed"),
        ):
            response = self.create_course()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "write failed"})


if __name__ == "__main__":
    unittest.main()
