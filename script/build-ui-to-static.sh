#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/web_ui"

if command -v corepack >/dev/null 2>&1; then
  corepack enable >/dev/null 2>&1 || true
fi

yarn install --frozen-lockfile || yarn install
yarn build

rm -rf "$ROOT_DIR/static/assets"
mkdir -p "$ROOT_DIR/static"
cp -R "$ROOT_DIR/web_ui/dist/assets" "$ROOT_DIR/static/assets"
cp "$ROOT_DIR/web_ui/dist/index.html" "$ROOT_DIR/static/index.html"

echo "Built UI -> $ROOT_DIR/static (served by backend :8001)"

