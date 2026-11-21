#!/usr/bin/env python3
"""Render opencode.json from the Vigilo template (replacement for
config_opencode.sh which needs perl, absent from the Wolfi worker image)."""
import json
import os
import pathlib

template = pathlib.Path(__file__).parent.parent / "configs" / "opencode.template.json"
template = template.read_text()
small = os.environ.get("OPENCODE_SMALL_MODEL", "focus")
medium = os.environ.get("OPENCODE_MEDIUM_MODEL", small)
large = os.environ.get("OPENCODE_LARGE_MODEL", small)

# r3n4: plafonne la fenetre de contexte demandee par opencode (compaction
# automatique avant la limite) pour ne pas saturer le pool KV de halogen.
ctx = int(os.environ.get("OPENCODE_MODEL_CONTEXT", "32768"))
out_tok = int(os.environ.get("OPENCODE_MODEL_OUTPUT", "8192"))

# r3n4: prix de reference ($/M tokens), aligne sur model_info du config LiteLLM
# (0.15 $/M in, 0.47 $/M out). opencode 1.x ignore le champ usage.cost renvoye
# par LiteLLM et ne sait chiffrer qu'avec ce champ -> sans lui, Vigilo affiche 0 $.
# cache.read = prix input : LiteLLM ne remet rien sur les tokens caches (verifie
# sur /spend/logs), donc on facture pareil pour coller a sa facturation.
cost_in = float(os.environ.get("OPENCODE_MODEL_COST_INPUT", "0.15"))
cost_out = float(os.environ.get("OPENCODE_MODEL_COST_OUTPUT", "0.47"))

models = {}
for m in dict.fromkeys([small, medium, large]):
    pretty = m.replace("-", " ").replace(".", " ").title()
    models[m] = {"name": pretty,
                 "limit": {"context": ctx, "output": out_tok},
                 "cost": {"input": cost_in, "output": cost_out,
                          "cache": {"read": cost_in, "write": 0}}}

cfg = template.replace("__MODELS__", json.dumps(models, indent=4))

# r3n4 21/11/26: ne présélectionner un provider web que si sa clé est fournie,
# sinon opencode bloque sur le prompt de sélection en run non-interactif.
_provider = os.environ.get("OPENCODE_WEBSEARCH_PROVIDER", "")
if not _provider:
    _provider = "exa" if os.environ.get("EXA_API_KEY") else (
        "tavily" if os.environ.get("TAVILY_API_KEY") else (
        "firecrawl" if os.environ.get("FIRECRAWL_API_KEY") else (
        "parallel" if os.environ.get("PARALLEL_API_KEY") else "random")))
cfg = cfg.replace("${OPENCODE_WEBSEARCH_PROVIDER:-exa}", _provider)

# r3n4: opencode 2.x -> permissions V2 sous la CLE PLURIELLE "permissions"
# (la doc officielle : « In V2, use `permissions` ... instead of `permission` »).
# Une carte "permission" (meme au format liste V2) est IGNOREE silencieusement
# par le runtime 2.x (onExcessProperty: ignore) -> toutes les regles deny
# tombaient, dont deny websearch : en run non-interactif un appel websearch
# devient un "ask" auto-rejete qui TUE le run entier
# (« Cancelled a request for input this run cannot answer: Web Search »).
# Correctif 20/11/26 : cle "permissions" (V2). 21/11/26 : web autorise, question deny.
perm_v2 = json.dumps([
    {"action": "*", "resource": "*", "effect": "allow"},
    # r3n4 21/11/26: websearch/webfetch RESTENT actives (outil de secu, checks
    # dynamiques sur la cible) -> allow explicite; seul "question" reste deny
    # (les questions interactives tuent un run non-interactif).
    {"action": "websearch", "resource": "*", "effect": "allow"},
    {"action": "webfetch", "resource": "*", "effect": "allow"},
    {"action": "question", "resource": "*", "effect": "deny"},
], indent=2)
import re as _re
# remplace une carte V1 "permission": {...} ou une liste V1/V2 "permission(s)": [...]
pat = _re.compile(r'"permissions?"\s*:\s*(\{[^}]*\}|\[[^\]]*\])')
cfg, n = pat.subn('"permissions": ' + perm_v2, cfg, count=1)
if n == 0:
    cfg = cfg.replace("{", "{\n  \"permissions\": " + perm_v2 + ",", 1)

for var in ("LITELLM_BASE_URL", "LITELLM_API_KEY",
            "OPENCODE_SMALL_MODEL", "OPENCODE_MEDIUM_MODEL", "OPENCODE_LARGE_MODEL",
            "OPENCODE_WEBSEARCH_PROVIDER"):
    cfg = cfg.replace("${%s}" % var, os.environ.get(var, ""))

out = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))) / "opencode"
out.mkdir(parents=True, exist_ok=True)
(out / "opencode.json").write_text(cfg)
json.loads(cfg)  # sanity: valid JSON
print("opencode.json rendered:", out / "opencode.json")
