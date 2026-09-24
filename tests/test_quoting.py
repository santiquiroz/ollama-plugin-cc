import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = [
    "agents/ollama-rescue.md",
    "skills/ollama-rescue/SKILL.md",
    "README.md",
    "README.es.md",
]
TASK_PLACEHOLDER = re.compile(r"<task>|<task text>|<texto de la tarea>")
OTHER_PLACEHOLDER = re.compile(r"<[a-z][^<>\n]*>")
FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
FAKE_TAG = "devstral-32k"

TASK = (
    "Rename `getUser` to \"fetchUser\" in $HOME; it's (( ) $(touch \"$OUT/pwned\")\n"
    "second line with a backslash \\n, a tab\tand acción"
)

SHIMS = r"""
capture() { printf '%s' "$2" > "$OUT/$1"; }
curl() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --data-binary) capture curl_body "$(cat)"; shift 2 ;;
      *api/tags*) printf '{"models":[{"name":"devstral-32k"}]}'; shift ;;
      *api/generate*) printf '{"response":"ok"}'; shift ;;
      *) shift ;;
    esac
  done
}
claude() {
  while [ $# -gt 0 ]; do
    case "$1" in
      -p) capture claude_prompt "$2"; shift 2 ;;
      *) shift ;;
    esac
  done
}
ollama() { echo "real ollama must not run" >&2; return 99; }
"""


def find_task_blocks(text):
    blocks = [dedent(match.group(2), len(match.group(1))) for match in FENCE.finditer(text)]
    return [block for block in blocks if TASK_PLACEHOLDER.search(block)]


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def render(block, task):
    with_tag = OTHER_PLACEHOLDER.sub(lambda m: m.group(0) if TASK_PLACEHOLDER.fullmatch(m.group(0)) else FAKE_TAG, block)
    return TASK_PLACEHOLDER.sub(lambda _m: task, with_tag)


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        sys.exit("FAIL: Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)")
    return bash


def run_rendered(bash, script, out_dir):
    script_path = out_dir / "rendered.sh"
    script_path.write_bytes((SHIMS + script).encode("utf-8"))
    env_prefix = {"OUT": out_dir.as_posix(), "TMPDIR": out_dir.as_posix()}
    command = "export " + " ".join(f"{key}='{value}'" for key, value in env_prefix.items()) + f"; . '{script_path.as_posix()}'"
    return subprocess.run([bash, "-c", command], capture_output=True)


def received_prompt(out_dir):
    body = out_dir / "curl_body"
    if body.exists():
        return json.loads(body.read_text(encoding="utf-8"))["prompt"]
    claude_prompt = out_dir / "claude_prompt"
    if claude_prompt.exists():
        return claude_prompt.read_bytes().decode("utf-8")
    return None


def check_block(bash, label, block):
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = run_rendered(bash, render(block, TASK), out_dir)
        errors = []
        if (out_dir / "pwned").exists():
            errors.append("task text executed a command substitution")
        prompt = received_prompt(out_dir)
        if prompt != TASK:
            errors.append(f"prompt mismatch: got {prompt!r}")
        if result.stderr:
            errors.append(f"stderr: {result.stderr.decode('utf-8', 'replace').strip()}")
    return [f"{label}: {error}" for error in errors]


def main():
    bash = find_bash()
    failures = []
    checked = 0
    for doc in DOCS:
        blocks = find_task_blocks((REPO / doc).read_text(encoding="utf-8"))
        if not blocks:
            failures.append(f"{doc}: no bash block with a task placeholder found")
        checked += len(blocks)
        for index, block in enumerate(blocks, start=1):
            failures.extend(check_block(bash, f"{doc} block {index}", block))
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        sys.exit(1)
    print(f"ok - task text reaches Ollama/claude byte for byte in {checked} blocks across {len(DOCS)} documents")


if __name__ == "__main__":
    main()
