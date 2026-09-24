#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.." || exit 1
PYTHON=$(command -v python3 || command -v python)
status=0
echo "== tests/validate.py"
"$PYTHON" -X utf8 tests/validate.py || status=1
if [ "${1:-}" = "--quick" ]; then
  exit $status
fi
for test in tests/test_*.py; do
  echo "== $test"
  "$PYTHON" -X utf8 "$test" || status=1
done
for test in tests/test_*.sh; do
  [ -e "$test" ] || continue
  echo "== $test"
  bash "$test" || status=1
done
exit $status
