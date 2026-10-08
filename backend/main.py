# Load .env file FIRST – before any module reads os.environ at import time
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import os
import logging

from fastapi import FastAPI
from sqlalchemy import text
from database import Base, SessionLocal, engine
from routers import projects, releases
from routers import release_hub
from routers import jira, github
from routers.jira_integration import router as jira_router
from routers.auth import router as auth_router
from services.github_service import sync_all_mapped_pull_requests

logger = logging.getLogger(__name__)
scheduler = None

# ── Database startup ────────────────────────────────────────────────────────
# Tables in the core.* schema were already created via the DDL script.
# create_all is a no-op for existing tables; it only creates missing ones.
# We wrap everything in try/except so the API still starts even when the DB
# is temporarily unreachable (e.g., during local dev without PostgreSQL).
try:
    Base.metadata.create_all(bind=engine)

    # Add 'status' column to core.ai_analysis if not present in original DDL.
    with engine.connect() as _conn:
        _row = _conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'core'
              AND table_name   = 'ai_analysis'
              AND column_name  = 'status'
        """)).fetchone()
        if not _row:
            _conn.execute(text(
                "ALTER TABLE core.ai_analysis ADD COLUMN status VARCHAR(50) DEFAULT 'GENERATED'"
            ))
        _conn.commit()

    # Add new columns to core.pull_requests if not present.
    with engine.connect() as _conn:
        for _col, _ddl in [
            ("jira_ref",   "ALTER TABLE core.pull_requests ADD COLUMN jira_ref VARCHAR(100)"),
            ("github_url", "ALTER TABLE core.pull_requests ADD COLUMN github_url TEXT"),
            ("created_at", "ALTER TABLE core.pull_requests ADD COLUMN created_at TIMESTAMP"),
        ]:
            _exists = _conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'core'
                  AND table_name   = 'pull_requests'
                  AND column_name  = :col
            """), {"col": _col}).fetchone()
            if not _exists:
                _conn.execute(text(_ddl))
        _conn.commit()

    # Add go_no_go_override to core.releases if not present.
    with engine.connect() as _conn:
        _exists = _conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'core'
              AND table_name   = 'releases'
              AND column_name  = 'go_no_go_override'
        """)).fetchone()
        if not _exists:
            _conn.execute(text(
                "ALTER TABLE core.releases ADD COLUMN go_no_go_override VARCHAR(50)"
            ))
        _conn.commit()

    # Add index to enforce business-level dedupe for PR upserts.
    with engine.connect() as _conn:
        _driver = engine.url.get_backend_name()
        if _driver == "sqlite":
            _conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_pull_requests_repo_number ON pull_requests(repository, pr_number)"
            ))
        else:
            _conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_pull_requests_repo_number ON core.pull_requests(repository, pr_number)"
            ))
        _conn.commit()

    # Add release_manager_id column to core.releases if not present.
    with engine.connect() as _conn:
        _driver = engine.url.get_backend_name()
        _tbl = "releases" if _driver == "sqlite" else "core.releases"
        _schema_filter = "AND table_schema = 'core'" if _driver != "sqlite" else ""
        _exists = _conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'releases'
              {_schema_filter}
              AND column_name = 'release_manager_id'
        """)).fetchone() if _driver != "sqlite" else None
        # For SQLite, use PRAGMA to check columns
        if _driver == "sqlite":
            _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(releases)")).fetchall()]
            if "release_manager_id" not in _cols:
                _conn.execute(text("ALTER TABLE releases ADD COLUMN release_manager_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL"))
        elif not _exists:
            _conn.execute(text("ALTER TABLE core.releases ADD COLUMN release_manager_id INTEGER REFERENCES core.users(user_id) ON DELETE SET NULL"))
        _conn.commit()

    # Add release_branch column to core.releases if not present (v3 migration).
    with engine.connect() as _conn:
        _driver = engine.url.get_backend_name()
        if _driver == "sqlite":
            _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(releases)")).fetchall()]
            if "release_branch" not in _cols:
                _conn.execute(text("ALTER TABLE releases ADD COLUMN release_branch TEXT"))
        else:
            _exists = _conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'core'
                  AND table_name   = 'releases'
                  AND column_name  = 'release_branch'
            """)).fetchone()
            if not _exists:
                _conn.execute(text("ALTER TABLE core.releases ADD COLUMN release_branch TEXT"))
        _conn.commit()

    # Add milestone_version column to core.pull_requests if not present.
    with engine.connect() as _conn:
        _driver = engine.url.get_backend_name()
        if _driver == "sqlite":
            _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(pull_requests)")).fetchall()]
            if "milestone_version" not in _cols:
                _conn.execute(text("ALTER TABLE pull_requests ADD COLUMN milestone_version VARCHAR(50)"))
        else:
            _exists = _conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'core'
                  AND table_name   = 'pull_requests'
                  AND column_name  = 'milestone_version'
            """)).fetchone()
            if not _exists:
                _conn.execute(text("ALTER TABLE core.pull_requests ADD COLUMN milestone_version VARCHAR(50)"))
        _conn.commit()

    # Add affects_version column to core.work_items if not present.
    with engine.connect() as _conn:
        _driver = engine.url.get_backend_name()
        if _driver == "sqlite":
            _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(work_items)")).fetchall()]
            if "affects_version" not in _cols:
                _conn.execute(text("ALTER TABLE work_items ADD COLUMN affects_version VARCHAR(100)"))
        else:
            _exists = _conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'core'
                  AND table_name   = 'work_items'
                  AND column_name  = 'affects_version'
            """)).fetchone()
            if not _exists:
                _conn.execute(text("ALTER TABLE core.work_items ADD COLUMN affects_version VARCHAR(100)"))
        _conn.commit()

    logger.info("Database initialised successfully.")
except Exception as _db_exc:
    logger.warning(
        "Could not connect to database on startup: %s\n"
        "The API will start but DB-dependent endpoints will fail until "
        "the database is reachable. "
        "To use SQLite locally, unset DATABASE_URL or point it to sqlite:///./projects.db",
        _db_exc,
    )

app = FastAPI(
    title="Release Manager API",
    description="REST API for managing Releases, Projects, and the ReleaseHub governance workspace",
    version="1.0.0"
)

app.include_router(projects.router)
app.include_router(releases.router)
app.include_router(release_hub.router)
app.include_router(jira.router)
app.include_router(github.router)
app.include_router(jira_router)
app.include_router(auth_router)


# Generated by GitHub Copilot
def _scheduled_github_sync() -> None:
    """Run periodic GitHub PR synchronization in a dedicated DB session."""
    db = SessionLocal()
    try:
        logger.info("Scheduled GitHub PR synchronization started")
        result = sync_all_mapped_pull_requests(db, state="all")
        logger.info("Scheduled GitHub PR synchronization completed: %s", result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scheduled GitHub PR synchronization failed: %s", exc)
    finally:
        db.close()


# Generated by GitHub Copilot
def _start_scheduler_if_enabled() -> None:
    """Start APScheduler-based periodic sync when enabled by environment variables."""
    global scheduler
    enabled = (os.environ.get("GITHUB_SYNC_SCHEDULER_ENABLED") or "false").lower() == "true"
    if not enabled:
        return

    interval_minutes = int(os.environ.get("GITHUB_SYNC_INTERVAL_MINUTES", "30"))
    if interval_minutes <= 0:
        logger.warning("GITHUB_SYNC_INTERVAL_MINUTES must be > 0; scheduler not started")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception as exc:  # noqa: BLE001
        logger.warning("APScheduler unavailable, scheduler disabled: %s", exc)
        return

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_github_sync,
        trigger="interval",
        minutes=interval_minutes,
        id="github_pr_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("GitHub scheduler started: interval=%s minutes", interval_minutes)


@app.on_event("startup")
def _startup_scheduler() -> None:
    """FastAPI startup hook to initialize optional scheduler."""
    _start_scheduler_if_enabled()


@app.on_event("shutdown")
def _shutdown_scheduler() -> None:
    """FastAPI shutdown hook to stop scheduler cleanly."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None


@app.get("/", tags=["Health"])
def root():
    return {"message": "Projects API is running"}


