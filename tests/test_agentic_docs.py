#!/usr/bin/env python3
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = "agents/ollama-rescue.md"
SKILL = "skills/ollama-rescue/SKILL.md"
CLAUDE_SNIPPET = "docs/claude-md-snippet.md"
AGENTS_SNIPPET = "docs/agents-md-snippet.md"
GUIDE = "docs/delegation-guide.md"

REPO_FILES_TRIGGER = re.compile(
    r"needs? (to )?read (or|/) ?edit|read/edit repository|repository reads/edits",
    re.IGNORECASE,
)
OPT_IN_MARKER = re.compile(r"--agentic|opt-in|explicitly", re.IGNORECASE)
TEXT_ONLY_CLAIM = re.compile(
    r"applied automatically|no filesystem or git access", re.IGNORECASE
)
MODE_CAVEAT = re.compile(r"agentic mode|--agentic|text[- ]mode", re.IGNORECASE)
SNIPPET_AGENTIC_QUALIFIER = re.compile(r"experimental|opt-in", re.IGNORECASE)
ITEM_START = re.compile(r"^\s*(- |\* |\| |\d+\. |#)")


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def split_items(text):
    items = []
    for block in re.split(r"\n\s*\n", text):
        current = []
        for line in block.split("\n"):
            if ITEM_START.match(line) and current:
                items.append(" ".join(current))
                current = []
            current.append(line.strip())
        items.append(" ".join(current))
    return [item for item in items if item]


def items_matching(relative, pattern):
    return [item for item in split_items(read(relative)) if pattern.search(item)]


def repo_file_triggers_without_opt_in(relative):
    return [
        item
        for item in items_matching(relative, REPO_FILES_TRIGGER)
        if not OPT_IN_MARKER.search(item)
    ]


def text_only_claims_without_caveat(relative):
    return [
        item
        for item in items_matching(relative, TEXT_ONLY_CLAIM)
        if not MODE_CAVEAT.search(item)
    ]


def unqualified_agentic_lines(relative):
    return [
        line.strip()
        for line in read(relative).split("\n")
        if "agentic" in line.lower() and not SNIPPET_AGENTIC_QUALIFIER.search(line)
    ]


def agent_header(text):
    return text.split("Selection guidance:", 1)[0]


def check_split_items_self_test():
    items = split_items("a\nb\n- c\n  d\n\n| e |\n| f |")
    expected = ["a b", "- c d", "| e |", "| f |"]
    return [] if items == expected else [f"split_items self-test: {items!r}"]


def check_agent_header():
    header = agent_header(read(AGENT))
    failures = []
    if "--agentic" not in header:
        failures.append(f"{AGENT}: header does not require --agentic")
    if re.search(r"clearly needs", header) and not re.search(
        r"(even|still)[^.]*clearly needs", header
    ):
        failures.append(f"{AGENT}: header picks agentic mode from the task shape")
    return failures


def check_repo_file_triggers():
    return [
        f"{relative}: agentic trigger without opt-in: {item[:160]}"
        for relative in (AGENT, SKILL, CLAUDE_SNIPPET, AGENTS_SNIPPET)
        for item in repo_file_triggers_without_opt_in(relative)
    ]


def check_text_only_claims():
    return [
        f"{relative}: absolute text-mode claim: {item[:160]}"
        for relative in (AGENT, SKILL, CLAUDE_SNIPPET, AGENTS_SNIPPET, GUIDE)
        for item in text_only_claims_without_caveat(relative)
    ]


def check_snippet_agentic_lines():
    return [
        f"{relative}: agentic without experimental/opt-in: {line}"
        for relative in (CLAUDE_SNIPPET, AGENTS_SNIPPET)
        for line in unqualified_agentic_lines(relative)
    ]


def check_snippet_tables():
    return [
        f"{relative}: proactive table/list recommends agentic mode: {item[:160]}"
        for relative in (CLAUDE_SNIPPET, AGENTS_SNIPPET)
        for item in items_matching(relative, re.compile(r"agentic", re.IGNORECASE))
        if item.startswith("|") or re.match(r"- Tasks? ", item)
    ]


def check_guide_section():
    guide = read(GUIDE)
    if not re.search(r"^## Agentic mode", guide, re.MULTILINE):
        return [f"{GUIDE}: missing an 'Agentic mode' section"]
    section = guide.split("## Agentic mode", 1)[1].split("\n## ", 1)[0]
    needed = ("--agentic", "acceptEdits", "git diff", "MEDIUM-LOW")
    return [f"{GUIDE}: Agentic mode section lacks {word}" for word in needed if word not in section]


def check_skill_agentic_section():
    skill = read(SKILL)
    section = skill.split("## Agentic mode", 1)[1].split("\n## ", 1)[0]
    failures = []
    if not re.search(r"experimental", section, re.IGNORECASE):
        failures.append(f"{SKILL}: Agentic mode section is not marked experimental")
    if not OPT_IN_MARKER.search(section.split("```", 1)[0]):
        failures.append(f"{SKILL}: Agentic mode section does not require an explicit request")
    return failures


CHECKS = (
    check_split_items_self_test,
    check_agent_header,
    check_repo_file_triggers,
    check_text_only_claims,
    check_snippet_agentic_lines,
    check_snippet_tables,
    check_guide_section,
    check_skill_agentic_section,
)


def main():
    failures = [failure for check in CHECKS for failure in check()]
    for failure in failures:
        print("FAIL", failure)
    print(f"{len(CHECKS)} checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
