---
description: Check whether Ollama is installed, running, and has the context-capped model this plugin delegates to — build it if missing
argument-hint: "[base model tag to use, e.g. devstral:24b]"
allowed-tools: Bash(ollama:*), AskUserQuestion
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

Step 3 — Context-capped model present?

This plugin always delegates to a tag named `ollama-rescue-mechanical` — never to a raw pulled tag directly. Reason: most current local coding models default to a very large native context window (100K-256K+ tokens), and Ollama reserves KV-cache proportional to that context by default. On a consumer GPU this overflows VRAM and forces heavy CPU offload even for a short one-line completion, making every delegated call far slower than it needs to be. Capping the context via a derivative Modelfile fixes this.

Check:

```bash
ollama list
```

- If `ollama-rescue-mechanical` is already listed, skip to Step 4.
- If not present, use `AskUserQuestion` once to ask which base model to build it from. Offer these options (verified working on Ollama's library as of this writing — check `ollama.com/library` or `ollama search <name>` for anything newer before committing, this landscape moves fast):
  - **`devstral:24b`** (Mistral, ~14GB, dense — most predictable latency, tuned specifically for reading multi-file codebases and writing patches. Recommended default for pure mechanical tasks.)
  - **`qwen3.6:27b`** (Alibaba, ~17GB, vision-capable — use if delegated tasks sometimes reference an image or screenshot.)
  - A **custom tag** the user names (any model already pulled or pullable via `ollama pull`).
- If the argument `$ARGUMENTS` already names a base tag, skip the question and use that directly.
- Pull the chosen base tag if not already present: `ollama pull <base-tag>`.
- Build the derivative model:

```bash
cat > /tmp/ollama-rescue-mechanical.Modelfile <<'EOF'
FROM <base-tag>
PARAMETER num_ctx 32768
PARAMETER num_predict 4096
EOF
ollama create ollama-rescue-mechanical -f /tmp/ollama-rescue-mechanical.Modelfile
```

  32768 is a reasonable default for mechanical tasks (enough for a handful of files of context without ballooning memory). `num_predict` caps the OUTPUT length — without it, a hybrid-reasoning ("thinking") model can occasionally get stuck rambling in its reasoning trace and never converge on an answer, which looks exactly like a hang (confirmed in practice: a Qwen3.6-class model logged 1800+ decoded tokens and climbing, at under 4 tok/s, on a single never-completing request). Capping output length turns "may never finish" into "finishes or hard-stops in a few minutes." A user who wants different caps can rerun this step with different `PARAMETER` values.

Step 4 — Smoke test

Run against the HTTP API directly (this is also how `ollama-rescue` itself calls the model — see below for why):

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"ollama-rescue-mechanical","prompt":"Reply with exactly one word: ready","stream":false}' \
  | jq -r '.response'
```

- Any coherent non-empty response (including a reasoning preamble followed by real content, which some models emit) counts as working. An empty response or a hard error means something is wrong with the built model — rerun Step 3.
- If `curl`/`jq` aren't available, `ollama run ollama-rescue-mechanical "Reply with exactly one word: ready"` also works as a one-off manual check, but note that `ollama run` is an interactive-terminal tool and can leave ANSI/TTY control codes mixed into output on real tasks — the agent and skill in this plugin always use the API instead, never the CLI, to avoid that.

Step 5 — Report GPU/CPU offload

While the model is still warm (within ~5 minutes of the smoke test), run:

```bash
ollama ps
```

- Report the `PROCESSOR` column (e.g. `77%/23% GPU/CPU`) so the user knows how much of the model is GPU-resident. A model spilling heavily to CPU (well under 50% GPU) will feel slow — if so, mention that a smaller base model or a shorter `num_ctx` cap would help, or that the base model may simply be too large for the available VRAM.

Step 6 — Consolidated report

Summarize in one short block: install state, service state, `ollama-rescue-mechanical` present (and which base model it was built from), smoke-test result, and the GPU/CPU split from Step 5.
