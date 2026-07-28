# Multi-Agent Delegation Guide

How to make Claude Code delegate work to a local Ollama model (this plugin) —
the cheapest possible lane, since it's free and runs on your own hardware —
and, optionally, to a paid mechanical delegate (e.g. the
[copilot-plugin-cc](https://github.com/santiquiroz/copilot-plugin-cc) plugin's
`copilot-rescue`) and a reasoning-capable delegate (e.g. Codex's
`codex-rescue`), so the main Claude thread stays focused on the work only it
can do.

## Which setup do you have?

This guide describes the full lane stack: Claude Code orchestrates, Ollama
(this plugin) takes the cheapest mechanical work, a paid mechanical delegate
picks up what Ollama can't handle well or isn't available for, and a
reasoning-capable delegate takes anything needing real judgment.

**Only running this plugin, no paid delegate at all?** That's a fully valid
setup — mechanical work still delegates to Ollama; anything Ollama can't
handle (reasoning-heavy work, or a task Ollama got visibly wrong) falls back
to inline instead of failing over to another lane. Use the
Ollama-only variant in [docs/claude-md-snippet.md](claude-md-snippet.md).

## The core split

| Lane | Owns | Examples |
|---|---|---|
| **Ollama (this plugin)** | The cheapest tier of purely mechanical, zero-domain-context work — try this first | Simple CRUD/mapping test specs, mechanical renames across 3+ files, dead code / unused import cleanup, interface generation from DTOs, component boilerplate shells, identical config blocks across N files, PR descriptions for self-explanatory commits |
| **Paid mechanical delegate** (e.g. Copilot CLI) | The same tier of work, when Ollama is unavailable, the model isn't set up, or its output was visibly wrong | Same list as above, as a fallback |
| **Reasoning delegate** (e.g. Codex) | Anything needing real reasoning, multi-step build fixing, or codebase-wide context | Build errors after a first failed fix, logic-bearing handlers/services, multi-file refactors that change control flow, complex test specs |
| **Keep inline (never delegate)** | Tasks where the WHY lives in your conversation | Domain logic and business rules, architecture and feature design, refactors requiring full codebase context |

Rule of thumb: if the delegate needs to understand *why*, it is not an Ollama
task. If it is purely mechanical shape/pattern work, try Ollama first — it
costs nothing.

## What makes this lane different from a paid CLI delegate

A paid delegate like Copilot CLI is itself agentic: it reads files, runs git,
and applies its own diffs. `ollama run` is not agentic at all — it's a plain
text-completion call with no filesystem or git access. That has two
consequences:

- **No allow/deny flag set is needed.** There's nothing to sandbox, because
  the model literally cannot touch your repo. The `ollama-rescue` subagent
  just returns text.
- **Nothing gets applied automatically.** Claude (the caller) has to read the
  returned text and apply it via its own Edit/Write tools, after reviewing
  it. Treat Ollama's output as a draft from a smaller, less reliable model —
  not as an already-vetted diff the way a paid delegate's result might be.

## The default-delegate discipline

- Before writing any code, decide the lane explicitly: Ollama, a paid
  delegate, a reasoning delegate, or inline. Inline is only for tasks on the
  never-delegate list or trivial edits (<5 lines, 1 file) where coordinating
  a delegation costs more than doing it.
- The main thread acts as orchestrator and reviewer: define the subtask
  contract, launch the delegation in the background, review the output when
  it returns (Ollama's output especially — see above). Never idle while a
  delegation runs — continue with the next subtask.

## The parallel pattern

```
Claude: writes SomeHandler (domain logic — inline, never delegated)
  → immediately launches reasoning delegate in background: "fix build errors in related module"
  → immediately launches /ollama:rescue --background "generate boilerplate tests for SomeHandler"
Claude: continues with the next task while both run
```

- WIP cap: 3-5 concurrent background delegations. Beyond that, coordination
  overhead and unreviewed compounding mistakes outweigh the parallelism gain.
- Kill-switch: after 3 stuck/failed iterations on the same delegated task,
  stop retrying that lane. Hand it to another lane once, or bring it back
  inline. Do not loop indefinitely.

## Concurrency on one GPU

If more than one Claude Code session (or any other client) delegates to the
same local Ollama instance at the same time, requests queue — Ollama does not
error out, it just processes them one after another (or in limited parallel,
depending on available VRAM). Two practical implications:

- **Stick to one default model** (`ollama-rescue-mechanical`) across every
  session and delegation. If two sessions request *different* models at the
  same time, Ollama tries to keep both loaded, which on a VRAM-constrained
  card forces much heavier CPU offload for both — slower than just queuing
  behind a single shared model.
- **Keep tasks short and bounded.** This lane is meant for one-shot mechanical
  completions, not long interactive sessions — a queued short task waits
  seconds, not minutes.

## Availability fallback chain

There's no quota to exhaust here — Ollama is local and free — but there is an
*availability* chain, since the service can be stopped, the model can be
missing, or the output can simply be wrong.

**Detection:** a connection-refused error (service not running), a
"model not found" error (setup never run, or run against a different tag),
or output that's clearly off-topic/truncated/wrong for the task.

**The chain:**

1. Ollama fails or its output is unusable for the task.
2. If a paid mechanical delegate is configured → retry the same task there.
3. If no paid delegate is configured, or it also fails → the main thread does
   the task inline. Do not loop retrying the same failing lane.

Tell the user when a fallback happened — which lane failed, which one picked
it up, or that the main thread took over. One line, no drama.

## Building the model this plugin delegates to

See `commands/setup.md` (Claude Code) or the main README (Codex / manual) for
the full steps. In short: pick a strong local coding model that fits your
VRAM (a 24B-30B class model in the 14-20GB range is a reasonable starting
point on a 16GB-class GPU), pull it, then wrap it in a tiny Modelfile that
pins `PARAMETER num_ctx` to a sane value — most current coding models default
to a huge native context window that will otherwise overflow consumer VRAM
and force heavy CPU offload on every call, even a one-line completion.
