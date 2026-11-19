"""Ownership / kind / host checks applied before a stored credential is used.

A credential is only ever usable by its owner, for the kind of secret it holds, and
(for GitLab tokens with a recorded base URL) only against that GitLab host. These
checks run both when a credential is linked (create/update) and again when a run
starts, right before the secret is decrypted.
"""
from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

from src.webapi.models import Credential

GITLAB_KIND = "gitlab_token"
GITHUB_KIND = "github_token"
COOKIE_KIND = "cookie_header"


class CredentialRejected(ValueError):
    pass


def _host_port(url: str) -> tuple[str, int] | None:
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        scheme = (parts.scheme or "https").lower()
        port = parts.port or (80 if scheme == "http" else 443)
    except ValueError:
        return None
    return (host, port) if host else None


def hosts_match(base_url: str | None, target_url: str | None) -> bool:
    """True when ``base_url`` is unset, or names the same host:port as ``target_url``."""
    if not base_url:
        return True
    a, b = _host_port(base_url), _host_port(target_url or "")
    return a is not None and a == b


def validate_gitlab_credential(
    cred: Credential | None, owner_id: uuid.UUID | None, repo_url: str | None
) -> None:
    """Raise :class:`CredentialRejected` unless ``cred`` is a gitlab_token owned by
    ``owner_id`` and (when it records a base URL) bound to ``repo_url``'s host."""
    if cred is None:
        raise CredentialRejected("Unknown credential")
    if owner_id is None or cred.owner_id != owner_id:
        raise CredentialRejected("Credential is not owned by the repository owner")
    if cred.kind != GITLAB_KIND:
        raise CredentialRejected("Credential is not a GitLab token")
    if repo_url and not hosts_match(cred.gitlab_base_url, repo_url):
        raise CredentialRejected("Credential is bound to a different GitLab host")


def validate_github_credential(
    cred: Credential | None, owner_id: uuid.UUID | None, repo_url: str | None
) -> None:
    """Raise :class:`CredentialRejected` unless ``cred`` is a github_token owned by
    ``owner_id`` and (when it records a base URL) bound to ``repo_url``'s host."""
    if cred is None:
        raise CredentialRejected("Unknown credential")
    if owner_id is None or cred.owner_id != owner_id:
        raise CredentialRejected("Credential is not owned by the repository owner")
    if cred.kind != GITHUB_KIND:
        raise CredentialRejected("Credential is not a GitHub token")
    if repo_url and not hosts_match(cred.gitlab_base_url, repo_url):
        raise CredentialRejected("Credential is bound to a different host")


def validate_repo_credential(
    cred: Credential | None, owner_id: uuid.UUID | None, repo_url: str | None,
    source_type: str,
) -> None:
    """Kind check dispatched on the repository's source type: a GitHub repository
    must carry a github_token, a GitLab one a gitlab_token. Upload sources never
    reach this (no credential), but default to the GitLab check."""
    if source_type == "github":
        validate_github_credential(cred, owner_id, repo_url)
    else:
        validate_gitlab_credential(cred, owner_id, repo_url)


def validate_cookie_credential(cred: Credential | None, owner_id: Any) -> None:
    if cred is None:
        raise CredentialRejected("Unknown credential")
    if owner_id is None or cred.owner_id != owner_id:
        raise CredentialRejected("Credential is not owned by the job owner")
    if cred.kind != COOKIE_KIND:
        raise CredentialRejected("Credential is not a cookie credential")
