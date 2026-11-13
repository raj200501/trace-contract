# Hidden behavioural tests for CS-01, condition llm_freeform.
#
# What the user ultimately wants (from the whole session, including the later
# correction that made the trimming opt-in):
#
#   B1  Without the new argument, humanize.naturalsize prints exactly what the
#       base version printed with the default format, in decimal, binary and
#       GNU modes ("3.0 MB", "1.0 KiB", "1.0K" keep their trailing ".0").
#   B2  Calls that pass a custom `format`, positionally (for example
#       naturalsize(3000, False, True, "%.3f")) or by keyword, and do not pass
#       the new argument, produce exactly what they produced before.
#   B3  naturalsize accepts the keyword argument `strip_trailing_zero`, and
#       strip_trailing_zero=False gives the same output as leaving it out.
#   B4  With strip_trailing_zero=True, a trailing ".0" is dropped in decimal and
#       binary modes: 3_000_000 -> "3 MB", 1024 (binary) -> "1 KiB".
#   B5  With strip_trailing_zero=True, a meaningful decimal is kept:
#       3000 (binary) -> "2.9 KiB".
#   B6  With strip_trailing_zero=True, only the fractional ".0" goes. Integer
#       digits are never dropped ("10 MB", "100 kB", "1000 KiB", "30000 QB"),
#       and plain byte counts are unchanged ("300 Bytes", "1 Byte").
#   B7  strip_trailing_zero=True works for negative sizes ("-3 MB", "-2.9 KiB").
#   B8  The trimming applies to the displayed (rounded) number, so a value that
#       rounds to a whole number at one decimal also loses the ".0"
#       (3000001 -> "3 MB", 999999 -> "1 MB").
#   B9  strip_trailing_zero=True also applies in GNU mode ("1K", "2.9K", "300B").
#   B10 With strip_trailing_zero=True and a custom format whose output has no
#       trailing fractional zero (or no decimal point at all), the number is kept
#       exactly as the format produced it ("%.0f" -> "10 MB", "%.2f" ->
#       "1.05 MB", "%.6f" -> "1.234567 MB").
#   B11 strip_trailing_zero=True works for str and float values as well as ints.
#
# Deliberately not checked, because the session leaves them open: whether
# strip_trailing_zero=True also trims a custom format's output that ends in
# zeros ("%.2f" giving "3.00" or "3.10", "%.3f" giving "2.930", or an explicit
# format="%.1f"), whether the new argument is keyword-only, the exact default
# object in the signature, translated output (catalogs are not compiled in the
# repository), docstrings and README text.
#
# The candidate is driven only through tc_sandbox. Expected values come either
# from literal strings checked against the base commit or from `oracle`, a copy
# of the base-commit algorithm. The oracle runs inside the sandbox next to the
# candidate, so both use the same float and log behaviour.

from __future__ import annotations

import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_default_examples_unchanged": ["B1"],
    "test_custom_format_calls_unchanged": ["B2"],
    "test_default_output_matches_base_everywhere": ["B1", "B2"],
    "test_explicit_false_matches_base": ["B3"],
    "test_strip_user_examples": ["B4", "B5"],
    "test_strip_drops_trailing_point_zero": ["B4"],
    "test_strip_keeps_meaningful_decimal": ["B5"],
    "test_strip_keeps_integer_digits_and_byte_counts": ["B6"],
    "test_strip_negative_sizes": ["B7"],
    "test_strip_uses_rounded_display_value": ["B8"],
    "test_strip_gnu_mode": ["B9"],
    "test_strip_custom_format_without_trailing_zero_unchanged": ["B10"],
    "test_strip_str_and_float_values": ["B11"],
    "test_strip_matches_base_minus_point_zero": ["B4", "B5", "B6", "B7", "B8", "B11"],
}

STRIP = {"strip_trailing_zero": True}

# Copy of the base-commit naturalsize. No locale is active in the sandbox, so
# gettext returns the msgids unchanged and plain suffix strings are used.
# strip=True drops a trailing ".0" from the number. It is only used with the
# default "%.1f" format, where every reading of the request agrees.
_ORACLE = r'''
from math import log as _oracle_log

_ORACLE_SUFFIXES = {
    "decimal": ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"),
    "binary": ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB"),
    "gnu": "KMGTPEZYRQ",
}


def oracle(value, binary=False, gnu=False, fmt="%.1f", strip=False):
    if strip and fmt != "%.1f":
        raise ValueError("oracle strip is only defined for the default format")
    if gnu:
        suffix = _ORACLE_SUFFIXES["gnu"]
    elif binary:
        suffix = _ORACLE_SUFFIXES["binary"]
    else:
        suffix = _ORACLE_SUFFIXES["decimal"]
    base = 1024 if (gnu or binary) else 1000
    bytes_ = float(value)
    abs_bytes = abs(bytes_)
    if abs_bytes == 1 and not gnu:
        return "%d Byte" % int(bytes_)
    if abs_bytes < base:
        return f"{int(bytes_)}B" if gnu else "%d Bytes" % int(bytes_)
    exp = int(min(_oracle_log(abs_bytes, base), len(suffix)))
    if exp < len(suffix) and abs(float(fmt % (abs_bytes / (base**exp)))) >= base:
        exp += 1
    number = fmt % (bytes_ / (base**exp))
    if strip and number.endswith(".0"):
        number = number[:-2]
    space = "" if gnu else " "
    return number + space + suffix[exp - 1]
'''

# Runs every planned call, records the output or the exception, and compares
# it with the oracle's answer.
_COMPARE_PLANS = r'''
import humanize

compared = 0
mismatches = []
for args, kwargs, want in PLANS:
    try:
        got = humanize.naturalsize(*args, **kwargs)
    except Exception as exc:
        got = "raised " + type(exc).__name__
    compared += 1
    if got != want and len(mismatches) < 10:
        mismatches.append(
            "naturalsize(*%r, **%r) returned %r, expected %r" % (args, kwargs, got, want)
        )
result = {"compared": compared, "mismatches": mismatches}
'''

_RUN_CALLS = r'''
import humanize

out = []
for args, kwargs in CALLS:
    try:
        out.append(humanize.naturalsize(*args, **kwargs))
    except Exception as exc:
        out.append("raised " + type(exc).__name__)
result = out
'''


def _calls_snippet(cases):
    calls = [(args, kwargs) for args, kwargs, _ in cases]
    return "CALLS = " + repr(calls) + "\n" + _RUN_CALLS


def _label(args, kwargs):
    parts = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    return "naturalsize(" + ", ".join(parts) + ")"


def _explain(cases, value):
    if not isinstance(value, list) or len(value) != len(cases):
        return "unexpected result: " + repr(value)[:2000]
    lines = [
        f"{_label(args, kwargs)} returned {got!r}, expected {expected!r}"
        for (args, kwargs, expected), got in zip(cases, value)
        if got != expected
    ]
    return "\n".join(lines)


def _plans_snippet(values, build_plans):
    # build_plans is source code that fills PLANS from VALUES using `oracle`.
    return (
        _ORACLE
        + "\nVALUES = "
        + repr(values)
        + "\nPLANS = []\n"
        + build_plans
        + "\n"
        + _COMPARE_PLANS
    )


def _sample_values(max_abs):
    """Deterministic mix of ints, floats and numeric strings, both signs."""
    rng = random.Random(20261113)
    ints = set()
    for base in (1000, 1024):
        for k in range(13):
            power = base**k
            for n in (1, 3, 10, 31, 100, 999, 1023):
                for d in (-1, 0, 1):
                    ints.add(n * power + d)
    for _ in range(150):
        ints.add(int(10 ** rng.uniform(0, 36)))
    ints = sorted(v for v in ints if 0 <= v < max_abs)
    floats = [rng.uniform(0.5, 1000.0) * 10 ** rng.randint(0, 32) for _ in range(60)]
    floats += [0.5, 1.0, 1.5, 999.9, 1000.0, 1023.5, 1024.0, 1024.5, 1049.9, 1050.0]
    floats = [f for f in floats if f < max_abs]
    strings = [str(v) for v in ints[::6]] + [repr(f) for f in floats[::4]]
    positives = ints + floats + strings
    negatives = (
        [-v for v in ints[::2] if v]
        + [-f for f in floats[::2]]
        + ["-" + s for s in strings[::2]]
    )
    return positives + negatives


def test_default_examples_unchanged():
    cases = [
        ((3_000_000,), {}, "3.0 MB"),
        ((1024,), {"binary": True}, "1.0 KiB"),
        ((3000,), {"binary": True}, "2.9 KiB"),
        ((1024,), {"gnu": True}, "1.0K"),
        ((1_000_000,), {}, "1.0 MB"),
        ((1_000_000,), {"binary": True}, "976.6 KiB"),
        ((1_000_000,), {"gnu": True}, "976.6K"),
        ((300, False, True), {}, "300B"),
        ((3000, False, True), {}, "2.9K"),
        ((3000, True), {}, "2.9 KiB"),
        ((10**28,), {}, "10.0 RB"),
        ((10**34 * 3,), {}, "30000.0 QB"),
        ((-4096, True), {}, "-4.0 KiB"),
        ((-3_000_000,), {}, "-3.0 MB"),
        ((999_999,), {}, "1.0 MB"),
        ((1024**2 - 1, False, True), {}, "1.0M"),
        ((10**7,), {}, "10.0 MB"),
        ((300,), {}, "300 Bytes"),
        ((1,), {}, "1 Byte"),
        (("1000",), {}, "1.0 kB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_custom_format_calls_unchanged():
    cases = [
        ((3000, False, True, "%.3f"), {}, "2.930K"),
        ((-3000, False, True, "%.3f"), {}, "-2.930K"),
        ((3_141_592, False, False, "%.2f"), {}, "3.14 MB"),
        ((3_000_000_000, False, True, "%.0f"), {}, "3G"),
        ((10**26 * 30, True, False, "%.3f"), {}, "2.423 RiB"),
        ((3_000_000, False, False, "%.2f"), {}, "3.00 MB"),
        ((3_100_000, False, False, "%.2f"), {}, "3.10 MB"),
        ((10**6, False, False, "%.1f"), {}, "1.0 MB"),
        ((1024, True, False, "%.1f"), {}, "1.0 KiB"),
        ((1024, False, True, "%.2f"), {}, "1.00K"),
        ((3_000_000,), {"format": "%.3f"}, "3.000 MB"),
        ((10**6,), {"format": "%.1f"}, "1.0 MB"),
        ((1024,), {"binary": True, "format": "%.2f"}, "1.00 KiB"),
        ((10**7,), {"format": "%.0f"}, "10 MB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_default_output_matches_base_everywhere():
    values = _sample_values(10**36)
    build = r'''
MODES = ((False, False), (True, False), (False, True), (True, True))
FORMATS = ("%.1f", "%.2f", "%.0f", "%.3f")
for value in VALUES:
    PLANS.append(((value,), {}, oracle(value)))
    for binary, gnu in MODES:
        want = oracle(value, binary, gnu)
        PLANS.append(((value, binary, gnu), {}, want))
        PLANS.append(((value,), {"binary": binary, "gnu": gnu}, want))
        for fmt in FORMATS:
            want = oracle(value, binary, gnu, fmt)
            PLANS.append(((value, binary, gnu, fmt), {}, want))
            PLANS.append(((value,), {"binary": binary, "gnu": gnu, "format": fmt}, want))
'''
    r = run_python(_plans_snippet(values, build), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    per_value = 1 + 4 * (2 + 2 * 4)
    assert r.value == {"compared": len(values) * per_value, "mismatches": []}


def test_explicit_false_matches_base():
    values = _sample_values(10**36)
    build = r'''
OFF = {"strip_trailing_zero": False}
for value in VALUES:
    PLANS.append(((value,), dict(OFF), oracle(value)))
    for binary, gnu in ((False, False), (True, False), (False, True)):
        PLANS.append(((value, binary, gnu), dict(OFF), oracle(value, binary, gnu)))
        PLANS.append(
            ((value, binary, gnu, "%.3f"), dict(OFF), oracle(value, binary, gnu, "%.3f"))
        )
        PLANS.append(
            (
                (value,),
                {"binary": binary, "gnu": gnu, "format": "%.2f", **OFF},
                oracle(value, binary, gnu, "%.2f"),
            )
        )
'''
    r = run_python(_plans_snippet(values, build), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    per_value = 1 + 3 * 3
    assert r.value == {"compared": len(values) * per_value, "mismatches": []}


def test_strip_user_examples():
    cases = [
        ((3_000_000,), dict(STRIP), "3 MB"),
        ((1024,), {"binary": True, **STRIP}, "1 KiB"),
        ((3000,), {"binary": True, **STRIP}, "2.9 KiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_drops_trailing_point_zero():
    cases = [
        ((10**3,), dict(STRIP), "1 kB"),
        ((10**6,), dict(STRIP), "1 MB"),
        ((10**9,), dict(STRIP), "1 GB"),
        ((10**12,), dict(STRIP), "1 TB"),
        ((10**15,), dict(STRIP), "1 PB"),
        ((10**18,), dict(STRIP), "1 EB"),
        ((10**21,), dict(STRIP), "1 ZB"),
        ((10**24,), dict(STRIP), "1 YB"),
        ((10**27,), dict(STRIP), "1 RB"),
        ((10**30,), dict(STRIP), "1 QB"),
        ((31 * 1000,), dict(STRIP), "31 kB"),
        ((32 * 1000**2,), dict(STRIP), "32 MB"),
        ((40 * 1000**10,), dict(STRIP), "40 QB"),
        ((1024,), {"binary": True, **STRIP}, "1 KiB"),
        ((32 * 1024**2,), {"binary": True, **STRIP}, "32 MiB"),
        ((40 * 1024**10,), {"binary": True, **STRIP}, "40 QiB"),
        ((1024**3, True), dict(STRIP), "1 GiB"),
        ((5 * 1024**4, True), dict(STRIP), "5 TiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_keeps_meaningful_decimal():
    cases = [
        ((3000, True), dict(STRIP), "2.9 KiB"),
        ((10**6,), {"binary": True, **STRIP}, "976.6 KiB"),
        ((1.123456789 * 10**6,), dict(STRIP), "1.1 MB"),
        ((31_000, True), dict(STRIP), "30.3 KiB"),
        ((1000**3 * 33, True), dict(STRIP), "30.7 GiB"),
        ((1000**10 * 40,), {"binary": True, **STRIP}, "31.6 QiB"),
        ((2_500_000,), dict(STRIP), "2.5 MB"),
        ((1050,), dict(STRIP), "1.1 kB"),
        ((10_500_000,), dict(STRIP), "10.5 MB"),
        ((999_900,), dict(STRIP), "999.9 kB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_keeps_integer_digits_and_byte_counts():
    cases = [
        ((10**7,), dict(STRIP), "10 MB"),
        ((10**5,), dict(STRIP), "100 kB"),
        ((500 * 10**3,), dict(STRIP), "500 kB"),
        ((2 * 10**10,), dict(STRIP), "20 GB"),
        ((10240,), {"binary": True, **STRIP}, "10 KiB"),
        ((100 * 1024**2,), {"binary": True, **STRIP}, "100 MiB"),
        ((1000 * 1024,), {"binary": True, **STRIP}, "1000 KiB"),
        ((10**28,), dict(STRIP), "10 RB"),
        ((10**34 * 3,), dict(STRIP), "30000 QB"),
        ((300,), dict(STRIP), "300 Bytes"),
        ((100,), dict(STRIP), "100 Bytes"),
        ((10,), dict(STRIP), "10 Bytes"),
        ((0,), dict(STRIP), "0 Bytes"),
        ((1,), dict(STRIP), "1 Byte"),
        ((1000,), {"binary": True, **STRIP}, "1000 Bytes"),
        ((1023, True), dict(STRIP), "1023 Bytes"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_negative_sizes():
    cases = [
        ((-3_000_000,), dict(STRIP), "-3 MB"),
        ((-1024,), {"binary": True, **STRIP}, "-1 KiB"),
        ((-4096, True), dict(STRIP), "-4 KiB"),
        ((-3000,), {"binary": True, **STRIP}, "-2.9 KiB"),
        ((-10**7,), dict(STRIP), "-10 MB"),
        ((-10**5,), dict(STRIP), "-100 kB"),
        ((-999_999,), dict(STRIP), "-1 MB"),
        ((-3_000_001,), dict(STRIP), "-3 MB"),
        ((-1.123456789 * 10**6,), dict(STRIP), "-1.1 MB"),
        ((-1,), dict(STRIP), "-1 Byte"),
        ((-300,), dict(STRIP), "-300 Bytes"),
        ((-1000,), {"binary": True, **STRIP}, "-1000 Bytes"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_uses_rounded_display_value():
    cases = [
        ((3_000_001,), dict(STRIP), "3 MB"),
        ((2_999_999,), dict(STRIP), "3 MB"),
        ((999_999,), dict(STRIP), "1 MB"),
        ((999_950,), dict(STRIP), "1 MB"),
        ((1_000_049,), dict(STRIP), "1 MB"),
        ((1.00001 * 10**6,), dict(STRIP), "1 MB"),
        ((10**9 + 1,), dict(STRIP), "1 GB"),
        ((1049,), dict(STRIP), "1 kB"),
        ((1999,), dict(STRIP), "2 kB"),
        ((1025,), {"binary": True, **STRIP}, "1 KiB"),
        ((1024**2 - 1,), {"binary": True, **STRIP}, "1 MiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_gnu_mode():
    cases = [
        ((1024,), {"gnu": True, **STRIP}, "1K"),
        ((1024, False, True), dict(STRIP), "1K"),
        ((1024, True, True), dict(STRIP), "1K"),
        ((2048,), {"gnu": True, "binary": False, **STRIP}, "2K"),
        ((3000,), {"gnu": True, **STRIP}, "2.9K"),
        ((3_000_000,), {"gnu": True, **STRIP}, "2.9M"),
        ((10**6,), {"gnu": True, **STRIP}, "976.6K"),
        ((1024**2 - 1,), {"gnu": True, **STRIP}, "1M"),
        ((10240,), {"gnu": True, **STRIP}, "10K"),
        ((1024**3 * 33,), {"gnu": True, **STRIP}, "33G"),
        ((-1024,), {"gnu": True, **STRIP}, "-1K"),
        ((300,), {"gnu": True, **STRIP}, "300B"),
        ((1,), {"gnu": True, **STRIP}, "1B"),
    ]
    values = _sample_values(10**33)
    build = (
        "EXAMPLES = "
        + repr(cases)
        + r'''
for args, kwargs, want in EXAMPLES:
    PLANS.append((args, kwargs, want))
for value in VALUES:
    for binary in (False, True):
        want = oracle(value, binary, True, strip=True)
        PLANS.append(((value, binary, True), {"strip_trailing_zero": True}, want))
        PLANS.append(
            ((value,), {"binary": binary, "gnu": True, "strip_trailing_zero": True}, want)
        )
'''
    )
    r = run_python(_plans_snippet(values, build), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == {"compared": len(cases) + 4 * len(values), "mismatches": []}


def test_strip_custom_format_without_trailing_zero_unchanged():
    cases = [
        ((10**7,), {"format": "%.0f", **STRIP}, "10 MB"),
        ((10**5,), {"format": "%.0f", **STRIP}, "100 kB"),
        ((-10**7,), {"format": "%.0f", **STRIP}, "-10 MB"),
        ((3_000_000_000, False, True, "%.0f"), dict(STRIP), "3G"),
        ((10 * 1024,), {"gnu": True, "format": "%.0f", **STRIP}, "10K"),
        ((2 * 1024**2,), {"binary": True, "format": "%.0f", **STRIP}, "2 MiB"),
        ((3_141_592,), {"format": "%.2f", **STRIP}, "3.14 MB"),
        ((3_141_592, False, False, "%.2f"), dict(STRIP), "3.14 MB"),
        ((1_050_000,), {"format": "%.2f", **STRIP}, "1.05 MB"),
        ((1_050_000_000,), {"format": "%.2f", **STRIP}, "1.05 GB"),
        ((1_234_567,), {"format": "%.6f", **STRIP}, "1.234567 MB"),
        ((10**26 * 30, True, False, "%.3f"), dict(STRIP), "2.423 RiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_str_and_float_values():
    cases = [
        (("3000000",), dict(STRIP), "3 MB"),
        (("10000000",), dict(STRIP), "10 MB"),
        (("1024",), {"binary": True, **STRIP}, "1 KiB"),
        (("3000",), {"binary": True, **STRIP}, "2.9 KiB"),
        (("-1000",), dict(STRIP), "-1 kB"),
        (("-3000",), {"binary": True, **STRIP}, "-2.9 KiB"),
        (("300",), dict(STRIP), "300 Bytes"),
        (("1",), dict(STRIP), "1 Byte"),
        ((3e6,), dict(STRIP), "3 MB"),
        ((2.5e6,), dict(STRIP), "2.5 MB"),
        ((1024.0,), {"binary": True, **STRIP}, "1 KiB"),
        ((1.123456789 * 10**3,), dict(STRIP), "1.1 kB"),
        ((1.0,), dict(STRIP), "1 Byte"),
    ]
    r = run_python(_calls_snippet(cases), timeout=20.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == [expected for _, _, expected in cases], _explain(cases, r.value)


def test_strip_matches_base_minus_point_zero():
    # Below 10**33 bytes the default-format number is at most "1000.0" in every
    # unit, so this sticks to realistic sizes. Larger numbers only occur once
    # the largest suffix is reached.
    values = _sample_values(10**33)
    build = r'''
ON = {"strip_trailing_zero": True}
for value in VALUES:
    PLANS.append(((value,), dict(ON), oracle(value, strip=True)))
    for binary in (False, True):
        want = oracle(value, binary, strip=True)
        PLANS.append(((value, binary), dict(ON), want))
        PLANS.append(((value, binary, False), dict(ON), want))
        PLANS.append(((value,), {"binary": binary, **ON}, want))
'''
    r = run_python(_plans_snippet(values, build), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    per_value = 1 + 2 * 3
    assert r.value == {"compared": len(values) * per_value, "mismatches": []}
