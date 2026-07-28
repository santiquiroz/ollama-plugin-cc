# Changelog

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
