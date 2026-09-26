---
name: ollama-rescue
description: Delegate a mechanical, zero-domain-context coding task to a local Ollama model in non-interactive mode — boilerplate, mechanical renames, dead code cleanup, simple CRUD/mapping specs, DTO-to-interface generation, PR descriptions for self-explanatory commits. Free, local, zero-quota. Do not use for domain logic, architecture decisions, or multi-step debugging.
---

Forward the requested task to a local Ollama model with one shell command. Do not do the task yourself once Ollama is invoked — return its output.

Use the text mode below by default. The experimental agentic mode runs only
when the caller explicitly asks for it (for example with `--agentic`); a task
that needs to read or edit repository files does not switch modes on its own.

## Command

Call Ollama's HTTP API directly — NOT the `ollama run` CLI:

```bash
PROMPT=$(cat <<'OLLAMA_TASK_EOF'
<task>
OLLAMA_TASK_EOF
)
MODEL_FLAG=""
installed_tags() {
  curl -sS http://localhost:11434/api/tags | tr ',{' '\n\n' \
    | sed -n 's/^ *"name" *: *"\([^"]*\)".*/\1/p' | sed 's/:latest$//'
}
resolve_model() {
  [ -n "$1" ] && { printf '%s\n' "$1"; return 0; }
  local tags
  tags=$(installed_tags) || return
  grep -x -m1 -e ollama-rescue-mechanical <<<"$tags" \
    || grep -E -m1 -e '^[^:]+-(32k|mechanical)(:.*)?$' <<<"$tags" \
    || { echo "OLLAMA_ERROR: no context-capped model (ollama-rescue-mechanical or a *-32k/*-mechanical tag) is installed; run /ollama:setup" >&2; return 1; }
}
JQ_REPLY='. as $raw | ((try fromjson catch null) | if type == "object" then . else {} end) as $reply
| if $reply.error then "OLLAMA_ERROR: \($reply.error)\n" | halt_error(1)
  elif ($reply.response | type) == "string" then $reply.response
  else "OLLAMA_ERROR: unexpected reply: \($raw)\n" | halt_error(1) end'
PY_REPLY='
import json, sys
raw = sys.stdin.buffer.read().decode("utf-8", "replace")
try:
    reply = json.loads(raw)
except ValueError:
    reply = None
reply = reply if isinstance(reply, dict) else {}
if reply.get("error"):
    sys.exit("OLLAMA_ERROR: " + str(reply["error"]))
if not isinstance(reply.get("response"), str):
    sys.exit("OLLAMA_ERROR: unexpected reply: " + raw)
sys.stdout.buffer.write(reply["response"].encode("utf-8") + b"\n")
'
NODE_REPLY='
const raw = require("fs").readFileSync(0, "utf8");
let reply = null;
try { reply = JSON.parse(raw); } catch {}
if (!reply || typeof reply !== "object") reply = {};
if (reply.error) { console.error("OLLAMA_ERROR: " + reply.error); process.exitCode = 1; }
else if (typeof reply.response !== "string") { console.error("OLLAMA_ERROR: unexpected reply: " + raw); process.exitCode = 1; }
else process.stdout.write(reply.response + "\n");
'
json_tool() {
  for tool in jq python3 python node; do
    "$tool" --version >/dev/null 2>&1 && { echo "$tool"; return 0; }
  done
  echo "OLLAMA_ERROR: jq, python or node is required to call the Ollama API" >&2
  return 127
}
request_body() {
  case "$JSON_TOOL" in
    jq) jq -Rs --arg model "$MODEL" '{model: $model, prompt: ., stream: false}' ;;
    node) node -e 'process.stdout.write(JSON.stringify({model: process.argv[1], prompt: require("fs").readFileSync(0, "utf8"), stream: false}))' "$MODEL" ;;
    *) "$JSON_TOOL" -c 'import json, sys; sys.stdout.write(json.dumps({"model": sys.argv[1], "prompt": sys.stdin.buffer.read().decode("utf-8"), "stream": False}))' "$MODEL" ;;
  esac
}
response_text() {
  case "$JSON_TOOL" in
    jq) jq -Rrs "$JQ_REPLY" ;;
    node) node -e "$NODE_REPLY" ;;
    *) "$JSON_TOOL" -c "$PY_REPLY" ;;
  esac
}
set -o pipefail
JSON_TOOL=$(json_tool) && MODEL=$(resolve_model "$MODEL_FLAG") && printf '%s' "$PROMPT" | request_body \
  | curl -sS http://localhost:11434/api/generate --data-binary @- | response_text
```

Put the task text verbatim between the two `OLLAMA_TASK_EOF` lines, never inside double quotes: the quoted heredoc passes backticks, `$VAR`, `$(...)`, quotes and newlines through literally, while double quotes would let the shell execute or expand them. If the task contains a line that is exactly `OLLAMA_TASK_EOF`, pick another delimiter. The JSON body is built and the reply parsed with the first available of `jq`, `python3`/`python` and `node`, so `jq` is not required. With `set -o pipefail` and `curl -sS`, failures are never silent: a connection error prints curl's message, a `{"error": ...}` body prints `OLLAMA_ERROR: <message>`, an empty or non-JSON body prints `OLLAMA_ERROR: unexpected reply: <body>`, and all of them exit non-zero. `ollama run` is an interactive-terminal tool that can leave ANSI/TTY control codes mixed into stdout even when not attached to a real terminal (confirmed in practice: real output came back with escape codes woven through actual code, needing a cleanup pass) — the HTTP API returns clean JSON instead.

Both modes resolve the model with the same `resolve_model` function: a tag the caller passed with `--model` goes into `MODEL_FLAG=""` and is used as-is; otherwise `ollama-rescue-mechanical` if `GET /api/tags` lists it, wherever it appears; otherwise the first listed context-capped tag (a name ending in `-32k` or `-mechanical`, e.g. `devstral-32k`); otherwise the command stops with `OLLAMA_ERROR: no context-capped model ... run /ollama:setup` without calling the model. A raw pulled tag such as `devstral:24b` is never picked automatically, and preferring `ollama-rescue-mechanical` keeps every session on one loaded model.

`ollama-rescue-mechanical` is a context-capped AND output-capped derivative model this plugin's setup builds via a small Modelfile (see `commands/setup.md` on the Claude Code side, or run the equivalent `ollama create` step manually — see the main README). Never call a raw pulled tag directly: most current coding models default to a huge native context window, and the resulting KV-cache overflows consumer VRAM, making the run far slower than it needs to be.

## Rules

- Preserve the user's task text verbatim in the prompt. Do not add commentary or hedging.
- **A task requiring correct reuse of a specific existing method/API signature is a bad fit unless that exact signature is pasted into the task text.** Confirmed in practice: asked to generate tests against an existing internal API, the model invented a plausible but nonexistent public method instead of the real private one it was never shown. Paste the real definitions inline for anything that touches existing code surface.
- In text mode, Ollama's completion is pure text — it has no filesystem or git access and cannot execute anything on its own. There is no allow/deny flag set to configure, unlike an agentic CLI delegate; the only safety consideration is that you (Codex) must actually read and review the returned text before applying it, since it was never applied automatically. Agentic mode is the exception: its child edits files itself (see below).
- Run the command synchronously — wait for it to finish, don't background it. Use a generous timeout (10+ minutes) for anything beyond a one-line snippet: sustained generation on modest consumer hardware has been observed under 5 tok/s, so a real task can genuinely take several minutes. A short timeout killing the call isn't evidence of a hang.
- Some models emit a reasoning preamble before the real answer, even via the API. Return the full output as-is; don't strip it yourself.
- Do not inspect the repo, grep, or do follow-up work beyond the one forwarded call — Ollama does the completion, you relay its output.

## Known issues to work around

- **Native-context VRAM blowup**: a raw pulled tag (not the `-mechanical` derivative) can default to a 100K-256K+ token context, which reserves KV-cache far larger than the model's own weights and forces most of the model onto slow CPU inference. Always use the context-capped tag.
- **Runaway reasoning trace**: hybrid-thinking models can occasionally never converge on an answer — confirmed in practice with 1800+ decoded tokens and climbing on one request. This looks exactly like a hang. The `-mechanical` tag also caps `num_predict` so a stuck generation hard-stops instead of running for hours; if it's still slow, prefer a non-reasoning base model.
- **Terminal control codes in output**: using `ollama run` instead of the HTTP API can corrupt returned code with ANSI escape sequences. Always use the API, as shown above.
- **API hallucination on existing code surface**: a small model asked to use a specific existing API it wasn't shown will sometimes invent a plausible-looking one instead. Paste real signatures inline; verify referenced symbols actually exist before accepting the output.
- **Cold start**: Ollama unloads an idle model after ~5 minutes by default (`OLLAMA_KEEP_ALIVE`). The first call after a gap reloads it (a few seconds to ~1 minute depending on size); calls within the window are instant.

## Availability / failure handling

There is no quota to exhaust — Ollama is local and free. If the command fails, it's one of:

- **Connection refused**: the Ollama background service isn't running. Tell the user to start it, or run the setup steps in the main README.
- **`OLLAMA_ERROR: no context-capped model`**: neither `ollama-rescue-mechanical` nor any `-32k`/`-mechanical` tag is installed; nothing was sent to the model. Point at `/ollama:setup` or the setup steps in the main README.
- **"model not found"**: the tag passed with `--model` hasn't been built yet. Point at the setup steps in the main README.
- **`OLLAMA_ERROR: jq, python or node is required`**: none of the JSON tools is on `PATH`; nothing was sent. Install one of them.
- **Slow/heavy CPU offload**: the base model is too large for the available VRAM even with the context cap. Suggest a smaller base model.

Report the error text verbatim instead of retrying silently — the caller decides whether to fall back to another approach or take the task over directly.

## Agentic mode

Experimental and opt-in: run this only when the caller explicitly asks for
agentic mode (for example with `--agentic`), never just because the task
needs repository reads/edits. Measured 2026-09-10 (Ollama 0.33.3):
`devstral-32k` and `qwen3.6-32k` answered with a greeting or a question
instead of calling tools in 4/4 runs, so real file edits are better served by
a bigger model or a frontier lane. When asked, run it from the current
repository directory in one foreground shell call (never background it) with
a timeout of at least `600000` ms:

```bash
CLAUDE_BIN=$(command -v claude 2>/dev/null || ls "$HOME/.local/bin/claude.exe" "$HOME/.local/bin/claude" 2>/dev/null | head -1)
[ -n "$CLAUDE_BIN" ] || { echo "claude CLI not found"; exit 127; }
PROMPT=$(cat <<'OLLAMA_TASK_EOF'
<task text>
OLLAMA_TASK_EOF
)
MODEL_FLAG=""
installed_tags() {
  curl -sS http://localhost:11434/api/tags | tr ',{' '\n\n' \
    | sed -n 's/^ *"name" *: *"\([^"]*\)".*/\1/p' | sed 's/:latest$//'
}
resolve_model() {
  [ -n "$1" ] && { printf '%s\n' "$1"; return 0; }
  local tags
  tags=$(installed_tags) || return
  grep -x -m1 -e ollama-rescue-mechanical <<<"$tags" \
    || grep -E -m1 -e '^[^:]+-(32k|mechanical)(:.*)?$' <<<"$tags" \
    || { echo "OLLAMA_ERROR: no context-capped model (ollama-rescue-mechanical or a *-32k/*-mechanical tag) is installed; run /ollama:setup" >&2; return 1; }
}
set -o pipefail
MODEL=$(resolve_model "$MODEL_FLAG") || exit 1
ISO=$(mktemp -d "${TMPDIR:-/tmp}/ollama-rescue-cfg.XXXXXX") || exit 1
trap 'rm -rf "$ISO"' EXIT
CLAUDE_CONFIG_DIR="$ISO" ANTHROPIC_BASE_URL=http://127.0.0.1:11434 ANTHROPIC_API_KEY=ollama ANTHROPIC_AUTH_TOKEN=ollama "$CLAUDE_BIN" -p "$PROMPT" --model "$MODEL" --permission-mode acceptEdits --disallowedTools "Task,Agent,WebSearch,WebFetch" --max-turns 40 --output-format text
```

The task text is positional and goes through the same quoted heredoc as text
mode, never inside double quotes (edits are auto-accepted, so an expanded
backtick or `$(...)` would run commands); stdin is not read. The model comes
from the same `resolve_model` as text mode (set `MODEL_FLAG` for `--model`).
`CLAUDE_CONFIG_DIR` points at an empty temporary directory so the child loads
no global `CLAUDE.md`, hooks or plugins (a SessionStart hook was observed
hijacking the small model's first answer) and needs no Anthropic login; the
`trap` deletes it on exit. `command -v claude` can fail in Git Bash when
`~/.local/bin` is not on `PATH`, hence the fallback. `--disallowedTools
Task,Agent` is mandatory: the child must not delegate recursively, and the
project's own `CLAUDE.md` (which still loads) may tell it to.
Edits are auto-accepted, so review `git diff`; this is MEDIUM-LOW trust from a
small local model. A mid-run kill is a false negative. Preflight
`POST http://127.0.0.1:11434/v1/messages` first: HTTP 200 means Ollama
>= 0.33 and agentic mode is available; HTTP 404 means fall back to text mode.

## Output

Return Ollama's stdout as-is. Do not paraphrase or summarize it. Mention once that it should be reviewed before use — it's a smaller local model, not a frontier one.
