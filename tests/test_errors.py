import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = ["agents/ollama-rescue.md", "skills/ollama-rescue/SKILL.md"]
TASK_PLACEHOLDER = re.compile(r"<task>|<task text>")
FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
OLLAMA_BASE = "http://localhost:11434"
MODEL = "ollama-rescue-mechanical"
TASK = "Reply with exactly: ok"
MISSING_MODEL_ERROR = "model 'x' not found"
PROXY_PAGE = "<html>502 Bad Gateway</html>"

HIDE_CHECK = r"""
for tool in $HIDE; do
  if command -v "$tool" >/dev/null 2>&1; then echo "test setup: could not hide $tool" >&2; exit 90; fi
done
"""

REPLIES = {
    "ok": (200, json.dumps({"response": "ok"})),
    "error": (404, json.dumps({"error": MISSING_MODEL_ERROR})),
    "not json": (502, PROXY_PAGE),
}


class FakeOllama(BaseHTTPRequestHandler):
    mode = "ok"
    requests = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        FakeOllama.requests.append((self.path, body))
        status, payload = REPLIES[FakeOllama.mode]
        encoded = payload.encode("utf-8")
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


def closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def find_text_mode_block(text):
    blocks = [dedent(match.group(2), len(match.group(1))) for match in FENCE.finditer(text)]
    return next((block for block in blocks if "api/generate" in block and TASK_PLACEHOLDER.search(block)), None)


def render(block, port):
    with_task = TASK_PLACEHOLDER.sub(lambda _m: TASK, block).replace("<model>", MODEL)
    return with_task.replace(OLLAMA_BASE, f"http://127.0.0.1:{port}")


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        sys.exit("FAIL: Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)")
    return bash


def has_any(directory, tools):
    return any(Path(directory, name).exists() for tool in tools for name in (tool, tool + ".exe"))


def path_without(tools):
    dirs = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join(d for d in dirs if d and not has_any(d, tools))


def run_block(bash, script, hidden_tools):
    env = {**os.environ, "PATH": path_without(hidden_tools), "HIDE": " ".join(hidden_tools)}
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "rendered.sh"
        script_path.write_bytes((HIDE_CHECK + script).encode("utf-8"))
        result = subprocess.run([bash, script_path.as_posix()], capture_output=True, timeout=120, env=env)
    stdout = result.stdout.decode("utf-8", "replace")
    stderr = result.stderr.decode("utf-8", "replace")
    return result.returncode, stdout, stderr


def check_ok(code, stdout, stderr):
    errors = []
    if code != 0:
        errors.append(f"exit {code}, expected 0 (stderr: {stderr.strip()!r})")
    if stdout.strip() != "ok":
        errors.append(f"stdout {stdout!r}, expected 'ok'")
    errors.extend(check_request_body())
    return errors


def check_request_body():
    if len(FakeOllama.requests) != 1:
        return [f"fake Ollama got {len(FakeOllama.requests)} requests, expected 1"]
    path, body = FakeOllama.requests[0]
    try:
        sent = json.loads(body)
    except ValueError:
        return [f"request body is not JSON: {body!r}"]
    expected = {"model": MODEL, "prompt": TASK, "stream": False}
    if path != "/api/generate" or sent != expected:
        return [f"request {path} {sent!r}, expected /api/generate {expected!r}"]
    return []


def check_failure(code, stdout, stderr, expected_text):
    output = stdout + stderr
    errors = []
    if code == 0:
        errors.append(f"exit 0 on failure (output: {output.strip()!r})")
    if expected_text.lower() not in output.lower():
        errors.append(f"output {output.strip()!r} does not mention {expected_text!r}")
    return errors


def scenarios(server_port):
    dead_port = closed_port()
    return [
        ("ok reply", "ok", server_port, check_ok),
        ("error reply", "error", server_port, lambda *r: check_failure(*r, MISSING_MODEL_ERROR)),
        ("non-JSON reply", "not json", server_port, lambda *r: check_failure(*r, PROXY_PAGE)),
        ("closed port", "ok", dead_port, lambda *r: check_failure(*r, "connect")),
    ]


def toolsets():
    sets = [("python, no jq", ["jq", "node"]), ("node, no jq or python", ["jq", "python3", "python"])]
    if shutil.which("jq"):
        sets.append(("jq", []))
    return sets


def check_block(bash, label, block, server_port):
    failures = []
    for tools_label, hidden in toolsets():
        for name, mode, port, check in scenarios(server_port):
            FakeOllama.mode, FakeOllama.requests = mode, []
            result = run_block(bash, render(block, port), hidden)
            failures.extend(f"{label} [{tools_label}] {name}: {e}" for e in check(*result))
    return failures + check_no_json_tool(bash, label, block, server_port)


def check_no_json_tool(bash, label, block, server_port):
    FakeOllama.mode, FakeOllama.requests = "ok", []
    result = run_block(bash, render(block, server_port), ["jq", "python3", "python", "node"])
    errors = check_failure(*result, "jq, python or node")
    if FakeOllama.requests:
        errors.append("sent a request without a JSON tool")
    return [f"{label} [no JSON tool]: {error}" for error in errors]


def main():
    bash = find_bash()
    if not shutil.which("jq"):
        print("note: jq is not installed here, so the jq branch is not exercised")
    server = start_fake_server()
    failures = []
    try:
        for doc in DOCS:
            block = find_text_mode_block((REPO / doc).read_text(encoding="utf-8"))
            if block is None:
                failures.append(f"{doc}: no text-mode bash block found")
                continue
            failures.extend(check_block(bash, doc, block, server.server_address[1]))
    finally:
        server.shutdown()
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        sys.exit(1)
    print(f"ok - text mode surfaces Ollama errors and works without jq in {len(DOCS)} documents")


if __name__ == "__main__":
    main()
