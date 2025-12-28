#!/usr/bin/env bash
set -euo pipefail

echo "=== RUN.SH ==="
echo "pwd: $(pwd)"
echo "listing:"
ls -la

python3 app.py
