#!/usr/bin/env bash
# Submit the latest EAS iOS build to App Store Connect / TestFlight.
#
# Usage (run in Terminal.app on your Mac — interactive prompts need a real TTY):
#   cd maxapp/mobile
#   chmod +x ./scripts/submit-ios-testflight.sh
#
# Option A — you know your App Store Connect App ID (numeric, from App Information → Apple ID):
#   ./scripts/submit-ios-testflight.sh 1234567890
#
# Option B — omit the ID; EAS may prompt (first time) or use values already in eas.json:
#   ./scripts/submit-ios-testflight.sh
#
# First-time submit often requires App Store Connect API key or app-specific password.
# See: https://docs.expo.dev/submit/ios/
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "${1:-}" ]]; then
  jq --arg id "$1" '.submit.production.ios.ascAppId = $id' eas.json > eas.json.tmp && mv eas.json.tmp eas.json
  echo "Set submit.production.ios.ascAppId to $1 in eas.json"
fi

unset CI
export EAS_BUILD_NO_EXPO_GO_WARNING="${EAS_BUILD_NO_EXPO_GO_WARNING:-1}"

# Note: Do not pass --what-to-test here — it maps to a changelog API that requires an Expo Enterprise plan.
# Add TestFlight “What to Test” text in App Store Connect after the build processes if you want.
exec npx eas-cli@latest submit --platform ios --profile production --latest --wait
