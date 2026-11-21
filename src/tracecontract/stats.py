"""Exact sign-flip randomization tests over task families (protocol v0.7 §15.7, v0.8 §16.6).

The reporting rules give every paired comparison of a new run an exact sign-flip p-value over
families, with its attainable floor. :func:`signflip` is the implementation that
``scripts/exploratory_reanalysis.py`` uses for the re-analysis of ``pilot-v0.3.3`` (decision
log D49), where it is checked against full enumeration. The script keeps its own copy, because
its recorded output carries the sha256 of the script itself; ``tests/test_stats.py`` checks that
the two agree and that this one matches full enumeration.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Callable, Sequence


def signflip_counter(ints: Sequence[int]) -> Callable[[int], int]:
    """``ge(t)``: how many of the 2^K sign assignments of ``ints`` give a signed sum >= t.

    The distribution is the generating function prod(x^-v + x^v), packed into one Python integer
    with B = K + 2 bits per coefficient. Coefficients are counts at most 2^K, so they never carry;
    the sum of the coefficients above an exponent is read off modulo 2^B - 1. Exact and fast.
    """
    k = len(ints)
    nz = [abs(x) for x in ints if x]
    zeros, total_v, bits = k - len(nz), sum(nz), k + 2
    poly = 1
    for v in nz:
        poly += poly << (2 * v * bits)
    mask = (1 << bits) - 1

    def ge(t: int) -> int:
        e = t + total_v
        if e <= 0:
            return 1 << k
        if e > 2 * total_v:
            return 0
        return ((poly >> (e * bits)) % mask) << zeros
    return ge


def integers(values: Sequence[Fraction | int]) -> list[int]:
    """``values`` scaled by the least common multiple of their denominators (the test is scale-invariant)."""
    scale = 1
    for v in values:
        scale = math.lcm(scale, Fraction(v).denominator)
    return [int(Fraction(v) * scale) for v in values]


def signflip(values: Sequence[Fraction | int]) -> dict:
    """Exact sign-flip randomization test of the sum of per-family values over all 2^K assignments.

    H0: each family's value is symmetric about zero (for a paired difference: the two arms are
    exchangeable within the family). ``p_greater`` tests H1: sum > 0, ``p_less`` H1: sum < 0.
    The floor is the smallest p-value K families can give; the conditional floor is the smallest
    one the observed zero-difference families allow (a zero cannot change sign).
    """
    k = len(values)
    if k == 0:
        return {"k": 0, "statistic": None, "p_greater": None, "p_less": None, "p_two_sided": None,
                "floor_one_sided": None, "floor_two_sided": None, "zero_families": 0, "conditional_floor_one_sided": None}
    ints = integers(values)
    t, total, ge = sum(ints), 1 << k, signflip_counter(ints)
    zeros = sum(1 for x in ints if x == 0)
    return {"k": k, "statistic": float(sum(Fraction(v) for v in values)), "p_greater": ge(t) / total, "p_less": ge(-t) / total,
            "p_two_sided": (min(total, 2 * ge(abs(t))) / total) if t else 1.0,
            "floor_one_sided": 1 / total, "floor_two_sided": min(1.0, 2 / total),
            "zero_families": zeros, "conditional_floor_one_sided": (1 << zeros) / total}
