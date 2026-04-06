import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app

client = TestClient(app.app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_auth_headers_requires_token() -> None:
    with patch.dict(os.environ, {}, clear=True):
        try:
            app._get_auth_headers()
            raise AssertionError("Expected HTTPException")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 500


def test_list_repos_for_user() -> None:
    payload = [
        {
            "name": "repo1",
            "full_name": "octocat/repo1",
            "private": False,
            "html_url": "https://github.com/octocat/repo1",
        }
    ]

    with patch("app._github_request", new=AsyncMock(return_value=payload)) as mock_request:
        response = client.get("/repos", params={"user_or_org": "octocat", "kind": "user"})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["repositories"][0]["full_name"] == "octocat/repo1"
    mock_request.assert_awaited_once_with("GET", "/users/octocat/repos")


def test_list_issues_filters_pull_requests() -> None:
    payload = [
        {
            "number": 1,
            "title": "Bug",
            "state": "open",
            "html_url": "https://github.com/octocat/Hello-World/issues/1",
        },
        {
            "number": 2,
            "title": "PR masquerading as issue",
            "state": "open",
            "html_url": "https://github.com/octocat/Hello-World/pull/2",
            "pull_request": {"url": "https://api.github.com/repos/octocat/Hello-World/pulls/2"},
        },
    ]

    with patch("app._github_request", new=AsyncMock(return_value=payload)):
        response = client.get("/list-issues", params={"owner": "octocat", "repo": "Hello-World", "state": "open"})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert len(body["issues"]) == 1
    assert body["issues"][0]["number"] == 1


def test_create_issue() -> None:
    payload = {
        "number": 7,
        "title": "Created via API",
        "state": "open",
        "html_url": "https://github.com/octocat/Hello-World/issues/7",
    }

    with patch("app._github_request", new=AsyncMock(return_value=payload)) as mock_request:
        response = client.post(
            "/create-issue",
            json={
                "owner": "octocat",
                "repo": "Hello-World",
                "title": "Created via API",
                "body": "Body",
            },
        )

    assert response.status_code == 200
    assert response.json()["number"] == 7
    mock_request.assert_awaited_once_with(
        "POST",
        "/repos/octocat/Hello-World/issues",
        json={"title": "Created via API", "body": "Body"},
    )


def test_list_commits() -> None:
    payload = [
        {
            "sha": "abc123",
            "commit": {"message": "Initial commit"},
            "author": {"login": "octocat"},
            "html_url": "https://github.com/octocat/Hello-World/commit/abc123",
        }
    ]

    with patch("app._github_request", new=AsyncMock(return_value=payload)) as mock_request:
        response = client.get("/commits", params={"owner": "octocat", "repo": "Hello-World", "per_page": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["commits"][0]["sha"] == "abc123"
    mock_request.assert_awaited_once_with(
        "GET",
        "/repos/octocat/Hello-World/commits",
        params={"per_page": 1},
    )


def test_end_to_end_connector_flow_with_mocked_github() -> None:
    repos_payload = [
        {
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "private": False,
            "html_url": "https://github.com/octocat/Hello-World",
        }
    ]
    issues_payload = [
        {
            "number": 1,
            "title": "Existing issue",
            "state": "open",
            "html_url": "https://github.com/octocat/Hello-World/issues/1",
        }
    ]
    create_issue_payload = {
        "number": 2,
        "title": "Created in flow",
        "state": "open",
        "html_url": "https://github.com/octocat/Hello-World/issues/2",
    }
    commits_payload = [
        {
            "sha": "def456",
            "commit": {"message": "Flow commit"},
            "author": {"login": "octocat"},
            "html_url": "https://github.com/octocat/Hello-World/commit/def456",
        }
    ]

    async def _mocked_request(method, path, params=None, json=None):  # noqa: ANN001,ANN202
        if method == "GET" and path == "/users/octocat/repos":
            return repos_payload
        if method == "GET" and path == "/repos/octocat/Hello-World/issues":
            return issues_payload
        if method == "POST" and path == "/repos/octocat/Hello-World/issues":
            return create_issue_payload
        if method == "GET" and path == "/repos/octocat/Hello-World/commits":
            return commits_payload
        raise AssertionError(f"Unexpected call: {method} {path} params={params} json={json}")

    with patch("app._github_request", new=AsyncMock(side_effect=_mocked_request)):
        repos_res = client.get("/repos", params={"user_or_org": "octocat", "kind": "user"})
        issues_res = client.get("/list-issues", params={"owner": "octocat", "repo": "Hello-World"})
        create_res = client.post(
            "/create-issue",
            json={"owner": "octocat", "repo": "Hello-World", "title": "Created in flow", "body": "body"},
        )
        commits_res = client.get("/commits", params={"owner": "octocat", "repo": "Hello-World", "per_page": 1})

    assert repos_res.status_code == 200
    assert issues_res.status_code == 200
    assert create_res.status_code == 200
    assert commits_res.status_code == 200
    assert repos_res.json()["repositories"][0]["full_name"] == "octocat/Hello-World"
    assert issues_res.json()["issues"][0]["number"] == 1
    assert create_res.json()["number"] == 2
    assert commits_res.json()["commits"][0]["sha"] == "def456"
