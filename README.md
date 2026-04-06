# GitHub Cloud Connector (FastAPI)

A simple backend connector to GitHub that authenticates via Personal Access Token (PAT) and exposes usable REST endpoints.

## Features

- Secure token handling via environment variables (`GITHUB_TOKEN`)
- Optional OAuth 2.0 flow for obtaining GitHub access tokens
- Real GitHub API integration using authenticated HTTP requests
- Endpoints to:
  - Fetch repositories (`/repos`)
  - List issues (`/list-issues`)
  - Create issue (`/create-issue`)
  - Fetch commits (`/commits`)

## Prerequisites

- Python 3.10+
- GitHub Personal Access Token with appropriate repo permissions

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set your GitHub token:

```bash
export GITHUB_TOKEN="your_token_here"
```

Or create a `.env` file:

```env
GITHUB_TOKEN=your_token_here

# Optional OAuth (bonus)
GITHUB_CLIENT_ID=Ov23liDnMbBT6vkt5ZCn
GITHUB_CLIENT_SECRET=your_secret_here
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
```

Or copy the demo template:

```bash
cp .env.example .env
```

## Run

```bash
uvicorn app:app --reload --port 8000
```

Open docs at: `http://127.0.0.1:8000/docs`

## API Endpoints

### 1) Health Check
`GET /health`

### 2) Fetch repositories
`GET /repos?user_or_org=<name>&kind=user`

- `kind`: `user` or `org`
- `token` (optional): use `?token=<oauth_or_pat_token>` to override `GITHUB_TOKEN`

Example:

```bash
curl "http://127.0.0.1:8000/repos?user_or_org=octocat&kind=user"
```

### 3) List issues from a repository
`GET /list-issues?owner=<owner>&repo=<repo>&state=open`

- `state`: `open`, `closed`, `all`
- `token` (optional): use `?token=<oauth_or_pat_token>`

Example:

```bash
curl "http://127.0.0.1:8000/list-issues?owner=octocat&repo=Hello-World&state=open"
```

### 4) Create an issue
`POST /create-issue`

Query parameter:
- `token` (optional): use `?token=<oauth_or_pat_token>`

Request body:

```json
{
  "owner": "your-owner",
  "repo": "your-repo",
  "title": "Issue title",
  "body": "Issue body"
}
```

Example:

```bash
curl -X POST "http://127.0.0.1:8000/create-issue" \
  -H "Content-Type: application/json" \
  -d '{"owner":"your-owner","repo":"your-repo","title":"Connector test issue","body":"Created via API"}'
```

### 5) Fetch commits from a repository
`GET /commits?owner=<owner>&repo=<repo>&per_page=10`

- `token` (optional): use `?token=<oauth_or_pat_token>`

Example:

```bash
curl "http://127.0.0.1:8000/commits?owner=octocat&repo=Hello-World&per_page=5"
```

### 6) OAuth login URL (bonus)
`GET /auth/github/login`

Returns an `authorize_url` and `state`.

If `GITHUB_CLIENT_ID`/`GITHUB_REDIRECT_URI` are not set, the app falls back to demo defaults:
- `GITHUB_CLIENT_ID=Ov23liDnMbBT6vkt5ZCn`
- `GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback`

### 7) OAuth callback (bonus)
`GET /auth/github/callback?code=<github_code>&state=<state>`

Returns GitHub access token payload. Use that token with connector endpoints:

```bash
curl "http://127.0.0.1:8000/repos?user_or_org=octocat&kind=user&token=<access_token>"
```

## Error handling

- Missing token returns a clear `500` message
- Upstream GitHub API errors are propagated with status code and response detail
- Input validation errors are handled by FastAPI/Pydantic

## Testing

Run tests with:

```bash
pytest -q
```

Run tests individually:

```bash
pytest -q tests/test_app.py::test_health_endpoint
pytest -q tests/test_app.py::test_get_auth_headers_requires_token
pytest -q tests/test_app.py::test_list_repos_for_user
pytest -q tests/test_app.py::test_list_issues_filters_pull_requests
pytest -q tests/test_app.py::test_create_issue
pytest -q tests/test_app.py::test_list_commits
pytest -q tests/test_app.py::test_end_to_end_connector_flow_with_mocked_github
```

Integration test strategy:

1. **Mocked integration flow** (included above): validates the complete connector sequence inside one test by exercising all key endpoints.
2. **Live integration check** (manual): set `GITHUB_TOKEN`, run the server, and call each endpoint via curl:

```bash
uvicorn app:app --reload --port 8000
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/repos?user_or_org=<your-user>&kind=user"
curl "http://127.0.0.1:8000/list-issues?owner=<owner>&repo=<repo>&state=open"
curl -X POST "http://127.0.0.1:8000/create-issue" -H "Content-Type: application/json" -d '{"owner":"<owner>","repo":"<repo>","title":"integration-test","body":"created from connector"}'
curl "http://127.0.0.1:8000/commits?owner=<owner>&repo=<repo>&per_page=5"
```
