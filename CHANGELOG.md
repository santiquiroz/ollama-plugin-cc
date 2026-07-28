# Changelog

## 0.1.2 — 2026-07-28

Found while running a real (non-trivial) delegated task, not just simple fire tests:

- Fix: `ollama-rescue` (agent + skill + setup smoke test) now calls Ollama's
  HTTP API (`curl .../api/generate`) directly instead of the `ollama run`
  CLI. `ollama run` is an interactive-terminal tool and left ANSI/TTY escape
  codes mixed into real code output, requiring a manual cleanup pass before
  it was usable — the API returns clean JSON with none of that.
- Docs: added explicit throughput expectations — sustained generation for a
  real task has been observed well under 5 tok/s on modest consumer
  hardware, so a full file can genuinely take several minutes. Recommend a
  10+ minute timeout for anything beyond a one-line snippet; a short
  timeout killing the call is a false negative, not evidence of a hang.
- Docs: added a new selection-guidance warning — a task requiring correct
  reuse of a *specific* existing method/API is a bad fit unless that exact
  signature is pasted into the task text. Confirmed in practice: asked to
  generate tests against an existing internal API, the model invented a
  plausible-looking but nonexistent public method instead of the real
  private one it was never shown. The safety-model section now also tells
  callers to verify referenced symbols actually exist before applying output.

## 0.1.1 — 2026-07-28

- Fix: `/ollama:setup` now also caps `PARAMETER num_predict 4096` on the
  `-mechanical` derivative model, not just `num_ctx`. Without an output cap,
  a hybrid-reasoning ("thinking") model can occasionally never converge on
  an answer — confirmed in practice with a Qwen3.6-class model logging
  1800+ decoded tokens and climbing, at under 4 tok/s, on a single request
  that never completed. This looked exactly like a hang and could run for
  hours; now a stuck generation hard-stops in a few minutes instead.
- Docs updated (README, README.es, agent, skill) to recommend a
  non-reasoning base model (e.g. `devstral:24b`) for agentic/tool-calling
  use specifically, since the reasoning trace is what tends to run away.

## 0.1.0 — 2026-07-27

Initial release.

- `ollama-rescue` subagent: thin forwarder to a local Ollama model. No
  allow/deny flags needed — `ollama run` has no filesystem or git access,
  unlike an agentic CLI delegate.
- `/ollama:rescue` command: delegate a mechanical task from any session.
- `/ollama:setup` command: verify Ollama is installed and running, and build
  the context-capped `ollama-rescue-mechanical` model from a base model of
  your choice.
- Codex CLI support: `ollama-rescue` ships as a Codex skill
  (`skills/ollama-rescue/SKILL.md`) with a `.codex-plugin/plugin.json`
  manifest for native `codex plugin marketplace add` install (experimental),
  plus a manual-copy install path and an `AGENTS.md` delegation snippet
  (`docs/agents-md-snippet.md`).
- Delegation guide covering the Ollama / paid-delegate / reasoning-delegate
  split, concurrency on one GPU, and the availability fallback chain, plus a
  ready-to-paste `CLAUDE.md` snippet with an Ollama-only variant.
