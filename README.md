# Release Manager — with AWS Bedrock AI Integration

A full-stack Python project with a **FastAPI** backend and a **Flask** UI, featuring
AI-powered release documentation generation via **AWS Bedrock**.

## Project Structure

```
├── backend/                        # FastAPI REST API (port 8000)
│   ├── main.py                     # App entry point + DB migrations
│   ├── database.py                 # SQLAlchemy engine + session
│   ├── models.py                   # ORM models (Project, Release, PR, Defect…)
│   ├── schemas.py                  # Pydantic request/response schemas
│   ├── bedrock_client.py           # ★ NEW – AWS Bedrock AI integration
│   ├── .env.example                # ★ NEW – copy to .env and fill in values
│   ├── requirements.txt            # Python dependencies (incl. boto3)
│   └── routers/
│       ├── projects.py             # CRUD /projects
│       ├── releases.py             # CRUD /releases
│       └── release_hub.py          # ★ UPDATED – /hub governance workspace
│
└── ui/                             # Flask Web UI (port 5000)
    ├── app.py                      # Flask routes
    ├── requirements.txt
    ├── static/css/
    │   ├── style.css
    │   └── hub_style.css           # ★ UPDATED – AI loading + output styles
    └── templates/
        ├── hub_overview.html       # ★ UPDATED – AI loading animation
        ├── hub_docs.html           # ★ UPDATED – Bedrock output display
        └── … (all other templates unchanged)
```

---

## Quick Setup

### Step 1 — AWS Bedrock credentials

1. Go to **AWS Console → IAM → Users → Create user** (programmatic access only)
2. Attach this inline policy (replace `<REGION>` and `<MODEL_ID>`):
   ```json
   {
     "Effect": "Allow",
     "Action": ["bedrock:InvokeModel"],
     "Resource": "arn:aws:bedrock:<REGION>::foundation-model/<MODEL_ID>"
   }
   ```
3. Create an access key → **Application running outside AWS** → save both values
4. Go to **AWS Console → Amazon Bedrock → Model access** → enable your chosen model

### Step 2 — Configure environment variables

```bash
cd backend
cp .env.example .env
```

Edit `.env` with your real values:
```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
FLASK_SECRET_KEY=any-long-random-string
BACKEND_URL=http://localhost:8000
```

**Recommended models:**
| Model ID | Speed | Quality | Cost |
|---|---|---|---|
| `amazon.nova-pro-v1:0` | Fast | ★★★★ | $$ |
| `amazon.nova-lite-v1:0` | Fastest | ★★★ | $ |
| `anthropic.claude-3-5-sonnet-20241022-v2:0` | Medium | ★★★★★ | $$$ |
| `anthropic.claude-3-haiku-20240307-v1:0` | Fast | ★★★★ | $$ |

---

## Running the Project

### Terminal 1 — Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend running at: http://localhost:8000  
API docs (Swagger): http://localhost:8000/docs

### Terminal 2 — Frontend (Flask UI)

```bash
cd ui
pip install -r requirements.txt
python app.py
```

UI running at: http://localhost:5000

---

## Using the AI Document Generation

1. Open http://localhost:5000
2. Create a **Project** (Projects menu)
3. Create a **Release** linked to that project
4. Open the release in **Release Hub** → add Pull Requests, Defects, Security Risks
5. Click **Generate Docs** on the Overview page
6. Watch the Bedrock AI loading animation → release notes appear automatically
7. Go to the **Docs tab** to read, edit, and approve the generated notes
8. Once approved, the Go/No-Go status updates to **Approved**

---

## How Bedrock Integration Works

```
User clicks "Generate Docs"
        │
        ▼
Flask  POST /hub/releases/{id}/docs/generate
        │
        ▼
FastAPI collects from DB:
  • Release metadata (name, version, owner, target date)
  • Project name + description
  • All Pull Requests (number, title, status)
  • All JIRA Defects (key, title, severity, status)
  • All Security Risks (id, description, status)
        │
        ▼
bedrock_client.py builds prompt → calls AWS Bedrock InvokeModel
        │
        ▼
Bedrock returns:
  RELEASE NOTES: <professional summary>
  IMPACT SUMMARY: <modules/areas affected>
        │
        ▼
Saved to release_docs table → displayed in hub_docs.html
```

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | ✅ | IAM access key ID |
| `AWS_SECRET_ACCESS_KEY` | ✅ | IAM secret access key |
| `AWS_REGION` | ✅ | AWS region (e.g. `us-east-1`) |
| `BEDROCK_MODEL_ID` | ✅ | Bedrock model string |
| `GITHUB_TOKEN` | optional | GitHub personal access token (recommended to avoid rate limits) |
| `GITHUB_OWNER` | optional | Default GitHub repository owner for `/api/github` calls |
| `GITHUB_REPO` | optional | Default GitHub repository name for `/api/github` calls |
| `JIRA_URL` | optional | Jira site URL (e.g. `https://your-domain.atlassian.net`) |
| `JIRA_EMAIL` | optional | Jira account email for API auth |
| `JIRA_TOKEN` | optional | Jira API token |
| `FLASK_SECRET_KEY` | ✅ | Flask session signing key |
| `BACKEND_URL` | optional | FastAPI URL (default: `http://localhost:8000`) |

---

## Jira and GitHub Operations

The backend now includes integration APIs compatible with the reference repo:

- `GET /api/jira/projects/live` – fetch projects from Jira
- `POST /api/jira/projects/sync` – sync Jira projects to DB
- `GET /api/jira/projects/{project_key}/issues` – fetch project issues with release mapping
- `POST /api/jira/projects/{project_key}/issues/sync` – sync issues to work items
- `POST /api/jira/releases/{release_id}/issues/sync` – sync Jira issues directly to a release
- `GET /api/github/prs` – fetch live PRs (`repository=owner/repo`, `state=open|closed|all`)
- `POST /api/github/releases/{release_id}/prs/sync` – sync PRs to release
- `GET /api/github/releases/{release_id}/prs` – fetch DB-stored PRs for release

To use release-level Git sync, set each project `repository_name` as `owner/repo`.


python -m uvicorn main:app --reload --port 8000
\connect root@localhost
proto@123
