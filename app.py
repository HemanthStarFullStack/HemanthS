import os
import secrets
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

load_dotenv()

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEFAULT_DEMO_GITHUB_CLIENT_ID = "Ov23liDnMbBT6vkt5ZCn"
DEFAULT_DEMO_REDIRECT_URI = "http://localhost:8000/auth/github/callback"

app = FastAPI(title="GitHub Cloud Connector", version="1.0.0")
oauth_state_store: dict[str, bool] = {}


class CreateIssueRequest(BaseModel):
    owner: str = Field(..., description="Repository owner or organization")
    repo: str = Field(..., description="Repository name")
    title: str = Field(..., min_length=1)
    body: str | None = None


def _get_auth_headers(token: str | None = None) -> dict[str, str]:
    resolved_token = token or os.getenv("GITHUB_TOKEN")
    if not resolved_token:
        raise HTTPException(
            status_code=500,
            detail="Missing token. Provide `token` in request or set GITHUB_TOKEN in environment/.env.",
        )

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {resolved_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _github_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = _get_auth_headers(token=token)

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(
            method=method,
            url=f"{GITHUB_API_BASE_URL}{path}",
            headers=headers,
            params=params,
            json=json,
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json()
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response.json()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/repos")
async def list_repos(
    user_or_org: str = Query(..., description="GitHub username or organization"),
    kind: str = Query("user", pattern="^(user|org)$"),
    token: str | None = Query(None, description="Optional GitHub token (PAT or OAuth token)"),
) -> dict[str, Any]:
    if kind == "org":
        path = f"/orgs/{user_or_org}/repos"
    else:
        path = f"/users/{user_or_org}/repos"

    data = await _github_request("GET", path, token=token)
    return {
        "count": len(data),
        "repositories": [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "html_url": repo["html_url"],
            }
            for repo in data
        ],
    }


@app.get("/list-issues")
async def list_issues(
    owner: str,
    repo: str,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    token: str | None = Query(None, description="Optional GitHub token (PAT or OAuth token)"),
) -> dict[str, Any]:
    data = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state},
        token=token,
    )
    issues = [issue for issue in data if "pull_request" not in issue]
    return {
        "count": len(issues),
        "issues": [
            {
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "html_url": issue["html_url"],
            }
            for issue in issues
        ],
    }


@app.post("/create-issue")
async def create_issue(payload: CreateIssueRequest, token: str | None = Query(None, description="Optional GitHub token (PAT or OAuth token)")) -> dict[str, Any]:
    data = await _github_request(
        "POST",
        f"/repos/{payload.owner}/{payload.repo}/issues",
        json={"title": payload.title, "body": payload.body},
        token=token,
    )
    return {
        "number": data["number"],
        "title": data["title"],
        "state": data["state"],
        "html_url": data["html_url"],
    }


@app.get("/commits")
async def list_commits(
    owner: str,
    repo: str,
    per_page: int = Query(10, ge=1, le=100),
    token: str | None = Query(None, description="Optional GitHub token (PAT or OAuth token)"),
) -> dict[str, Any]:
    data = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/commits",
        params={"per_page": per_page},
        token=token,
    )
    return {
        "count": len(data),
        "commits": [
            {
                "sha": commit["sha"],
                "message": commit["commit"]["message"],
                "author": (commit.get("author") or {}).get("login"),
                "url": commit["html_url"],
            }
            for commit in data
        ],
    }


@app.get("/auth/github/login")
async def github_oauth_login() -> dict[str, str]:
    client_id = os.getenv("GITHUB_CLIENT_ID", DEFAULT_DEMO_GITHUB_CLIENT_ID)
    redirect_uri = os.getenv("GITHUB_REDIRECT_URI", DEFAULT_DEMO_REDIRECT_URI)

    state = secrets.token_urlsafe(24)
    oauth_state_store[state] = True
    authorize_url = (
        f"{GITHUB_OAUTH_AUTHORIZE_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=repo"
        f"&state={state}"
    )
    return {"authorize_url": authorize_url, "state": state}


@app.get("/auth/github/callback")
async def github_oauth_callback(code: str, state: str) -> dict[str, Any]:
    if state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
    del oauth_state_store[state]

    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    redirect_uri = os.getenv("GITHUB_REDIRECT_URI", DEFAULT_DEMO_REDIRECT_URI)

    if not client_id:
        client_id = DEFAULT_DEMO_GITHUB_CLIENT_ID

    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="Missing GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, or GITHUB_REDIRECT_URI.",
        )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GITHUB_OAUTH_TOKEN_URL,
            headers={"Accept": "application/json"},
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "state": state,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    if "access_token" not in data:
        raise HTTPException(status_code=400, detail=data)

    return {
        "access_token": data["access_token"],
        "token_type": data.get("token_type", "bearer"),
        "scope": data.get("scope", ""),
        "usage": "Use this token in query param: ?token=<access_token> for connector endpoints.",
    }
