# AGENTS.md snippet (Codex)

Paste into your repo's `AGENTS.md` (or `~/.codex/AGENTS.md` for a global default) to make Codex delegate mechanical work to a local Ollama model proactively, via the `ollama-rescue` skill from this plugin.

```markdown
# Ollama delegation (ollama-rescue skill)

Ollama owns the cheapest tier of pure-mechanical, zero-domain-context work —
free, local, no quota. Use the `ollama-rescue` skill proactively — no user
prompt needed — for:

- Simple test specs (CRUD/mapping, no branching logic)
- Mechanical renames across 3+ files
- Dead code removal / unused imports / debug-statement cleanup
- Interface generation from DTOs/entities (pure field mapping)
- Component boilerplate shells
- Identical config blocks applied to N similar files
- PR descriptions when commits are self-explanatory

Never delegate: domain logic, business rules, architecture decisions, complex
refactors requiring full codebase context, anything where the WHY lives in
this conversation.

Ollama's output is a plain text completion, never applied automatically —
read and review it before using it, more critically than a paid delegate's
result. On a connection-refused or "model not found" error, the local Ollama
service isn't running or the model hasn't been set up yet — don't retry
blindly, point at the plugin's setup steps instead.
```

Requires Ollama installed and running locally (`ollama --version`, `ollama list`) with the `ollama-rescue-mechanical` model built. See the main [README](../README.md) for setup steps.
