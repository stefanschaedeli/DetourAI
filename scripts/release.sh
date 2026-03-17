#!/usr/bin/env bash
# Usage: ./scripts/release.sh [patch|minor|major]
# Default: patch — increments the last version number
set -euo pipefail

BUMP="${1:-patch}"

# Get latest version tag (vX.Y.Z)
LATEST=$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
if [[ -z "$LATEST" ]]; then
  echo "Error: no version tag found (expected vX.Y.Z)" >&2
  exit 1
fi

# Parse
MAJOR=$(echo "$LATEST" | cut -d. -f1 | tr -d 'v')
MINOR=$(echo "$LATEST" | cut -d. -f2)
PATCH=$(echo "$LATEST" | cut -d. -f3)

case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  *)
    echo "Usage: $0 [patch|minor|major]" >&2
    exit 1
    ;;
esac

NEW_VERSION="v${MAJOR}.${MINOR}.${PATCH}"
RELEASE_TAG="release/${NEW_VERSION}"

echo "Current: $LATEST"
echo "Next:    $NEW_VERSION  (release tag: $RELEASE_TAG)"
echo ""
read -r -p "Push and trigger pipeline? [y/N] " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

git tag "$NEW_VERSION"
git tag "$RELEASE_TAG"
git push origin "$NEW_VERSION" "$RELEASE_TAG"

echo ""
echo "✓ Tags pushed: $NEW_VERSION  $RELEASE_TAG"
echo "→ Pipeline: https://github.com/stefanschaedeli/travelman3/actions"
