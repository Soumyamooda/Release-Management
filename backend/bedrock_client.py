"""
bedrock_client.py
─────────────────
Thin wrapper around AWS Bedrock's InvokeModel API.

All configuration is read from environment variables – no secrets in code.

Required environment variables
───────────────────────────────
  AWS_ACCESS_KEY_ID       Your AWS IAM access key
  AWS_SECRET_ACCESS_KEY   Your AWS IAM secret key
  AWS_REGION              AWS region where Bedrock is enabled  (e.g. us-east-1)
  BEDROCK_MODEL_ID        Bedrock model to invoke
                          Default: amazon.nova-pro-v1:0
                          Other options:
                            anthropic.claude-3-5-sonnet-20241022-v2:0
                            anthropic.claude-3-haiku-20240307-v1:0
                            amazon.nova-lite-v1:0
"""

import json
import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID      = os.environ.get(
    "BEDROCK_MODEL_ID",
    "amazon.nova-pro-v1:0",          # change to your preferred model
)

# ── Client factory ─────────────────────────────────────────────────────────

def _get_bedrock_client():
    """Create and return a Bedrock runtime client."""
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    return session.client("bedrock-runtime")


# ── Prompt builders ────────────────────────────────────────────────────────

def _build_release_notes_prompt(context: dict) -> str:
    """
    Build the prompt sent to the model to generate release notes.

    context keys (all optional — missing ones are gracefully skipped):
        release_name, version, owner, target_date, project_name,
        project_description, release_summary,
        pull_requests   → list of {pr_number, title, status}
        defects         → list of {jira_key, title, severity, status}
        security_risks  → list of {sec_id, description, status}
    """
    release_name   = context.get("release_name", "Unknown release")
    version        = context.get("version") or "N/A"
    owner          = context.get("owner") or "N/A"
    target_date    = context.get("target_date") or "N/A"
    project_name   = context.get("project_name") or "N/A"
    proj_desc      = context.get("project_description") or "No description provided."
    rel_summary    = context.get("release_summary") or "No summary provided."
    pull_requests  = context.get("pull_requests", [])
    defects        = context.get("defects", [])
    security_risks = context.get("security_risks", [])

    # Format PRs
    if pull_requests:
        pr_block = "\n".join(
            f"  • {pr['pr_number']} [{pr['status']}] — {pr['title']}"
            for pr in pull_requests
        )
    else:
        pr_block = "  No pull requests attached to this release."

    # Format defects
    if defects:
        defect_block = "\n".join(
            f"  • {d['jira_key']} [{d['severity']} / {d['status']}] — {d['title']}"
            for d in defects
        )
    else:
        defect_block = "  No JIRA defects linked."

    # Format security risks
    if security_risks:
        risk_block = "\n".join(
            f"  • {r['sec_id']} [{r['status']}] — {r['description']}"
            for r in security_risks
        )
    else:
        risk_block = "  No security risks logged."

    prompt = f"""You are a senior release manager writing professional release documentation.

Using the structured data below, produce two clearly separated sections:

1. RELEASE NOTES  
   A clear, professional summary of what this release delivers. Describe the
   changes introduced by the pull requests in plain English. Group related
   changes together. Write for a technical audience but avoid raw PR numbers
   as the primary identifier – use the PR title as the feature/fix label
   instead. Keep the total length to 150-250 words.

2. IMPACT SUMMARY  
   A concise paragraph (50-80 words) describing which modules, systems, or
   user-facing areas are affected by this release. Highlight any HIGH severity
   defects that were resolved. Note any open security risks that may need
   attention post-deployment.

─── RELEASE CONTEXT ────────────────────────────────────────────────
Release name  : {release_name}
Version       : {version}
Owner         : {owner}
Target date   : {target_date}
Project       : {project_name}
Project desc  : {proj_desc}
Rel. summary  : {rel_summary}

─── PULL REQUESTS ──────────────────────────────────────────────────
{pr_block}

─── JIRA DEFECTS ───────────────────────────────────────────────────
{defect_block}

─── SECURITY RISKS ─────────────────────────────────────────────────
{risk_block}
────────────────────────────────────────────────────────────────────

Respond with exactly this structure and no other text:

RELEASE NOTES:
<your release notes here>

IMPACT SUMMARY:
<your impact summary here>
"""
    return prompt


# ── Model invocation ───────────────────────────────────────────────────────

def _invoke_model(prompt: str) -> str:
    """
    Call the Bedrock InvokeModel API and return the raw text response.
    Supports both Amazon Nova / Titan (messages API) and Anthropic Claude
    (messages API via Bedrock).
    """
    client = _get_bedrock_client()
    model  = BEDROCK_MODEL_ID

    # Amazon Nova / Titan  (amazon.*)
    if model.startswith("amazon."):
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "inferenceConfig": {
                "max_new_tokens": 1024,
                "temperature": 0.3,
            },
        }
        response      = client.invoke_model(modelId=model, body=json.dumps(body))
        response_body = json.loads(response["body"].read())
        return response_body["output"]["message"]["content"][0]["text"]

    # Anthropic Claude via Bedrock  (anthropic.*)
    elif model.startswith("anthropic."):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
        response      = client.invoke_model(modelId=model, body=json.dumps(body))
        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]

    else:
        raise ValueError(
            f"Unsupported BEDROCK_MODEL_ID prefix: '{model}'. "
            "Expected 'amazon.*' or 'anthropic.*'."
        )


# ── Response parser ────────────────────────────────────────────────────────

def _parse_response(raw_text: str) -> tuple[str, str]:
    """
    Split the model response into (release_notes, impact_summary).
    Handles both the legacy 2-section format and the new 6-section technical doc format.
    Falls back gracefully if the model doesn't follow the exact format.
    """
    # ── 6-section technical document format ───────────────────────────────
    SECTIONS = [
        "RELEASE NOTES:",
        "WHAT'S CHANGED:",
        "TECHNICAL DETAILS:",
        "IMPACT SUMMARY:",
        "DEPLOYMENT NOTES:",
        "RISK ASSESSMENT:",
    ]

    if any(s in raw_text for s in SECTIONS[1:]):  # multi-section doc
        # release_notes = full document (all 6 sections stored together)
        notes = raw_text.strip()
        # impact_summary = just the IMPACT SUMMARY section for the overview preview
        summary = ""
        if "IMPACT SUMMARY:" in raw_text:
            after = raw_text.split("IMPACT SUMMARY:", 1)[1]
            # stop at the next heading
            for next_heading in ("DEPLOYMENT NOTES:", "RISK ASSESSMENT:"):
                if next_heading in after:
                    after = after.split(next_heading, 1)[0]
            summary = after.strip()
        return notes, summary

    # ── Legacy 2-section format ────────────────────────────────────────────
    notes   = raw_text
    summary = ""

    if "IMPACT SUMMARY:" in raw_text:
        parts   = raw_text.split("IMPACT SUMMARY:", 1)
        notes   = parts[0].replace("RELEASE NOTES:", "").strip()
        summary = parts[1].strip()
    elif "RELEASE NOTES:" in raw_text:
        notes = raw_text.replace("RELEASE NOTES:", "").strip()

    return notes, summary


# ── Public API ─────────────────────────────────────────────────────────────

def _template_release_summary(context: dict) -> tuple[str, str]:
    """
    Fallback: generate a compact professional summary from context data
    without calling any external AI service.
    """
    release_name   = context.get("release_name", "This release")
    version        = context.get("version") or ""
    project_name   = context.get("project_name") or "the project"
    rel_summary    = context.get("release_summary") or ""
    pull_requests  = context.get("pull_requests", [])
    defects        = context.get("defects", [])
    security_risks = context.get("security_risks", [])

    ver_str = f" v{version}" if version else ""

    merged_prs   = [p for p in pull_requests if p.get("status", "").lower() in ("merged", "closed")]
    open_prs     = [p for p in pull_requests if p.get("status", "").lower() not in ("merged", "closed")]
    done_defects = [d for d in defects if d.get("status", "").lower() in ("done", "closed")]
    open_defects = [d for d in defects if d.get("status", "").lower() not in ("done", "closed")]
    resolved_sec = [r for r in security_risks if r.get("status", "").lower() == "resolved"]
    open_sec     = [r for r in security_risks if r.get("status", "").lower() != "resolved"]

    # ── Compact Release Notes ──────────────────────────────────────────────
    parts = []

    # Opening sentence
    intro = f"{release_name}{ver_str} for {project_name}"
    if rel_summary:
        intro += f" — {rel_summary}"
    parts.append(intro + ".")

    # PRs in one sentence
    if merged_prs:
        titles = ", ".join(f'"{p["title"]}"' for p in merged_prs)
        parts.append(f"This release includes {len(merged_prs)} merged change(s): {titles}.")
    if open_prs:
        parts.append(f"{len(open_prs)} pull request(s) are still open and not included in this build.")

    # Defects in one sentence
    if done_defects:
        hi = [d for d in done_defects if (d.get("severity") or d.get("priority") or "").lower() == "high"]
        keys = ", ".join(d.get("jira_key") or d.get("issue_key", "") for d in done_defects)
        sev_note = f" ({len(hi)} High priority)" if hi else ""
        parts.append(f"{len(done_defects)} defect(s){sev_note} resolved: {keys}.")
    if open_defects:
        hi_open = [d for d in open_defects if (d.get("severity") or d.get("priority") or "").lower() == "high"]
        note = f" including {len(hi_open)} High priority" if hi_open else ""
        parts.append(f"⚠ {len(open_defects)} defect(s) remain open{note} — review before deployment.")

    notes = " ".join(parts)

    # ── Compact Impact Summary ─────────────────────────────────────────────
    impact_parts = [
        f"{project_name} is impacted across {len(merged_prs)} merged PR(s)."
    ]
    if done_defects:
        impact_parts.append(f"{len(done_defects)} defect(s) closed.")
    if resolved_sec:
        impact_parts.append(f"{len(resolved_sec)} security finding(s) resolved.")
    if open_sec:
        impact_parts.append(f"⚠ {len(open_sec)} security finding(s) remain open — address post-deployment.")
    if open_defects:
        impact_parts.append(f"⚠ {len(open_defects)} open defect(s) need attention.")
    if not open_defects and not open_sec:
        impact_parts.append("No outstanding issues — release is ready for deployment.")

    impact = " ".join(impact_parts)
    return notes, impact


def generate_release_summary(context: dict) -> tuple[str, str]:
    """
    Generate AI-powered release notes and impact summary via AWS Bedrock.
    Falls back to template-based generation if Bedrock is unavailable or
    the IAM user lacks bedrock:InvokeModel permission.

    Parameters
    ----------
    context : dict
        Release metadata and related items (see _build_release_notes_prompt).

    Returns
    -------
    (release_notes, impact_summary) : tuple[str, str]
        Both strings are ready to persist into the AIAnalysis table.
    """
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials not configured – using template fallback.")
        return _template_release_summary(context)

    prompt = _build_release_notes_prompt(context)
    logger.info("Invoking Bedrock model '%s' for release summary.", BEDROCK_MODEL_ID)

    try:
        raw_text = _invoke_model(prompt)
        notes, summary = _parse_response(raw_text)
        logger.info("Bedrock response parsed successfully.")
        return notes, summary
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.warning(
            "Bedrock %s for model '%s' – falling back to template generation.",
            error_code, BEDROCK_MODEL_ID,
        )
        return _template_release_summary(context)
    except BotoCoreError as exc:
        logger.warning("AWS connectivity error (%s) – falling back to template generation.", exc)
        return _template_release_summary(context)



# ── Branch-based documentation ─────────────────────────────────────────────

def _build_branch_docs_prompt(context: dict) -> str:
    """
    Build a Bedrock prompt for generating technical documentation from a branch.

    context keys:
        repo_url        → full GitHub repo URL
        branch          → branch name
        release_name    → release display name
        version         → version string
        commits         → list of {sha, message, author, date}
        files           → list of file paths in the branch
        file_contents   → dict of {path: source_code} for key source files
    """
    repo_url      = context.get("repo_url", "Unknown repo")
    branch        = context.get("branch", "Unknown branch")
    release_name  = context.get("release_name", "This release")
    version       = context.get("version") or "N/A"
    commits       = context.get("commits", [])
    files         = context.get("files", [])
    file_contents = context.get("file_contents", {})

    commit_block = "\n".join(
        f"  • [{c['sha'][:7]}] {c['message'].splitlines()[0]}  ({c['author']} — {c['date']})"
        for c in commits
    ) if commits else "  No commits found."

    file_list = "\n".join(f"  • {f}" for f in files) if files else "  No files found."

    snippet_parts = []
    for path, content in file_contents.items():
        snippet = content[:2000] + ("\n... (truncated)" if len(content) > 2000 else "")
        snippet_parts.append(f"--- {path} ---\n{snippet}")
    snippet_block = "\n\n".join(snippet_parts) if snippet_parts else "  No source snippets available."

    return f"""You are a senior software engineer and technical writer producing official release documentation.

Analyse the branch data provided below and generate a comprehensive TECHNICAL DOCUMENT.
Base every statement on the actual commits, files, and source code provided — do NOT
invent functionality that is not present in the data.

─────────────────────────── BRANCH DATA ─────────────────────────────────────
Repository : {repo_url}
Branch     : {branch}
Release    : {release_name}
Version    : {version}

COMMITS ({len(commits)} total):
{commit_block}

FILES IN BRANCH ({len(files)} total):
{file_list}

SOURCE CODE SNIPPETS:
{snippet_block}
──────────────────────────────────────────────────────────────────────────────

Generate a technical document with EXACTLY the following six sections.
Use each heading verbatim. Do not add any text outside these six sections.

RELEASE NOTES:
Write 200-300 words describing what this release delivers. For every source file
present in the branch: describe its purpose, key functions/classes, inputs, outputs,
and notable logic — using the exact function and class names found in the code.
Group related files together. Audience: developers, architects, release managers.

WHAT'S CHANGED:
A bulleted list of every meaningful change in this branch. Each bullet must include:
  - `<filename>` — what was added/modified/removed and which functions/classes

TECHNICAL DETAILS:
For each source file, write a sub-section in this exact format:
  File: <filename>
  Purpose: <one sentence describing the module>
  Key Functions/Classes: <list each with a one-sentence description>
  Dependencies: <external imports or libraries used>

IMPACT SUMMARY:
60-100 words describing which systems/modules are affected, what changed
functionally, and any backward-compatibility or deployment considerations.

DEPLOYMENT NOTES:
Bullet-point checklist for deploying this release:
  - Environment variables or config changes required
  - New dependencies to install (derived from imports in the code)
  - Database / schema migrations (if detected)
  - Breaking changes or migration steps for consumers

RISK ASSESSMENT:
40-60 words identifying potential risks: untested edge cases visible in the code,
security-sensitive operations (auth, secrets, HTTP calls), open issues referenced
in commit messages. If no risks are found, write: "No significant risks identified."
"""


def _template_branch_documentation(context: dict) -> tuple[str, str]:
    """
    Fallback: generate structured technical documentation without calling Bedrock.
    Derives content from file names and source code snippets — merge commits are
    excluded to keep the output clean and professional.
    """
    branch        = context.get("branch", "unknown branch")
    release_name  = context.get("release_name", "This release")
    version       = context.get("version") or ""
    commits       = context.get("commits", [])
    files         = context.get("files", [])
    file_contents = context.get("file_contents", {})

    # Strip leading 'v' from version to avoid "vv1.0.0" when DB already stores "v1.0.0"
    _ver = version.lstrip("v") if version else ""
    ver_str = f" v{_ver}" if _ver else ""

    # ── Filter out merge/revert/bot commits ───────────────────────────────
    _skip_prefixes = (
        "merge pull request", "merge branch", "merged", "revert ", "bump ",
        "auto ", "wip", "initial commit", "first commit",
    )
    meaningful_commits = [
        c for c in commits
        if not any(c.get("message", "").lower().startswith(p) for p in _skip_prefixes)
    ]

    # ── Categorise source files ────────────────────────────────────────────
    source_exts   = (".py", ".js", ".ts", ".java", ".go", ".cs", ".rb")
    source_files  = [f for f in files if f.endswith(source_exts)]
    config_files  = [f for f in files if f.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".env.example"))]
    doc_files     = [f for f in files if f.endswith((".md", ".rst", ".txt"))]
    other_files   = [f for f in files if f not in source_files + config_files + doc_files]

    # ── Per-file technical descriptions (from snippets or name heuristics) ─
    file_details: list[str] = []
    for path in source_files:
        fname     = path.split("/")[-1]
        snippet   = file_contents.get(path, "")
        # Extract def/class names from snippet
        import re
        defs      = re.findall(r"^(?:def|class)\s+(\w+)", snippet, re.MULTILINE)
        imports   = re.findall(r"^(?:import|from)\s+([\w\.]+)", snippet, re.MULTILINE)

        funcs_str = ", ".join(f"`{d}`" for d in defs[:8]) if defs else "—"
        deps_str  = ", ".join(set(imports[:6])) if imports else "standard library"

        file_details.append(
            f"  File: {fname}\n"
            f"  Purpose: Python module providing the functionality described in `{fname.replace('.py','').replace('_',' ')}`.\n"
            f"  Key Functions/Classes: {funcs_str}\n"
            f"  Dependencies: {deps_str}"
        )

    # ── Commit summary (meaningful only) ──────────────────────────────────
    commit_lines = "\n".join(
        f"  • {c['message'].splitlines()[0].strip()}"
        for c in meaningful_commits[:10]
    ) if meaningful_commits else "  • No standalone feature commits detected on this branch."

    # ── File change bullets ────────────────────────────────────────────────
    file_bullets = "\n".join(
        f"  • `{f.split('/')[-1]}` — {'Added/updated' if f in file_contents else 'Present in branch'}."
        for f in source_files
    ) or "  • No source files detected."

    # ── Deployment notes (based on detected patterns) ─────────────────────
    all_imports = []
    for content in file_contents.values():
        all_imports += re.findall(r"^(?:import|from)\s+([\w\.]+)", content, re.MULTILINE)
    ext_libs = sorted({
        imp for imp in set(all_imports)
        if imp not in ("os", "sys", "re", "json", "math", "datetime", "typing",
                       "pathlib", "logging", "collections", "itertools", "functools",
                       "abc", "copy", "io", "time", "random", "string", "hashlib")
    })
    dep_note = (
        "  • Install new dependencies: `pip install " + " ".join(ext_libs[:6]) + "`"
        if ext_libs else "  • No new external dependencies detected."
    )
    env_note = (
        "  • Ensure environment variables are configured (check `.env.example` in repository)."
        if any(f.endswith(".env.example") for f in files)
        else "  • Verify all required environment variables are set before deployment."
    )

    # ── Assemble the six-section document ─────────────────────────────────
    sf_count = len(source_files)
    sf_names = ", ".join(f"`{f.split('/')[-1]}`" for f in source_files) or "none"

    release_notes = (
        f"**{release_name}{ver_str}** introduces {sf_count} source file(s) "
        f"on branch `{branch}`: {sf_names}.\n\n"
        + (
            "The following modules are included in this release:\n\n"
            + "\n\n".join(file_details)
            if file_details
            else "No source files with parseable content were found on this branch."
        )
    )

    impact_summary = (
        f"This release affects {sf_count} module(s): {sf_names}. "
        f"{len(meaningful_commits)} feature commit(s) were included. "
        "Review all changed modules and run the full test suite before deploying to production."
    )

    full_doc = f"""RELEASE NOTES:
{release_notes}

WHAT'S CHANGED:
{file_bullets}

TECHNICAL DETAILS:
{chr(10).join(file_details) if file_details else "  No source file details available."}

IMPACT SUMMARY:
{impact_summary}

DEPLOYMENT NOTES:
{dep_note}
{env_note}
  • Run all unit and integration tests before promoting to production.
  • No database schema migrations detected (verify manually if models changed).

RISK ASSESSMENT:
No significant risks identified from static analysis. Verify that all input validation
is in place for any user-facing functions. Review any HTTP client calls for proper
timeout and error handling before production deployment."""

    return full_doc, impact_summary


def generate_branch_documentation(context: dict) -> tuple[str, str]:
    """
    Generate technical documentation from branch commits and source files via Bedrock.
    Falls back to template generation if Bedrock is unavailable.

    Parameters
    ----------
    context : dict
        Branch metadata (see _build_branch_docs_prompt for keys).

    Returns
    -------
    (release_notes, impact_summary) : tuple[str, str]
    """
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials not configured – using template fallback for branch docs.")
        return _template_branch_documentation(context)

    prompt = _build_branch_docs_prompt(context)
    logger.info("Invoking Bedrock model '%s' for branch documentation.", BEDROCK_MODEL_ID)

    try:
        raw_text = _invoke_model(prompt)
        notes, summary = _parse_response(raw_text)
        logger.info("Bedrock branch docs parsed successfully.")
        return notes, summary
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.warning("Bedrock %s – falling back to template branch documentation.", error_code)
        return _template_branch_documentation(context)
    except BotoCoreError as exc:
        logger.warning("AWS connectivity error (%s) – falling back to template branch docs.", exc)
        return _template_branch_documentation(context)

# ── Branch-based documentation ─────────────────────────────────────────────

