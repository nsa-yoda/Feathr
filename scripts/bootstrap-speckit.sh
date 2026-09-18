#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v specify >/dev/null 2>&1; then
  echo "ERROR: 'specify' is not installed. Install Spec Kit first, preferably:" >&2
  echo "  uv tool install specify-cli" >&2
  exit 1
fi

specify version

CONSTITUTION_BACKUP="$(mktemp)"
cp .specify/memory/constitution.md "$CONSTITUTION_BACKUP"
trap 'rm -f "$CONSTITUTION_BACKUP"' EXIT

if [ ! -d .agents/skills/speckit-specify ]; then
  echo "Initializing Spec Kit for Codex..."
  specify init --here --force --non-interactive --integration codex --script sh
  cp "$CONSTITUTION_BACKUP" .specify/memory/constitution.md
else
  echo "Codex Spec Kit skills already present; preserving existing initialization."
fi

echo "Ensuring mandatory review extensions are installed..."
set +e
specify extension add staff-review --from https://github.com/arunt14/spec-kit-staff-review/archive/refs/tags/v1.0.0.zip
STAFF_RC=$?
specify extension add review --from https://github.com/ismaelJimenez/spec-kit-review/archive/refs/tags/v1.0.1.zip
REVIEW_RC=$?
set -e

# Re-running extension add may return non-zero when an extension already exists, so the
# authoritative verification is the installed skill/extension inventory below.
specify extension list

if [ "$STAFF_RC" -ne 0 ]; then
  echo "NOTE: staff-review add returned non-zero. This is acceptable only if it is already installed; verify the list above." >&2
fi
if [ "$REVIEW_RC" -ne 0 ]; then
  echo "NOTE: review add returned non-zero. This is acceptable only if it is already installed; verify the list above." >&2
fi

# The extension installer for the active Codex integration should materialize review skills.
# Fail the handoff bootstrap if neither a matching skill nor obvious extension artifact exists.
if ! find .agents/skills -maxdepth 1 -type d -iname '*staff*review*' -print -quit 2>/dev/null | grep -q .; then
  echo "ERROR: staff-review Codex skill not found under .agents/skills. Resolve extension installation before implementation." >&2
  exit 1
fi
if ! find .agents/skills -maxdepth 1 -type d -iname '*review*' ! -iname '*staff*review*' -print -quit 2>/dev/null | grep -q .; then
  echo "ERROR: multi-agent review Codex skill not found under .agents/skills. Resolve extension installation before implementation." >&2
  exit 1
fi

echo
echo "Bootstrap complete. Restart/re-open Codex if newly installed skills are not visible."
echo "Read CODEX-HANDOFF.md before beginning Feature 001."
