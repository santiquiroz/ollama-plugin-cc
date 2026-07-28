---
name: ollama-rescue
description: Delegate a mechanical, zero-domain-context coding task to a local Ollama model in non-interactive mode — boilerplate, mechanical renames, dead code cleanup, simple CRUD/mapping specs, DTO-to-interface generation, PR descriptions for self-explanatory commits. Free, local, zero-quota. Do not use for domain logic, architecture decisions, or multi-step debugging.
---

Forward the requested task to a local Ollama model with one shell command. Do not do the task yourself once Ollama is invoked — return its output.

## Command

Call Ollama's HTTP API directly — NOT the `ollama run` CLI:

```bash
curl -s http://localhost:11434/api/generate \
  -d "$(jq -n --arg model "ollama-rescue-mechanical" --arg prompt "<task>" '{model:$model, prompt:$prompt, stream:false}')" \
  | jq -r '.response'
```

Building the JSON body with `jq -n` avoids breaking on quotes/newlines/backticks in the task text. `ollama run` is an interactive-terminal tool that can leave ANSI/TTY control codes mixed into stdout even when not attached to a real terminal (confirmed in practice: real output came back with escape codes woven through actual code, needing a cleanup pass) — the HTTP API returns clean JSON instead.

`ollama-rescue-mechanical` is a context-capped AND output-capped derivative model this plugin's setup builds via a small Modelfile (see `commands/setup.md` on the Claude Code side, or run the equivalent `ollama create` step manually — see the main README). Never call a raw pulled tag directly: most current coding models default to a huge native context window, and the resulting KV-cache overflows consumer VRAM, making the run far slower than it needs to be.

## Rules

- Preserve the user's task text verbatim in the prompt. Do not add commentary or hedging.
- **A task requiring correct reuse of a specific existing method/API signature is a bad fit unless that exact signature is pasted into the task text.** Confirmed in practice: asked to generate tests against an existing internal API, the model invented a plausible but nonexistent public method instead of the real private one it was never shown. Paste the real definitions inline for anything that touches existing code surface.
- Ollama's completion is pure text — it has no filesystem or git access and cannot execute anything on its own. There is no allow/deny flag set to configure, unlike an agentic CLI delegate; the only safety consideration is that you (Codex) must actually read and review the returned text before applying it, since it was never applied automatically.
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
- **"model not found"**: `ollama-rescue-mechanical` hasn't been built yet. Point at the setup steps in the main README.
- **Slow/heavy CPU offload**: the base model is too large for the available VRAM even with the context cap. Suggest a smaller base model.

Report the error text verbatim instead of retrying silently — the caller decides whether to fall back to another approach or take the task over directly.

## Output

Return Ollama's stdout as-is. Do not paraphrase or summarize it. Mention once that it should be reviewed before use — it's a smaller local model, not a frontier one.
