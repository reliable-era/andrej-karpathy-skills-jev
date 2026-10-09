import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, mock, test } from "node:test";

const home = mkdtempSync(join(tmpdir(), "jev-pi-adapter-test-"));
process.env.KARPATHY_JEV_HOME = home;
after(() => rmSync(home, { recursive: true, force: true }));
let calls = [], responses = [];
mock.module("node:child_process", { namedExports: { spawn(command, args, options) {
  assert.equal(command, "python3");
  assert.equal(args.at(-1), "hook");
  assert.equal(options.cwd, home);
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {};
  child.stdin = { end(text) {
    const payload = JSON.parse(text);
    calls.push(payload);
    const response = responses.shift() || { code: 0, stdout: "", stderr: "" };
    queueMicrotask(() => {
      child.stdout.emit("data", response.stdout || "");
      child.stderr.emit("data", response.stderr || "");
      child.emit("close", response.code);
    });
  } };
  return child;
} } });
const { default: adapter } = await import("../extensions/karpathy-jev.ts");
let serial = 0;
async function setup() {
  calls = []; responses = [];
  const handlers = {}, entries = [];
  const pi = { on(name, handler) { handlers[name] = handler; }, appendEntry(...args) { entries.push(args); } };
  adapter(pi);
  const sid = `case-${++serial}`;
  const ctx = { cwd: home, signal: undefined, sessionManager: { getSessionId: () => sid } };
  await handlers.session_start({}, ctx);
  await handlers.before_agent_start({ prompt: "Fix the unscored fixture" }, ctx);
  return { handlers, ctx, entries, sid };
}

test("turn start reaches the unchanged hook; sibling edits share one review", async () => {
  const { handlers: h, ctx } = await setup();
  await Promise.all(["edit", "write"].map((toolName, i) => h.tool_call({ toolName,
    toolCallId: `edit-${i}`, input: { path: "file.py" } }, ctx)));
  assert.deepEqual(calls.map(x => x.hook_event_name), ["UserPromptSubmit", "PreToolUse"]);
});

test("first-edit revise blocks sibling edits; subsequent retry can proceed", async () => {
  const { handlers: h, ctx } = await setup();
  responses = [{ code: 2, stderr: "Clarify the proposed change" }];
  const events = [0, 1].map(i => ({ toolName: "edit", toolCallId: `e-${i}`, input: { path: "file.py" } }));
  const results = await Promise.all(events.map(e => h.tool_call(e, ctx)));
  assert.ok(results.every(r => r.block));
  assert.equal(await h.tool_call({ ...events[0], toolCallId: "retry" }, ctx), undefined);
  assert.equal(calls.length, 2);
});

test("Bash gets the router's pipefail rewrite, not a narrated exit", async () => {
  const { handlers: h, ctx, sid } = await setup();
  responses = [{ code: 0, stdout: JSON.stringify({ hookSpecificOutput: {
    updatedInput: { command: "set -o pipefail; false | tail" } } }) }];
  const event = { toolName: "bash", toolCallId: "b", input: { command: "false | tail" } };
  await h.tool_call(event, ctx);
  assert.equal(event.input.command, "set -o pipefail; false | tail");
  await h.tool_result({ toolName: "bash", toolCallId: "b", content: [], isError: true,
    structuredContent: { exit_code: 1, output: "" } }, ctx);
  const rows = readFileSync(join(home, `pi-${sid}.jsonl`), "utf8").trim().split("\n").map(JSON.parse);
  assert.equal(rows.at(-1).structuredContent.exit_code, 1);
  assert.equal(rows.at(-1).message.content[0].is_error, true);
});

test("finish revise requests continuation and preserves other boundary entries", async () => {
  const { handlers: h, ctx } = await setup();
  responses = [{ code: 2, stderr: "Run a relevant behavioral test" }, { code: 0 }];
  const prior = { type: "custom", customType: "another-extension" };
  const event = { outcome: "completed", entries: [prior] };
  const result = await h.agent_before_settle(event, ctx);
  assert.equal(result.continue, true);
  assert.deepEqual(result.entries[0], prior);
  assert.match(result.entries[1].content, /behavioral test/);
  assert.equal(await h.agent_before_settle(event, ctx), undefined);
  assert.deepEqual(calls.filter(c => c.hook_event_name === "Stop").map(c => c.stop_hook_active), [false, true]);
});

test("at most two finish reviews even if both ask to revise", async () => {
  const { handlers: h, ctx } = await setup();
  responses = [{ code: 2, stderr: "Revise one" }, { code: 2, stderr: "Revise two" }];
  const event = { outcome: "completed", entries: [] };
  assert.equal((await h.agent_before_settle(event, ctx)).continue, true);
  assert.equal((await h.agent_before_settle(event, ctx)).continue, true);
  assert.equal(await h.agent_before_settle(event, ctx), undefined);
  assert.equal(calls.filter(c => c.hook_event_name === "Stop").length, 2);
});

test("aborted/error runs do not request finish judgments", async () => {
  const { handlers: h, ctx } = await setup();
  for (const outcome of ["aborted", "error"]) {
    assert.equal(await h.agent_before_settle({ outcome, entries: [] }, ctx), undefined);
  }
  assert.equal(calls.length, 1);
});
