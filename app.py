import os
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

load_dotenv()

GITHUB_API_BASE_URL = "https://api.github.com"

app = FastAPI(title="GitHub Cloud Connector", version="1.0.0")


class CreateIssueRequest(BaseModel):
    owner: str = Field(..., description="Repository owner or organization")
    repo: str = Field(..., description="Repository name")
    title: str = Field(..., min_length=1)
    body: str | None = None


def _get_auth_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Missing GITHUB_TOKEN environment variable. Set it in your environment or .env file.",
        )

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _github_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    headers = _get_auth_headers()

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
) -> dict[str, Any]:
    if kind == "org":
        path = f"/orgs/{user_or_org}/repos"
    else:
        path = f"/users/{user_or_org}/repos"

    data = await _github_request("GET", path)
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
async def list_issues(owner: str, repo: str, state: str = Query("open", pattern="^(open|closed|all)$")) -> dict[str, Any]:
    data = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state},
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
async def create_issue(payload: CreateIssueRequest) -> dict[str, Any]:
    data = await _github_request(
        "POST",
        f"/repos/{payload.owner}/{payload.repo}/issues",
        json={"title": payload.title, "body": payload.body},
    )
    return {
        "number": data["number"],
        "title": data["title"],
        "state": data["state"],
        "html_url": data["html_url"],
    }


@app.get("/commits")
async def list_commits(owner: str, repo: str, per_page: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    data = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/commits",
        params={"per_page": per_page},
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
