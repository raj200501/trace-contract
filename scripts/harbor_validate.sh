#!/usr/bin/env bash
# Validate the Harbor export on the synthetic fixture task FX-01 (population `fixture`, not evidence).
# Decision log D20, D35, D39, D40, D45. Requires Docker and a Harbor 0.25.0 CLI, given as $HARBOR (for example a
# separate venv: `uv venv /tmp/harbor-venv && uv pip install --python /tmp/harbor-venv/bin/python harbor==0.25.0`,
# then HARBOR=/tmp/harbor-venv/bin/harbor). Uses the `local-validation` network variant (D20). HARBOR_TELEMETRY=0
# keeps Harbor from sending usage events.
#
# Trials and expected outcomes:
#   oracle-reference  oracle, CANDIDATE=reference                -> reward 1.0
#   oracle-wrong      oracle, CANDIDATE=FX-01-wrong              -> reward 0.0
#   nop-trial         nop agent                                  -> reward 0.0
#   probe-timeout     a candidate that plants reward files in /logs/verifier, starts a detached process that
#                     keeps planting, and hangs in every sandbox call. Exported with timeout_sec=60 (runner timeout
#                     30 s); FX-01's verifier makes two calls of up to 20 s each, so the grader's runner timeout
#                     fires                                      -> no reward (Harbor: RewardFileNotFoundError)
#   probe-collect     a candidate that plants reward files and then fails a sandbox call that a probe module makes
#                     while pytest collects it. FX-01's own tests reach candidate code only inside test functions,
#                     so a candidate cannot break their collection; the probe verifier (FX-01's tests plus that
#                     module) stands for a verifier that derives its cases from candidate code
#                                                                -> no reward (Harbor: RewardFileNotFoundError)
# The probes are tamper_probe candidates added to a temporary copy of the fixture; the fixture is not changed.
# With CONTROL_REV=<git revision>, both probes also run against the exporter of that revision, recorded under
# control/ (for example CONTROL_REV=c5ede4c, the last exporter before tc-harbor-export/0.2.0, which shows that
# the probes catch the defect fixed in 0.2.0; there they are expected to yield reward 1.0).
#
# The lint output, each trial's result.json and verifier/tc_detail.json, and summary.json are copied to
# results/harbor_validation/<exporter version>/, with the temporary directory and the Harbor installation
# replaced by placeholders, so the claim can be checked. Exit code 1 if any trial differs from its expected outcome.
set -euo pipefail
: "${HARBOR:?set HARBOR to a Harbor 0.25.0 CLI}"
export HARBOR_TELEMETRY=0 NO_COLOR=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
"$ROOT/.venv/bin/python" - "$ROOT" "$WORK" "${CONTROL_REV:-}" <<'PY'
import importlib.util, json, shutil, subprocess, sys
from pathlib import Path
from tracecontract.cli import CACHE
from tracecontract.harbor_export import export_task
from tracecontract.patches import diff_dirs
from tracecontract.schemas import Candidate, CandidateOrigin, CheckSpec, Split, VerifierSpec, sha256_text
from tracecontract.store import dump, load
from tracecontract.verifier import checks_sha256, hash_test_dir

root, work, control_rev = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
fx = root / "tests" / "fixtures" / "harbor_fx01"
cache = CACHE / "images"
export_task(fx / "tasks" / "FX-01", "v1", work / "harbor_task", snapshot_root=fx / "snapshots", cache_dir=cache,
            candidates=["FX-01-reference", "FX-01-wrong"], network="local-validation")

# Probe candidates. Each one tries to leave a passing reward where Harbor reads it, then makes the grade end
# without one: by hanging past the runner timeout, or by failing a sandbox call made at collection time.
PLANT = r'''import os, sys, time

REWARDS = {"reward.json": '{"reward": 1.0, "R1": 1.0}\n', "reward.txt": "1.0\n"}


def plant():
    for name, text in REWARDS.items():
        try:
            with open(os.path.join("/logs/verifier", name), "w") as fh:
                fh.write(text)
            print(f"probe: planted {name}", file=sys.stderr)
        except OSError as exc:
            print(f"probe: could not plant {name}: {exc!r}", file=sys.stderr)
'''
PROBES = {
    "FX-01-probe-timeout": PLANT + r'''

def keep_planting():
    """A detached process (own session, re-parented) that keeps planting while the grader runs."""
    pid = os.fork()
    if pid == 0:
        os.setsid()
        if os.fork() == 0:
            while True:
                plant()
                time.sleep(0.2)
        os._exit(0)
    os.waitpid(pid, 0)


def add(a, b):
    plant()
    keep_planting()
    time.sleep(3600)
    return a + b
''',
    "FX-01-probe-collect": PLANT + r'''

def add(a, b):
    plant()
    raise RuntimeError("probe: fail the collection-time sandbox call")
''',
}
COLLECT_MODULE = r'''"""Probe module of scripts/harbor_validate.sh: a sandbox call made while pytest collects this module.

It stands for a verifier that derives its cases from candidate code; the module fails to collect when the call fails.
"""
from tc_sandbox import run_python

CALL = run_python("from calc import add\nresult = add(1, 1)")
if not (CALL.ok and CALL.value == 2):
    raise RuntimeError(f"collection-time sandbox call failed: {CALL!r}")


def test_collection_time_call():
    assert CALL.value == 2
'''

pfx = work / "probe_fixture"
shutil.copytree(fx, pfx)
task, base = pfx / "tasks" / "FX-01", pfx / "snapshots" / "FX-01"
manifest = json.loads((task / "task.json").read_text())
for cid, src in PROBES.items():
    d = work / "probe_src" / cid
    shutil.copytree(base, d)
    (d / "calc.py").write_text(src)
    patch = diff_dirs(base, d)
    dump(Candidate(candidate_id=cid, task_id="FX-01", origin=CandidateOrigin.tamper_probe, split=Split.dev, patch=patch,
                   patch_sha256=sha256_text(patch), produced_by="scripts/harbor_validate.sh",
                   description="Harbor validation probe: plants reward files, then ends the grade without a reward"),
         task / "candidates" / f"{cid}.json")
    manifest["candidates"].append(f"candidates/{cid}.json")
v1 = load(task / "verifiers" / "v1" / "spec.json", VerifierSpec)
shutil.copytree(task / "verifiers" / "v1" / "tests", task / "verifiers" / "v1-collect-probe" / "tests")
(task / "verifiers" / "v1-collect-probe" / "tests" / "test_collect_probe.py").write_text(COLLECT_MODULE)
probe_spec = v1.model_copy(update={
    "verifier_id": "v1-collect-probe", "test_dir": "verifiers/v1-collect-probe/tests",
    "checks": [*v1.checks, CheckSpec(check_id="test_collect_probe.py::test_collection_time_call", requirement_ids=["R1"])],
    "content_sha256": hash_test_dir(task / "verifiers" / "v1-collect-probe" / "tests")})
dump(probe_spec.model_copy(update={"checks_sha256": checks_sha256(probe_spec)}), task / "verifiers" / "v1-collect-probe" / "spec.json")
manifest["verifiers"].append("verifiers/v1-collect-probe/spec.json")
(task / "task.json").write_text(json.dumps(manifest, indent=2) + "\n")


def export_probes(export, dest: Path) -> None:
    kw = dict(snapshot_root=pfx / "snapshots", cache_dir=cache, network="local-validation")
    export(task, "v1", dest / "probe_timeout_task", candidates=["FX-01-probe-timeout"], timeout_sec=60.0, **kw)
    export(task, "v1-collect-probe", dest / "probe_collect_task", candidates=["FX-01-probe-collect"], **kw)


export_probes(export_task, work)
if control_rev:
    src = subprocess.run(["git", "-C", str(root), "show", f"{control_rev}:src/tracecontract/harbor_export.py"],
                         capture_output=True, text=True, check=True).stdout
    (work / "control_harbor_export.py").write_text(src)
    spec = importlib.util.spec_from_file_location("tracecontract._control_harbor_export", work / "control_harbor_export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    export_probes(mod.export_task, work / "control")
PY
cd "$WORK"
mkdir -p logs
set +e
"$HARBOR" lint harbor_task > lint.txt 2>&1
LINT_RC=$?
set -e
echo "lint rc=$LINT_RC" | tee -a lint.txt
run_trial() {  # <task dir> <trial name> <harbor args>...; Harbor's own output stays in $WORK/logs
  "$HARBOR" trial start -p "$1" --trial-name "$2" --trials-dir trials "${@:3}" > "logs/$2.log" 2>&1 \
    || echo "$2: harbor exited with $?" | tee -a logs/harbor_rc.txt
}
run_trial harbor_task oracle-reference -a oracle --ae CANDIDATE=reference
run_trial harbor_task oracle-wrong -a oracle --ae CANDIDATE=FX-01-wrong
run_trial harbor_task nop-trial -a nop
run_trial probe_timeout_task probe-timeout -a oracle --ae CANDIDATE=FX-01-probe-timeout
run_trial probe_collect_task probe-collect -a oracle --ae CANDIDATE=FX-01-probe-collect
if [ -n "${CONTROL_REV:-}" ]; then
  run_trial control/probe_timeout_task control-probe-timeout -a oracle --ae CANDIDATE=FX-01-probe-timeout
  run_trial control/probe_collect_task control-probe-collect -a oracle --ae CANDIDATE=FX-01-probe-collect
fi
HARBOR_VENV="$(cd "$(dirname "$(readlink -f "$HARBOR")")/.." && pwd)"
"$ROOT/.venv/bin/python" - "$ROOT" "$WORK" "$("$HARBOR" --version 2>/dev/null || echo unknown)" "$LINT_RC" \
  "$HARBOR_VENV" "${CONTROL_REV:-}" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
from tracecontract.harbor_export import EXPORTER_VERSION
from tracecontract.sandbox.docker_runner import HARNESS_VERSION

root, work, harbor_version, lint_rc, harbor_venv, control_rev = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].strip(), \
    int(sys.argv[4]), sys.argv[5], sys.argv[6]
out = root / "results" / "harbor_validation" / EXPORTER_VERSION.replace("/", "-")
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
# The temporary directory is not kept, and the Harbor installation path is local to this host.
PLACEHOLDERS = sorted({str(work): "<work>", str(work.resolve()): "<work>", harbor_venv: "<harbor-venv>"}.items(),
                      key=lambda kv: -len(kv[0]))


def scrub(v):
    if isinstance(v, str):
        for path, name in PLACEHOLDERS:
            v = v.replace(path, name)
        return v
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items()}
    return v


EXPECTED = {"oracle-reference": {"reward": 1.0, "R1": 1.0}, "oracle-wrong": {"reward": 0.0, "R1": 0.0},
            "nop-trial": {"reward": 0.0, "R1": 0.0}, "probe-timeout": None, "probe-collect": None}
CONTROL_EXPECTED = {"control-probe-timeout": {"reward": 1.0, "R1": 1.0}, "control-probe-collect": {"reward": 1.0, "R1": 1.0}}


def record(t: str, dest: Path) -> dict:
    res = json.loads((work / "trials" / t / "result.json").read_text())
    res["trial_uri"] = f"trials/{t}"
    res = scrub(res)
    dest.mkdir(parents=True)
    (dest / "result.json").write_text(json.dumps(res, indent=2) + "\n")
    det = work / "trials" / t / "verifier" / "tc_detail.json"
    if det.exists():
        (dest / "tc_detail.json").write_text(json.dumps(scrub(json.loads(det.read_text())), indent=2) + "\n")
    exc = res.get("exception_info") or {}
    return {"rewards": (res.get("verifier_result") or {}).get("rewards"), "exception": exc.get("exception_type")}


shutil.copyfile(work / "lint.txt", out / "lint.txt")
summary = {"exporter_version": EXPORTER_VERSION, "harness_version": HARNESS_VERSION, "harbor_version": harbor_version,
           "lint_rc": lint_rc, "trials": {}, "outcomes": {}, "expected": EXPECTED}
for t in EXPECTED:
    o = record(t, out / t)
    summary["trials"][t] = o["rewards"]
    summary["outcomes"][t] = o
ok = lint_rc == 0 and all(summary["trials"][t] == e for t, e in EXPECTED.items())
if control_rev:
    rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", control_rev], capture_output=True, text=True,
                         check=True).stdout.strip()
    control = {"exporter_revision": rev, "trials": {}, "outcomes": {}, "expected": CONTROL_EXPECTED}
    for t in CONTROL_EXPECTED:
        o = record(t, out / "control" / t)
        control["trials"][t] = o["rewards"]
        control["outcomes"][t] = o
    summary["control"] = control
    ok = ok and all(control["trials"][t] == e for t, e in CONTROL_EXPECTED.items())
summary["as_expected"] = ok
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
sys.path.insert(0, str(root / "scripts"))
from scan_tracked_files import RULES  # the publication scan's rules (session-local paths, credentials)

leaks = [p for p in out.rglob("*") if p.is_file() and (any(path in p.read_text(errors="replace") for path, _ in PLACEHOLDERS)
                                                        or any(pat.search(p.read_text(errors="replace")) for _, pat in RULES))]
if leaks:
    sys.exit(f"local paths or secrets left in {[str(p.relative_to(root)) for p in leaks]}")
print(f"recorded in {out.relative_to(root)}: {summary['trials']}" + (f"; control {summary['control']['trials']}" if control_rev else ""))
if not ok:
    sys.exit("some trials differ from their expected outcomes (see summary.json)")
PY
echo "trials kept in $WORK"
