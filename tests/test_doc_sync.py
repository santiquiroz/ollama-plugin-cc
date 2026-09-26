#!/usr/bin/env python3
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = "agents/ollama-rescue.md"
SKILL = "skills/ollama-rescue/SKILL.md"
READMES = ("README.md", "README.es.md")
GUIDE = "docs/delegation-guide.md"
AGENTIC_DOCS = (AGENT, SKILL) + READMES

FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
TASK_PLACEHOLDER = re.compile(r"<task>|<task text>|<texto de la tarea>")
OTHER_PLACEHOLDER = re.compile(r"<[a-z][^<>\n]*>")
CLAUDE_CALL = re.compile(r'-p "\$PROMPT"')
RESOLVER_LINE = re.compile(r'^(CLAUDE_BIN=.*|\[ -n "\$CLAUDE_BIN" \].*)$', re.MULTILINE)
EXPLAINS_WHY_NOT = re.compile(r"(instead of|rather than|en vez del?)\s+(the\s+)?(CLI\s+)?`ollama run", re.IGNORECASE)
STALE_GLOBAL_CLAUDE_MD = re.compile(r"reads\s+the\s+global\s+`?CLAUDE\.md", re.IGNORECASE)
MODE_FROM_TASK_SHAPE = re.compile(r"choose it when|elegilo\s+cuando", re.IGNORECASE)
ISOLATION_MARKERS = (
    'ISO=$(mktemp -d',
    "trap 'rm -rf \"$ISO\"' EXIT",
    'CLAUDE_CONFIG_DIR="$ISO"',
    '"$CLAUDE_BIN" -p "$PROMPT"',
)
FAKE_TAG = "devstral-32k"
CHILD_EXIT = 7

SHIMS = r"""
curl() {
  case "$*" in
    *api/tags*) printf '{"models":[{"name":"devstral-32k"}]}' ;;
  esac
}
claude() {
  printf '%s' "$CLAUDE_CONFIG_DIR" > "$OUT/config_dir"
  [ -d "$CLAUDE_CONFIG_DIR" ] && : > "$OUT/config_dir_existed"
  return 7
}
ollama() { echo "real ollama must not run" >&2; return 99; }
"""


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def bash_blocks(relative):
    return [dedent(match.group(2), len(match.group(1))) for match in FENCE.finditer(read(relative))]


def agentic_blocks(relative):
    return [block for block in bash_blocks(relative) if CLAUDE_CALL.search(block)]


def prose_items(relative):
    items = []
    for block in re.split(r"\n\s*\n", read(relative)):
        items.extend(block.split("\n") if block.lstrip().startswith("|") else [block])
    return items


def agent_resolver_lines():
    return RESOLVER_LINE.findall(agentic_blocks(AGENT)[0])


def missing_isolation(block):
    expected = ISOLATION_MARKERS + tuple(agent_resolver_lines())
    return [marker for marker in expected if marker not in block]


def check_ollama_run_only_explained():
    return [
        f"{relative}: mentions `ollama run` without saying it is not used: {item.strip()[:160]}"
        for relative in READMES
        for item in prose_items(relative)
        if "`ollama run" in item and not EXPLAINS_WHY_NOT.search(" ".join(item.split()))
    ]


def check_agentic_blocks_isolated():
    failures = []
    for relative in AGENTIC_DOCS:
        blocks = agentic_blocks(relative)
        if not blocks:
            failures.append(f"{relative}: no agentic bash block found")
        failures += [
            f"{relative}: agentic block lacks {marker}"
            for block in blocks
            for marker in missing_isolation(block)
        ]
    return failures


def check_no_stale_global_claude_md_reason():
    return [
        f"{relative}: still says the isolated child reads the global CLAUDE.md"
        for relative in (AGENT, SKILL)
        if STALE_GLOBAL_CLAUDE_MD.search(read(relative))
    ]


def check_readmes_keep_agentic_opt_in():
    return [
        f"{relative}: picks agentic mode from the task shape: {item.strip()[:160]}"
        for relative in READMES
        for item in prose_items(relative)
        if MODE_FROM_TASK_SHAPE.search(item)
    ]


def check_guide_mentions_num_predict():
    return [] if "num_predict" in read(GUIDE) else [f"{GUIDE}: does not mention num_predict"]


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        return None
    return bash


def render(block):
    with_task = TASK_PLACEHOLDER.sub("Reply with exactly: ok", block)
    return OTHER_PLACEHOLDER.sub(FAKE_TAG, with_task)


def run_block(bash, block, work):
    out, tmp = work / "out", work / "tmp"
    out.mkdir()
    tmp.mkdir()
    script = work / "block.sh"
    script.write_bytes((SHIMS + render(block)).encode("utf-8"))
    env_prefix = f"export OUT='{out.as_posix()}' TMPDIR='{tmp.as_posix()}'; "
    result = subprocess.run([bash, "-c", env_prefix + f"bash '{script.as_posix()}'"], capture_output=True)
    return result, out, tmp


def run_failures(result, out, tmp):
    failures = []
    if not (out / "config_dir_existed").exists():
        failures.append("the child did not get an existing CLAUDE_CONFIG_DIR")
    if list(tmp.iterdir()):
        failures.append(f"the isolated config dir was left behind: {[p.name for p in tmp.iterdir()]}")
    if result.returncode != CHILD_EXIT:
        failures.append(f"exit {result.returncode} instead of the child's {CHILD_EXIT}")
    if result.stderr:
        failures.append(f"stderr: {result.stderr.decode('utf-8', 'replace').strip()}")
    return failures


def check_agentic_blocks_clean_up():
    bash = find_bash()
    if bash is None:
        return ["Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)"]
    failures = []
    for relative in AGENTIC_DOCS:
        for index, block in enumerate(agentic_blocks(relative), start=1):
            with tempfile.TemporaryDirectory() as tmp:
                result, out, tmp_dir = run_block(bash, block, Path(tmp))
                failures += [f"{relative} agentic block {index}: {failure}" for failure in run_failures(result, out, tmp_dir)]
    return failures


CHECKS = (
    check_ollama_run_only_explained,
    check_agentic_blocks_isolated,
    check_no_stale_global_claude_md_reason,
    check_readmes_keep_agentic_opt_in,
    check_guide_mentions_num_predict,
    check_agentic_blocks_clean_up,
)


def main():
    failures = [failure for check in CHECKS for failure in check()]
    for failure in failures:
        print("FAIL", failure)
    print(f"{len(CHECKS)} checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
