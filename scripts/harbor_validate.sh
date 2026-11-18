#!/usr/bin/env bash
# Validate the Harbor export on the synthetic fixture task FX-01 (population `fixture`, not evidence).
# Decision log D20, D35. Requires Docker and a Harbor 0.25.0 CLI, given as $HARBOR (for example a
# separate venv: `uv venv /tmp/harbor-venv && uv pip install --python /tmp/harbor-venv/bin/python harbor==0.25.0`,
# then HARBOR=/tmp/harbor-venv/bin/harbor). Uses the `local-validation` network variant (D20).
# Expected: lint rc=0; oracle CANDIDATE=reference -> reward 1.0; oracle CANDIDATE=FX-01-wrong -> 0.0; nop -> 0.0.
set -euo pipefail
: "${HARBOR:?set HARBOR to a Harbor 0.25.0 CLI}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
"$ROOT/.venv/bin/python" - "$ROOT" "$WORK" <<'PY'
import sys
from pathlib import Path
from tracecontract.cli import CACHE
from tracecontract.harbor_export import export_task
root, work = Path(sys.argv[1]), Path(sys.argv[2])
fx = root / "tests" / "fixtures" / "harbor_fx01"
export_task(fx / "tasks" / "FX-01", "v1", work / "harbor_task", snapshot_root=fx / "snapshots", cache_dir=CACHE / "images",
            candidates=["FX-01-reference", "FX-01-wrong"], network="local-validation")
PY
cd "$WORK"
"$HARBOR" lint harbor_task && echo "lint rc=0"
"$HARBOR" trial start -p harbor_task -a oracle --ae CANDIDATE=reference --trial-name oracle-reference --trials-dir trials > /dev/null
"$HARBOR" trial start -p harbor_task -a oracle --ae CANDIDATE=FX-01-wrong --trial-name oracle-wrong --trials-dir trials > /dev/null
"$HARBOR" trial start -p harbor_task -a nop --trial-name nop-trial --trials-dir trials > /dev/null
for t in oracle-reference oracle-wrong nop-trial; do
  echo "$t $(grep -o '"reward": [0-9.]*' trials/$t/result.json | head -1)"
done
echo "trials kept in $WORK"
