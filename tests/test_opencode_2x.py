"""OpenCode 2.x integration: CLI flags and config template.

OpenCode 2.x removed ``--dangerously-skip-permissions`` and ``--dir``; the
executor now passes ``--auto`` (auto-approve permissions) and relies on the
subprocess cwd. The config template switched from the 1.x ``"permission"``
object to the 2.x ``"permissions"`` array.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def test_executor_uses_opencode_2x_flags():
    """The command line must use --auto (2.x) and NOT the removed 1.x flags."""
    src = Path("src/ai/opencode_executor.py").read_text()
    m = re.search(r"cmd = \[(.*?)\]", src, re.S)
    assert m, "cmd list not found"
    cmd = m.group(1)
    # strip comments before checking flags (the 2.x note mentions the old flag)
    cmd_code = "\n".join(l for l in cmd.splitlines() if not l.strip().startswith("#"))
    assert '"--auto"' in cmd_code
    assert "--dangerously-skip-permissions" not in cmd_code
    assert '"--dir"' not in cmd_code
    assert '"--format", "json"' in cmd_code


def test_opencode_template_allows_web_tools_and_presets_provider():
    """Web tools are a security feature (dynamic checks): they must be allowed
    and the search provider preset, or non-interactive runs block on the
    provider selection prompt ('Cancelled a request for input: Web Search')."""
    raw = Path("configs/opencode.template.json").read_text().replace("__MODELS__", "{}")
    cfg = json.loads(raw)
    actions = {p["action"] for p in cfg["permissions"] if p["effect"] == "allow"}
    assert "websearch" in actions and "webfetch" in actions
    assert "websearch" in cfg and "provider" in cfg["websearch"]


def test_opencode_template_uses_2x_permissions_array():
    raw = Path("configs/opencode.template.json").read_text()
    # template has a __MODELS__ placeholder -> stub it before json parsing
    raw = raw.replace("__MODELS__", "{}")
    cfg = json.loads(raw)
    assert "permissions" in cfg and isinstance(cfg["permissions"], list)
    assert {"action": "*", "resource": "*", "effect": "allow"} in cfg["permissions"]
    assert "permission" not in cfg  # 1.x key must be gone


def test_dockerfiles_pin_opencode_2x_with_sha():
    for name in ("Dockerfile", "Dockerfile.opencode"):
        p = Path(name)
        if not p.exists():
            continue
        t = p.read_text()
        assert 'OPENCODE_VERSION=2.' in t, f"{name}: not pinned to 2.x"
        assert "sha256sum -c" in t, f"{name}: no checksum verification"
        assert "opencode-linux-" in t and "tar.gz" in t, f"{name}: not the release tarball"
