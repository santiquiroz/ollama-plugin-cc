# ollama-plugin-cc

Delegate mechanical coding tasks from [Claude Code](https://claude.com/claude-code)
to a local [Ollama](https://ollama.com) model, running entirely on your own
hardware.

Claude Code stays the orchestrator — it writes the domain logic, defines each
subtask contract, and reviews the output. Ollama absorbs the purely
mechanical work (boilerplate, renames, dead-code cleanup, simple specs, DTO
mapping, PR descriptions) in the background, for free, so your Claude context
and tokens go to the work only Claude can do. It's the cheapest possible
delegation lane — try it before reaching for a paid CLI delegate.

Inspired by the structure of
[santiquiroz/copilot-plugin-cc](https://github.com/santiquiroz/copilot-plugin-cc),
which this plugin pairs well with as a fallback lane (see
[docs/delegation-guide.md](docs/delegation-guide.md)).
**Not affiliated with Ollama, Meta, Mistral, Alibaba, Zhipu/Z.ai, or Anthropic.**

> Lea esto en español: [README.es.md](README.es.md)

## Requirements

- Claude Code
- [Ollama](https://ollama.com/download) installed and running locally
- A GPU (or enough system RAM) to run at least one ~15-25GB local coding
  model at usable speed — see [Choosing a model](#choosing-a-model) below.
  CPU-only works too, just slower.

## Install

In Claude Code:

```
/plugin marketplace add santiquiroz/ollama-plugin-cc
/plugin install ollama@ollama-plugin-cc
```

Then set up the model this plugin delegates to:

```
/ollama:setup
```

This checks Ollama is installed and running, then walks you through picking
a base model and builds a context-capped derivative tag
(`ollama-rescue-mechanical`) from it — see
[Why the context cap](#why-the-context-cap) below for why that step matters.

## Usage

Explicit delegation:

```
/ollama:rescue remove all unused imports under src/ and fix the import order
/ollama:rescue --background generate boilerplate test specs for src/services/user-mapper.ts
/ollama:rescue --model ollama-rescue-vision describe the layout in this screenshot and scaffold a matching component
```

Proactive delegation: the `ollama-rescue` agent describes itself so Claude
Code picks it for mechanical tasks on its own. To wire it into your own
delegation rules, paste the block from
[docs/claude-md-snippet.md](docs/claude-md-snippet.md) into your `CLAUDE.md`.

Full orchestration patterns — the Ollama/paid-delegate/reasoning-delegate
split, the parallel pattern, WIP caps, concurrency on one GPU, and the
availability fallback chain — live in
[docs/delegation-guide.md](docs/delegation-guide.md).

## Why the context cap (and the output cap)

Most current local coding models default to a large native context window
(100K-256K+ tokens). Ollama reserves KV-cache proportional to that context
*by default*, even for a one-line completion — on a consumer GPU this
overflows VRAM and forces heavy CPU offload, making every delegated call far
slower than it needs to be, for no benefit (mechanical tasks rarely need more
than a few files of context).

`/ollama:setup` fixes this by building a small derivative Modelfile:

```
FROM <your chosen base model>
PARAMETER num_ctx 32768
PARAMETER num_predict 4096
```

...and tagging the result `ollama-rescue-mechanical`. This plugin's agent and
skill only ever call that tag, never a raw pulled one.

`num_predict` caps the OUTPUT length, and it matters for a different reason
than `num_ctx`: hybrid-reasoning ("thinking") models can occasionally get
stuck rambling in their reasoning trace and never converge on an answer —
confirmed in practice with a Qwen3.6-class model logging 1800+ decoded
tokens and climbing, at under 4 tok/s, on a single request that never
completed. Without an output cap that looks exactly like a hang and can run
for hours; with it, a stuck generation hard-stops in a few minutes instead of
never. If your delegated tasks are agentic/tool-calling (not just this
plugin's one-shot forwarder), also prefer a non-reasoning base model
(`devstral:24b` doesn't have a visible "thinking" mode; `qwen3.6:27b` does) —
the reasoning trace is exactly what tends to run away.

## Choosing a model

Any coding-capable model that fits your VRAM works. As of this writing, these
are known-good starting points on a 16GB-class consumer GPU (check
`ollama.com/library` or `ollama search <name>` for anything newer — this
landscape moves fast):

| Model | Approx. size | Notes |
|---|---|---|
| `devstral:24b` | ~14GB | Dense, most predictable latency, no visible "thinking" mode, tuned specifically for reading multi-file codebases and writing patches. Recommended default for this plugin's mechanical-only use case, and the safer pick for agentic/tool-calling use in general. |
| `qwen3.6:27b` | ~17GB | Vision-capable — useful if some delegated tasks reference an image or screenshot. Hybrid-reasoning model; cap `num_predict` if you use it, see above. |
| `qwen3-coder:30b` | ~18GB | MoE, widely field-tested for agentic coding tool-calling. |
| `glm-4.7-flash:q4_K_M` | ~19GB | MoE, described by its authors as the strongest model in the 30B class. Requires a recent Ollama version. |

None of these need to be the model you use for interactive coding elsewhere
— this plugin's use case is narrow (mechanical, zero-domain-context), so a
smaller/faster model than your daily driver is often the better fit.

## Set expectations on speed, not just capability

On modest consumer GPUs, sustained generation for a real (non-trivial) task
has been observed well under 5 tok/s — a full file or test class can
genuinely take several minutes, not seconds. The `ollama-rescue` agent and
skill use a 10+ minute timeout for anything beyond a one-line snippet for
exactly this reason. This is still a net win over doing the work inline —
launch it in the background and keep working, per
[docs/delegation-guide.md](docs/delegation-guide.md) — but don't expect
"generate a full xUnit test file" to come back in the same few seconds a
one-line completion does.

## Safety model

Unlike an agentic CLI delegate, calling Ollama's HTTP API is a **pure
text-completion request** — it has no filesystem or git access and cannot
execute anything on its own. There is no allow/deny flag set to configure,
because there's nothing for the model to sandbox: it returns text, and
Claude (the caller) applies it via its own Edit/Write tools after reviewing
it. (The agent and skill call the API directly rather than the `ollama run`
CLI — see [Known issues](#known-issues-this-plugin-works-around) below for
why.)

That review step matters more here than with a paid delegate: local models
in this size class are more prone to subtle mistakes than a frontier cloud
model — including inventing a plausible-looking but nonexistent API when
asked to reuse something from your existing codebase it was never actually
shown (confirmed in practice) — and unlike an agentic CLI's already-applied
diff, nothing here has been vetted by anything except a much smaller model.
For any task that touches an existing method/API surface, paste the real
signature into the task text rather than trusting the model to already know
it, and check that any referenced symbols in the output actually exist
before applying it.

## Known issues this plugin works around

| Issue | Workaround baked in |
|---|---|
| Native-context VRAM blowup — most models default to a huge context window that overflows consumer VRAM and forces heavy CPU offload | `/ollama:setup` always builds a context-capped derivative tag (`PARAMETER num_ctx 32768` by default) and the agent/skill only ever call that tag |
| Runaway reasoning trace on hybrid-thinking models — generation never converges, looks exactly like a hang | `/ollama:setup` also caps `PARAMETER num_predict 4096` by default, so a stuck generation hard-stops instead of running for hours |
| Terminal control codes corrupting output — `ollama run` is an interactive-terminal tool and can leave ANSI/TTY escape sequences mixed into stdout even when not attached to a real terminal (confirmed in practice: real code output came back interleaved with escape codes, needing a manual cleanup pass) | The agent and skill call Ollama's HTTP API (`curl .../api/generate`) directly instead of the `ollama run` CLI, returning clean JSON with no terminal artifacts |

## Concurrency

If more than one Claude Code session delegates to the same local Ollama
instance at once, requests queue rather than error out. Keep every session
on the same default model (`ollama-rescue-mechanical`) — if two sessions
request *different* models at the same time, Ollama tries to keep both
loaded, which on a VRAM-constrained card is slower for both than simply
queuing behind one shared model. See
[docs/delegation-guide.md](docs/delegation-guide.md#concurrency-on-one-gpu)
for the full explanation.

## What's in the plugin

| Piece | Purpose |
|---|---|
| `agents/ollama-rescue.md` | Thin forwarder subagent — one `ollama run` call, output returned verbatim |
| `/ollama:rescue` | Delegate a task explicitly (`--background`, `--wait`, `--model <tag>`) |
| `/ollama:setup` | Verify Ollama is installed/running and build the context-capped model |
| `docs/delegation-guide.md` | Full multi-lane orchestration guide (Ollama + paid delegate + reasoning delegate) |
| `docs/claude-md-snippet.md` | Ready-to-paste CLAUDE.md block, with an Ollama-only variant |
| `.codex-plugin/plugin.json` | Codex CLI plugin manifest (experimental native install) |
| `skills/ollama-rescue/SKILL.md` | Codex skill — same forwarder logic, Codex runs the shell call itself (no subagent layer) |
| `docs/agents-md-snippet.md` | Ready-to-paste `AGENTS.md` block for Codex users |

## Codex CLI

The same idea, for [Codex CLI](https://developers.openai.com/codex/): delegate
mechanical work to a local Ollama model, so Codex's reasoning stays on the
work only it can do. Ships as a Codex **skill**
(`skills/ollama-rescue/SKILL.md`) instead of a subagent — Codex runs the
forwarded `ollama run ...` command itself, since Codex has no separate
subagent/Task layer.

### Requirements

- Codex CLI
- Ollama installed, running, and set up per [Install](#install) above

### Install

**Manual (confirmed working):**

```bash
mkdir -p ~/.agents/skills
cp -r skills/ollama-rescue ~/.agents/skills/ollama-rescue
```

Or repo-scoped only: copy into `<your-repo>/.agents/skills/ollama-rescue/` instead.

**Native plugin marketplace (experimental — Codex's plugin system is new;
please open an issue if the paths below don't match your Codex CLI version):**

```
codex plugin marketplace add santiquiroz/ollama-plugin-cc
```

Then open the plugin browser (`/plugins` inside Codex) and install `ollama`.

### Usage

Codex matches skills implicitly by their `description`, or you can invoke
explicitly. Ask for a mechanical task and Codex should pick `ollama-rescue`
on its own; to wire proactive delegation into your own instructions, paste
the block from [docs/agents-md-snippet.md](docs/agents-md-snippet.md) into
your `AGENTS.md`.

### Safety model

Same as the Claude Code side — see [Safety model](#safety-model) above.
`ollama run` has no filesystem/git access regardless of which agent is
calling it.

## License

[MIT](LICENSE)
