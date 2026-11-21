"""The exploratory re-analysis of pilot-v0.3.3 (scripts/exploratory_reanalysis.py): exact tests and counts."""

from __future__ import annotations

import importlib.util
import itertools
import json
import random
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "runs" / "pilot-v0.3.3"
OUT = ROOT / "results" / "analyses" / "pilot-v0.3.3-exploratory"


def _module():
    spec = importlib.util.spec_from_file_location("exploratory_reanalysis", ROOT / "scripts" / "exploratory_reanalysis.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


er = _module()


@pytest.fixture(scope="module")
def pilot():
    return er.load_pilot(RUN, ROOT / "tasks", ROOT / "results" / "audits")


@pytest.fixture(scope="module")
def analysis(pilot):
    return er.build_analysis(pilot)


def _enumerate(values: list[Fraction]) -> tuple[Fraction, Fraction, Fraction]:
    t, n = sum(values), 2 ** len(values)
    sums = [sum(s * v for s, v in zip(signs, values)) for signs in itertools.product((1, -1), repeat=len(values))]
    return (Fraction(sum(x >= t for x in sums), n), Fraction(sum(x <= t for x in sums), n),
            Fraction(sum(abs(x) >= abs(t) for x in sums), n))


def test_signflip_matches_full_enumeration():
    rng = random.Random(7)
    for _ in range(200):
        values = [Fraction(rng.randint(-4, 4), rng.randint(1, 6)) - Fraction(rng.randint(0, 3), 10) for _ in range(rng.randint(1, 8))]
        r = er.signflip(values)
        assert (Fraction(r["p_greater"]), Fraction(r["p_less"]), Fraction(r["p_two_sided"])) == _enumerate(values)
    assert er.signflip([])["p_greater"] is None


def test_c1_vs_c3_false_acceptance_randomization_p_value(analysis):
    d = analysis["paired_comparisons"]["comparisons"]["initial_plain_vs_full_plain"]["fa"]
    assert {f: v["difference"] for f, v in d["per_family"].items()} == pytest.approx(
        {"CS-01": 1 / 6, "CS-02": 0.0, "CS-03": 0.5, "CS-04": 0.8})
    for stat in ("pooled", "family_mean"):
        sf = d["signflip"][stat]
        # Only the all-positive assignments (CS-02's zero difference either way) reach the observed sum: 2/16.
        assert sf["p_greater"] == 0.125
        assert sf["p_two_sided"] == 0.25
        assert sf["floor_one_sided"] == 0.0625
        assert sf["conditional_floor_one_sided"] == 0.125
    assert d["discordant"] == {"a_accepts_b_rejects": 6, "a_rejects_b_accepts": 0}


def test_counts_match_the_frozen_analysis_and_the_design_audit(analysis):
    assert analysis["consistency"]["counts_match_frozen_analysis"] is True
    assert analysis["consistency"]["requirement_maps_match_run_manifest"] is True
    pooled = lambda c: analysis["per_family"]["conditions"][c]["pooled"]  # noqa: E731
    assert (pooled("initial_plain")["fa"]["num"], pooled("initial_plain")["fa"]["den"]) == (6, 17)
    assert (pooled("full_plain")["fa"]["num"], pooled("full_plain")["fr"]["num"]) == (0, 0)
    gated = analysis["oracle_gated"]
    c1 = gated["per_arm"]["initial_plain"]
    assert (c1["cells_kept"], c1["pooled"]["fa"]["num"], c1["pooled"]["fa"]["den"], c1["pooled"]["fr"]["num"], c1["pooled"]["fr"]["den"]) == (3, 5, 11, 0, 8)
    for cond in ("full_plain", "full_audited"):
        rec = gated["design_audit_reproduction"][cond]["recomputed"]
        assert rec["common_support_with_initial_plain"] == {"fa": [0, 11], "fr": [0, 8]}
        assert rec["per_arm"] == {"fa": [0, 17], "fr": [0, 10]}
    distinct = analysis["distinct_patches"]
    assert distinct["n_distinct"] == 31
    assert distinct["groups"][0]["members"] == ["CS-04-pre-correction", "CS-04-eval-nm-2"]
    assert distinct["conditions"]["initial_plain"]["pooled"]["fa"] == {"num": 5, "den": 16, "rate": 5 / 16}
    bounds = analysis["ambiguous_bounds"]["conditions"]["initial_plain"]
    assert (bounds["as_invalid"]["pooled"]["fa"]["num"], bounds["as_invalid"]["pooled"]["fa"]["den"]) == (10, 22)
    assert (bounds["as_valid"]["pooled"]["fr"]["num"], bounds["as_valid"]["pooled"]["fr"]["den"]) == (3, 15)


def test_labeler_agreement_and_right_reason(analysis):
    ag = analysis["labeler_agreement"]["conditions"]["full_plain"]
    assert (ag["refcheck"]["n"], ag["checks"]["n"], ag["construction_constructed_only"]["n"], ag["d19"]["n"]) == (32, 32, 28, 27)
    assert ag["refcheck"]["agree"] == 30  # it rejects two ambiguous near misses that pass the reference checks
    rr = analysis["right_reason"]["conditions"]
    assert (rr["initial_plain"]["total"]["rejected"], rr["initial_plain"]["total"]["right_reason"]) == (11, 6)
    assert rr["full_plain"]["total"]["right_reason"] == 17
    assert rr["llm_freeform"]["evaluable"] is False


def test_b2_equivalence_cannot_be_shown_with_four_families(analysis):
    eq = analysis["b2_equivalence"]["comparisons"]["llm_freeform_vs_full_plain"]["d19"]
    assert eq["fr"]["tost"]["pooled"]["p_tost"] == 0.0625  # identical outcomes still cannot go below 1/16
    assert eq["fa"]["discordant"] == {"a_accepts_b_rejects": 1, "a_rejects_b_accepts": 0}


def test_plan_primary_endpoint_in_the_pilot(analysis):
    nn = analysis["natural_negatives"]
    assert (nn["eligible_families"], nn["families"]) == (2, 4)  # CS-01 and CS-04 pre-correction states are invalid
    sf = nn["comparison"]["signflip"]["pooled"]
    assert (sf["k"], sf["p_greater"], sf["floor_one_sided"]) == (2, 0.25, 0.25)


def test_chi2_quantiles():
    assert er.chi2_ppf(0.10, 3) == pytest.approx(0.5844, abs=1e-4)
    assert er.chi2_ppf(0.90, 3) == pytest.approx(6.2514, abs=1e-4)
    assert er.chi2_ppf(0.95, 1) == pytest.approx(3.8415, abs=1e-4)


def test_simulation_cells_are_reproducible():
    arms = er.Arms(0.4, 0.1, 0.05, 0.05)
    first = er.power_cell(er._rng("t"), arms, 12, 2, 50)
    assert first == er.power_cell(er._rng("t"), arms, 12, 2, 50)
    cell = er.coverage_cell(er._rng("c"), arms, Fraction(7, 20), 4, 2, 30, 20)
    assert cell["signflip_coverage"] == 1.0  # with 4 families no 95% test can reject
    assert cell["attainable_level"] == 0.875
    assert er._deff_bound_rejects(0, 40, 2, 0.3) and not er._deff_bound_rejects(0, 20, 2, 0.3)


def test_recorded_analysis_is_current(analysis):
    path = OUT / "analysis.json"
    if not path.exists():
        pytest.skip("no recorded output")
    recorded = json.loads(path.read_text())
    fresh = json.loads(json.dumps(analysis, sort_keys=True, default=str))
    for d in (recorded, fresh):
        d["meta"].pop("git_revision")
    assert fresh == recorded
