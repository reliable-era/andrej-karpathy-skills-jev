"""Jev client: one POST to /v1/systemone, an offline fake for tests, and typed answer readers.

Standard library only. See https://docs.typesafe.ai/api.md for the request and response shapes.
"""
import json
import os
import re
import urllib.request

# KARPATHY_JEV_API_URL points elsewhere, e.g. OpenCode Zen: https://opencode.ai/zen/v1/systemone
API_URL = os.environ.get("KARPATHY_JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
TIMEOUT = 20
last_response_model = None


def home():
    return os.path.expanduser(os.environ.get("KARPATHY_JEV_HOME", "~/.karpathy-jev"))


def api_key():
    k = os.environ.get("TYPESAFE_API_KEY")
    if k:
        return k.strip()
    path = os.path.join(home(), "key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip() or None
    return None


# Secret shapes from hermes-jev-skills jevkit/privacy.py. Emails, hashes and other long runs are left alone:
# masking them would corrupt the diffs that the scope and simplicity questions read. Unlike hermes, names
# are matched upper-case only (env-var style), so code such as `sort_key = ...` is not masked.
_SECRET_ASSIGNMENT = re.compile(
    r"(\b[A-Z][A-Z0-9]*(?:[_-][A-Z0-9]+)*[_-]"
    r"(?:SECRET|SECRET[_-]?\w*KEY|API[_-]?KEY|KEY|TOKEN|PASSWORD|PASSWD|CREDENTIALS?|AUTH)\b\s*[:=]\s*)\S+")
_TOKEN_SHAPES = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|apikey_[A-Za-z0-9_]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,})\b")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)


def mask_secrets(value):
    """Replace secret-shaped substrings in every string of a JSON-like value with [secret]."""
    if isinstance(value, str):
        value = _PRIVATE_KEY.sub("[secret]", value)
        value = _SECRET_ASSIGNMENT.sub(r"\1[secret]", value)
        return _TOKEN_SHAPES.sub("[secret]", value)
    if isinstance(value, dict):
        return {k: mask_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_secrets(v) for v in value]
    return value


def _http(state, questions, model):
    global last_response_model
    key = api_key()
    if not key:
        raise RuntimeError("no TypeSafe key (set TYPESAFE_API_KEY or write it to ~/.karpathy-jev/key)")
    body = json.dumps({"state": mask_secrets(state), "model": model, "questions": questions}, ensure_ascii=False).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        payload = json.load(r)
    last_response_model = payload.get("model")
    return payload["answers"]


def _fake(state, questions, model):
    """Answers from the JSON file in KARPATHY_JEV_FAKE, keyed by question id; unlisted questions get a 'no'."""
    global last_response_model
    last_response_model = model
    with open(os.environ["KARPATHY_JEV_FAKE"]) as f:
        canned = json.load(f)
    out = {}
    for qid, q in questions.items():
        if qid in canned:
            out[qid] = canned[qid]
        elif q["type"] == "noul":
            out[qid] = {"type": "noul", "noul": 0.0}
        elif q["type"] == "choice":
            first = next(iter(q["criteria"]))
            out[qid] = {"type": "choice", "choice": first, "confidence": 1.0,
                        "probabilities": {k: 1.0 if k == first else 0.0 for k in q["criteria"]}}
        else:
            out[qid] = {"type": "score", "score": 0.0, "confidence": 1.0}
    return out


def ask(state, questions, model):
    if not questions:
        return {}
    return (_fake if os.environ.get("KARPATHY_JEV_FAKE") else _http)(state, questions, model)


# --- typed readers ---

def noul(answers, qid):
    v = (answers.get(qid) or {}).get("noul")
    return float(v) if isinstance(v, (int, float)) else None


def prob(answers, qid, option):
    """P(option) from a Choice answer. Use this, not `confidence`, to decide: confidence is distribution shape."""
    a = answers.get(qid) or {}
    p = (a.get("probabilities") or {}).get(option)
    if isinstance(p, (int, float)):
        return float(p)
    if not a:
        return None
    return 1.0 if a.get("choice") == option else 0.0


def score(answers, qid):
    v = (answers.get(qid) or {}).get("score")
    return float(v) if isinstance(v, (int, float)) else None
