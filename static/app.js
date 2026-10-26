"use strict";

const API_URL = new URL("/api/courses", window.location.href).href;
const STATUSES = ["Not Started", "In Progress", "Completed"];
const courses = [];
const courseList = document.querySelector("#course-list");
const courseCount = document.querySelector("#course-count");
const loading = document.querySelector("#loading");
const loadingText = document.querySelector("#loading-text");
const editDialog = document.querySelector("#edit-dialog");
const editForm = document.querySelector("#edit-form");
const noticeTimers = new WeakMap();

/**
 * Displays a temporary status message and replaces any pending dismissal.
 * @param {HTMLElement} element Element that displays the message.
 * @param {string} message Message to display.
 * @param {"success" | "error"} type Visual message style.
 */
function showNotice(element, message, type) {
  const existingTimer = noticeTimers.get(element);
  if (existingTimer !== undefined) window.clearTimeout(existingTimer);

  element.textContent = message;
  element.className = `notice visible ${type}`;
  noticeTimers.set(element, window.setTimeout(() => clearNotice(element), 3000));
}

/**
 * Clears a status message and cancels its pending dismissal.
 * @param {HTMLElement} element Element whose message should be cleared.
 */
function clearNotice(element) {
  const timer = noticeTimers.get(element);
  if (timer !== undefined) {
    window.clearTimeout(timer);
    noticeTimers.delete(element);
  }

  element.textContent = "";
  element.className = "notice";
}

/**
 * Updates the loading indicator and disables interactive controls while busy.
 * @param {boolean} isLoading Whether an operation is in progress.
 * @param {string} message Loading message to display.
 */
function setLoading(isLoading, message) {
  loadingText.textContent = message;
  loading.classList.toggle("visible", isLoading);
  document.querySelectorAll("button, select").forEach((control) => {
    control.disabled = isLoading;
  });
}

/**
 * Sends a request to the courses API and parses its JSON response.
 * @param {string} [path=""] API path appended to the courses endpoint.
 * @param {RequestInit} [options={}] Fetch options for the request.
 * @returns {Promise<Object | null>} Parsed JSON response, if present.
 * @throws {Error} If the service cannot be reached or returns an error.
 */
async function request(path = "", options = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers }
    });
  } catch {
    throw new Error("Could not connect to the course service. Check that the server is running and try again.");
  }

  const contentType = response.headers.get("content-type") || "";
  const result = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(result?.error || `The request failed (${response.status}). Please try again.`);
  }
  return result;
}

/**
 * Formats a date for display, avoiding timezone shifts for date-only values.
 * @param {string} value Date value returned by the API.
 * @param {boolean} [includeTime=false] Whether the value includes a timestamp.
 * @returns {string} Localized date or an em dash for invalid/missing values.
 */
function formatDate(value, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const options = includeTime
    ? { year: "numeric", month: "short", day: "numeric" }
    : { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" };
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

/**
 * Maps a course status to its CSS class.
 * @param {string} status Course status.
 * @returns {string} CSS class for the status.
 */
function statusClass(status) {
  if (status === "Completed") return "completed";
  if (status === "In Progress") return "in-progress";
  return "not-started";
}

/**
 * Creates an element with optional class and text content.
 * @param {string} tag HTML tag name.
 * @param {string} [className=""] CSS class name.
 * @param {string} [text] Text content.
 * @returns {HTMLElement} The created element.
 */
function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

/** Renders the current course collection into the dashboard. */
function renderCourses() {
  courseList.replaceChildren();
  courseCount.textContent = `${courses.length} ${courses.length === 1 ? "course" : "courses"}`;
  if (courses.length === 0) {
    const empty = makeElement("div", "panel empty-state");
    empty.append(makeElement("strong", "", "Your learning list is ready."));
    empty.append(document.createTextNode("Add a course above to get started."));
    courseList.append(empty);
    return;
  }

  courses.forEach((course) => {
    const card = makeElement("article", "panel course-card");
    const top = makeElement("div", "course-top");
    top.append(makeElement("h3", "course-title", course.name));
    top.append(makeElement("span", "course-id", `#${course.id}`));
    card.append(top);
    card.append(makeElement("p", "description", course.description));

    const meta = makeElement("div", "course-meta");
    const target = makeElement("div");
    target.append(makeElement("span", "meta-label", "Target date"));
    target.append(makeElement("span", "meta-value", formatDate(course.target_date)));
    const created = makeElement("div");
    created.append(makeElement("span", "meta-label", "Added"));
    created.append(makeElement("span", "meta-value", formatDate(course.created_at, true)));
    meta.append(target, created);

    const statusField = makeElement("div", "field");
    statusField.append(makeElement("label", "meta-label", "Status"));
    const statusSelect = makeElement("select", `status-select ${statusClass(course.status)}`);
    statusSelect.setAttribute("aria-label", `Status for ${course.name}`);
    STATUSES.forEach((status) => {
      const option = makeElement("option", "", status);
      option.value = status;
      option.selected = status === course.status;
      statusSelect.append(option);
    });
    statusSelect.addEventListener("change", () => updateStatus(course.id, statusSelect));
    statusField.append(statusSelect);
    meta.append(statusField);
    card.append(meta);

    const actions = makeElement("div", "card-actions");
    const editButton = makeElement("button", "button button-subtle", "Edit");
    editButton.type = "button";
    editButton.addEventListener("click", () => openEdit(course));
    const deleteButton = makeElement("button", "button button-delete", "Remove");
    deleteButton.type = "button";
    deleteButton.addEventListener("click", () => removeCourse(course.id, deleteButton));
    actions.append(editButton, deleteButton);
    card.append(actions);
    courseList.append(card);
  });
}

/**
 * Loads the course collection from the API and renders it.
 * Shows an error notice if the request or response is invalid.
 * @returns {Promise<void>}
 */
async function loadCourses() {
  const notice = document.querySelector("#list-notice");
  clearNotice(notice);
  setLoading(true, "Loading courses…");
  try {
    const result = await request();
    if (!result || !Array.isArray(result.courses)) {
      throw new Error("The course service returned an unexpected response. Please try again.");
    }
    courses.splice(0, courses.length, ...result.courses);
    renderCourses();
  } catch (error) {
    showNotice(notice, error.message, "error");
    courseList.replaceChildren();
  } finally {
    setLoading(false, "");
  }
}

/**
 * Reads and normalizes editable course fields from a form.
 * @param {HTMLFormElement} form Course form.
 * @returns {{name: string, description: string, target_date: string, status: string}} Course fields.
 */
function getFormData(form) {
  const values = Object.fromEntries(new FormData(form).entries());
  return {
    name: values.name.trim(),
    description: values.description.trim(),
    target_date: values.target_date,
    status: values.status
  };
}

document.querySelector("#add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const notice = document.querySelector("#form-notice");
  clearNotice(notice);
  if (!form.reportValidity()) return;
  const courseData = getFormData(form);
  setLoading(true, "Adding your course…");
  try {
    const created = await request("", { method: "POST", body: JSON.stringify(courseData) });
    courses.unshift(created);
    renderCourses();
    form.reset();
    showNotice(notice, "Course added successfully.", "success");
  } catch (error) {
    showNotice(notice, error.message, "error");
  } finally {
    setLoading(false, "");
  }
});

/**
 * Populates and opens the edit dialog for a course.
 * @param {Object} course Course to edit.
 */
function openEdit(course) {
  clearNotice(document.querySelector("#edit-notice"));
  editForm.elements.id.value = course.id;
  editForm.elements.name.value = course.name;
  editForm.elements.description.value = course.description;
  editForm.elements.target_date.value = course.target_date;
  editForm.elements.status.value = course.status;
  editDialog.showModal();
}

editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!editForm.reportValidity()) return;
  const id = editForm.elements.id.value;
  const notice = document.querySelector("#edit-notice");
  clearNotice(notice);
  const courseData = getFormData(editForm);
  setLoading(true, "Saving your changes…");
  try {
    const updated = await request(`/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(courseData)
    });
    const index = courses.findIndex((course) => String(course.id) === id);
    if (index !== -1) courses[index] = updated;
    renderCourses();
    editDialog.close();
    showNotice(document.querySelector("#list-notice"), "Course updated successfully.", "success");
  } catch (error) {
    showNotice(notice, error.message, "error");
  } finally {
    setLoading(false, "");
  }
});

document.querySelector("#cancel-edit").addEventListener("click", () => editDialog.close());

/**
 * Updates a course status and restores the prior selection on failure.
 * @param {number | string} id Course ID.
 * @param {HTMLSelectElement} select Status control that initiated the update.
 * @returns {Promise<void>}
 */
async function updateStatus(id, select) {
  const previous = courses.find((course) => String(course.id) === String(id))?.status;
  if (!previous) return;
  const notice = document.querySelector("#list-notice");
  clearNotice(notice);
  setLoading(true, "Updating course status…");
  try {
    const updated = await request(`/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ status: select.value })
    });
    const index = courses.findIndex((course) => String(course.id) === String(id));
    if (index !== -1) courses[index] = updated;
    renderCourses();
    showNotice(notice, "Course status updated successfully.", "success");
  } catch (error) {
    select.value = previous;
    showNotice(notice, error.message, "error");
  } finally {
    setLoading(false, "");
  }
}

/**
 * Confirms and removes a course from the API and dashboard.
 * @param {number | string} id Course ID.
 * @param {HTMLButtonElement} button Remove button that initiated the action.
 * @returns {Promise<void>}
 */
async function removeCourse(id, button) {
  const course = courses.find((item) => String(item.id) === String(id));
  if (!course || !window.confirm(`Remove "${course.name}" from your courses?`)) return;
  const notice = document.querySelector("#list-notice");
  clearNotice(notice);
  button.disabled = true;
  setLoading(true, "Removing course…");
  try {
    await request(`/${encodeURIComponent(id)}`, { method: "DELETE" });
    const index = courses.findIndex((item) => String(item.id) === String(id));
    if (index !== -1) courses.splice(index, 1);
    renderCourses();
    showNotice(notice, "Course removed successfully.", "success");
  } catch (error) {
    showNotice(notice, error.message, "error");
  } finally {
    setLoading(false, "");
  }
}

loadCourses();
