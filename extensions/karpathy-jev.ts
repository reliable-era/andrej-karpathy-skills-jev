import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { spawn } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Explicitly load only in the Jev arm. Feed the unchanged Claude-hook router
// an observed-event journal; never ask the agent to fabricate its own evidence.
export default function (pi: ExtensionAPI) {
  const router = resolve(dirname(fileURLToPath(import.meta.url)), "../skills/karpathy-jev/scripts/router.py");
  let sid = "";
  let journal = "";
  let reviews = 0;
  let firstEdit: Promise<{ code: number; stdout: string; stderr: string }> | undefined;

  function record(type: string, content: unknown[], extra = {}) {
    appendFileSync(journal, JSON.stringify({ type, message: { content }, ...extra }) + "\n", { mode: 0o600 });
  }

  function hook(ctx: ExtensionContext, event: string, fields = {}) {
    return new Promise<{ code: number; stdout: string; stderr: string }>((accept, reject) => {
      const child = spawn("python3", [router, "hook"], { cwd: ctx.cwd, signal: ctx.signal });
      let stdout = "", stderr = "";
      const timer = setTimeout(() => child.kill("SIGTERM"), 30000);
      child.stdout.on("data", (part) => { stdout += part; });
      child.stderr.on("data", (part) => { stderr += part; });
      child.on("error", (error) => { clearTimeout(timer); reject(error); });
      child.on("close", (code) => {
        clearTimeout(timer);
        if (code === null) { reject(new Error("Jev hook terminated without an exit receipt")); return; }
        pi.appendEntry("karpathy-jev-hook", { event, code, stdout, stderr });
        accept({ code, stdout, stderr });
      });
      child.stdin.end(JSON.stringify({ hook_event_name: event, session_id: sid,
        cwd: ctx.cwd, transcript_path: journal, ...fields }));
    });
  }

  pi.on("session_start", async (_event, ctx) => {
    sid = ctx.sessionManager.getSessionId();
    const home = process.env.KARPATHY_JEV_HOME || join(homedir(), ".karpathy-jev");
    mkdirSync(home, { recursive: true, mode: 0o700 });
    journal = join(home, `pi-${sid}.jsonl`);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    firstEdit = undefined;
    reviews = 0;
    record("user", [{ type: "text", text: event.prompt }]);
    await hook(ctx, "UserPromptSubmit", { prompt: event.prompt });
  });

  pi.on("message_end", async (event) => {
    if (event.message.role !== "assistant") return;
    record("assistant", event.message.content.filter((part) => part.type === "text"));
  });

  pi.on("tool_call", async (event, ctx) => {
    const names: Record<string, string> = { edit: "Edit", write: "Write", bash: "Bash" };
    const name = names[event.toolName] || event.toolName;
    if (name === "Bash") {
      const response = await hook(ctx, "PreToolUse", { tool_name: name, tool_input: event.input });
      if (response.stdout.trim()) {
        const updated = JSON.parse(response.stdout).hookSpecificOutput?.updatedInput;
        if (updated) Object.assign(event.input, updated);
      }
    } else if (name === "Edit" || name === "Write") {
      // All sibling edits await the same first judgment; no duplicate request race.
      firstEdit ??= hook(ctx, "PreToolUse", { tool_name: name, tool_input: event.input });
      const response = await firstEdit;
      if (response.code === 2) {
        firstEdit = Promise.resolve({ code: 0, stdout: "", stderr: "" });
        return { block: true, reason: response.stderr };
      }
      if (response.code !== 0) throw new Error(`Jev first-edit hook exit ${response.code}`);
    }
    record("assistant", [{ type: "tool_use", id: event.toolCallId, name, input: event.input }]);
  });

  pi.on("tool_result", async (event) => {
    record("user", [{ type: "tool_result", tool_use_id: event.toolCallId,
      content: event.content, is_error: event.isError }], { structuredContent: event.structuredContent });
  });

  pi.on("agent_before_settle", async (event, ctx) => {
    if (event.outcome !== "completed" || reviews >= 2) return;
    const response = await hook(ctx, "Stop", { stop_hook_active: reviews > 0 });
    reviews++;
    if (response.code === 2) return {
      entries: [...event.entries, { type: "custom_message" as const, customType: "karpathy-jev-review",
        content: response.stderr, display: true }],
      continue: true,
    };
    if (response.code !== 0) throw new Error(`Jev finish hook exit ${response.code}`);
  });
}
