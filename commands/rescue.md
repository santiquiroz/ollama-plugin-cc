---
description: Delegate a mechanical, zero-domain-context task to the Ollama rescue subagent
argument-hint: "[--background|--wait] [--model <tag>] [the mechanical task Ollama should perform]"
allowed-tools: AskUserQuestion, Agent
---

Invoke the `ollama:ollama-rescue` subagent via the `Agent` tool (`subagent_type: "ollama:ollama-rescue"`), forwarding the raw user request as the prompt.
`ollama:ollama-rescue` is a subagent, not a skill — do not call it via the `Skill` tool. This command runs inline so the `Agent` tool stays in scope.
The final user-visible response must be Ollama's output verbatim.

Raw user request:
$ARGUMENTS

Execution mode:

- If the request includes `--background`, run the subagent in the background and continue other work; relay the result when it completes.
- If the request includes `--wait`, run the subagent in the foreground.
- If neither flag is present, default to foreground.
- `--background` and `--wait` are execution flags for Claude Code. Do not forward them in the prompt, and do not treat them as part of the natural-language task text.
- `--model <tag>` is a runtime-selection flag naming a different context-capped model this plugin has set up (e.g. a vision-capable one). Preserve it in the forwarded prompt, but do not treat it as part of the natural-language task text.

Operating rules:

- The subagent is a thin forwarder only. It uses one `Bash` call to invoke `ollama run <model> "<task>"` and returns that command's stdout as-is.
- Return the Ollama output verbatim to the user. Do not paraphrase, summarize, rewrite, or add commentary before or after it. Do note, once, that this output should be reviewed before being applied — it comes from a small local model, not a paid frontier model.
- Do not ask the subagent to inspect files, monitor progress, summarize output, or do follow-up work of its own.
- If the returned output shows Ollama is not installed, not running, or the expected model is missing, tell the user to run `/ollama:setup`.
- If the user did not supply a task, ask what mechanical task Ollama should perform.
