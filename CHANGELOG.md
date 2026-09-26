# Changelog

## 0.3.0 — 2026-09-26

- Security fix: the agent, the Codex skill and both READMEs now pass the task
  text to the shell through a quoted heredoc (`PROMPT=$(cat <<'OLLAMA_TASK_EOF'
  ... OLLAMA_TASK_EOF)`) and use `"$PROMPT"`, instead of pasting it inside
  double quotes. Backticks, `$VAR` and `$(...)` in a task were being executed
  or expanded by bash, so the model received a mutilated task with exit 0, and
  in agentic mode (auto-accepted edits) the task text could run commands.
  The old claim that `jq -n` protected against backticks was wrong: it only
  keeps the JSON valid.
- Added `tests/test_quoting.py` (run with `bash tests/run.sh`): it renders
  every documented task template with a hostile task and checks, with shimmed
  `curl`/`claude` and no network, that the prompt arrives byte for byte.
- Fix: text mode no longer hides Ollama failures or needs `jq`. The agent and
  the Codex skill run with `set -o pipefail` and `curl -sS`, and build and
  parse the JSON with the first available of `jq`, `python3`/`python` and
  `node`. A `{"error": ...}` reply now prints `OLLAMA_ERROR: <message>` and
  exits non-zero (it used to print `null` with exit 0), an unreachable server
  prints curl's connection error and exits non-zero (it used to print nothing
  with exit 0), and a machine without `jq` works as long as Python or Node is
  installed.
- `/ollama:setup` reports which JSON tool text mode will use, and its smoke
  test prints the raw JSON reply instead of piping it to `jq`.
- Added `tests/test_errors.py`: a fake Ollama (`http.server` on an ephemeral
  127.0.0.1 port) checks the ok, error, non-JSON and closed-port cases with
  `jq` hidden from `PATH`, once with Python and once with Node.
- Fix: text and agentic mode now resolve the model with the same
  `resolve_model` snippet: `--model` as-is, else `ollama-rescue-mechanical` if
  `/api/tags` lists it, else the first `-32k`/`-mechanical` tag, else
  `OLLAMA_ERROR: no context-capped model ... run /ollama:setup` before any
  model is called. Text mode used to hardcode `ollama-rescue-mechanical` (a
  "model not found" on machines that only have e.g. `devstral-32k`), and
  agentic mode took the first capped tag even when `ollama-rescue-mechanical`
  was installed. Raw tags such as `devstral:24b` are never picked.
- Added `tests/test_model_resolution.py`: a fake `/api/tags` checks both modes
  of the agent and the skill for the four cases, plus that all four copies of
  the snippet are identical.
- Fix: `/ollama:setup` declares every command its steps run in
  `allowed-tools` (`curl`, `cat`, and `--version` probes of `jq`, `python3`,
  `python` and `node`), so it no longer stops on permission prompts. The JSON
  tool check spells out each probe instead of running `"$tool" --version`.
- Fix: `/ollama:setup` reads the server version from `GET /api/version`
  (0.33 or newer, compared numerically, so 0.9 is older than 0.33) and probes
  `/v1/messages` only after `ollama-rescue-mechanical` exists. The old
  preflight ran against a placeholder tag before the model was built and
  reported every 404 as an old Ollama; the report now tells `no (Ollama
  <version> is older than 0.33)` apart from `model not found`. The Modelfile
  is written to `${TMPDIR:-/tmp}` instead of a hardcoded `/tmp`.
- Added `tests/test_setup.py`: it extracts the commands from every bash block
  in `commands/*.md` and checks them against `allowed-tools`, and runs the
  version, probe and Modelfile steps against a fake Ollama with a shimmed
  `ollama`.
- Docs: agentic mode is opt-in only. The agent used to pick it on its own for
  any task that "clearly needs to read or edit files", contradicting its own
  "only with `--agentic`" rule, and the CLAUDE.md/AGENTS.md snippets listed it
  as a proactive trigger. Now the agent, the Codex skill and both snippets use
  it only on an explicit `--agentic` request and mark it experimental, the
  "never applied automatically" claims are scoped to text mode (agentic edits
  are auto-accepted, so review `git diff`), and `docs/delegation-guide.md` has
  an "Agentic mode" section on its status, trust and review.
- Added `tests/test_agentic_docs.py`: it checks those rules on the agent, the
  skill, the snippets and the delegation guide.
- Added `tests/validate.py`, now the first step of `bash tests/run.sh`: it
  checks that the three manifests parse, that their versions match each other
  and the first release heading of this changelog, that the agent, skill and
  commands have the frontmatter Claude Code needs, that `/ollama:rescue`
  points at the agent by its real name, and that every bash block in the
  agent, the skill and the commands passes `bash -n`. `bash tests/run.sh
  --quick` runs only these checks.
- Docs: the agentic command in the Codex skill and both READMEs now matches
  the agent's: it resolves the `claude` binary explicitly and runs the child
  with an empty temporary `CLAUDE_CONFIG_DIR`. The published copies still ran
  plain `claude` with the user's config, so hooks and the global `CLAUDE.md`
  could hijack the child again, which 0.2.0 said was fixed. The agent and the
  skill delete that directory with a `trap` on exit (the agent's `mktemp` used
  to leave one behind per run), and no longer justify `--disallowedTools
  Task,Agent` with the global `CLAUDE.md` the isolated child never loads. The
  READMEs' Codex section no longer says the skill runs `ollama run`, and their
  agentic intro no longer says to pick the mode when a task needs repository
  context. `docs/delegation-guide.md` explains the `num_predict` cap.
- Added `tests/test_doc_sync.py`: it checks those docs stay in sync and runs
  every agentic block with a shimmed `claude` to confirm the child gets an
  existing isolated config dir, the dir is gone afterwards and the child's
  exit status is kept. `tests/validate.py` now also runs `bash -n` on the
  READMEs' bash blocks.

## 0.2.0 — 2026-09-10

- Added opt-in **agentic mode** (experimental) for tasks that need repository
  reads and edits. Measured 2026-09-10: plumbing works, but devstral-32k and
  qwen3.6-32k did not call tools in any run; the child now runs with an empty
  `CLAUDE_CONFIG_DIR` (no hooks/global CLAUDE.md), resolves the `claude`
  binary explicitly and falls back to the first `-32k`/`-mechanical` tag.
  It runs a headless Claude Code instance against Ollama's native Anthropic
  Messages API, with auto-accepted edits and recursive delegation disabled.
- Added Ollama Anthropic API compatibility preflight to `/ollama:setup`.
  Ollama 0.33 or newer is required for agentic mode; older versions retain
  text mode.
- Updated Claude Code and Codex instructions, safety guidance, delegation
  snippets, and manifests for the two-mode workflow.

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
