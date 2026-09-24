import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = ["agents/ollama-rescue.md", "skills/ollama-rescue/SKILL.md"]
TASK_PLACEHOLDER = re.compile(r"<task>|<task text>")
OTHER_PLACEHOLDER = re.compile(r"<[a-z][^<>\n]*>")
FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
MODEL_FLAG_LINE = re.compile(r'^MODEL_FLAG=""$', re.MULTILINE)
RESOLVER = re.compile(r'^MODEL_FLAG=""\n.*?^resolve_model\(\) \{\n.*?^\}$', re.MULTILINE | re.DOTALL)
OLLAMA_URL = re.compile(r"http://(localhost|127\.0\.0\.1):11434")
UNRESOLVED = "UNRESOLVED-PLACEHOLDER"
TASK = "Reply with exactly: ok"

SHIMS = r"""
claude() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) printf '%s' "$2" > "$OUT/claude_model"; shift 2 ;;
      *) shift ;;
    esac
  done
}
ollama() { echo "real ollama must not run" >&2; return 99; }
"""

SCENARIOS = [
    (
        "prefers ollama-rescue-mechanical even when it is not listed first",
        "",
        ["devstral:24b", "qwen3.6-32k:latest", "ollama-rescue-mechanical:latest", "devstral-32k:latest"],
        "ollama-rescue-mechanical",
    ),
    (
        "falls back to the first -32k tag and skips raw tags",
        "",
        ["devstral:24b", "devstral-32k:latest", "qwen3.6-32k:latest", "glm-4.7-flash-32k:latest"],
        "devstral-32k",
    ),
    (
        "accepts any -mechanical tag as context-capped",
        "",
        ["qwen2.5-coder:32b", "coder-mechanical:latest"],
        "coder-mechanical",
    ),
    (
        "fails with a pointer to /ollama:setup when only raw tags exist",
        "",
        ["devstral:24b", "qwen2.5-coder:32b"],
        None,
    ),
    (
        "fails with a pointer to /ollama:setup when no model is installed",
        "",
        [],
        None,
    ),
    (
        "respects --model",
        "qwen3.6-32k",
        ["ollama-rescue-mechanical:latest", "devstral-32k:latest"],
        "qwen3.6-32k",
    ),
]


class FakeOllama(BaseHTTPRequestHandler):
    tags = []
    generate_models = []

    def do_GET(self):
        if self.path != "/api/tags":
            return self.reply(404, {"error": "not found"})
        models = [{"name": tag, "model": tag, "details": {"families": ["llama"]}} for tag in FakeOllama.tags]
        return self.reply(200, {"models": models})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        FakeOllama.generate_models.append(body.get("model"))
        return self.reply(200, {"response": "ok"})

    def reply(self, status, payload):
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
        pass


def start_fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def is_forwarding_block(block):
    return TASK_PLACEHOLDER.search(block) and ("api/generate" in block or '-p "$PROMPT"' in block)


def find_forwarding_blocks(text):
    blocks = [dedent(match.group(2), len(match.group(1))) for match in FENCE.finditer(text)]
    return [block for block in blocks if is_forwarding_block(block)]


def render(block, model_flag, port):
    with_task = TASK_PLACEHOLDER.sub(lambda _m: TASK, block)
    with_flag = MODEL_FLAG_LINE.sub(lambda _m: f'MODEL_FLAG="{model_flag}"', with_task)
    local = OLLAMA_URL.sub(f"http://127.0.0.1:{port}", with_flag)
    return OTHER_PLACEHOLDER.sub(UNRESOLVED, local)


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        sys.exit("FAIL: Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)")
    return bash


def run_rendered(bash, script, out_dir):
    script_path = out_dir / "rendered.sh"
    script_path.write_bytes((SHIMS + script).encode("utf-8"))
    exports = f"export OUT='{out_dir.as_posix()}' TMPDIR='{out_dir.as_posix()}'"
    command = f"{exports}; . '{script_path.as_posix()}'"
    result = subprocess.run([bash, "-c", command], capture_output=True, timeout=120)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return result.returncode, output


def used_models(out_dir):
    claude_model = out_dir / "claude_model"
    from_claude = [claude_model.read_text(encoding="utf-8")] if claude_model.exists() else []
    return FakeOllama.generate_models + from_claude


def check_resolved(code, output, models, expected):
    if code != 0:
        return [f"exit {code}, expected 0 (output: {output.strip()!r})"]
    if models != [expected]:
        return [f"used models {models!r}, expected [{expected!r}]"]
    return []


def check_refused(code, output, models):
    errors = []
    if code == 0:
        errors.append(f"exit 0 without a context-capped model (output: {output.strip()!r})")
    if "/ollama:setup" not in output:
        errors.append(f"output {output.strip()!r} does not point at /ollama:setup")
    if models:
        errors.append(f"called Ollama with {models!r} although no context-capped model exists")
    return errors


def run_scenario(bash, block, port, model_flag, tags, expected):
    FakeOllama.tags, FakeOllama.generate_models = tags, []
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        code, output = run_rendered(bash, render(block, model_flag, port), out_dir)
        models = used_models(out_dir)
    if expected is None:
        return check_refused(code, output, models)
    return check_resolved(code, output, models, expected)


def check_block(bash, label, block, port):
    failures = []
    if not MODEL_FLAG_LINE.search(block):
        failures.append(f'{label}: no MODEL_FLAG="" line for the --model value')
    for name, model_flag, tags, expected in SCENARIOS:
        errors = run_scenario(bash, block, port, model_flag, tags, expected)
        failures.extend(f"{label}: {name}: {error}" for error in errors)
    return failures


def check_doc(bash, doc, port):
    blocks = find_forwarding_blocks((REPO / doc).read_text(encoding="utf-8"))
    if len(blocks) != 2:
        return [f"{doc}: found {len(blocks)} forwarding blocks, expected text mode and agentic mode"], []
    failures = []
    for index, block in enumerate(blocks, start=1):
        failures.extend(check_block(bash, f"{doc} block {index}", block, port))
    return failures, blocks


def check_same_resolver(blocks):
    resolvers = {match.group(0) if match else None for match in map(RESOLVER.search, blocks)}
    if None in resolvers or len(resolvers) != 1:
        return ["the resolve_model snippet differs between blocks (or is missing); keep one copy in sync"]
    return []


def main():
    bash = find_bash()
    server = start_fake_server()
    failures, blocks = [], []
    try:
        for doc in DOCS:
            doc_failures, doc_blocks = check_doc(bash, doc, server.server_address[1])
            failures.extend(doc_failures)
            blocks.extend(doc_blocks)
    finally:
        server.shutdown()
    failures.extend(check_same_resolver(blocks))
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        sys.exit(1)
    print(f"ok - {len(blocks)} blocks resolve the model the same way ({len(SCENARIOS)} scenarios each)")


if __name__ == "__main__":
    main()
