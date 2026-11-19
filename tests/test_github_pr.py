"""GitHub PR creation: content parity with the GitLab path, remote validation.

Mirror of test_gitlab_mr.py: same fixtures and expectations for the report
content, plus the github-specific gates (host validation, API dialect).
"""
from __future__ import annotations

import json

import pytest

from src.services import github_pr

REMOTE = "https://github.com/team/app.git"

INDEX = {"total_vulnerabilities": 2, "by_type": {
    "injection": [{
        "ID": "VG-001", "title": "SQL injection in the search endpoint", "category": "injection",
        "category_label": "SQL Injection", "vulnerability_type": "injection", "severity": "high",
        "confidence": "high", "file": "app/search.py", "line": 42, "cwe": "CWE-89",
        "description": "User input is concatenated into the query.",
        "source": "request.args['q']", "sink": "cursor.execute(query)",
        "entry_point": "GET /search", "attack_path": "q=' OR 1=1 -- dumps the users table",
        "status": "exploited", "verdict": "confirmed",
        "verdict_summary": "The harness dumped all rows through the q parameter.",
        "harness_path": "deliverables/harness/VG-001.py",
        "screenshots": ["screenshots/vg_001_dump.png"],
    }],
    "xss": [{
        "ID": "VG-002", "title": "Reflected XSS in the greeting", "category": "xss",
        "severity": "medium", "status": "potential", "file": "web/greet.py", "line": 7,
        "sink": "render_template_string(name)", "verdict_summary": "Reachable, not proven.",
    }],
}}


@pytest.fixture
def deliv(tmp_path):
    d = tmp_path / "repo" / "deliverables"
    (d / "evidence").mkdir(parents=True)
    (d / "screenshots").mkdir()
    (d / "findings_index.json").write_text(json.dumps(INDEX))
    (d / "evidence" / "VG-001.md").write_text("Request `GET /search?q=' OR 1=1 --` returned 57 users.")
    (d / "screenshots" / "vg_001_dump.png").write_bytes(b"x")
    return tmp_path / "repo"


def manifest(repo, branches):
    (repo / "deliverables" / "remediation_manifest.json").write_text(
        json.dumps({"branches": branches}))


@pytest.fixture
def api(monkeypatch):
    calls = []

    def fake(method, endpoint, token, data=None):
        calls.append((method, endpoint, data))
        if method == "GET":
            return {"default_branch": "main"}
        return {"html_url": "https://github.com/team/app/pull/7", "number": 7}

    monkeypatch.setattr(github_pr, "_github_api_request", fake)
    return calls


class TestParseGithubRepo:
    def test_plain_and_dot_git(self):
        assert github_pr.parse_github_repo("https://github.com/o/r") == "o/r"
        assert github_pr.parse_github_repo("https://github.com/o/r.git") == "o/r"

    def test_rejects_lookalikes_and_wrong_schemes(self):
        for bad in ("https://github.com.evil.com/o/r", "http://github.com/o/r",
                    "git@github.com:o/r.git", "https://gitlab.com/o/r",
                    "https://github.com/o", "not a url"):
            with pytest.raises(ValueError):
                github_pr.parse_github_repo(bad)


class TestCreateRemediationPrs:
    async def test_pr_created_with_gitlab_parity_content(self, deliv, api):
        manifest(deliv, [{"branch": "fix/VG-001", "finding_ids": ["VG-001"]}])
        out = await github_pr.create_remediation_prs(
            str(deliv), "sess", ["fix/VG-001"], token="t", remote_url=REMOTE)
        assert out["created"][0]["mr_url"].endswith("/pull/7")
        assert out["created"][0]["mr_iid"] == 7
        get = [c for c in api if c[0] == "GET"][0]
        assert get[1] == "/repos/team/app"          # default branch lookup
        post = [c for c in api if c[0] == "POST"][0]
        assert post[1] == "/repos/team/app/pulls"
        data = post[2]
        assert data["head"] == "fix/VG-001" and data["base"] == "main"
        assert data["title"].startswith("[HIGH] Fix VG-001: SQL injection")
        for needle in ("cursor.execute(query)", "request.args['q']",
                       "The harness dumped all rows", "returned 57 users",
                       "CWE-89", "app/search.py:42"):
            assert needle in data["body"]

    async def test_one_pr_per_branch_covering_several_findings(self, deliv, api):
        manifest(deliv, [{"branch": "fix/VG-001-VG-002", "finding_ids": ["VG-001", "VG-002"]}])
        out = await github_pr.create_remediation_prs(
            str(deliv), "sess", ["fix/VG-001-VG-002"], token="t", remote_url=REMOTE)
        assert len(out["created"]) == 1
        assert out["created"][0]["finding_ids"] == ["VG-001", "VG-002"]
        posts = [c for c in api if c[0] == "POST"]
        assert len(posts) == 1 and "render_template_string(name)" in posts[0][2]["body"]

    async def test_bad_remote_rejected_before_any_request(self, deliv, api):
        with pytest.raises(ValueError):
            await github_pr.create_remediation_prs(
                str(deliv), "s", ["fix/x"], token="t",
                remote_url="https://github.com.evil.com/team/app")
        assert api == []   # nothing left the platform

    async def test_empty_branch_list_short_circuits(self, deliv, api):
        out = await github_pr.create_remediation_prs(
            str(deliv), "s", [], token="t", remote_url=REMOTE)
        assert out == {"created": [], "failed": [], "total": 0} and api == []

    async def test_api_failure_recorded_not_raised(self, deliv, monkeypatch):
        def boom(method, endpoint, token, data=None):
            if method == "POST":
                raise RuntimeError("GitHub API error 422: Validation Failed supersecret")
            return {"default_branch": "main"}
        monkeypatch.setattr(github_pr, "_github_api_request", boom)
        manifest(deliv, [{"branch": "fix/VG-001", "finding_ids": ["VG-001"]}])
        out = await github_pr.create_remediation_prs(
            str(deliv), "s", ["fix/VG-001"], token="supersecret", remote_url=REMOTE)
        assert out["failed"] and "supersecret" not in out["failed"][0]["error"]
