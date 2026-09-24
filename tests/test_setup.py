import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SETUP = REPO / "commands" / "setup.md"
FENCE = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
BASH_RULE = re.compile(r"Bash\(([^)]*)\)")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
OLLAMA_URL = re.compile(r"http://(localhost|127\.0\.0\.1):11434")
KEYWORDS = {"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "!", "{", "}"}
LOOP_HEADS = {"for", "case", "select", "function"}
BUILTINS = {"echo", "printf", "[", "[[", "test", "set", "exit", "return", "break", "continue", "true", "false", "local", ":"}
CAPPED_MODEL = "ollama-rescue-mechanical"

SHIMS = r"""
ollama() {
  printf '%s\n' "$@" > "$OUT/ollama_args"
  while [ $# -gt 0 ]; do
    if [ "$1" = "-f" ]; then cp "$2" "$OUT/modelfile_copy"; fi
    shift
  done
}
"""


class Splitter:
    def __init__(self, script):
        self.script, self.i = script, 0
        self.segments, self.buffers, self.contexts = [], [[]], ["cmd"]

    def run(self):
        while self.i < len(self.script):
            self.step()
        self.flush()
        return ["".join(segment).strip() for segment in self.segments if "".join(segment).strip()]

    def flush(self):
        self.segments.append(self.buffers[-1])
        self.buffers[-1] = []

    def emit(self, text, width=1):
        self.buffers[-1].append(text)
        self.i += width

    def step(self):
        ch, pair = self.script[self.i], self.script[self.i:self.i + 2]
        if self.contexts[-1] == "'":
            return self.step_single_quote(ch)
        if ch == "\\":
            return self.emit(pair, 2)
        if pair == "$(":
            return self.open_substitution()
        if self.contexts[-1] == '"':
            return self.step_double_quote(ch)
        return self.step_command(ch, pair)

    def step_single_quote(self, ch):
        if ch == "'":
            self.contexts.pop()
        self.emit(ch)

    def step_double_quote(self, ch):
        if ch == '"':
            self.contexts.pop()
        self.emit(ch)

    def open_substitution(self):
        self.buffers.append([])
        self.contexts.append("cmd")
        self.i += 2

    def close_substitution(self):
        self.flush()
        self.buffers.pop()
        self.contexts.pop()
        self.i += 1

    def step_command(self, ch, pair):
        if ch in "'\"":
            self.contexts.append(ch)
            return self.emit(ch)
        if ch == ")" and len(self.contexts) > 1:
            return self.close_substitution()
        if pair in ("&&", "||"):
            self.flush()
            self.i += 2
            return None
        if ch in ";|\n()":
            self.flush()
            self.i += 1
            return None
        return self.emit(ch)


def strip_heredoc_bodies(script):
    kept, delimiter = [], None
    for line in script.splitlines():
        if delimiter is not None:
            delimiter = None if line.strip() == delimiter else delimiter
            continue
        kept.append(line)
        match = HEREDOC.search(line)
        delimiter = match.group(1) if match else None
    return "\n".join(kept)


def words(segment):
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def drop_keywords_and_assignments(tokens):
    start = 0
    while start < len(tokens) and (tokens[start] in KEYWORDS or re.match(r"^\w+=", tokens[start])):
        start += 1
    return tokens[start:]


def external_command(segment):
    tokens = drop_keywords_and_assignments(words(segment))
    if not tokens or tokens[0] in LOOP_HEADS or tokens[0] in BUILTINS:
        return None
    return " ".join(tokens)


def commands_in(script):
    joined = strip_heredoc_bodies(script).replace("\\\n", " ")
    found = (external_command(segment) for segment in Splitter(joined).run())
    return [command for command in found if command]


def dedent(block, width):
    return "".join(line[width:] if line.startswith(" " * width) else line for line in block.splitlines(True))


def bash_blocks(text):
    return [dedent(match.group(2), len(match.group(1))) for match in FENCE.finditer(text)]


def allowed_bash_rules(text):
    match = FRONTMATTER.match(text.replace("\r\n", "\n"))
    if match is None:
        return []
    fields = match.group(1).splitlines()
    return BASH_RULE.findall(next((field for field in fields if field.startswith("allowed-tools:")), ""))


def is_allowed(command, rules):
    return any(rule_matches(rule, command) for rule in rules)


def rule_matches(rule, command):
    if rule.endswith(":*"):
        prefix = rule[:-2]
        return command == prefix or command.startswith(prefix + " ")
    return command == rule


def check_extractor():
    cases = [
        ('X=$(curl -sS "http://a/b") || echo "no | pipe"', ["curl -sS http://a/b"]),
        ("cat > \"$F\" <<'EOF'\nFROM rm -rf |\nEOF\nollama create m -f \"$F\"", ["cat > $F <<EOF", "ollama create m -f $F"]),
        ("if jq --version >/dev/null 2>&1; then echo a; elif node -v; then :; fi", ["jq --version >/dev/null 2>&1", "node -v"]),
        ("re='\"v\":\"([0-9]+)\"'\n[[ $a =~ $re ]] && [ \"$b\" -ge 3 ]", []),
        ('echo "x $(uname -s) y" | tr a b', ["uname -s", "tr a b"]),
    ]
    failures = []
    for script, expected in cases:
        got = commands_in(script)
        if got != expected:
            failures.append(f"extractor: {script!r} gave {got!r}, expected {expected!r}")
    return failures


def check_allowed_tools(doc):
    text = doc.read_text(encoding="utf-8")
    rules = allowed_bash_rules(text)
    commands = [command for block in bash_blocks(text) for command in commands_in(block)]
    return [
        f"{doc.relative_to(REPO).as_posix()}: `{command}` is not covered by allowed-tools {rules}"
        for command in commands
        if not is_allowed(command, rules)
    ]


class FakeOllama(BaseHTTPRequestHandler):
    version = "0.33.3"
    models = {CAPPED_MODEL}
    paths = []

    def do_GET(self):
        FakeOllama.paths.append(("GET", self.path))
        if self.path == "/api/version":
            return self.reply(200, {"version": FakeOllama.version})
        return self.reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        FakeOllama.paths.append(("POST", self.path))
        if self.path != "/v1/messages":
            return self.reply(404, {"error": "not found"})
        if body.get("model") not in FakeOllama.models:
            message = f"model '{body.get('model')}' not found"
            return self.reply(404, {"type": "error", "error": {"type": "not_found_error", "message": message}})
        return self.reply(200, {"type": "message", "content": [{"type": "text", "text": "hi"}]})

    def reply(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
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


def find_bash():
    bash = shutil.which("bash")
    if bash is None or "system32" in bash.lower():
        sys.exit("FAIL: Git Bash not found on PATH (run from Git Bash: bash tests/run.sh)")
    return bash


def run_script(bash, script, port):
    rendered = OLLAMA_URL.sub(f"http://127.0.0.1:{port}", script)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        out.mkdir()
        script_path = Path(tmp) / "rendered.sh"
        script_path.write_bytes(f'OUT="{out.as_posix()}"\nTMPDIR="{out.as_posix()}"\n{SHIMS}\n{rendered}'.encode("utf-8"))
        result = subprocess.run([bash, script_path.as_posix()], capture_output=True, timeout=120)
        artifacts = {path.name: path.read_text(encoding="utf-8") for path in out.iterdir()}
    return result.returncode, result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace"), artifacts


def find_block(text, marker):
    return next((block for block in bash_blocks(text) if marker in block), None)


VERSION_SCENARIOS = [
    ("0.33.3", "supported"),
    ("0.34.0-rc1", "supported"),
    ("1.0.0", "supported"),
    ("0.32.5", "older than 0.33"),
    ("0.9.1", "older than 0.33"),
]


def check_version_step(bash, text, port):
    block = find_block(text, "/api/version")
    if block is None:
        return ["setup.md: no bash block queries /api/version for the server version"]
    failures = []
    for version, expected in VERSION_SCENARIOS:
        FakeOllama.version, FakeOllama.paths = version, []
        _code, output, _artifacts = run_script(bash, block, port)
        if version not in output or expected not in output:
            failures.append(f"version step with {version}: output {output.strip()!r}, expected {version!r} and {expected!r}")
        if any(method == "POST" for method, _path in FakeOllama.paths):
            failures.append(f"version step with {version} sent a model request: {FakeOllama.paths}")
    return failures


PROBE_SCENARIOS = [
    ("capped model installed", {CAPPED_MODEL}, "Anthropic API: sí"),
    ("capped model missing", set(), "model not found"),
]


def check_probe_step(bash, text, port):
    block = find_block(text, "/v1/messages")
    if block is None:
        return ["setup.md: no bash block probes /v1/messages"]
    if re.search(r"<[a-z][^<>\n]*>", block):
        return ["setup.md: the /v1/messages probe still has a placeholder tag"]
    failures = []
    for name, models, expected in PROBE_SCENARIOS:
        FakeOllama.version, FakeOllama.models, FakeOllama.paths = "0.33.3", models, []
        _code, output, _artifacts = run_script(bash, block, port)
        if expected not in output:
            failures.append(f"probe step, {name}: output {output.strip()!r}, expected {expected!r}")
    FakeOllama.models = {CAPPED_MODEL}
    return failures


def check_modelfile_step(bash, text, port):
    block = find_block(text, "ollama create")
    if block is None:
        return ["setup.md: no bash block builds the capped model"]
    if "/tmp" in block.replace("${TMPDIR:-/tmp}", ""):
        return ["setup.md: the Modelfile path hardcodes /tmp instead of honouring $TMPDIR"]
    _code, output, artifacts = run_script(bash, block.replace("<base-tag>", "devstral:24b"), port)
    modelfile = artifacts.get("modelfile_copy", "")
    failures = []
    if "FROM devstral:24b" not in modelfile or "PARAMETER num_ctx 32768" not in modelfile:
        failures.append(f"Modelfile step: $TMPDIR copy {modelfile!r} (output {output.strip()!r})")
    if CAPPED_MODEL not in artifacts.get("ollama_args", ""):
        failures.append(f"Modelfile step: ollama args {artifacts.get('ollama_args')!r}")
    return failures


def main():
    failures = check_extractor()
    for doc in sorted((REPO / "commands").glob("*.md")):
        failures.extend(check_allowed_tools(doc))
    bash = find_bash()
    text = SETUP.read_text(encoding="utf-8")
    server = start_fake_server()
    try:
        port = server.server_address[1]
        failures.extend(check_version_step(bash, text, port))
        failures.extend(check_probe_step(bash, text, port))
        failures.extend(check_modelfile_step(bash, text, port))
    finally:
        server.shutdown()
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        sys.exit(1)
    print("ok - /ollama:setup permissions cover its commands; version, probe and Modelfile steps behave")


if __name__ == "__main__":
    main()
