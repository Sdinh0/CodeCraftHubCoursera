from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file


app = Flask(__name__)

# Keep the data file next to this application so it works from any working directory.
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "courses.json"
COURSE_STATUSES = {"Not Started", "In Progress", "Completed"}
REQUIRED_FIELDS = {"name", "description", "target_date", "status"}
EDITABLE_FIELDS = REQUIRED_FIELDS


class CourseDataError(Exception):
    """Raised when the course data file cannot be read or written safely."""


def ensure_data_file():
    """Create the data folder and an empty JSON array if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")


ensure_data_file()


def load_courses():
    """Read all saved courses from the JSON file."""
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            courses = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise CourseDataError(f"Could not read course data: {error}") from error

    if not isinstance(courses, list):
        raise CourseDataError("Course data must be a JSON array")
    return courses


def save_courses(courses):
    """Write all courses back to the JSON file."""
    try:
        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(courses, file, indent=2)
    except OSError as error:
        raise CourseDataError(f"Could not save course data: {error}") from error


def get_next_id(courses):
    """Choose the next ID, starting at 1 when there are no saved courses."""
    # Using the largest existing ID avoids reusing IDs after a course is deleted.
    return max((course["id"] for course in courses), default=0) + 1


def get_course_payload() -> dict[str, Any] | Response:
    """Return a JSON object, or a 400 response when the request body is invalid."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        response = jsonify({"error": "Request body must be a JSON object"})
        response.status_code = 400
        return response
    return payload


def validate_course_fields(payload: dict[str, Any], partial: bool = False) -> str | None:
    """Check required fields, value types, date format, and allowed status."""
    # Report missing and unexpected fields before reading individual values.
    unknown_fields = set(payload) - EDITABLE_FIELDS
    if unknown_fields:
        return f"Unknown field(s): {', '.join(sorted(unknown_fields))}"

    missing_fields = REQUIRED_FIELDS - payload.keys()
    if not partial and missing_fields:
        return f"Missing required field(s): {', '.join(sorted(missing_fields))}"
    if partial and not payload:
        return "At least one field is required"

    for field, value in payload.items():
        if not isinstance(value, str):
            return f"The {field} field must be a string"
        if field in {"name", "description"} and not value.strip():
            return f"The {field} field cannot be empty"

    if "target_date" in payload:
        target_date = payload["target_date"]
        try:
            parsed_date = date.fromisoformat(target_date)
        except ValueError:
            return "The target_date field must use YYYY-MM-DD format"
        if parsed_date.isoformat() != target_date:
            return "The target_date field must use YYYY-MM-DD format"

    if "status" in payload and payload["status"] not in COURSE_STATUSES:
        return f"Status must be one of: {', '.join(sorted(COURSE_STATUSES))}"
    return None


@app.errorhandler(CourseDataError)
def handle_course_data_error(error):
    """Return a clear API response when reading or writing course data fails."""
    app.logger.error("%s", error)
    return jsonify({"error": str(error)}), 500


@app.route("/", methods=["GET"])
def home():
    """Serve the course dashboard."""
    return send_file(Path(__file__).resolve().parent / "index.html")


@app.route("/api/courses", methods=["GET"])
def get_all_courses():
    """Return every saved course."""
    courses = load_courses()
    return jsonify({"total": len(courses), "courses": courses}), 200


@app.route("/api/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    """Find and return one course by its ID."""
    courses = load_courses()
    course = next((item for item in courses if item["id"] == course_id), None)
    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404
    return jsonify(course), 200


@app.route("/api/courses", methods=["POST"])
def create_course():
    """Validate and save a new course."""
    payload = get_course_payload()
    if isinstance(payload, Response):
        return payload

    error = validate_course_fields(payload)
    if error:
        return jsonify({"error": error}), 400

    courses = load_courses()
    # The API creates IDs and timestamps so clients do not have to provide them.
    course = {
        "id": get_next_id(courses),
        "name": payload["name"].strip(),
        "description": payload["description"].strip(),
        "target_date": payload["target_date"],
        "status": payload["status"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    courses.append(course)
    save_courses(courses)
    return jsonify(course), 201


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    """Replace a course's editable fields while keeping its ID and creation time."""
    payload = get_course_payload()
    if isinstance(payload, Response):
        return payload

    error = validate_course_fields(payload)
    if error:
        return jsonify({"error": error}), 400

    courses = load_courses()
    course = next((item for item in courses if item["id"] == course_id), None)
    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    # Keep the original ID and created_at even when the course details change.
    updated_course = {
        "id": course_id,
        "name": payload["name"].strip(),
        "description": payload["description"].strip(),
        "target_date": payload["target_date"],
        "status": payload["status"],
        "created_at": course["created_at"],
    }
    courses[courses.index(course)] = updated_course
    save_courses(courses)
    return jsonify(updated_course), 200


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    """Delete a course and save the updated list."""
    courses = load_courses()
    course = next((item for item in courses if item["id"] == course_id), None)
    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    courses.remove(course)
    save_courses(courses)
    return jsonify({"message": f"Course with ID {course_id} deleted"}), 200


@app.route("/api/courses/<int:course_id>/status", methods=["PATCH"])
@app.route("/api/courses/<int:course_id>", methods=["PATCH"])
def update_course_status(course_id):
    """Update the status without replacing the whole course."""
    payload = get_course_payload()
    if isinstance(payload, Response):
        return payload
    if set(payload) != {"status"}:
        return jsonify({"error": "Request body must contain only the status field"}), 400

    error = validate_course_fields(payload, partial=True)
    if error:
        return jsonify({"error": error}), 400

    courses = load_courses()
    course = next((item for item in courses if item["id"] == course_id), None)
    if course is None:
        return jsonify({"error": f"Course with ID {course_id} not found"}), 404

    course["status"] = payload["status"]
    save_courses(courses)
    return jsonify(course), 200


if __name__ == "__main__":
    # Debug mode is convenient while developing locally.
    app.run(debug=True)
