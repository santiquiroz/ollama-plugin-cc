# Changelog

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
