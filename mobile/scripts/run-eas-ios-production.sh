#!/usr/bin/env bash
# Run from your Mac terminal (not headless CI) the first time so EAS can set up Apple credentials.
# If your shell exports CI=1 (e.g. Cursor), it is cleared here so the CLI can prompt when needed.
set -euo pipefail
cd "$(dirname "$0")/.."
unset CI
export EAS_BUILD_NO_EXPO_GO_WARNING=1
exec npx eas-cli@latest build --platform ios --profile production "$@"
