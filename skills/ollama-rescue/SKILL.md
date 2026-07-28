---
name: ollama-rescue
description: Delegate a mechanical, zero-domain-context coding task to a local Ollama model in non-interactive mode — boilerplate, mechanical renames, dead code cleanup, simple CRUD/mapping specs, DTO-to-interface generation, PR descriptions for self-explanatory commits. Free, local, zero-quota. Do not use for domain logic, architecture decisions, or multi-step debugging.
---

Forward the requested task to a local Ollama model with one shell command. Do not do the task yourself once Ollama is invoked — return its output.

## Command

```
ollama run ollama-rescue-mechanical "<task>"
```

`ollama-rescue-mechanical` is a context-capped derivative model this plugin's setup builds via a small Modelfile (see `commands/setup.md` on the Claude Code side, or run the equivalent `ollama create` step manually — see the main README). Never call a raw pulled tag directly: most current coding models default to a huge native context window, and the resulting KV-cache overflows consumer VRAM, making the run far slower than it needs to be.

## Rules

- Preserve the user's task text verbatim in the prompt. Do not add commentary or hedging.
- Ollama's `run` mode is pure text completion — it has no filesystem or git access and cannot execute anything on its own. There is no allow/deny flag set to configure, unlike an agentic CLI delegate; the only safety consideration is that you (Codex) must actually read and review the returned text before applying it, since it was never applied automatically.
- Run the command synchronously — wait for it to finish, don't background it.
- Some models emit a `Thinking...` preamble before the real answer. Return the full output as-is; don't strip it yourself.
- Do not inspect the repo, grep, or do follow-up work beyond the one forwarded command — Ollama does the completion, you relay its output.

## Known issues to work around

- **Native-context VRAM blowup**: a raw pulled tag (not the `-mechanical` derivative) can default to a 100K-256K+ token context, which reserves KV-cache far larger than the model's own weights and forces most of the model onto slow CPU inference. Always use the context-capped tag.
- **Runaway reasoning trace**: hybrid-thinking models can occasionally never converge on an answer — confirmed in practice with 1800+ decoded tokens and climbing on one request. This looks exactly like a hang. The `-mechanical` tag also caps `num_predict` so a stuck generation hard-stops instead of running for hours; if it's still slow, prefer a non-reasoning base model.
- **Cold start**: Ollama unloads an idle model after ~5 minutes by default (`OLLAMA_KEEP_ALIVE`). The first call after a gap reloads it (a few seconds to ~1 minute depending on size); calls within the window are instant.

## Availability / failure handling

There is no quota to exhaust — Ollama is local and free. If the command fails, it's one of:

- **Connection refused**: the Ollama background service isn't running. Tell the user to start it, or run the setup steps in the main README.
- **"model not found"**: `ollama-rescue-mechanical` hasn't been built yet. Point at the setup steps in the main README.
- **Slow/heavy CPU offload**: the base model is too large for the available VRAM even with the context cap. Suggest a smaller base model.

Report the error text verbatim instead of retrying silently — the caller decides whether to fall back to another approach or take the task over directly.

## Output

Return Ollama's stdout as-is. Do not paraphrase or summarize it. Mention once that it should be reviewed before use — it's a smaller local model, not a frontier one.
