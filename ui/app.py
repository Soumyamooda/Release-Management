import os
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

# Load backend .env so JIRA_URL and other shared vars are available
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def require_login():
    public_routes = {"login", "logout", "static"}
    if request.endpoint not in public_routes and not session.get("user"):
        return redirect(url_for("login"))


def api_get(path, **kwargs):
    response = requests.get(f"{BACKEND_URL}{path}", **kwargs)
    response.raise_for_status()
    return response.json()


def api_post(path, json=None, **kwargs):
    response = requests.post(f"{BACKEND_URL}{path}", json=json, **kwargs)
    response.raise_for_status()
    return response.json()


def api_put(path, json=None, **kwargs):
    response = requests.put(f"{BACKEND_URL}{path}", json=json, **kwargs)
    response.raise_for_status()
    return response.json()


def api_delete(path, **kwargs):
    response = requests.delete(f"{BACKEND_URL}{path}", **kwargs)
    response.raise_for_status()


# ── Auth routes ─────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        try:
            resp = requests.post(f"{BACKEND_URL}/auth/login", json={"email": email, "password": password})
            if resp.status_code == 200:
                session["user"] = resp.json()
                return redirect(url_for("index"))
            else:
                flash("Invalid email or password.", "danger")
        except requests.RequestException as e:
            flash(f"Could not connect to backend: {e}", "danger")
    return render_template("login.html", release_id=None, active_tab=None, is_login=True)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# ── Release routes ──────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    status_filter = request.args.get("status", "")
    try:
        releases = api_get("/releases/")
    except requests.RequestException as e:
        flash(f"Could not connect to backend: {e}", "danger")
        releases = []

    def _norm(s):
        return (s or "").upper().replace(" ", "_")

    stats = {
        "total": len(releases),
        "in_progress": sum(1 for r in releases if _norm(r["status"]) == "IN_PROGRESS"),
        "in_review": sum(1 for r in releases if _norm(r["status"]) == "IN_REVIEW"),
        "ready": sum(1 for r in releases if _norm(r["status"]) == "READY"),
        "deployed": sum(1 for r in releases if _norm(r["status"]) == "DEPLOYED"),
    }

    if status_filter:
        releases = [r for r in releases if _norm(r["status"]) == _norm(status_filter)]

    items = []
    for r in releases:
        try:
            overview = _hub_get(f"/releases/{r['release_id']}/overview")
            items.append({"release": overview["release"], "decision": overview["decision"]})
        except requests.RequestException:
            items.append({
                "release": r,
                "decision": {"open_defects": 0, "open_security_risks": 0},
            })

    return render_template("index.html", releases=items, stats=stats, status_filter=status_filter,
                           release_id=None, active_tab=None)


@app.route("/releases/new", methods=["GET", "POST"])
def create_release():
    try:
        projects = api_get("/projects/")
    except requests.RequestException:
        projects = []

    if request.method == "POST":
        project_id_raw = request.form.get("project_id")
        user_id = session.get("user", {}).get("user_id") if session.get("user") else None
        _branch = request.form.get("release_branch") or None
        payload = {
            "release_name": request.form["release_name"],
            "project_id": int(project_id_raw) if project_id_raw else None,
            "release_manager_id": user_id,
            "status": request.form.get("status", "IN_PROGRESS"),
            "readiness_pct": int(request.form.get("readiness_pct", 0)),
            "version": request.form.get("version") or None,
            "release_date": request.form.get("release_date") or None,
            "release_summary": request.form.get("release_summary") or None,
            "release_branch": ("https://github.com/Soumya-mooda/Release-Management/commits/" + _branch) if _branch else None,
        }
        try:
            api_post("/releases/", json=payload)
            flash("Release created successfully.", "success")
            return redirect(url_for("index"))
        except requests.RequestException as e:
            flash(f"Error creating release: {e}", "danger")

    return render_template("release_form.html", release=None, projects=projects, release_id=None, active_tab=None)


@app.route("/releases/<int:release_id>/edit", methods=["GET", "POST"])
def edit_release(release_id):
    try:
        release = api_get(f"/releases/{release_id}")
        projects = api_get("/projects/")
    except requests.RequestException as e:
        flash(f"Release not found: {e}", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        project_id_raw = request.form.get("project_id")
        _branch = request.form.get("release_branch") or None
        payload = {
            "release_name": request.form["release_name"],
            "project_id": int(project_id_raw) if project_id_raw else None,
            "status": request.form.get("status", "IN_PROGRESS"),
            "readiness_pct": int(request.form.get("readiness_pct", 0)),
            "version": request.form.get("version") or None,
            "release_date": request.form.get("release_date") or None,
            "release_summary": request.form.get("release_summary") or None,
            "release_branch": ("https://github.com/Soumya-mooda/Release-Management/commits/" + _branch) if _branch else None,
        }
        try:
            api_put(f"/releases/{release_id}", json=payload)
            flash("Release updated successfully.", "success")
            return redirect(url_for("index"))
        except requests.RequestException as e:
            flash(f"Error updating release: {e}", "danger")

    return render_template("release_form.html", release=release, projects=projects, release_id=None, active_tab=None)


@app.route("/releases/<int:release_id>/delete", methods=["POST"])
def delete_release(release_id):
    try:
        api_delete(f"/releases/{release_id}")
        flash("Release deleted.", "success")
    except requests.RequestException as e:
        flash(f"Error deleting release: {e}", "danger")
    return redirect(url_for("index"))


# ── Project routes ──────────────────────────────────────────────────────────

@app.route("/projects")
def projects():
    try:
        project_list = api_get("/projects/")
    except requests.RequestException as e:
        flash(f"Could not connect to backend: {e}", "danger")
        project_list = []
    return render_template("projects.html", projects=project_list)


@app.route("/projects/new", methods=["GET", "POST"])
def create_project():
    if request.method == "POST":
        payload = {
            "project_name": request.form["project_name"],
            "description": request.form.get("description") or None,
            "status": request.form.get("status", "ACTIVE"),
        }
        try:
            api_post("/projects/", json=payload)
            flash("Project created successfully.", "success")
            return redirect(url_for("projects"))
        except requests.RequestException as e:
            flash(f"Error creating project: {e}", "danger")
    return render_template("project_form.html", project=None)


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def edit_project(project_id):
    try:
        project = api_get(f"/projects/{project_id}")
    except requests.RequestException as e:
        flash(f"Project not found: {e}", "danger")
        return redirect(url_for("projects"))

    if request.method == "POST":
        payload = {
            "project_name": request.form["project_name"],
            "description": request.form.get("description") or None,
            "status": request.form.get("status", "ACTIVE"),
        }
        try:
            api_put(f"/projects/{project_id}", json=payload)
            flash("Project updated successfully.", "success")
            return redirect(url_for("projects"))
        except requests.RequestException as e:
            flash(f"Error updating project: {e}", "danger")

    return render_template("project_form.html", project=project)


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    try:
        api_delete(f"/projects/{project_id}")
        flash("Project deleted.", "success")
    except requests.RequestException as e:
        flash(f"Error deleting project: {e}", "danger")
    return redirect(url_for("projects"))


# ═══════════════════════════════════════════════════════════════════════════
# ReleaseHub routes
# ═══════════════════════════════════════════════════════════════════════════

def _hub_get(path, **kwargs):
    """Shorthand for hub API GET calls."""
    return api_get(f"/hub{path}", **kwargs)


def _hub_post(path, **kwargs):
    return api_post(f"/hub{path}", **kwargs)


def _hub_put(path, **kwargs):
    return api_put(f"/hub{path}", **kwargs)


def _hub_delete(path, **kwargs):
    return api_delete(f"/hub{path}", **kwargs)


def _hub_patch(path, json=None, **kwargs):
    response = requests.patch(f"{BACKEND_URL}/hub{path}", json=json, **kwargs)
    response.raise_for_status()
    return response.json()


# ── Hub list ────────────────────────────────────────────────────────────────

@app.route("/hub")
def hub_list():
    try:
        releases = api_get("/releases/")
    except requests.RequestException as e:
        flash(f"Could not connect to backend: {e}", "danger")
        releases = []

    items = []
    for r in releases:
        try:
            overview = _hub_get(f"/releases/{r['release_id']}/overview")
            items.append({"release": overview["release"], "decision": overview["decision"]})
        except requests.RequestException:
            items.append({
                "release": r,
                "decision": {"open_defects": 0, "open_security_risks": 0,
                             "docs_status": "Not Generated", "go_no_go": "In Review"},
            })

    return render_template("hub_list.html", releases=items, release_id=None, active_tab=None)


# ── Overview ────────────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>")
def hub_overview(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
    except requests.RequestException as e:
        flash(f"Could not load release hub: {e}", "danger")
        return redirect(url_for("hub_list"))
    return render_template(
        "hub_overview.html",
        overview=overview,
        release_id=release_id,
        active_tab="overview",
    )


# ── Go/No-Go update ─────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/go-no-go", methods=["POST"])
def hub_update_go_no_go(release_id):
    value = request.form.get("go_no_go", "")
    try:
        requests.patch(
            f"{BACKEND_URL}/hub/releases/{release_id}/go-no-go",
            json={"go_no_go": value},
        ).raise_for_status()
    except requests.RequestException as e:
        flash(f"Could not update Go/No-Go: {e}", "danger")
    return redirect(request.referrer or url_for("hub_overview", release_id=release_id))


# ── Pull Requests ───────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/pull-requests")
def hub_pull_requests(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
        prs = _hub_get(f"/releases/{release_id}/pull-requests")
    except requests.RequestException as e:
        flash(f"Could not load pull requests: {e}", "danger")
        return redirect(url_for("hub_overview", release_id=release_id))
    return render_template(
        "hub_pull_requests.html",
        release=overview["release"],
        pull_requests=prs,
        release_id=release_id,
        active_tab="prs",
        jira_base_url=os.environ.get("JIRA_URL", "").rstrip("/"),
    )


@app.route("/hub/releases/<int:release_id>/pull-requests/add", methods=["POST"])
def hub_add_pr(release_id):
    payload = {
        "pr_number": request.form["pr_number"],
        "title": request.form["title"],
        "status": request.form.get("status", "OPEN"),
        "github_url": request.form.get("github_url") or None,
        "jira_ref":   request.form.get("jira_ref") or None,
        "author":     request.form.get("author") or None,
        "created_at": request.form.get("created_at") or None,
    }
    try:
        _hub_post(f"/releases/{release_id}/pull-requests", json=payload)
        flash("Pull request added.", "success")
    except requests.RequestException as e:
        flash(f"Error adding PR: {e}", "danger")
    return redirect(url_for("hub_pull_requests", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/pull-requests/<int:pr_id>/update", methods=["POST"])
def hub_update_pr(release_id, pr_id):
    payload = {
        "pr_number": request.form["pr_number"],
        "title": request.form["title"],
        "status": request.form.get("status", "OPEN"),
        "github_url": request.form.get("github_url") or None,
        "jira_ref":   request.form.get("jira_ref") or None,
        "author":     request.form.get("author") or None,
        "created_at": request.form.get("created_at") or None,
    }
    try:
        _hub_put(f"/releases/{release_id}/pull-requests/{pr_id}", json=payload)
        flash("Pull request updated.", "success")
    except requests.RequestException as e:
        flash(f"Error updating PR: {e}", "danger")
    return redirect(url_for("hub_pull_requests", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/pull-requests/<int:pr_id>/delete", methods=["POST"])
def hub_delete_pr(release_id, pr_id):
    try:
        _hub_delete(f"/releases/{release_id}/pull-requests/{pr_id}")
        flash("Pull request removed.", "success")
    except requests.RequestException as e:
        flash(f"Error deleting PR: {e}", "danger")
    return redirect(url_for("hub_pull_requests", release_id=release_id))


# ── JIRA Defects ────────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/defects")
def hub_defects(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
        defects = _hub_get(f"/releases/{release_id}/defects")
    except requests.RequestException as e:
        flash(f"Could not load defects: {e}", "danger")
        return redirect(url_for("hub_overview", release_id=release_id))
    return render_template(
        "hub_defects.html",
        release=overview["release"],
        defects=defects,
        release_id=release_id,
        active_tab="defects",
        jira_base_url=os.environ.get("JIRA_URL", "").rstrip("/"),
    )


@app.route("/hub/releases/<int:release_id>/defects/sync-jira", methods=["POST"])
def hub_sync_jira_defects(release_id):
    """Trigger a live JIRA sync to pull latest status, severity and assignee into the DB."""
    try:
        result = requests.post(
            f"{BACKEND_URL}/jira/releases/{release_id}/sync-from-project"
        )
        result.raise_for_status()
        data = result.json()
        flash(
            f"JIRA sync complete — {data.get('newly_synced', 0)} added, "
            f"{data.get('already_existed', 0)} updated.",
            "success",
        )
    except requests.RequestException as e:
        flash(f"JIRA sync failed: {e}", "danger")
    return redirect(url_for("hub_defects", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/defects/add", methods=["POST"])
def hub_add_defect(release_id):
    payload = {
        "issue_key":   request.form["issue_key"],
        "title":       request.form["title"],
        "issue_type":  request.form.get("issue_type") or None,
        "priority":    request.form.get("priority", "Medium"),
        "status":      request.form.get("status", "Open"),
        "assigned_to": request.form.get("assigned_to") or None,
    }
    try:
        _hub_post(f"/releases/{release_id}/defects", json=payload)
        flash("Work item added.", "success")
    except requests.RequestException as e:
        flash(f"Error adding work item: {e}", "danger")
    return redirect(url_for("hub_defects", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/defects/<int:defect_id>/update", methods=["POST"])
def hub_update_defect(release_id, defect_id):
    payload = {
        "issue_key":   request.form["issue_key"],
        "title":       request.form["title"],
        "issue_type":  request.form.get("issue_type") or None,
        "priority":    request.form.get("priority", "Medium"),
        "status":      request.form.get("status", "Open"),
        "assigned_to": request.form.get("assigned_to") or None,
    }
    try:
        _hub_put(f"/releases/{release_id}/defects/{defect_id}", json=payload)
        flash("Work item updated.", "success")
    except requests.RequestException as e:
        flash(f"Error updating work item: {e}", "danger")
    return redirect(url_for("hub_defects", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/defects/<int:defect_id>/delete", methods=["POST"])
def hub_delete_defect(release_id, defect_id):
    try:
        _hub_delete(f"/releases/{release_id}/defects/{defect_id}")
        flash("Defect removed.", "success")
    except requests.RequestException as e:
        flash(f"Error deleting defect: {e}", "danger")
    return redirect(url_for("hub_defects", release_id=release_id))


# ── Security Risks ──────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/security")
def hub_security(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
        risks = _hub_get(f"/releases/{release_id}/security-risks")
    except requests.RequestException as e:
        flash(f"Could not load security risks: {e}", "danger")
        return redirect(url_for("hub_overview", release_id=release_id))
    return render_template(
        "hub_security.html",
        release=overview["release"],
        security_risks=risks,
        release_id=release_id,
        active_tab="security",
    )


@app.route("/hub/releases/<int:release_id>/security/add", methods=["POST"])
def hub_add_risk(release_id):
    payload = {
        "tool_name":      request.form.get("tool_name") or None,
        "severity":       request.form.get("severity") or None,
        "title":          request.form["title"],
        "recommendation": request.form.get("recommendation") or None,
        "status":         "Open",
    }
    try:
        _hub_post(f"/releases/{release_id}/security-risks", json=payload)
        flash("Security finding created.", "success")
    except requests.RequestException as e:
        flash(f"Error creating finding: {e}", "danger")
    return redirect(url_for("hub_security", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/security/<int:risk_id>/update", methods=["POST"])
def hub_update_risk(release_id, risk_id):
    payload = {
        "tool_name":      request.form.get("tool_name") or None,
        "severity":       request.form.get("severity") or None,
        "title":          request.form["title"],
        "recommendation": request.form.get("recommendation") or None,
        "status":         request.form.get("status", "Open"),
    }
    try:
        _hub_put(f"/releases/{release_id}/security-risks/{risk_id}", json=payload)
        flash("Security finding updated.", "success")
    except requests.RequestException as e:
        flash(f"Error updating finding: {e}", "danger")
    return redirect(url_for("hub_security", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/security/<int:risk_id>/resolve", methods=["POST"])
def hub_resolve_risk(release_id, risk_id):
    try:
        _hub_put(f"/releases/{release_id}/security-risks/{risk_id}", json={"status": "Resolved"})
        flash("Security finding marked as resolved.", "success")
    except requests.RequestException as e:
        flash(f"Error resolving finding: {e}", "danger")
    return redirect(url_for("hub_security", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/security/<int:risk_id>/delete", methods=["POST"])
def hub_delete_risk(release_id, risk_id):
    try:
        _hub_delete(f"/releases/{release_id}/security-risks/{risk_id}")
        flash("Security risk removed.", "success")
    except requests.RequestException as e:
        flash(f"Error deleting risk: {e}", "danger")
    return redirect(url_for("hub_security", release_id=release_id))


# ── Documentation ───────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/docs")
def hub_docs(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
    except requests.RequestException as e:
        flash(f"Could not load release: {e}", "danger")
        return redirect(url_for("hub_overview", release_id=release_id))

    doc = overview.get("doc")
    return render_template(
        "hub_docs.html",
        release=overview["release"],
        doc=doc,
        release_id=release_id,
        active_tab="docs",
    )


@app.route("/hub/releases/<int:release_id>/docs/generate", methods=["POST"])
def hub_generate_docs(release_id):
    try:
        _hub_post(f"/releases/{release_id}/docs/generate", json={})
        flash("Release notes generated successfully.", "success")
    except requests.RequestException as e:
        flash(f"Error generating docs: {e}", "danger")
    return redirect(url_for("hub_docs", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/docs/generate-from-branch", methods=["POST"])
def hub_generate_docs_from_branch(release_id):
    """Generate technical documentation from the release's linked GitHub branch."""
    try:
        _hub_post(f"/releases/{release_id}/docs/generate-from-branch", json={})
        flash("Technical documentation generated from branch successfully.", "success")
    except requests.RequestException as e:
        flash(f"Error generating branch docs: {e}", "danger")
    return redirect(url_for("hub_docs", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/docs/generate-ajax", methods=["POST"])
def hub_generate_docs_ajax(release_id):
    """AJAX endpoint – returns JSON doc content for the pop-up modal."""
    try:
        # Use branch-based generation if release_branch is set
        overview = _hub_get(f"/releases/{release_id}/overview")
        release_branch = (overview.get("release") or {}).get("release_branch")
        endpoint = f"/releases/{release_id}/docs/generate-from-branch" if release_branch else f"/releases/{release_id}/docs/generate"
        doc = _hub_post(endpoint, json={})
        return jsonify({"ok": True, "doc": doc})
    except requests.RequestException as exc:
        detail = str(exc)
        try:
            if hasattr(exc, "response") and exc.response is not None:
                detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return jsonify({"ok": False, "error": detail}), 500


@app.route("/hub/releases/<int:release_id>/docs/approve-ajax", methods=["POST"])
def hub_approve_docs_ajax(release_id):
    """AJAX endpoint – approves the generated doc and stores APPROVED status in DB."""
    try:
        doc = api_post(f"/hub/releases/{release_id}/docs/approve", json={})
        return jsonify({"ok": True, "doc": doc})
    except requests.RequestException as exc:
        detail = str(exc)
        try:
            if hasattr(exc, "response") and exc.response is not None:
                detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return jsonify({"ok": False, "error": detail}), 500


@app.route("/hub/releases/<int:release_id>/docs/update", methods=["POST"])
def hub_update_docs(release_id):
    payload = {
        "release_notes": request.form.get("release_notes") or None,
        "impact_summary": request.form.get("impact_summary") or None,
    }
    try:
        _hub_put(f"/releases/{release_id}/docs", json=payload)
        flash("Documentation saved.", "success")
    except requests.RequestException as e:
        flash(f"Error saving docs: {e}", "danger")
    return redirect(url_for("hub_docs", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/docs/approve", methods=["POST"])
def hub_approve_docs(release_id):
    try:
        api_post(f"/hub/releases/{release_id}/docs/approve", json={})
        flash("Documentation approved.", "success")
    except requests.RequestException as e:
        flash(f"Error approving docs: {e}", "danger")
    return redirect(url_for("hub_docs", release_id=release_id))


# ── Actions ─────────────────────────────────────────────────────────────────

@app.route("/hub/releases/<int:release_id>/actions")
def hub_actions(release_id):
    try:
        overview = _hub_get(f"/releases/{release_id}/overview")
    except requests.RequestException as e:
        flash(f"Could not load release: {e}", "danger")
        return redirect(url_for("hub_list"))
    return render_template(
        "hub_actions.html",
        release=overview["release"],
        decision=overview["decision"],
        release_id=release_id,
        active_tab="actions",
    )


@app.route("/hub/releases/<int:release_id>/actions/go-no-go", methods=["POST"])
def hub_set_go_no_go(release_id):
    """Save the manual Go/No-Go override selection to the releases table."""
    value = request.form.get("go_no_go", "").strip()
    valid = {"", "GO", "GO (Tentative)", "NO-GO"}
    if value not in valid:
        flash("Invalid Go/No-Go value.", "danger")
        return redirect(url_for("hub_actions", release_id=release_id))
    try:
        _hub_patch(f"/releases/{release_id}/go-no-go", json={"go_no_go": value})
        label = value if value else "(cleared)"
        flash(f"Go/No-Go set to {label}.", "success")
    except requests.RequestException as e:
        flash(f"Error saving Go/No-Go: {e}", "danger")
    return redirect(url_for("hub_actions", release_id=release_id))


@app.route("/hub/releases/<int:release_id>/actions/deploy", methods=["POST"])
def hub_mark_deployed(release_id):
    try:
        api_put(f"/releases/{release_id}", json={"status": "DEPLOYED"})
        flash("Release marked as Deployed.", "success")
    except requests.RequestException as e:
        flash(f"Error updating status: {e}", "danger")
    return redirect(url_for("hub_actions", release_id=release_id))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

