"""Evidence collection: what the router may show Jev. Everything here is observed, not claimed.

- Transcripts (Claude Code and Codex JSONL): the request, what the agent said, tool calls and their status.
- Git: the diff since a baseline snapshot taken when the turn started, plus files created during the turn.
- Recorded runs (agent mode, no transcript): commands executed through `router.py run`, with real exit codes.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

MAX_HUNK_CHARS = 1500
MAX_MSG_CHARS = 2000
OUTPUT_TAIL = 800
NEW_FILE_LINES = 80
TAIL_BYTES = 768 * 1024

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_based_edit_tool"}
COMMAND_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "container.exec"}
HARNESS_PREFIXES = (
    "Stop hook feedback", "PreToolUse:", "PostToolUse:", "[Request interrupted", "[Image:", "Caveat: The messages below",
    "API Error", "Another Claude session sent", "# AGENTS.md instructions", "The following is the Codex agent history",
)
REVERT = re.compile(r"\bgit\s+(stash(?!\s+(pop|apply|list|show|drop))|apply\s+(-R|--reverse)\b|checkout\s|restore\s|revert\s)")
REAPPLY = re.compile(r"\bgit\s+(stash\s+(pop|apply)\b|apply\s+(?!-R\b|--reverse\b)\S)")
MASKED_PIPE = re.compile(r"\|\s*(tail|head|grep|less|more|cat|wc|sed|awk|sort|uniq|tee|cut|tr)\b[^|]*$")
MASKED_TAIL = re.compile(r"(;|\|\||\n)\s*(echo|true|exit 0|git (stash (pop|apply)|apply|checkout|restore))\b[^;&|\n]*$")
ECHO_MARK = re.compile(r"""echo\s+["']?([^"'$;&|\n]*?)\$\?""")  # the literal text an `echo "EXIT: $?"` prints before the code
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.\w+$|\.(test|spec)\.\w+$")


# --- transcripts (Claude Code and Codex JSONL) ---

def _rows(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        start = max(0, os.path.getsize(path) - TAIL_BYTES)
        f.seek(start)
        text = f.read().decode("utf-8", "replace")
    if start:
        text = text.split("\n", 1)[-1]
    rows = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def _clean_human(s):
    s = (s or "").strip()
    if not s or s.startswith("<") or s.startswith(HARNESS_PREFIXES):
        return None
    return s


def human_text(d):
    if d.get("type") == "response_item":  # Codex
        p = d.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "user":
            return None
        c = p.get("content") or []
        return _clean_human("\n".join(b.get("text", "") for b in c if isinstance(b, dict)))
    if d.get("type") != "user":
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return _clean_human(c) if isinstance(c, str) else None


def assistant_text(d):
    if d.get("type") == "response_item":
        p = d.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "assistant":
            return None
        c = p.get("content") or []
    elif d.get("type") == "assistant":
        c = (d.get("message") or {}).get("content")
    else:
        return None
    if not isinstance(c, list):
        return None
    s = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
    return s.strip() or None


ECHO_STATUS = re.compile(r"(;|&&|\|\||\n)\s*echo\b[^;&|\n]*\$\?[^;&|\n]*$")
FAIL_MARK = re.compile(r"\b\d+ (failed|errors?)\b|^FAILED\b|^FAIL:|Traceback \(most recent call last\)", re.M)
PASS_MARK = re.compile(r"\b\d+ passed\b|^OK$|^OK \(", re.M)
PIPE = re.compile(r"(?<!\|)\|(?!\|)")


def with_pipefail(command):
    """A piped command reports the last stage's exit status; with pipefail it reports the check's."""
    if PIPE.search(command) and "pipefail" not in command:
        return "set -o pipefail; " + command
    return command


def observed_result(command, status, output="", pipefail=False):
    """A command whose last stage is a text filter or an echo reports that stage's exit code, not the check's.
    `pipefail` says the harness ran the command with pipefail (the hook rewrote it), so a pipe is not masking.
    When the echo prints `$?`, the check's own exit code is on the output's last line: use that."""
    piped = MASKED_PIPE.search(command) and "pipefail" not in command and not pipefail
    if status == "ok" and (piped or MASKED_TAIL.search(command)):
        marks = [m.group(1).strip() for m in ECHO_MARK.finditer(command)]  # e.g. "EXIT:" from echo "EXIT: $?"
        found = [re.findall(re.escape(mk) + r"\s*(\d+)", output) for mk in marks if mk]
        codes = [int(f[-1]) for f in found if f]
        if codes:  # the check's own exit code, printed by the agent's echo, wherever it sits in the output
            return "ok" if all(c == 0 for c in codes) else "error"
        last = output.strip().splitlines()[-1] if output.strip() else ""
        m = re.search(r"(\d+)\s*$", last) if ECHO_STATUS.search(command) else None
        if m:
            return "ok" if int(m.group(1)) == 0 else "error"
        if FAIL_MARK.search(output):  # a test runner's own summary is observed output
            return "error"
        if PASS_MARK.search(output):
            return "ok"
        return "masked"
    return status


def _command_of(name, inp):
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            return inp
    if not isinstance(inp, dict):
        return ""
    c = inp.get("command") or inp.get("cmd") or ""
    if isinstance(c, list):  # Codex: ["bash", "-lc", "pytest -q"]
        c = c[-1] if c else ""
    return str(c)


def _output_text(output):
    if isinstance(output, list):  # Claude: [{"type": "text", "text": ...}]
        return "\n".join(b.get("text", "") for b in output if isinstance(b, dict))
    return output if isinstance(output, str) else json.dumps(output)


def _paths_of(inp):
    """Files an edit tool call touches: Claude tools name one path; a Codex apply_patch names them in the patch."""
    if isinstance(inp, str):
        return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", inp, re.M)
    if isinstance(inp, dict):
        return [p for p in (inp.get("file_path"), inp.get("notebook_path"), inp.get("path")) if isinstance(p, str)]
    return []


def _codex_status(output):
    text = output if isinstance(output, str) else json.dumps(output)
    try:
        meta = json.loads(text).get("metadata") or {}
        if isinstance(meta.get("exit_code"), int):
            return "ok" if meta["exit_code"] == 0 else "error"
    except (ValueError, AttributeError):
        pass
    m = re.search(r"(?:exit[_ ]code\"?:?\s*)(-?\d+)", text, re.I)
    if m:
        return "ok" if int(m.group(1)) == 0 else "error"
    return "unknown"


def on_unfixed_code(calls):
    """Commands run while the fix was not in the tree: before the first edit of a non-test file (adding a test
    first is fine), or after the change was stashed or reverted and before it was reapplied or edited again.
    A failing test here is a reproduction."""
    out, unfixed = [], True
    for c in calls:
        if c["kind"] == "edit" and any(not TEST_PATH.search(p) for p in (c.get("paths") or ["?"])):
            unfixed = False
        elif c["kind"] == "command":
            if REVERT.search(c["command"]):
                unfixed = True
            if unfixed:
                out.append(c)
            if REAPPLY.search(c["command"]):
                unfixed = False
    return out


def read_turn(path, pipefail=False):
    """The current turn: request, assistant messages, and tool calls in order with their status.
    `pipefail`: the hook rewrote piped commands, so their recorded status is the check's own."""
    rows = _rows(path)
    start = 0
    request = None
    for j in range(len(rows) - 1, -1, -1):
        h = human_text(rows[j])
        if h:
            start, request = j, h
            break
    calls, status, outputs, texts = [], {}, {}, []
    for d in rows[start:]:
        t = assistant_text(d)
        if t:
            texts.append((len(calls), t))
        if d.get("type") == "response_item":
            p = d.get("payload") or {}
            if p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                name = p.get("name") or ("local_shell" if p.get("type") == "local_shell_call" else "")
                args = p.get("arguments") or p.get("input") or p.get("action")
                calls.append({"id": p.get("call_id"), "name": name, "command": _command_of(name, args), "paths": _paths_of(args)})
            elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
                status[p.get("call_id")] = _codex_status(p.get("output"))
                outputs[p.get("call_id")] = _output_text(p.get("output"))
            continue
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if d.get("type") == "assistant" and b.get("type") == "tool_use":
                calls.append({"id": b.get("id"), "name": b.get("name"), "command": _command_of(b.get("name"), b.get("input")),
                              "paths": _paths_of(b.get("input"))})
            elif d.get("type") == "user" and b.get("type") == "tool_result":
                status[b.get("tool_use_id")] = "error" if b.get("is_error") else "ok"
                outputs[b.get("tool_use_id")] = _output_text(b.get("content"))
    for c in calls:
        c["status"] = status.get(c["id"], "pending")
        c["kind"] = "edit" if c["name"] in EDIT_TOOLS else "command" if c["name"] in COMMAND_TOOLS else "other"
    first_edit = next((i for i, c in enumerate(calls) if c["kind"] == "edit"), None)
    last_edit = max((i for i, c in enumerate(calls) if c["kind"] == "edit"), default=None)
    before_first_edit = [t[:MAX_MSG_CHARS] for n, t in texts if first_edit is None or n <= first_edit]
    commands = lambda cs: [{"command": c["command"][:300],  # noqa: E731
                            "result": observed_result(c["command"], c["status"], outputs.get(c["id"], ""), pipefail),
                            "output": outputs.get(c["id"], "")[-OUTPUT_TAIL:]} for c in cs if c["kind"] == "command"]
    return {
        "request": request,
        "messages_before_first_edit": before_first_edit,
        "final_message": texts[-1][1][:MAX_MSG_CHARS] if texts else "",
        "calls": calls,
        "edited": last_edit is not None,
        "commands_on_unfixed_code": commands(on_unfixed_code(calls)),
        "commands_after_last_edit": commands(calls[last_edit + 1:] if last_edit is not None else []),
    }


# --- git evidence ---

def _git(cwd, *args, env=None):
    r = subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=60, env=dict(os.environ, **(env or {})))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def _private_objects(cwd):
    """Git env that reads the repo's objects but writes new ones to our own store, never into the repo."""
    store = os.path.join(os.path.expanduser(os.environ.get("KARPATHY_JEV_HOME", "~/.karpathy-jev")), "objects")
    os.makedirs(store, exist_ok=True)
    repo_objects = os.path.join(_git(cwd, "rev-parse", "--absolute-git-dir").strip(), "objects")
    return {"GIT_OBJECT_DIRECTORY": store, "GIT_ALTERNATE_OBJECT_DIRECTORIES": repo_objects}


def snapshot(cwd):
    """Baseline for this turn: a tree of the working tree (tracked files) plus the untracked file list."""
    try:
        _git(cwd, "rev-parse", "--is-inside-work-tree")
    except Exception:
        return None
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    if not _git(cwd, "status", "--porcelain", "--untracked-files=no").strip():  # clean tree: HEAD is the baseline
        return {"base": _git(cwd, "rev-parse", "HEAD").strip(), "untracked": untracked}
    env = _private_objects(cwd)
    git_dir = os.path.dirname(env["GIT_ALTERNATE_OBJECT_DIRECTORIES"])
    fd, index = tempfile.mkstemp(dir=env["GIT_OBJECT_DIRECTORY"], prefix="index-")
    os.close(fd)
    try:
        if os.path.exists(os.path.join(git_dir, "index")):
            shutil.copyfile(os.path.join(git_dir, "index"), index)
        else:
            os.remove(index)
        env["GIT_INDEX_FILE"] = index
        _git(cwd, "add", "-u", env=env)
        base = _git(cwd, "write-tree", env=env).strip()
    finally:
        if os.path.exists(index):
            os.remove(index)
    return {"base": base, "untracked": untracked}


def parse_diff(text):
    hunks, file, cur = [], None, None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            m = re.search(r" b/(.+)$", line)
            file, cur = (m.group(1) if m else None), None
        elif line.startswith("@@") and file:
            cur = {"file": file, "header": line.split("@@")[1].strip() if line.count("@@") >= 2 else line, "diff": ""}
            hunks.append(cur)
        elif cur is not None and line[:1] in ("+", "-", " ") and not line.startswith(("+++", "---")):
            cur["diff"] += line + "\n"
    for h in hunks:
        if len(h["diff"]) > MAX_HUNK_CHARS:
            h["diff"] = h["diff"][:MAX_HUNK_CHARS] + "…[truncated]\n"
    return hunks


def turn_hunks(cwd, snap):
    """Hunks changed since the baseline, plus files created during the turn."""
    if not snap:
        snap = snapshot(cwd)
        if not snap or not snap.get("base"):
            return []
        # no baseline recorded: fall back to everything uncommitted
        text = _git(cwd, "diff", "HEAD")
        return parse_diff(text)
    hunks = parse_diff(_git(cwd, "diff", snap["base"], env=_private_objects(cwd))) if snap.get("base") else []
    now = _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    own = os.path.relpath(os.path.expanduser(os.environ.get("KARPATHY_JEV_HOME", "~/.karpathy-jev")), cwd)  # never count the hook's own files as changes
    for path in sorted(set(now) - set(snap.get("untracked") or [])):
        if not own.startswith("..") and (path == own or path.startswith(own.rstrip("/") + "/")):
            continue
        try:
            with open(os.path.join(cwd, path), encoding="utf-8") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        body = "".join(f"+{l}\n" for l in lines[:NEW_FILE_LINES])
        if len(lines) > NEW_FILE_LINES:
            body += f"+…[{len(lines) - NEW_FILE_LINES} more lines]\n"
        hunks.append({"file": path, "header": "new file", "diff": body[:MAX_HUNK_CHARS]})
    return hunks



# --- agent mode: observed runs instead of a transcript ---

def run_recorded(cmd, runs_path, changed=False):
    """Run a command, stream its output, and record the real exit code, the output's tail, a timestamp, and
    whether the turn had already changed files (a failing run before any change is a reproduction)."""
    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as err:  # e.g. ./runtests.py not found from this directory: an observed failure, not a crash
        tail, rc = str(err).encode(), 127
        sys.stderr.write(str(err) + "\n")
    else:
        tail = b""
        for chunk in iter(lambda: proc.stdout.read(4096), b""):
            sys.stdout.buffer.write(chunk)
            sys.stdout.flush()
            tail = (tail + chunk)[-4 * OUTPUT_TAIL:]
        rc = proc.wait()
    text = cmd if isinstance(cmd, str) else " ".join(cmd)
    output = tail.decode("utf-8", "replace")
    entry = {"ts": t0, "command": text, "changed": changed, "exit_code": rc,
             "result": observed_result(text, "ok" if rc == 0 else "error", output), "output": output[-OUTPUT_TAIL:]}
    os.makedirs(os.path.dirname(runs_path), exist_ok=True)
    with open(runs_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return rc


def runs_on_unfixed_code(runs_path):
    """Recorded runs made while the tree matched the turn's baseline (no change yet, or stashed)."""
    if not os.path.exists(runs_path):
        return []
    return [{"command": e["command"][:300], "result": e["result"], "output": e.get("output", "")}
            for e in (json.loads(l) for l in open(runs_path)) if not e.get("changed")]


def runs_after_last_edit(runs_path, cwd, hunks):
    """Recorded runs that started after the newest modification of any changed file."""
    mtimes = []
    for h in hunks:
        try:
            mtimes.append(os.path.getmtime(os.path.join(cwd, h["file"])))
        except OSError:
            pass
    last_edit = max(mtimes, default=0)
    out = []
    if os.path.exists(runs_path):
        for line in open(runs_path):
            e = json.loads(line)
            if e["ts"] > last_edit:
                out.append({"command": e["command"][:300], "result": e["result"], "output": e.get("output", "")})
    return out
