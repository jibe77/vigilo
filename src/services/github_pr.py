"""GitHub pull requests for pushed fix branches.

Mirror of gitlab_mr.py for GitHub remotes: one PR per pushed fix/* branch,
targeting the repository's default branch and describing every finding the
branch fixes. The content builders are imported from the GitLab path so both
forges deliver the same report; only the API dialect differs.

The token is the run's GitHub credential, redeemed just in time by the caller;
it never comes from the environment and never touches disk. Requests go to
api.github.com only, with no proxies and no redirects: the token must only go
where the URL says.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from src.audit.redact import redact
from src.services.gitlab_mr import (
    _branch_finding_ids,
    _build_mr_description,
    _build_mr_title,
    _find_vuln_in_index,
    _load_findings_index,
    _manifest_finding_ids,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Treat 3xx as an error (HTTPError) instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


# No proxies from the environment either: the token must only go where the URL says.
_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def parse_github_repo(remote_url: str) -> str:
    """Extract ``owner/repo`` from an https GitHub remote URL.

    Only github.com remotes are accepted: the repository schema already rejects
    other hosts at creation, this is the last gate before the token leaves the
    platform. Raises ValueError on anything else.
    """
    try:
        parsed = urllib.parse.urlparse(remote_url.strip())
    except ValueError as exc:
        raise ValueError(f"invalid remote URL: {remote_url!r}") from exc
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "github.com":
        raise ValueError(f"not a github.com remote: {remote_url!r}")
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2 or not all(parts[:2]):
        raise ValueError(f"cannot extract owner/repo from {remote_url!r}")
    return "/".join(parts[:2])


def _github_api_request(
    method: str, endpoint: str, token: str, data: dict | None = None
) -> dict:
    """Make a GitHub REST API request against API_BASE."""
    url = f"{API_BASE}{endpoint}"
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with _NO_REDIRECT_OPENER.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            # Never follow a redirect: it would replay the token to another host.
            raise RuntimeError(
                f"GitHub API answered with a redirect (HTTP {exc.code}); refusing to follow it"
            ) from exc
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("GitHub API error %d: %s", exc.code, error_body)
        raise RuntimeError(f"GitHub API error {exc.code}: {error_body}") from exc


async def create_remediation_prs(
    repo_path: str,
    session_id: str,
    pushed_branches: list[str],
    *,
    token: str,
    remote_url: str,
) -> dict[str, Any]:
    """Create one GitHub PR per pushed fix branch.

    Same contract as :func:`gitlab_mr.create_remediation_mrs` (the result keys
    stay ``mr_url``/``mr_iid`` so the delivery state stays forge-neutral):
    ``token`` is the run's GitHub credential, redeemed just in time by the
    caller, and ``remote_url`` is the repository's remote from the platform.

    Each PR targets the default branch and describes every finding the branch
    fixes. The blocking HTTP calls run in a thread so the activity keeps
    heartbeating.
    """
    if not pushed_branches:
        logger.info("No pushed branches - skipping PR creation")
        return {"created": [], "failed": [], "total": 0}
    if not remote_url:
        raise RuntimeError("no repository remote URL - cannot determine the GitHub project")

    project = parse_github_repo(remote_url)
    repo_info = await asyncio.to_thread(
        _github_api_request, "GET", f"/repos/{project}", token
    )
    default_branch = repo_info.get("default_branch") or "main"

    index = _load_findings_index(repo_path)
    manifest_ids = _manifest_finding_ids(repo_path)

    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for branch in pushed_branches:
        ids = _branch_finding_ids(branch, manifest_ids, index)
        entries = [_find_vuln_in_index(index, i) for i in ids]
        title = _build_mr_title(branch, ids, entries)
        description = _build_mr_description(repo_path, branch, ids, session_id, entries)
        # Evidence write-ups may quote the run's secrets: mask every registered
        # secret in what leaves the platform.
        title, description = redact(title), redact(description)
        try:
            pr = await asyncio.to_thread(
                _github_api_request, "POST", f"/repos/{project}/pulls", token,
                {
                    "title": title,
                    "head": branch,
                    "base": default_branch,
                    "body": description,
                },
            )
            created.append({
                "branch": branch, "finding_ids": ids,
                "mr_url": pr.get("html_url", ""), "mr_iid": pr.get("number", 0),
            })
            logger.info("Created PR #%s for %s: %s", pr.get("number"), branch, pr.get("html_url", ""))
        except Exception as exc:  # noqa: BLE001
            failed.append({"branch": branch, "finding_ids": ids,
                           "error": str(exc).replace(token, "<token>")[:500]})
            logger.warning("Failed to create PR for %s: %s",
                           branch, str(exc).replace(token, "<token>"))

    logger.info("PR creation complete: %d created, %d failed out of %d branches",
                len(created), len(failed), len(pushed_branches))
    return {"created": created, "failed": failed, "total": len(pushed_branches)}
