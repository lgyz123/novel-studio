#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$WORKSPACE_DIR/app/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BASHRC_FILE="${HOME}/.bashrc"
ZSHRC_FILE="${HOME}/.zshrc"
SNIPPET_BEGIN="# >>> novel-studio codespaces >>>"
SNIPPET_END="# <<< novel-studio codespaces <<<"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$WORKSPACE_DIR/app/requirements.txt"

SNIPPET=$(cat <<EOF
${SNIPPET_BEGIN}
if [ -n "\${CODESPACES:-}" ] && [ -f "$VENV_DIR/bin/activate" ]; then
  if [ "\${VIRTUAL_ENV:-}" != "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
  fi
fi
${SNIPPET_END}
EOF
)

update_rc() {
  local file="$1"
  touch "$file"
  python3 - <<PY
from pathlib import Path
path = Path(${file@Q})
text = path.read_text(encoding="utf-8")
begin = ${SNIPPET_BEGIN@Q}
end = ${SNIPPET_END@Q}
snippet = ${SNIPPET@Q}
if begin in text and end in text:
    start = text.index(begin)
    finish = text.index(end) + len(end)
    new_text = text[:start].rstrip() + "\n\n" + snippet + "\n"
else:
    new_text = text.rstrip() + "\n\n" + snippet + "\n"
path.write_text(new_text, encoding="utf-8")
PY
}

update_rc "$BASHRC_FILE"
update_rc "$ZSHRC_FILE"

echo "Codespaces setup complete. Virtual environment: $VENV_DIR"
