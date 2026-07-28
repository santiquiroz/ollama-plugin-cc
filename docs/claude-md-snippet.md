# CLAUDE.md snippet

Paste the block below into your `~/.claude/CLAUDE.md` (or a project
`CLAUDE.md`) to make Claude Code delegate mechanical work to this plugin
proactively, before reaching for a paid delegate. If you also run a paid
mechanical delegate (e.g. the
[copilot-plugin-cc](https://github.com/santiquiroz/copilot-plugin-cc) plugin)
and/or a reasoning-capable delegate (e.g. Codex), see
[docs/delegation-guide.md](delegation-guide.md) for the full multi-lane split
— this snippet only covers the Ollama lane. No other delegate at all? Skip to
the [Ollama-only variant](#ollama-only-no-other-delegate) below.

```markdown
# Ollama delegation (ollama plugin)

Mandatory, no user prompt needed: before writing code, decide explicitly —
Ollama (mechanical, free, try first), a paid delegate (mechanical fallback),
a reasoning delegate, or inline. Inline only for the never-delegate list
below or trivial edits (<5 lines, 1 file) where coordinating delegation costs
more than doing it.

Ollama owns the cheapest tier of pure-mechanical, zero-domain-context work.
Delegate proactively, before any paid delegate:

| Trigger | Action |
|---|---|
| Creating/updating simple test specs (CRUD/mapping, no branching logic) | `ollama:ollama-rescue` subagent, background |
| Mechanical rename across 3+ files | `ollama:ollama-rescue` subagent, background |
| Dead code removal / unused imports / debug-statement cleanup | `ollama:ollama-rescue` subagent, background |
| Generating interfaces from DTOs/entities (pure field mapping) | `ollama:ollama-rescue` subagent, background |
| Component boilerplate shells (imports, constructor, lifecycle) | `ollama:ollama-rescue` subagent, background |
| Applying an identical config block to N similar files | `ollama:ollama-rescue` subagent, background |
| PR description when commits are self-explanatory | `ollama:ollama-rescue` subagent, background |

Never delegate: domain logic, business rules, architecture decisions, complex
refactors requiring full codebase context, any task where the WHY lives in
this conversation.

Rules:
- Ollama's output is never applied automatically — it's a plain text
  completion, not an agentic diff. Read and review it before applying via
  Edit/Write, more critically than you would a paid delegate's result.
- Launch delegations in the background and keep working — never idle waiting.
- WIP cap: 3-5 concurrent delegations. Kill-switch: 3 failed iterations on
  the same task → stop retrying, bring it inline (or hand to a paid delegate
  if one is configured).
- Availability fallback: Ollama's service isn't running, the model isn't
  built yet, or its output was visibly wrong → fall back to a paid delegate
  if configured, otherwise do the task inline. There's no quota here, only
  availability — don't loop retrying a failing lane.
- Two sessions delegating to Ollama at once queue behind each other rather
  than failing — keep them on the same default model (`ollama-rescue-mechanical`)
  to avoid VRAM contention from loading multiple different models at once.
```

## Ollama-only (no other delegate)

If this plugin is your only delegate, fold everything Ollama can't take
(reasoning-shaped work, or anything Ollama got wrong) back into "keep inline."
Use this variant instead:

```markdown
# Ollama delegation (ollama plugin)

Ollama is the only delegate here. Before writing code, decide: Ollama
(mechanical) or inline (everything else — including build-fixing, multi-file
refactors, and anything needing real reasoning, since there's no other
delegate to hand those to). Inline only for the never-delegate list below or
trivial edits (<5 lines, 1 file) where coordinating delegation costs more
than doing it.

Ollama owns pure-mechanical, zero-domain-context work. Delegate proactively:

| Trigger | Action |
|---|---|
| Creating/updating simple test specs (CRUD/mapping, no branching logic) | `ollama:ollama-rescue` subagent, background |
| Mechanical rename across 3+ files | `ollama:ollama-rescue` subagent, background |
| Dead code removal / unused imports / debug-statement cleanup | `ollama:ollama-rescue` subagent, background |
| Generating interfaces from DTOs/entities (pure field mapping) | `ollama:ollama-rescue` subagent, background |
| Component boilerplate shells (imports, constructor, lifecycle) | `ollama:ollama-rescue` subagent, background |
| Applying an identical config block to N similar files | `ollama:ollama-rescue` subagent, background |
| PR description when commits are self-explanatory | `ollama:ollama-rescue` subagent, background |

Never delegate (stays inline — no other lane to fall back to): domain logic,
business rules, architecture decisions, complex refactors requiring full
codebase context, build/type errors needing multi-step diagnosis, anything
where the WHY lives in this conversation.

Rules:
- Ollama's output is never applied automatically — read and review it before
  applying via Edit/Write.
- Launch delegations in the background and keep working — never idle waiting.
- WIP cap: 3-5 concurrent delegations. Kill-switch: 3 failed iterations on
  the same task → stop retrying, bring it inline.
- Availability fallback: Ollama unavailable or visibly wrong → do the task
  inline and say so once. There's no quota here, only availability.
```

If you later add a paid or reasoning delegate, switch to the multi-lane block
above and change the fallback rule back to failing over between lanes instead
of dropping straight to inline.
