#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

VENV_DIR=".venv"
PORT="${PORT:-8000}"

# Prefer Python 3.12 or 3.11 (pydantic-core does not support 3.14 yet)
find_python() {
  for cmd in python3.12 python3.11 python3.13 python3; do
    if command -v "$cmd" &>/dev/null; then
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
      if [ -n "$ver" ] && [ "$ver" != "3.14" ]; then
        echo "$cmd"
        return
      fi
    fi
  done
  return 1
}

PYTHON=$(find_python) || true
if [ -z "$PYTHON" ]; then
  echo "ERROR: No compatible Python found. Python 3.14 is not yet supported by pydantic."
  echo "Install Python 3.12 or 3.11, for example:"
  echo "  brew install python@3.12"
  echo "  # or: pyenv install 3.12.0 && pyenv local 3.12.0"
  echo "Then remove the existing venv and run again:"
  echo "  rm -rf $VENV_DIR && ./start.sh"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment with $PYTHON..."
  "$PYTHON" -m venv "$VENV_DIR"
elif [ -x "$VENV_DIR/bin/python" ]; then
  venv_ver=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
  if [ "$venv_ver" = "3.14" ]; then
    echo "ERROR: Existing .venv uses Python 3.14, which is not supported."
    echo "Remove it and run again (script will use a compatible Python if installed):"
    echo "  rm -rf $VENV_DIR && ./start.sh"
    echo "Install Python 3.12 if needed: brew install python@3.12"
    exit 1
  fi
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/installed.flag" ] || [ "requirements.txt" -nt "$VENV_DIR/installed.flag" ]; then
  echo "Installing dependencies..."
  pip install -q -r requirements.txt
  touch "$VENV_DIR/installed.flag"
fi

# Create application database if it does not exist (uses .env / app.config)
"$VENV_DIR/bin/python" ensure_db.py || true

echo "Starting FastAPI backend on http://0.0.0.0:${PORT}"
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
