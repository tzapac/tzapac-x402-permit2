#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-}"
OUT_DIR="${2:-reports}"
PATCHES_FLAG="${3:-}"

if [[ -z "$BASE_REF" ]]; then
  if git show-ref --verify --quiet refs/remotes/upstream/master; then
    BASE_REF="upstream/master"
  elif git show-ref --verify --quiet refs/remotes/origin/master; then
    BASE_REF="origin/master"
  else
    BASE_REF="$(git rev-list --max-parents=0 HEAD)"
  fi
fi

HEAD_REF="$(git rev-parse HEAD)"
RANGE="${BASE_REF}..${HEAD_REF}"
DATE_UTC="$(date -u +"%Y-%m-%d %H:%M:%SZ")"

if git diff --quiet "$RANGE"; then
  BASE_REF="$(git rev-list --max-parents=0 HEAD)"
  RANGE="${BASE_REF}..${HEAD_REF}"
fi

mkdir -p "$OUT_DIR"
REPORT_FILE="${OUT_DIR}/permit2-change-report.md"
DIFF_FILE="${OUT_DIR}/permit2-change.diff"

cat >"$REPORT_FILE" <<EOF
# Change Report

## Metadata
- Generated: ${DATE_UTC}
- Base ref: ${BASE_REF}
- Head ref: ${HEAD_REF}
- Range: ${RANGE}

## Summary Stats

EOF

git diff --stat "$RANGE" >>"$REPORT_FILE"

cat >>"$REPORT_FILE" <<EOF

## Changed Files (Per-File Diff)
EOF

git diff --name-status --find-renames "$RANGE" | while read -r status path_a path_b; do
  if [[ -z "$status" ]]; then
    continue
  fi

  if [[ "$status" =~ ^R ]]; then
    old_path="$path_a"
    new_path="$path_b"
    cat >>"$REPORT_FILE" <<EOF

### Renamed: ${old_path} -> ${new_path}

\`\`\`diff
EOF
    git diff "$RANGE" -- "$old_path" "$new_path" >>"$REPORT_FILE"
    echo "\`\`\`" >>"$REPORT_FILE"
    continue
  fi

  cat >>"$REPORT_FILE" <<EOF

### ${status} ${path_a}

\`\`\`diff
EOF
  git diff "$RANGE" -- "$path_a" >>"$REPORT_FILE"
  echo "\`\`\`" >>"$REPORT_FILE"
done

cat >>"$REPORT_FILE" <<EOF

## Unchanged Top-Level Entries
EOF

git ls-tree --name-only "$BASE_REF" | while read -r entry; do
  if [[ -z "$entry" ]]; then
    continue
  fi
  if ! git diff --name-only "$RANGE" -- "$entry" | grep -q .; then
    echo "- $entry" >>"$REPORT_FILE"
  fi
done

git diff "$RANGE" >"$DIFF_FILE"

if [[ "$PATCHES_FLAG" == "--patches" ]]; then
  PATCH_DIR="${OUT_DIR}/patches"
  mkdir -p "$PATCH_DIR"
  git format-patch "$RANGE" -o "$PATCH_DIR" >/dev/null
fi

echo "Report: ${REPORT_FILE}"
echo "Diff: ${DIFF_FILE}"
if [[ "$PATCHES_FLAG" == "--patches" ]]; then
  echo "Patches: ${PATCH_DIR}"
fi
