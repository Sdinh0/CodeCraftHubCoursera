import json
from pathlib import Path

import pytest

import app as course_app

VALID_COURSE = {
    "name": "Flask Fundamentals",
    "description": "Learn to build a REST API",
    "target_date": "2026-12-31",
    "status": "Not Started",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide an API client backed by temporary course storage."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(course_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(course_app, "DATA_FILE", data_dir / "courses.json")
    course_app.ensure_data_file()
    return course_app.app.test_client()


def create_course(client):
    return client.post("/api/courses", json=VALID_COURSE)


def test_home_serves_learning_dashboard(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"CodeCraftHub: Your Learning Management Platform" in response.data
    assert b"/static/favicon.ico" in response.data
    assert b"/static/style.css" in response.data
    assert b"/static/app.js" in response.data
    assert b"<script>\n" not in response.data


def test_dashboard_favicon_is_served(client):
    response = client.get("/static/favicon.ico")

    assert response.status_code == 200
    assert response.mimetype in {"image/vnd.microsoft.icon", "image/x-icon"}
    assert response.data.startswith(b"\x00\x00\x01\x00")


def test_dashboard_stylesheet_is_served(client):
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"
    assert b".course-grid" in response.data


def test_dashboard_javascript_is_served(client):
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert response.mimetype in {"text/javascript", "application/javascript"}
    assert b"async function loadCourses()" in response.data


def test_missing_data_file_is_created_automatically(client):
    course_app.DATA_FILE.unlink()

    course_app.ensure_data_file()

    assert course_app.DATA_FILE.exists()
    assert json.loads(course_app.DATA_FILE.read_text(encoding="utf-8")) == []


def test_get_all_courses_returns_empty_list(client):
    response = client.get("/api/courses")

    assert response.status_code == 200
    assert response.get_json() == {"total": 0, "courses": []}


def test_post_creates_course_with_generated_id_and_timestamp(client):
    response = create_course(client)

    assert response.status_code == 201
    course = response.get_json()
    assert course["id"] == 1
    assert course["name"] == VALID_COURSE["name"]
    assert course["created_at"]
    assert set(course) == {
        "id",
        "name",
        "description",
        "target_date",
        "status",
        "created_at",
    }
    saved_courses = json.loads(course_app.DATA_FILE.read_text(encoding="utf-8"))
    assert saved_courses == [course]


def test_get_course_returns_existing_course(client):
    created = create_course(client).get_json()

    response = client.get(f"/api/courses/{created['id']}")

    assert response.status_code == 200
    assert response.get_json() == created


def test_put_replaces_course_and_preserves_created_at(client):
    original = create_course(client).get_json()
    updated_fields = {
        **VALID_COURSE,
        "name": "Flask REST API",
        "description": "Build and test a course API",
        "target_date": "2027-01-15",
        "status": "In Progress",
    }

    response = client.put(f"/api/courses/{original['id']}", json=updated_fields)

    assert response.status_code == 200
    updated = response.get_json()
    assert updated["name"] == "Flask REST API"
    assert updated["status"] == "In Progress"
    assert updated["id"] == original["id"]
    assert updated["created_at"] == original["created_at"]


def test_patch_updates_course_status(client):
    created = create_course(client).get_json()

    response = client.patch(
        f"/api/courses/{created['id']}/status",
        json={"status": "Completed"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "Completed"


def test_patch_resource_route_updates_course_status(client):
    created = create_course(client).get_json()

    response = client.patch(
        f"/api/courses/{created['id']}",
        json={"status": "In Progress"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "In Progress"


def test_patch_rejects_fields_other_than_status(client):
    created = create_course(client).get_json()

    response = client.patch(
        f"/api/courses/{created['id']}/status",
        json={"name": "Not allowed here"},
    )

    assert response.status_code == 400
    assert "only the status field" in response.get_json()["error"]


def test_delete_removes_course(client):
    created = create_course(client).get_json()

    response = client.delete(f"/api/courses/{created['id']}")

    assert response.status_code == 200
    assert response.get_json() == {"message": f"Course with ID {created['id']} deleted"}
    assert client.get("/api/courses").get_json()["total"] == 0


def test_post_rejects_missing_required_fields(client):
    response = client.post("/api/courses", json={"name": "Incomplete course"})

    assert response.status_code == 400
    assert "Missing required field(s)" in response.get_json()["error"]


def test_put_rejects_missing_required_fields(client):
    response = client.put("/api/courses/1", json={"name": "Incomplete replacement"})

    assert response.status_code == 400
    assert "Missing required field(s)" in response.get_json()["error"]


def test_post_rejects_empty_required_text(client):
    response = client.post("/api/courses", json={**VALID_COURSE, "description": " "})

    assert response.status_code == 400
    assert "description field cannot be empty" in response.get_json()["error"]


def test_post_rejects_invalid_target_date(client):
    response = client.post("/api/courses", json={**VALID_COURSE, "target_date": "12/31/2026"})

    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.get_json()["error"]


def test_post_rejects_invalid_status(client):
    response = client.post("/api/courses", json={**VALID_COURSE, "status": "Paused"})

    assert response.status_code == 400
    assert "Status must be one of" in response.get_json()["error"]


def test_post_rejects_non_json_body(client):
    response = client.post(
        "/api/courses",
        data="not-json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Request body must be a JSON object"}


def test_get_returns_not_found_for_missing_course(client):
    response = client.get("/api/courses/999999")

    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_put_returns_not_found_for_missing_course(client):
    response = client.put("/api/courses/999999", json=VALID_COURSE)

    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_patch_returns_not_found_for_missing_course(client):
    response = client.patch(
        "/api/courses/999999/status",
        json={"status": "Completed"},
    )

    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_delete_returns_not_found_for_missing_course(client):
    response = client.delete("/api/courses/999999")

    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_read_storage_error_returns_server_error(client, monkeypatch):
    def fail_read():
        raise course_app.CourseDataError("read failed")

    monkeypatch.setattr(course_app, "load_courses", fail_read)

    response = client.get("/api/courses")

    assert response.status_code == 500
    assert response.get_json() == {"error": "read failed"}


def test_write_storage_error_returns_server_error(client, monkeypatch):
    def fail_write(courses):
        raise course_app.CourseDataError("write failed")

    monkeypatch.setattr(course_app, "save_courses", fail_write)

    response = create_course(client)

    assert response.status_code == 500
    assert response.get_json() == {"error": "write failed"}
