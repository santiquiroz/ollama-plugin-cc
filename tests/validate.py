import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = [
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
]
BASH_DOCS = [
    "agents/ollama-rescue.md",
    "skills/ollama-rescue/SKILL.md",
    "commands/rescue.md",
    "commands/setup.md",
    "README.md",
    "README.es.md",
]
FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
PLACEHOLDER = re.compile(r"<[a-z][^<>\n]*>")
CHANGELOG_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)
SUBAGENT_TYPE = re.compile(r'subagent_type: "([^"]+)"')
BASH_ERROR_LINE = re.compile(r"here-document at line (\d+)|line (\d+):")


def read(relative):
    return (REPO / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def load_manifest(relative):
    try:
        return json.loads(read(relative)), None
    except (OSError, ValueError) as error:
        return None, f"{relative}: invalid JSON ({error})"


def load_manifests():
    loaded = {relative: load_manifest(relative) for relative in MANIFESTS}
    manifests = {relative: data for relative, (data, _error) in loaded.items() if data is not None}
    errors = [error for _data, error in loaded.values() if error]
    return manifests, errors


def marketplace_entry(marketplace, plugin_name):
    entries = [entry for entry in marketplace.get("plugins", []) if entry.get("name") == plugin_name]
    return entries[0] if entries else {}


def declared_versions(manifests):
    plugin = manifests[".claude-plugin/plugin.json"]
    marketplace = manifests[".claude-plugin/marketplace.json"]
    return {
        ".claude-plugin/plugin.json": plugin.get("version"),
        ".claude-plugin/marketplace.json metadata": marketplace.get("metadata", {}).get("version"),
        ".claude-plugin/marketplace.json plugins[]": marketplace_entry(marketplace, plugin.get("name")).get("version"),
        ".codex-plugin/plugin.json": manifests[".codex-plugin/plugin.json"].get("version"),
        "CHANGELOG.md first release": first_changelog_release(),
    }


def first_changelog_release():
    match = CHANGELOG_RELEASE.search(read("CHANGELOG.md"))
    return match.group(1) if match else None


def check_manifests_parse():
    return load_manifests()[1]


def check_versions_in_sync():
    manifests, errors = load_manifests()
    if errors:
        return ["versions not checked: a manifest does not parse"]
    versions = declared_versions(manifests)
    if len(set(versions.values())) == 1 and None not in versions.values():
        return []
    return ["versions out of sync: " + ", ".join(f"{where}={version}" for where, version in versions.items())]


def check_plugin_names_match():
    manifests, errors = load_manifests()
    if errors:
        return ["names not checked: a manifest does not parse"]
    name = manifests[".claude-plugin/plugin.json"].get("name")
    failures = []
    if not marketplace_entry(manifests[".claude-plugin/marketplace.json"], name):
        failures.append(f".claude-plugin/marketplace.json: no plugins[] entry named {name!r}")
    if manifests[".codex-plugin/plugin.json"].get("name") != name:
        failures.append(f".codex-plugin/plugin.json: name differs from .claude-plugin/plugin.json ({name!r})")
    return failures


def frontmatter(relative):
    lines = read(relative).split("\n")
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    body = lines[1 : lines.index("---", 1)]
    return dict(line.split(":", 1) for line in body if ":" in line and not line.startswith(" "))


def missing_frontmatter_keys(relative, keys):
    fields = frontmatter(relative)
    if fields is None:
        return [f"{relative}: no YAML frontmatter"]
    return [f"{relative}: frontmatter has no {key!r}" for key in keys if not fields.get(key, "").strip()]


def frontmatter_name(relative):
    return ((frontmatter(relative) or {}).get("name") or "").strip()


def check_frontmatter():
    failures = missing_frontmatter_keys("agents/ollama-rescue.md", ["name", "description"])
    failures += missing_frontmatter_keys("skills/ollama-rescue/SKILL.md", ["name", "description"])
    for command in sorted((REPO / "commands").glob("*.md")):
        failures += missing_frontmatter_keys(command.relative_to(REPO).as_posix(), ["description"])
    return failures


def check_names_match_paths():
    failures = []
    if frontmatter_name("agents/ollama-rescue.md") != "ollama-rescue":
        failures.append("agents/ollama-rescue.md: frontmatter name is not 'ollama-rescue'")
    if frontmatter_name("skills/ollama-rescue/SKILL.md") != "ollama-rescue":
        failures.append("skills/ollama-rescue/SKILL.md: frontmatter name is not its directory 'ollama-rescue'")
    return failures


def check_rescue_command_targets_agent():
    manifests, errors = load_manifests()
    if errors:
        return ["agent reference not checked: a manifest does not parse"]
    expected = f'{manifests[".claude-plugin/plugin.json"].get("name")}:{frontmatter_name("agents/ollama-rescue.md")}'
    referenced = set(SUBAGENT_TYPE.findall(read("commands/rescue.md")))
    if referenced == {expected}:
        return []
    return [f"commands/rescue.md: subagent_type {sorted(referenced)} does not match the agent {expected!r}"]


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def bash_blocks():
    blocks = []
    for relative in BASH_DOCS:
        text = read(relative)
        for match in FENCE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            blocks.append((f"{relative}:{line}", dedent(match.group(2), len(match.group(1)))))
    return blocks


def as_parseable(block):
    return PLACEHOLDER.sub("PLACEHOLDER", block)


def wrap_blocks(blocks):
    # One wrapper function per block lets a single `bash -n` parse every block (process startup is slow on Windows).
    script, spans = "", []
    for index, (where, block) in enumerate(blocks):
        start = script.count("\n") + 1
        script += f"__block_{index}() {{\n{as_parseable(block)}\n}}\n"
        spans.append((start, script.count("\n"), where))
    return script, spans


def block_at(spans, line):
    return next((where for start, end, where in spans if start <= line <= end), "unknown block")


def culprit(spans, stderr):
    # An unclosed heredoc is only a warning at EOF; the line where it opened names the real culprit.
    matches = BASH_ERROR_LINE.findall(stderr)
    heredocs = [int(heredoc) for heredoc, _line in matches if heredoc]
    lines = heredocs or [int(line) for _heredoc, line in matches if line]
    return block_at(spans, lines[0]) if lines else "unknown block"


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        return None
    return bash


def bash_syntax_errors(bash, script):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blocks.sh"
        path.write_bytes(script.encode("utf-8"))
        result = subprocess.run([bash, "-n", path.as_posix()], capture_output=True, text=True, encoding="utf-8")
    return result.returncode, result.stderr.replace(path.as_posix(), "blocks.sh").strip()


def check_bash_blocks_parse():
    blocks = bash_blocks()
    if not blocks:
        return ["no ```bash blocks found in " + ", ".join(BASH_DOCS)]
    bash = find_bash()
    if bash is None:
        return ["Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)"]
    script, spans = wrap_blocks(blocks)
    code, stderr = bash_syntax_errors(bash, script)
    if code == 0 and not stderr:
        return []
    return [f"bash -n fails in the block at {culprit(spans, stderr)}: {stderr}"]


def check_bash_wrapper_self_test():
    indented_heredoc_end = "PROMPT=$(cat <<'EOF'\n<task>\n  EOF\n)\n"
    blocks = [("before", "echo ok\n"), ("bad", indented_heredoc_end), ("after", "echo ok\n")]
    script, spans = wrap_blocks(blocks)
    bash = find_bash()
    if bash is None:
        return []
    code, stderr = bash_syntax_errors(bash, script)
    if code != 0 and culprit(spans, stderr) == "bad":
        return []
    return [f"self-test: the bash -n wrapper did not flag the broken block (exit {code}, {stderr!r})"]


CHECKS = (
    check_manifests_parse,
    check_versions_in_sync,
    check_plugin_names_match,
    check_frontmatter,
    check_names_match_paths,
    check_rescue_command_targets_agent,
    check_bash_wrapper_self_test,
    check_bash_blocks_parse,
)


def main():
    failures = [failure for check in CHECKS for failure in check()]
    for failure in failures:
        print("FAIL", failure)
    print(f"{len(CHECKS)} checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
