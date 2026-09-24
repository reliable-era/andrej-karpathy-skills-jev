"""Jev client: one POST to /v1/systemone, an offline fake for tests, and typed answer readers.

Standard library only. See https://docs.typesafe.ai/api.md for the request and response shapes.
"""
import json
import os
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
TIMEOUT = 20


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


def _http(state, questions, model):
    key = api_key()
    if not key:
        raise RuntimeError("no TypeSafe key (set TYPESAFE_API_KEY or write it to ~/.karpathy-jev/key)")
    body = json.dumps({"state": state, "model": model, "questions": questions}, ensure_ascii=False).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)["answers"]


def _fake(state, questions, model):
    """Answers from the JSON file in KARPATHY_JEV_FAKE, keyed by question id; unlisted questions get a 'no'."""
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
            out[qid] = {"type": "choice", "choice": first, "confidence": 1.0, "probabilities": {first: 1.0}}
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
