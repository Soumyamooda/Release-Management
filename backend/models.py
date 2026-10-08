"""
models.py – SQLAlchemy ORM models mapped to the core schema in PostgreSQL.

Tables live under the 'core' schema:
  core.users, core.projects, core.releases, core.pull_requests,
  core.work_items, core.security_findings, core.ai_analysis,
  core.workflow_actions
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name    = Column(String(100))
    email   = Column(String(150))
    role    = Column(String(50))
    password = Column(String(255))
    password = Column(String(255))


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": "core"}

    project_id      = Column(Integer, primary_key=True, autoincrement=True)
    project_name    = Column(String(150), nullable=False, unique=True)
    repository_name = Column(String(150))
    jira_project    = Column(String(50))
    release_manager = Column(Integer, ForeignKey("core.users.user_id"))
    created_date    = Column(DateTime, server_default=func.now())

    manager  = relationship("User", foreign_keys=[release_manager])
    releases = relationship("Release", back_populates="project")


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_release_project_version"),
        {"schema": "core"},
    )

    release_id            = Column(Integer, primary_key=True, autoincrement=True)
    project_id            = Column(Integer, ForeignKey("core.projects.project_id", ondelete="RESTRICT"), nullable=False)
    release_manager_id    = Column(Integer, ForeignKey("core.users.user_id", ondelete="SET NULL"), nullable=True)
    release_name          = Column(String(150), nullable=False)
    version               = Column(String(20), nullable=False, default="UNVERSIONED")
    environment           = Column(String(50))
    status                = Column(String(50), nullable=False, default="In Progress")
    release_date          = Column(DateTime)
    total_prs             = Column(Integer)
    total_work_items      = Column(Integer)
    total_security_issues = Column(Integer)
    security_score        = Column(Numeric(5, 2))
    ai_risk_score         = Column(Numeric(5, 2))
    release_summary       = Column(Text)
    go_no_go_override     = Column(String(50), nullable=True)
    release_branch        = Column(Text, nullable=True)
    created_date          = Column(DateTime, server_default=func.now())

    project           = relationship("Project", back_populates="releases")
    manager           = relationship("User")
    pull_requests     = relationship("PullRequest",     back_populates="release", cascade="all, delete-orphan")
    work_items        = relationship("WorkItem",        back_populates="release", cascade="all, delete-orphan")
    security_findings = relationship("SecurityFinding", back_populates="release", cascade="all, delete-orphan")
    ai_analysis       = relationship("AIAnalysis",      back_populates="release", uselist=False, cascade="all, delete-orphan")
    workflow_actions  = relationship("WorkflowAction",  back_populates="release", cascade="all, delete-orphan")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = {"schema": "core"}

    pr_id         = Column(Integer, primary_key=True, autoincrement=True)
    release_id    = Column(Integer, ForeignKey("core.releases.release_id", ondelete="CASCADE"), nullable=False)
    pr_number     = Column(Integer)
    title         = Column(Text)
    author        = Column(String(100))
    repository    = Column(String(150))
    status        = Column(String(50), default="Open")
    lines_added   = Column(Integer)
    lines_deleted = Column(Integer)
    merged_date   = Column(DateTime)
    jira_ref          = Column(String(100))      # linked JIRA issue key e.g. PROJ-123
    github_url        = Column(Text)             # direct link to PR on GitHub
    created_at        = Column(DateTime)         # date the PR was raised
    milestone_version = Column(String(50))       # GitHub milestone title (version) for this PR

    release = relationship("Release", back_populates="pull_requests")


class WorkItem(Base):
    """Replaces JiraDefect – maps to core.work_items."""
    __tablename__ = "work_items"
    __table_args__ = {"schema": "core"}

    work_item_id   = Column(Integer, primary_key=True, autoincrement=True)
    release_id     = Column(Integer, ForeignKey("core.releases.release_id", ondelete="CASCADE"), nullable=False)
    issue_key      = Column(String(50), nullable=False)
    title          = Column(Text, nullable=False)
    issue_type     = Column(String(50))
    priority       = Column(String(50), default="Medium")
    status         = Column(String(50), default="Open")
    assigned_to    = Column(String(100))
    affects_version = Column(String(100), nullable=True)  # JIRA Affects Version field

    release = relationship("Release", back_populates="work_items")


class SecurityFinding(Base):
    """Replaces SecurityRisk – maps to core.security_findings."""
    __tablename__ = "security_findings"
    __table_args__ = {"schema": "core"}

    finding_id     = Column(Integer, primary_key=True, autoincrement=True)
    release_id     = Column(Integer, ForeignKey("core.releases.release_id", ondelete="CASCADE"), nullable=False)
    tool_name      = Column(String(100))
    severity       = Column(String(50))
    title          = Column(Text, nullable=False)
    recommendation = Column(Text)
    status         = Column(String(50), default="Open")

    release = relationship("Release", back_populates="security_findings")


class AIAnalysis(Base):
    """
    Replaces ReleaseDoc – maps to core.ai_analysis.
    'status' column (NOT_GENERATED/GENERATED/APPROVED) added via migration in main.py.
    """
    __tablename__ = "ai_analysis"
    __table_args__ = {"schema": "core"}

    analysis_id    = Column(Integer, primary_key=True, autoincrement=True)
    release_id     = Column(Integer, ForeignKey("core.releases.release_id", ondelete="CASCADE"), nullable=False, unique=True)
    pr_summary     = Column(Text)
    release_notes  = Column(Text)
    risk_summary   = Column(Text)       # replaces impact_summary
    overall_score  = Column(Numeric(5, 2))
    recommendation = Column(Text)
    generated_time = Column(DateTime, server_default=func.now())
    status         = Column(String(50), default="GENERATED")  # added via migration

    release = relationship("Release", back_populates="ai_analysis")


class WorkflowAction(Base):
    __tablename__ = "workflow_actions"
    __table_args__ = {"schema": "core"}

    workflow_id  = Column(Integer, primary_key=True, autoincrement=True)
    release_id   = Column(Integer, ForeignKey("core.releases.release_id", ondelete="CASCADE"), nullable=False)
    action_name  = Column(String(100))
    status       = Column(String(50))
    remarks      = Column(Text)
    created_time = Column(DateTime, server_default=func.now())

    release = relationship("Release", back_populates="workflow_actions")

