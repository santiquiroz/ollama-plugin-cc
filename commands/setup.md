---
description: Check whether Ollama is installed, running, and has the context-capped model this plugin delegates to — build it if missing
argument-hint: "[base model tag to use, e.g. devstral:24b]"
allowed-tools: Bash(ollama:*), Bash(curl:*), Bash(cat:*), Bash(jq --version:*), Bash(python3 --version:*), Bash(python --version:*), Bash(node --version:*), AskUserQuestion
---

Run these checks in order and report a single consolidated status at the end.

Step 1 — Installed?

Run:

```bash
ollama --version
```

- If the command is not found: report the install docs (https://ollama.com/download) for the user's OS and stop.

Step 2 — Service reachable?

Run:

```bash
ollama list
```

- If this errors with a connection failure (not just "no models"), the Ollama background service isn't running. Tell the user to start it (the Ollama desktop app starts it automatically on Windows/macOS; on Linux, `systemctl start ollama` or `ollama serve` in a separate terminal) and stop here.

Step 2.2 — JSON tool for text mode

The agent and skill build the request and parse Ollama's reply with the first
tool they find among `jq`, `python3`/`python` and `node`. Run (each probe is
spelled out so it matches this command's `allowed-tools`):

```bash
if jq --version >/dev/null 2>&1; then echo "JSON tool: jq"
elif python3 --version >/dev/null 2>&1; then echo "JSON tool: python3"
elif python --version >/dev/null 2>&1; then echo "JSON tool: python"
elif node --version >/dev/null 2>&1; then echo "JSON tool: node"
else echo "JSON tool: none"
fi
```

- Report the tool it printed. `jq` is not required: Python or Node is enough.
- If it prints `none`, text mode cannot run on this machine; tell the user to install any one of jq, Python or Node, and continue with the remaining checks.

Step 2.5 — Ollama server version

Agentic mode needs Ollama's Anthropic Messages API, which ships in Ollama 0.33.
Ask the running server for its version (this needs no model, and unlike
`ollama --version` it reports the server, not the CLI):

```bash
VERSION_JSON=$(curl -sS --max-time 10 http://127.0.0.1:11434/api/version)
version_re='"version" *: *"(([0-9]+)\.([0-9]+)[^"]*)"'
if [[ ! $VERSION_JSON =~ $version_re ]]; then
  echo "Ollama server version: unknown (reply: ${VERSION_JSON:-none})"
elif [ "${BASH_REMATCH[2]}" -gt 0 ] || [ "${BASH_REMATCH[3]}" -ge 33 ]; then
  echo "Ollama server version: ${BASH_REMATCH[1]} (>= 0.33, Anthropic API supported)"
else
  echo "Ollama server version: ${BASH_REMATCH[1]} (older than 0.33, text mode only)"
fi
```

- `older than 0.33`: report `Anthropic API: no (Ollama <version> is older
  than 0.33)`, tell the user to update Ollama for agentic mode, and skip
  Step 3.5. Text mode still works.
- `unknown`: report the reply verbatim and treat agentic mode as unavailable.

Step 3 — Context-capped model present?

This plugin delegates to a tag named `ollama-rescue-mechanical` (falling back to another tag ending in `-32k` or `-mechanical` only when that one is missing) — never to a raw pulled tag directly. Reason: most current local coding models default to a very large native context window (100K-256K+ tokens), and Ollama reserves KV-cache proportional to that context by default. On a consumer GPU this overflows VRAM and forces heavy CPU offload even for a short one-line completion, making every delegated call far slower than it needs to be. Capping the context via a derivative Modelfile fixes this.

Check:

```bash
ollama list
```

- If `ollama-rescue-mechanical` is already listed, skip to Step 3.5.
- If not present, use `AskUserQuestion` once to ask which base model to build it from. Offer these options (verified working on Ollama's library as of this writing — check `ollama.com/library` or `ollama search <name>` for anything newer before committing, this landscape moves fast):
  - **`devstral:24b`** (Mistral, ~14GB, dense — most predictable latency, tuned specifically for reading multi-file codebases and writing patches. Recommended default for pure mechanical tasks.)
  - **`qwen3.6:27b`** (Alibaba, ~17GB, vision-capable — use if delegated tasks sometimes reference an image or screenshot.)
  - A **custom tag** the user names (any model already pulled or pullable via `ollama pull`).
- If the argument `$ARGUMENTS` already names a base tag, skip the question and use that directly.
- Pull the chosen base tag if not already present: `ollama pull <base-tag>`.
- Build the derivative model (the Modelfile goes to `$TMPDIR`, falling back
  to `/tmp`; the file is overwritten on every run, so nothing piles up):

```bash
MODELFILE="${TMPDIR:-/tmp}/ollama-rescue-mechanical.Modelfile"
cat > "$MODELFILE" <<'EOF'
FROM <base-tag>
PARAMETER num_ctx 32768
PARAMETER num_predict 4096
EOF
ollama create ollama-rescue-mechanical -f "$MODELFILE"
```

  32768 is a reasonable default for mechanical tasks (enough for a handful of files of context without ballooning memory). `num_predict` caps the OUTPUT length — without it, a hybrid-reasoning ("thinking") model can occasionally get stuck rambling in its reasoning trace and never converge on an answer, which looks exactly like a hang (confirmed in practice: a Qwen3.6-class model logged 1800+ decoded tokens and climbing, at under 4 tok/s, on a single never-completing request). Capping output length turns "may never finish" into "finishes or hard-stops in a few minutes." A user who wants different caps can rerun this step with different `PARAMETER` values.

Step 3.5 — Anthropic API probe

Skip this step when Step 2.5 reported a server older than 0.33. Otherwise,
now that the tag exists, probe the Anthropic Messages API with it:

```bash
REPLY=$(curl -sS --max-time 300 -w '\n%{http_code}' -X POST http://127.0.0.1:11434/v1/messages \
  -H 'content-type: application/json' \
  -d '{"model":"ollama-rescue-mechanical","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}')
BODY=${REPLY%$'\n'*}
CODE=${REPLY##*$'\n'}
if [ "$CODE" = 200 ]; then
  echo "Anthropic API: sí (agentic mode available)"
elif [ "$CODE" = 404 ]; then
  echo "Anthropic API: model not found (ollama-rescue-mechanical is missing, rerun Step 3): $BODY"
else
  echo "Anthropic API: unexpected HTTP ${CODE:-none}: $BODY"
fi
```

- Because Step 2.5 already confirmed the server is 0.33 or newer, a 404 here
  means the model is missing, not that Ollama is too old; do not report it as
  an old Ollama.
- Agentic mode only ever runs context-capped derivative tags such as
  `ollama-rescue-mechanical`, `devstral-32k` or `qwen3.6-32k`; never an
  uncapped raw tag.

Step 4 — Smoke test

Run against the HTTP API directly (this is also how `ollama-rescue` itself calls the model — see below for why):

```bash
curl -sS http://localhost:11434/api/generate \
  -d '{"model":"ollama-rescue-mechanical","prompt":"Reply with exactly one word: ready","stream":false}'
```

- The reply is one JSON object, printed raw so this check needs no JSON tool. A coherent non-empty `response` field (including a reasoning preamble followed by real content, which some models emit) counts as working. An `error` field (e.g. `model ... not found`), an empty `response` or a curl error means something is wrong with the built model or the service — report the text verbatim and rerun Step 3.
- If `curl` isn't available, `ollama run ollama-rescue-mechanical "Reply with exactly one word: ready"` also works as a one-off manual check, but note that `ollama run` is an interactive-terminal tool and can leave ANSI/TTY control codes mixed into output on real tasks — the agent and skill in this plugin always use the API instead, never the CLI, to avoid that.

Step 5 — Report GPU/CPU offload

While the model is still warm (within ~5 minutes of the smoke test), run:

```bash
ollama ps
```

- Report the `PROCESSOR` column (e.g. `77%/23% GPU/CPU`) so the user knows how much of the model is GPU-resident. A model spilling heavily to CPU (well under 50% GPU) will feel slow — if so, mention that a smaller base model or a shorter `num_ctx` cap would help, or that the base model may simply be too large for the available VRAM.

Step 6 — Consolidated report

Summarize in one short block: install state, service state, JSON tool from
Step 2.2 (or `none`), Ollama server version from Step 2.5, Anthropic API
from Step 3.5 — keep the three cases apart: `sí`, `no (Ollama <version> is
older than 0.33)` or `model not found` —, whether agentic mode is available,
`ollama-rescue-mechanical` present (and which base model it was built from),
smoke-test result, and the GPU/CPU split from Step 5.
