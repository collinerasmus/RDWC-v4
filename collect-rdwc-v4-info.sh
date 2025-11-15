#!/usr/bin/env bash
set -euo pipefail

OWNER="collinerasmus"
REPO="rdwc-v4"
OUTDIR="${REPO}-checks-$(date +%Y%m%d%H%M%S)"
mkdir -p "$OUTDIR"

# Check dependencies
missing=()
command -v jq >/dev/null 2>&1 || missing+=("jq")
command -v curl >/dev/null 2>&1 || missing+=("curl")
GH_AVAILABLE=0
if command -v gh >/dev/null 2>&1; then
  GH_AVAILABLE=1
fi

if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing dependencies: ${missing[*]}" >&2
  echo "Install them and re-run. On macOS: brew install jq curl gh. On Debian/Ubuntu: sudo apt install -y jq curl gh" >&2
  exit 1
fi

# Helper: try gh first, fallback to curl with GITHUB_TOKEN
call_api() {
  local path="$1"
  if [ "$GH_AVAILABLE" -eq 1 ] && gh auth status >/dev/null 2>&1; then
    gh api "$path"
  else
    if [ -z "${GITHUB_TOKEN:-}" ]; then
      echo "ERROR: gh CLI not authenticated and GITHUB_TOKEN not set. Export GITHUB_TOKEN or run 'gh auth login' and re-run." >&2
      return 2
    fi
    curl -s -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com${path}"
  fi
}

echo "Collecting repo metadata..."
if call_api "/repos/$OWNER/$REPO" > "$OUTDIR/repo.json"; then
  :
else
  echo "Failed to fetch repo metadata. Ensure gh is authenticated or GITHUB_TOKEN is set and has repo scope." >&2
fi

echo "Collecting authenticated user's repo permissions (if available)..."
if [ -s "$OUTDIR/repo.json" ]; then
  jq '.permissions // {}' "$OUTDIR/repo.json" > "$OUTDIR/permissions.json" || echo "{}" > "$OUTDIR/permissions.json"
else
  echo "{}" > "$OUTDIR/permissions.json"
fi

echo "Listing collaborators..."
call_api "/repos/$OWNER/$REPO/collaborators?per_page=100" > "$OUTDIR/collaborators.json" || echo "[]" > "$OUTDIR/collaborators.json"

echo "Listing teams (if any)..."
call_api "/repos/$OWNER/$REPO/teams" > "$OUTDIR/teams.json" || echo "[]" > "$OUTDIR/teams.json"

echo "Checking GitHub App installation for this repo..."
# repository installation endpoint may return 404 if not installed or token lacks permission
if [ -n "${GITHUB_TOKEN:-}" ]; then
  curl -s -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/$OWNER/$REPO/installation" > "$OUTDIR/installation.json" || echo "{}" > "$OUTDIR/installation.json"
else
  # Try with gh api - may 404 if not enough perms
  if [ "$GH_AVAILABLE" -eq 1 ]; then
    gh api "repos/$OWNER/$REPO/installation" > "$OUTDIR/installation.json" 2>/dev/null || echo "{}" > "$OUTDIR/installation.json"
  else
    echo "{}" > "$OUTDIR/installation.json"
  fi
fi

echo "Gathering Actions permissions, workflows and secrets..."
call_api "/repos/$OWNER/$REPO/actions/permissions" > "$OUTDIR/actions_permissions.json" 2>/dev/null || echo "{}" > "$OUTDIR/actions_permissions.json"
call_api "/repos/$OWNER/$REPO/actions/workflows" > "$OUTDIR/workflows.json" 2>/dev/null || echo '{"workflows":[]}' > "$OUTDIR/workflows.json"
call_api "/repos/$OWNER/$REPO/actions/secrets?per_page=100" > "$OUTDIR/actions_secrets.json" 2>/dev/null || echo '{"secrets":[]}' > "$OUTDIR/actions_secrets.json"

echo "Listing branches and gathering branch protection for protected branches..."
call_api "/repos/$OWNER/$REPO/branches?per_page=100" > "$OUTDIR/branches.json" 2>/dev/null || echo "[]" > "$OUTDIR/branches.json"

# For each branch, try to fetch protection (non-fatal)
if [ -s "$OUTDIR/branches.json" ]; then
  jq -r '.[].name' "$OUTDIR/branches.json" | while read -r BR; do
    safeBR=$(printf '%s' "$BR" | sed 's/ /%20/g')
    echo "  - checking protection for branch: $BR"
    if call_api "/repos/$OWNER/$REPO/branches/$safeBR/protection" > "$OUTDIR/protection_${BR}.json" 2>/dev/null; then
      :
    else
      echo "{}" > "$OUTDIR/protection_${BR}.json"
    fi
  done
fi

echo "Done. Results saved to: $OUTDIR"
echo
echo "Please compress the folder and paste the following files back into the chat for analysis:"
echo "  repo.json, permissions.json, collaborators.json, installation.json, actions_permissions.json, workflows.json, actions_secrets.json, and protection_*.json"
