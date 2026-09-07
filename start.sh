#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "Run python3 bootstrap.py once before starting the app." >&2
  exit 1
fi
exec .venv/bin/python run.py "$@"
