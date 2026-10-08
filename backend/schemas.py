from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


# ── Projects ───────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    project_name: str
    repository_name: Optional[str] = None
    jira_project: Optional[str] = None
    release_manager: Optional[int] = None


class ProjectUpdate(BaseModel):
    project_name: Optional[str] = None
    repository_name: Optional[str] = None
    jira_project: Optional[str] = None
    release_manager: Optional[int] = None


class ProjectResponse(BaseModel):
    project_id: int
    project_name: str
    repository_name: Optional[str] = None
    jira_project: Optional[str] = None
    release_manager: Optional[int] = None
    created_date: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Releases ───────────────────────────────────────────────────────────────

class ReleaseCreate(BaseModel):
    release_name: str
    project_id: Optional[int] = None
    release_manager_id: Optional[int] = None
    version: Optional[str] = None
    environment: Optional[str] = None
    status: str = "In Progress"
    release_date: Optional[datetime] = None
    release_summary: Optional[str] = None
    release_branch: Optional[str] = None


class ReleaseUpdate(BaseModel):
    release_name: Optional[str] = None
    project_id: Optional[int] = None
    release_manager_id: Optional[int] = None
    version: Optional[str] = None
    environment: Optional[str] = None
    status: Optional[str] = None
    release_date: Optional[datetime] = None
    release_summary: Optional[str] = None
    security_score: Optional[float] = None
    ai_risk_score: Optional[float] = None
    release_branch: Optional[str] = None


class ReleaseResponse(BaseModel):
    release_id: int
    release_name: str
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    status: str
    version: Optional[str] = None
    environment: Optional[str] = None
    release_date: Optional[datetime] = None
    release_summary: Optional[str] = None
    release_branch: Optional[str] = None
    security_score: Optional[float] = None
    ai_risk_score: Optional[float] = None
    # Computed / compatibility fields
    readiness_pct: int = 0
    owner: Optional[str] = None        # derived from project.manager.name
    target_date: Optional[datetime] = None  # alias for release_date
    created_at: Optional[datetime] = None   # alias for created_date
    go_no_go_override: Optional[str] = None  # manual override: GO | GO (Tentative) | NO-GO

    class Config:
        from_attributes = True


# ── Pull Requests ──────────────────────────────────────────────────────────

class PullRequestCreate(BaseModel):
    pr_number: Optional[int] = None
    title: str
    author: Optional[str] = None
    repository: Optional[str] = None
    status: str = "Open"
    lines_added: Optional[int] = None
    lines_deleted: Optional[int] = None
    merged_date: Optional[datetime] = None
    jira_ref: Optional[str] = None
    github_url: Optional[str] = None
    created_at: Optional[datetime] = None


class PullRequestUpdate(BaseModel):
    pr_number: Optional[int] = None
    title: Optional[str] = None
    author: Optional[str] = None
    repository: Optional[str] = None
    status: Optional[str] = None
    lines_added: Optional[int] = None
    lines_deleted: Optional[int] = None
    merged_date: Optional[datetime] = None
    jira_ref: Optional[str] = None
    github_url: Optional[str] = None
    created_at: Optional[datetime] = None
    milestone_version: Optional[str] = None


class PullRequestResponse(BaseModel):
    pr_id: int
    release_id: int
    pr_number: Optional[int] = None
    title: Optional[str] = None
    author: Optional[str] = None
    repository: Optional[str] = None
    status: str = "Open"
    lines_added: Optional[int] = None
    lines_deleted: Optional[int] = None
    merged_date: Optional[datetime] = None
    jira_ref: Optional[str] = None
    github_url: Optional[str] = None
    created_at: Optional[datetime] = None
    milestone_version: Optional[str] = None

    class Config:
        from_attributes = True


# ── Work Items (replaces JIRA Defects) ────────────────────────────────────

class WorkItemCreate(BaseModel):
    issue_key: str
    title: str
    issue_type: Optional[str] = None
    priority: str = "Medium"
    status: str = "Open"
    assigned_to: Optional[str] = None


class WorkItemUpdate(BaseModel):
    issue_key: Optional[str] = None
    title: Optional[str] = None
    issue_type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None


class WorkItemResponse(BaseModel):
    work_item_id: int
    release_id: int
    issue_key: str
    title: str
    issue_type: Optional[str] = None
    priority: str = "Medium"
    status: str = "Open"
    assigned_to: Optional[str] = None
    # Compatibility aliases used by hub_defects.html / hub_overview.html
    jira_key: Optional[str] = None      # = issue_key
    severity: Optional[str] = None      # = priority
    defect_id: Optional[int] = None     # = work_item_id
    jira_parent_key: Optional[str] = None
    jira_url: Optional[str] = None

    class Config:
        from_attributes = True


# ── Security Findings (replaces Security Risks) ───────────────────────────

class SecurityFindingCreate(BaseModel):
    tool_name: Optional[str] = None
    severity: Optional[str] = None
    title: str
    recommendation: Optional[str] = None
    status: str = "Open"


class SecurityFindingUpdate(BaseModel):
    tool_name: Optional[str] = None
    severity: Optional[str] = None
    title: Optional[str] = None
    recommendation: Optional[str] = None
    status: Optional[str] = None


class SecurityFindingResponse(BaseModel):
    finding_id: int
    release_id: int
    tool_name: Optional[str] = None
    severity: Optional[str] = None
    title: str
    recommendation: Optional[str] = None
    status: str = "Open"
    # Compatibility aliases used by hub_security.html / hub_overview.html
    risk_id: Optional[int] = None       # = finding_id
    sec_id: Optional[str] = None        # = tool_name
    description: Optional[str] = None  # = title
    pr_reference: Optional[str] = None

    class Config:
        from_attributes = True


# ── AI Analysis (replaces Release Docs) ──────────────────────────────────

class AIAnalysisResponse(BaseModel):
    analysis_id: int
    release_id: int
    pr_summary: Optional[str] = None
    release_notes: Optional[str] = None
    risk_summary: Optional[str] = None
    overall_score: Optional[float] = None
    recommendation: Optional[str] = None
    generated_time: Optional[datetime] = None
    status: str = "GENERATED"
    # Compatibility aliases used by hub_docs.html / hub_overview.html
    doc_id: Optional[int] = None            # = analysis_id
    impact_summary: Optional[str] = None    # = risk_summary
    generated_at: Optional[datetime] = None # = generated_time

    class Config:
        from_attributes = True


class AIAnalysisUpdate(BaseModel):
    release_notes: Optional[str] = None
    risk_summary: Optional[str] = None
    pr_summary: Optional[str] = None
    recommendation: Optional[str] = None


# ── Workflow Actions ───────────────────────────────────────────────────────

class WorkflowActionResponse(BaseModel):
    workflow_id: int
    release_id: int
    action_name: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    created_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Hub decision / readiness ───────────────────────────────────────────────

class ReleaseDecision(BaseModel):
    open_defects: int
    open_security_risks: int
    docs_status: str
    go_no_go: str


class ReadinessCategoryScore(BaseModel):
    label: str
    score: int
    max_score: int
    detail: str


class ReadinessBreakdown(BaseModel):
    total: int
    categories: List[ReadinessCategoryScore]
    risk_level: str     # "LOW" | "MEDIUM" | "HIGH"


# ── Standalone readiness score ─────────────────────────────────────────────

class PullRequestInput(BaseModel):
    pr_number: Optional[str] = None
    title: str
    status: str = "Open"


class DefectInput(BaseModel):
    issue_key: str
    title: str
    priority: str = "Medium"
    status: str = "Open"


class SecurityRiskInput(BaseModel):
    title: str
    severity: Optional[str] = None
    status: str = "Open"


class ReadinessScoreRequest(BaseModel):
    pull_requests: List[PullRequestInput] = []
    defects: List[DefectInput] = []
    security_risks: List[SecurityRiskInput] = []
    target_date: Optional[date] = None


class ReadinessScoreResponse(BaseModel):
    readiness: ReadinessBreakdown
    target_date: Optional[date] = None
    days_to_target: Optional[int] = None


# ── Hub overview ───────────────────────────────────────────────────────────

class ReleaseOverview(BaseModel):
    release: ReleaseResponse
    pull_requests: List[PullRequestResponse]
    defects: List[WorkItemResponse]          # work_items exposed as "defects"
    security_risks: List[SecurityFindingResponse]  # security_findings as "security_risks"
    doc: Optional[AIAnalysisResponse]
    decision: ReleaseDecision
    readiness: ReadinessBreakdown


# Generated by GitHub Copilot
class JiraIssueResponse(BaseModel):
    """API response for Jira issue summaries with local release mapping."""
    key: str
    summary: str
    status: str
    priority: str
    assignee: str
    release_id: Optional[int] = None


# Generated by GitHub Copilot
class GitHubPullRequestResponse(BaseModel):
    """API response for GitHub pull request summaries."""
    number: int
    title: str
    state: str
    author: str
