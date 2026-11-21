"""tracecontract.stats (the exact sign-flip test of new runs) and metrics.paired_signflip.

The package's sign-flip test must equal full enumeration and the copy that
scripts/exploratory_reanalysis.py keeps for the frozen re-analysis of pilot-v0.3.3 (D49).
Synthetic inputs only; not research evidence.
"""

from __future__ import annotations

import importlib.util
import itertools
import random
import sys
from fractions import Fraction
from pathlib import Path

from tracecontract.metrics import Row, paired_signflip
from tracecontract.stats import integers, signflip

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("exploratory_reanalysis_for_stats", ROOT / "scripts" / "exploratory_reanalysis.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def _enumerate(values: list[Fraction]) -> tuple[Fraction, Fraction, Fraction]:
    t, n = sum(values), 2 ** len(values)
    sums = [sum(s * v for s, v in zip(signs, values)) for signs in itertools.product((1, -1), repeat=len(values))]
    return (Fraction(sum(x >= t for x in sums), n), Fraction(sum(x <= t for x in sums), n),
            Fraction(sum(abs(x) >= abs(t) for x in sums), n))


def _values(rng: random.Random) -> list[Fraction]:
    return [Fraction(rng.randint(-5, 5), rng.randint(1, 7)) for _ in range(rng.randint(1, 9))]


def test_signflip_matches_full_enumeration():
    rng = random.Random(20261121)
    for _ in range(400):
        values = _values(rng)
        r = signflip(values)
        assert (Fraction(r["p_greater"]), Fraction(r["p_less"]), Fraction(r["p_two_sided"])) == _enumerate(values)
        k, zeros = len(values), sum(1 for v in values if v == 0)
        assert (r["k"], r["zero_families"], r["floor_one_sided"]) == (k, zeros, 1 / 2 ** k)
        assert r["floor_two_sided"] == min(1.0, 2 / 2 ** k) and r["conditional_floor_one_sided"] == 2 ** zeros / 2 ** k
    assert signflip([])["p_greater"] is None and signflip([])["k"] == 0


def test_signflip_equals_the_copy_in_the_exploratory_script():
    er = _script()
    rng = random.Random(7)
    for _ in range(300):
        values = _values(rng)
        assert signflip(values) == er.signflip(values)
    assert integers([Fraction(1, 2), Fraction(-1, 3), 2]) == [3, -2, 12]


def test_the_pilot_family_differences():
    """D49: C1 vs C3 FA per family +1/6, 0, +1/2, +4/5 gives p = 0.125 one-sided and 0.25 two-sided."""
    r = signflip([Fraction(1, 6), Fraction(0), Fraction(1, 2), Fraction(4, 5)])
    assert (r["p_greater"], r["p_two_sided"], r["floor_one_sided"], r["conditional_floor_one_sided"]) == (0.125, 0.25, 0.0625, 0.125)


def _row(fam: str, cid: str, cond: str, outcome: str, label: str | None) -> Row:
    return Row(task_id=fam, family_id=fam, candidate_id=cid, condition=cond, outcome=outcome, label=label)


def test_paired_signflip_counts_errors_per_family():
    rows = []
    for fam, a_out, b_out in (("F1", "pass", "task_failure"), ("F2", "pass", "pass"), ("F3", "pass", "task_failure")):
        rows += [_row(fam, f"{fam}-bad", "A", a_out, "invalid"), _row(fam, f"{fam}-bad", "B", b_out, "invalid"),
                 _row(fam, f"{fam}-ok", "A", "task_failure", "valid"), _row(fam, f"{fam}-ok", "B", "pass", "valid")]
    rows.append(_row("F4", "F4-unlabeled", "A", "pass", None))  # no labeled candidate: F4 carries no difference
    rows.append(_row("F4", "F4-unlabeled", "B", "pass", None))
    rows.append(_row("F1", "F1-only-a", "A", "pass", "invalid"))  # scored by A only: not a paired candidate
    fa = paired_signflip(rows, "A", "B", "fa")
    assert fa["per_family_counts"] == {"F1": {"a_num": 1, "b_num": 0, "den": 1}, "F2": {"a_num": 1, "b_num": 1, "den": 1},
                                       "F3": {"a_num": 1, "b_num": 0, "den": 1}, "F4": {"a_num": 0, "b_num": 0, "den": 0}}
    assert fa["n_families_labeled"] == 3
    sf = fa["signflip"]["pooled"]
    assert (sf["k"], sf["p_greater"], sf["zero_families"], sf["conditional_floor_one_sided"]) == (3, 0.25, 1, 0.25)
    fr = paired_signflip(rows, "A", "B", "fr")  # A rejects every valid candidate, B none
    assert fr["signflip"]["family_mean"]["p_greater"] == 0.125
