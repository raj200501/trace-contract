"""Reference checks for CS-01: ``naturalsize(..., strip_trailing_zero=...)``.

Black-box checks written from the CS-01 reference contract. Candidate code is only
reached through ``tc_sandbox.run_python``; every expected value is either a literal
(contract examples and the base commit's documented/tested outputs) or comes from
``_base_naturalsize`` below, an independent model of the base-commit function with
no locale active. That model is evaluated in the grader process, never in the
sandbox.

How the statements are read:

* R-default-unchanged / R-custom-format-unchanged: without ``strip_trailing_zero``
  the output equals the base-commit output exactly (all modes, custom formats
  given positionally as the 4th argument or by keyword).
* R-opt-in: ``strip_trailing_zero=False`` behaves like the default; with ``True``
  and the default format a trailing ``.0`` of the number is dropped
  (``3.0 MB`` -> ``3 MB``, ``10.0 MB`` -> ``10 MB``) and nothing else changes.
* R-keep-meaningful: with ``True``, a non-zero decimal is never removed
  (``2.9 KiB`` stays ``2.9 KiB``), and digits that are not a trailing ``.0`` (such as
  the zeros of ``300 Bytes`` or ``10 MB``) stay.

Deliberately NOT checked, because the contract leaves it unspecified:
``strip_trailing_zero=True`` together with GNU mode or with any custom format,
whether the new argument is keyword-only or may also be passed positionally, and
how its default is declared (only its behaviour is checked).
"""

import json
import math
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_opt_in_contract_examples": ["R-opt-in"],
    "test_opt_in_explicit_false_is_the_default": ["R-opt-in"],
    "test_opt_in_drops_point_zero_for_every_suffix": ["R-opt-in"],
    "test_opt_in_drops_point_zero_after_rounding_and_for_negative_and_string_input": ["R-opt-in"],
    "test_opt_in_keeps_integer_zeros": ["R-opt-in", "R-keep-meaningful"],
    "test_opt_in_leaves_byte_counts_unchanged": ["R-opt-in", "R-keep-meaningful"],
    "test_opt_in_random_point_zero_outputs": ["R-opt-in"],
    "test_keep_meaningful_contract_example": ["R-keep-meaningful"],
    "test_keep_meaningful_nonzero_decimals_table": ["R-keep-meaningful"],
    "test_keep_meaningful_random_nonzero_decimals": ["R-keep-meaningful"],
    "test_default_contract_examples": ["R-default-unchanged"],
    "test_default_base_suite_and_docstring_outputs": ["R-default-unchanged"],
    "test_default_random_inputs_all_modes": ["R-default-unchanged"],
    "test_custom_format_contract_examples": ["R-custom-format-unchanged"],
    "test_custom_format_positional_table": ["R-custom-format-unchanged"],
    "test_custom_format_keyword_table": ["R-custom-format-unchanged"],
    "test_custom_format_random_inputs": ["R-custom-format-unchanged"],
}

STRIP = {"strip_trailing_zero": True}

# --------------------------------------------------------------------------------------
# Sandbox plumbing: one sandbox call evaluates a whole batch of naturalsize calls.
# A case is [value, positional_args_after_value, keyword_args].
# --------------------------------------------------------------------------------------

_SNIPPET = """
import json
import humanize

cases = json.loads(__CASES__)
out = []
for value, args, kwargs in cases:
    try:
        out.append(["ok", humanize.naturalsize(value, *args, **kwargs)])
    except Exception as exc:
        out.append(["raised", type(exc).__name__ + ": " + str(exc)[:200]])
result = out
"""


def _snippet(cases):
    return _SNIPPET.replace("__CASES__", repr(json.dumps(cases)))


def _describe(case):
    value, args, kwargs = case
    parts = [repr(value)] + [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    return "naturalsize(" + ", ".join(parts) + ")"


def _mismatches(cases, expected, r):
    """Compare a batch result with the expected strings; returns readable mismatches."""
    assert r.ok, r
    got = r.value
    assert isinstance(got, list) and len(got) == len(cases), r
    bad = []
    for case, want, have in zip(cases, expected, got):
        if have != ["ok", want]:
            bad.append(f"{_describe(case)}: expected {want!r}, got {have!r}")
    return bad


def _split(rows):
    return [[v, list(a), dict(k)] for v, a, k, _ in rows], [e for _, _, _, e in rows]


def _with_negatives(rows):
    """Add the negated input for every row (the base prefixes the output with '-')."""
    out = list(rows)
    for value, args, kwargs, expected in rows:
        if abs(float(value)) < 1:  # int(-0.5) is 0: no sign to prefix
            continue
        if isinstance(value, str):
            out.append(("-" + value, args, kwargs, "-" + expected))
        else:
            out.append((-value, args, kwargs, "-" + expected))
    return out


# --------------------------------------------------------------------------------------
# Independent model of the base-commit naturalsize (English, no locale activated).
# --------------------------------------------------------------------------------------

_DECIMAL = ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB")
_BINARY = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB")
_GNU = "KMGTPEZYRQ"
_MODES = ((False, False), (True, False), (False, True), (True, True))


def _base_naturalsize(value, binary=False, gnu=False, fmt="%.1f"):
    suffix = _GNU if gnu else (_BINARY if binary else _DECIMAL)
    base = 1024 if (gnu or binary) else 1000
    number = float(value)
    magnitude = abs(number)
    if magnitude == 1 and not gnu:
        return "%d Byte" % int(number)
    if magnitude < base:
        return f"{int(number)}B" if gnu else "%d Bytes" % int(number)
    exp = int(min(math.log(magnitude, base), len(suffix)))
    if exp < len(suffix) and abs(float(fmt % (magnitude / (base**exp)))) >= base:
        exp += 1
    return fmt % (number / (base**exp)) + ("" if gnu else " ") + suffix[exp - 1]


def _drop_point_zero(text):
    """The contract's rule for the default format: a trailing '.0' of the number goes."""
    number, sep, unit = text.partition(" ")
    if number.endswith(".0"):
        number = number[:-2]
    return number + sep + unit


def _random_values(seed, count):
    rng = random.Random(seed)
    values = []
    for _ in range(count):
        kind = rng.randrange(6)
        if kind == 0:  # integer of random magnitude
            digits = rng.randint(1, 36)
            value = rng.randrange(10 ** (digits - 1), 10**digits)
        elif kind == 1:  # whole multiple of a power of 1000
            value = rng.randint(1, 999) * 1000 ** rng.randint(1, 10)
        elif kind == 2:  # whole multiple of a power of 1024
            value = rng.randint(1, 1023) * 1024 ** rng.randint(1, 10)
        elif kind == 3:  # float with a random mantissa
            value = rng.uniform(1.0, 1024.0) * rng.choice((1000, 1024)) ** rng.randint(0, 10)
        elif kind == 4:  # close to a suffix boundary (exercises the rounding carry)
            step = rng.choice((1000, 1024)) ** rng.randint(1, 10)
            value = step + rng.randint(-(step // 400), step // 400)
        else:  # byte counts
            value = rng.randint(0, 2100)
        if rng.random() < 0.3:
            value = -value
        if rng.random() < 0.1:
            value = str(value)
        values.append(value)
    return values


def _strip_call(rng, value, binary):
    style = rng.randrange(4)
    if style == 0:
        return [value, [], {"binary": binary, "strip_trailing_zero": True}]
    if style == 1:
        return [value, [binary], {"strip_trailing_zero": True}]
    if style == 2:
        return [value, [binary, False], {"strip_trailing_zero": True}]
    return [value, [], {"binary": True, "strip_trailing_zero": True} if binary else {"strip_trailing_zero": True}]


def _strip_cases(seed, count, point_zero):
    """Default-format, non-GNU calls with strip_trailing_zero=True.

    point_zero=True keeps the inputs whose base output ends in '.0' (expected: that
    '.0' dropped); point_zero=False keeps those with a non-zero decimal (expected:
    the base output unchanged).
    """
    rng = random.Random(seed * 7 + 1)
    cases, expected = [], []
    for value in _random_values(seed, count):
        for binary in (False, True):
            base_out = _base_naturalsize(value, binary)
            number = base_out.partition(" ")[0]
            if "." not in number or number.endswith(".0") != point_zero:
                continue
            cases.append(_strip_call(rng, value, binary))
            expected.append(_drop_point_zero(base_out) if point_zero else base_out)
    return cases, expected


# ======================================================================================
# R-opt-in
# ======================================================================================


def test_opt_in_contract_examples():
    rows = [
        (3000000, [], STRIP, "3 MB"),
        (1024, [], {"binary": True, "strip_trailing_zero": True}, "1 KiB"),
    ]
    cases, expected = _split(rows)
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_opt_in_explicit_false_is_the_default():
    rows = [
        (3000000, [], {"strip_trailing_zero": False}, "3.0 MB"),
        (1024, [], {"binary": True, "strip_trailing_zero": False}, "1.0 KiB"),
        (1024, [True], {"strip_trailing_zero": False}, "1.0 KiB"),
        (10**7, [], {"strip_trailing_zero": False}, "10.0 MB"),
        (3000, [], {"binary": True, "strip_trailing_zero": False}, "2.9 KiB"),
        (10**34 * 3, [], {"strip_trailing_zero": False}, "30000.0 QB"),
        (300, [], {"strip_trailing_zero": False}, "300 Bytes"),
        (1, [], {"strip_trailing_zero": False}, "1 Byte"),
    ]
    cases, expected = _split(_with_negatives(rows))
    rng = random.Random(11)
    for value in _random_values(11, 250):
        for binary in (False, True):
            if binary or rng.random() < 0.5:
                cases.append([value, [], {"binary": binary, "strip_trailing_zero": False}])
            else:
                cases.append([value, [], {"strip_trailing_zero": False}])
            expected.append(_base_naturalsize(value, binary))
    r = run_python(_snippet(cases), timeout=60.0)
    assert _mismatches(cases, expected, r) == []


def test_opt_in_drops_point_zero_for_every_suffix():
    rows = []
    for exp, unit in enumerate(_DECIMAL, start=1):
        for k in (1, 3, 7, 25, 999):
            rows.append((k * 1000**exp, [], STRIP, f"{k} {unit}"))
    for exp, unit in enumerate(_BINARY, start=1):
        for k in (1, 2, 5, 31, 999):
            rows.append((k * 1024**exp, [], {"binary": True, "strip_trailing_zero": True}, f"{k} {unit}"))
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases), timeout=60.0)
    assert _mismatches(cases, expected, r) == []


def test_opt_in_drops_point_zero_after_rounding_and_for_negative_and_string_input():
    rows = [
        (3000001, [], STRIP, "3 MB"),  # '%.1f' gives '3.0' before the '.0' is dropped
        (3040000, [], STRIP, "3 MB"),
        (1999949, [], STRIP, "2 MB"),
        (999999, [], STRIP, "1 MB"),  # rounding carries 1000.0 kB into 1.0 MB
        (999999999, [], STRIP, "1 GB"),
        (999999999999, [], STRIP, "1 TB"),
        (1024**2 - 1, [], {"binary": True, "strip_trailing_zero": True}, "1 MiB"),
        (1024**3 - 1, [True], STRIP, "1 GiB"),
        (2.04 * 1024**2, [], {"binary": True, "strip_trailing_zero": True}, "2 MiB"),
        (4096, [True], STRIP, "4 KiB"),
        (3e6, [], STRIP, "3 MB"),
        (1048576.0, [], {"binary": True, "strip_trailing_zero": True}, "1 MiB"),
        (1e30, [], STRIP, "1 QB"),
        ("3000000", [], STRIP, "3 MB"),
        ("1000", [], STRIP, "1 kB"),
        ("1024", [], {"binary": True, "strip_trailing_zero": True}, "1 KiB"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_opt_in_keeps_integer_zeros():
    rows = [
        (10**4, [], STRIP, "10 kB"),
        (10**5, [], STRIP, "100 kB"),
        (10**7, [], STRIP, "10 MB"),
        (2 * 10**7, [], STRIP, "20 MB"),
        (10**8, [], STRIP, "100 MB"),
        (5 * 10**11, [], STRIP, "500 GB"),
        (10**28, [], STRIP, "10 RB"),
        (10**33, [], STRIP, "1000 QB"),
        (10**34 * 3, [], STRIP, "30000 QB"),
        (10**36, [], STRIP, "1000000 QB"),
        (10 * 1024**2, [], {"binary": True, "strip_trailing_zero": True}, "10 MiB"),
        (100 * 1024, [True], STRIP, "100 KiB"),
        (1000 * 1024**3, [], {"binary": True, "strip_trailing_zero": True}, "1000 GiB"),
        (1024**11, [], {"binary": True, "strip_trailing_zero": True}, "1024 QiB"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_opt_in_leaves_byte_counts_unchanged():
    rows = [
        (300, [], STRIP, "300 Bytes"),
        (1, [], STRIP, "1 Byte"),
        (0, [], STRIP, "0 Bytes"),
        (10, [], STRIP, "10 Bytes"),
        (100, [], STRIP, "100 Bytes"),
        (999, [], STRIP, "999 Bytes"),
        (1.0, [], STRIP, "1 Byte"),
        (20.7, [], STRIP, "20 Bytes"),
        ("300", [], STRIP, "300 Bytes"),
        (1, [], {"binary": True, "strip_trailing_zero": True}, "1 Byte"),
        (100, [], {"binary": True, "strip_trailing_zero": True}, "100 Bytes"),
        (1000, [True], STRIP, "1000 Bytes"),
        (1023, [], {"binary": True, "strip_trailing_zero": True}, "1023 Bytes"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_opt_in_random_point_zero_outputs():
    cases, expected = _strip_cases(seed=21, count=900, point_zero=True)
    assert len(cases) > 200
    r = run_python(_snippet(cases), timeout=60.0)
    bad = _mismatches(cases, expected, r)
    assert bad == [], f"{len(bad)} of {len(cases)} calls differ, e.g. {bad[:15]}"


# ======================================================================================
# R-keep-meaningful
# ======================================================================================


def test_keep_meaningful_contract_example():
    rows = [
        (3000, [], {"binary": True}, "2.9 KiB"),
        (3000, [], {"binary": True, "strip_trailing_zero": True}, "2.9 KiB"),
    ]
    cases, expected = _split(rows)
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_keep_meaningful_nonzero_decimals_table():
    rows = [
        (1500, [], STRIP, "1.5 kB"),
        (3141592, [], STRIP, "3.1 MB"),
        (999949, [], STRIP, "999.9 kB"),
        (10500000, [], STRIP, "10.5 MB"),
        (100100, [], STRIP, "100.1 kB"),
        (1.123456789 * 10**6, [], STRIP, "1.1 MB"),
        (2.5e9, [], STRIP, "2.5 GB"),
        (1.23456 * 10**34, [], STRIP, "12345.6 QB"),
        ("1500", [], STRIP, "1.5 kB"),
        (3000, [True], STRIP, "2.9 KiB"),
        (1536, [], {"binary": True, "strip_trailing_zero": True}, "1.5 KiB"),
        (20992, [], {"binary": True, "strip_trailing_zero": True}, "20.5 KiB"),
        (1000**1 * 31, [], {"binary": True, "strip_trailing_zero": True}, "30.3 KiB"),
        (1000**2 * 32, [], {"binary": True, "strip_trailing_zero": True}, "30.5 MiB"),
        (1.7 * 1024**3, [], {"binary": True, "strip_trailing_zero": True}, "1.7 GiB"),
        (10**26 * 30, [], {"binary": True, "strip_trailing_zero": True}, "2.4 RiB"),
        (1000**10 * 40, [True], STRIP, "31.6 QiB"),
        ("3000", [], {"binary": True, "strip_trailing_zero": True}, "2.9 KiB"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_keep_meaningful_random_nonzero_decimals():
    cases, expected = _strip_cases(seed=31, count=500, point_zero=False)
    assert len(cases) > 200
    r = run_python(_snippet(cases), timeout=60.0)
    bad = _mismatches(cases, expected, r)
    assert bad == [], f"{len(bad)} of {len(cases)} calls differ, e.g. {bad[:15]}"


# ======================================================================================
# R-default-unchanged
# ======================================================================================


def test_default_contract_examples():
    rows = [
        (3000000, [], {}, "3.0 MB"),
        (1024, [], {"binary": True}, "1.0 KiB"),
        (3000, [], {"gnu": True}, "2.9K"),
        (300, [], {}, "300 Bytes"),
        (1, [], {}, "1 Byte"),
    ]
    cases, expected = _split(rows)
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


# Outputs asserted by the base commit's own test suite and docstring (default format).
_BASE_DEFAULT_FORMAT_ROWS = [
    (300, [], "300 Bytes"),
    ("1000", [], "1.0 kB"),
    (10**3, [], "1.0 kB"),
    (10**6, [], "1.0 MB"),
    (10**9, [], "1.0 GB"),
    (10**12, [], "1.0 TB"),
    (10**15, [], "1.0 PB"),
    (10**18, [], "1.0 EB"),
    (10**21, [], "1.0 ZB"),
    (10**24, [], "1.0 YB"),
    (10**27, [], "1.0 RB"),
    (10**30, [], "1.0 QB"),
    (1000**1 * 31, [], "31.0 kB"),
    (1000**2 * 32, [], "32.0 MB"),
    (1000**3 * 33, [], "33.0 GB"),
    (1000**4 * 34, [], "34.0 TB"),
    (1000**5 * 35, [], "35.0 PB"),
    (1000**6 * 36, [], "36.0 EB"),
    (1000**7 * 37, [], "37.0 ZB"),
    (1000**8 * 38, [], "38.0 YB"),
    (1000**9 * 39, [], "39.0 RB"),
    (1000**10 * 40, [], "40.0 QB"),
    (300, [True], "300 Bytes"),
    (1024**1 * 31, [True], "31.0 KiB"),
    (1024**2 * 32, [True], "32.0 MiB"),
    (1024**3 * 33, [True], "33.0 GiB"),
    (1024**4 * 34, [True], "34.0 TiB"),
    (1024**5 * 35, [True], "35.0 PiB"),
    (1024**6 * 36, [True], "36.0 EiB"),
    (1024**7 * 37, [True], "37.0 ZiB"),
    (1024**8 * 38, [True], "38.0 YiB"),
    (1024**9 * 39, [True], "39.0 RiB"),
    (1024**10 * 40, [True], "40.0 QiB"),
    (1000**1 * 31, [True], "30.3 KiB"),
    (1000**2 * 32, [True], "30.5 MiB"),
    (1000**3 * 33, [True], "30.7 GiB"),
    (1000**4 * 34, [True], "30.9 TiB"),
    (1000**5 * 35, [True], "31.1 PiB"),
    (1000**6 * 36, [True], "31.2 EiB"),
    (1000**7 * 37, [True], "31.3 ZiB"),
    (1000**8 * 38, [True], "31.4 YiB"),
    (1000**9 * 39, [True], "31.5 RiB"),
    (1000**10 * 40, [True], "31.6 QiB"),
    (1000**1 * 31, [False, True], "30.3K"),
    (1000**2 * 32, [False, True], "30.5M"),
    (1000**3 * 33, [False, True], "30.7G"),
    (1000**4 * 34, [False, True], "30.9T"),
    (1000**5 * 35, [False, True], "31.1P"),
    (1000**6 * 36, [False, True], "31.2E"),
    (1000**7 * 37, [False, True], "31.3Z"),
    (1000**8 * 38, [False, True], "31.4Y"),
    (1000**9 * 39, [False, True], "31.5R"),
    (1000**10 * 40, [False, True], "31.6Q"),
    (300, [False, True], "300B"),
    (3000, [False, True], "2.9K"),
    (3000000, [False, True], "2.9M"),
    (1024, [False, True], "1.0K"),
    (1, [False, False], "1 Byte"),
    (1.0, [False, False], "1 Byte"),
    ("1", [False, False], "1 Byte"),
    (1.123456789, [], "1 Bytes"),
    (1.123456789 * 10**3, [], "1.1 kB"),
    (1.123456789 * 10**6, [], "1.1 MB"),
    (1.123456789, [False, True], "1B"),
    (1.123456789 * 10**3, [False, True], "1.1K"),
    (1.123456789 * 10**6, [False, True], "1.1M"),
    (999999, [], "1.0 MB"),
    (999999999, [], "1.0 GB"),
    (999999999999, [], "1.0 TB"),
    (1024**2 - 1, [True], "1.0 MiB"),
    (1024**3 - 1, [True], "1.0 GiB"),
    (1024**2 - 1, [False, True], "1.0M"),
    (3000000, [], "3.0 MB"),
    (3000, [True], "2.9 KiB"),
    (10**28, [], "10.0 RB"),
    (10**34 * 3, [], "30000.0 QB"),
    (4096, [True], "4.0 KiB"),
]


def test_default_base_suite_and_docstring_outputs():
    rows = [(v, a, {}, e) for v, a, e in _BASE_DEFAULT_FORMAT_ROWS]
    rows += [
        (10**7, [], {}, "10.0 MB"),
        (3000, [], {"binary": True}, "2.9 KiB"),
        (3000, [], {"gnu": True}, "2.9K"),
        (3000, [], {"binary": True, "gnu": True}, "2.9K"),
        (1024, [True, True], {}, "1.0K"),
        (1, [], {"gnu": True}, "1B"),
        (0, [], {}, "0 Bytes"),
        (0, [False, True], {}, "0B"),
        (1023, [], {"binary": True}, "1023 Bytes"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_default_random_inputs_all_modes():
    rng = random.Random(41)
    cases, expected = [], []
    for value in _random_values(41, 400):
        for binary, gnu in _MODES:
            style = rng.randrange(3)
            if style == 0:
                call = [value, [binary, gnu], {}]
            elif style == 1:
                call = [value, [], {"binary": binary, "gnu": gnu}]
            else:
                call = [value, [], {k: True for k, on in (("binary", binary), ("gnu", gnu)) if on}]
            cases.append(call)
            expected.append(_base_naturalsize(value, binary, gnu))
    r = run_python(_snippet(cases), timeout=60.0)
    bad = _mismatches(cases, expected, r)
    assert bad == [], f"{len(bad)} of {len(cases)} calls differ, e.g. {bad[:15]}"


# ======================================================================================
# R-custom-format-unchanged
# ======================================================================================


def test_custom_format_contract_examples():
    rows = [
        (3000, [False, True, "%.3f"], {}, "2.930K"),
        (3000000, [], {"format": "%.2f"}, "3.00 MB"),
    ]
    cases, expected = _split(rows)
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_custom_format_positional_table():
    rows = [
        (3141592, [False, False, "%.2f"], {}, "3.14 MB"),
        (3000, [False, True, "%.3f"], {}, "2.930K"),
        (3000000000, [False, True, "%.0f"], {}, "3G"),
        (10**26 * 30, [True, False, "%.3f"], {}, "2.423 RiB"),
        (3000000, [False, False, "%.2f"], {}, "3.00 MB"),
        (3000000, [False, False, "%.1f"], {}, "3.0 MB"),
        (2500000, [False, False, "%.3f"], {}, "2.500 MB"),
        (10**7, [False, False, "%.0f"], {}, "10 MB"),
        (999999, [False, False, "%.2f"], {}, "1.00 MB"),
        (1024, [True, False, "%.2f"], {}, "1.00 KiB"),
        (1024, [False, True, "%.2f"], {}, "1.00K"),
        (3000000, [False, False, "%.2e"], {}, "3.00e+00 MB"),
        (3000, [False, True, "%d"], {}, "2K"),
        (300, [False, False, "%.2f"], {}, "300 Bytes"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


def test_custom_format_keyword_table():
    rows = [
        (3000000, [], {"format": "%.2f"}, "3.00 MB"),
        (3141592, [], {"format": "%.2f"}, "3.14 MB"),
        (3000000, [], {"format": "%.1f"}, "3.0 MB"),
        (2500000, [], {"format": "%.3f"}, "2.500 MB"),
        (10**6, [], {"format": "%.0f"}, "1 MB"),
        (10**7, [], {"format": "%.0f"}, "10 MB"),
        (3000000, [], {"format": "%.2e"}, "3.00e+00 MB"),
        (3141592, [], {"format": "%d"}, "3 MB"),
        (10**34 * 3, [], {"format": "%.2f"}, "30000.00 QB"),
        (1024, [], {"binary": True, "format": "%.3f"}, "1.000 KiB"),
        (3000, [True], {"format": "%.2f"}, "2.93 KiB"),
        (3000, [], {"gnu": True, "format": "%.3f"}, "2.930K"),
        (1024, [], {"gnu": True, "format": "%.2f"}, "1.00K"),
        (300, [], {"format": "%.3f"}, "300 Bytes"),
    ]
    cases, expected = _split(_with_negatives(rows))
    r = run_python(_snippet(cases))
    assert _mismatches(cases, expected, r) == []


# Rounding formats only: a truncating format such as "%d" would turn 1-ulp float
# differences (unrelated to this task) into visible output changes.
_FORMATS = ("%.0f", "%.1f", "%.2f", "%.3f", "%.4f", "%.2e", "%g", "%6.2f", "%+.1f")


def test_custom_format_random_inputs():
    rng = random.Random(51)
    cases, expected = [], []
    for value in _random_values(51, 1200):
        binary, gnu = rng.choice(_MODES)
        fmt = rng.choice(_FORMATS)
        style = rng.randrange(3)
        if style == 0:
            call = [value, [binary, gnu, fmt], {}]
        elif style == 1:
            call = [value, [], {"binary": binary, "gnu": gnu, "format": fmt}]
        else:
            call = [value, [binary, gnu], {"format": fmt}]
        cases.append(call)
        expected.append(_base_naturalsize(value, binary, gnu, fmt))
    r = run_python(_snippet(cases), timeout=60.0)
    bad = _mismatches(cases, expected, r)
    assert bad == [], f"{len(bad)} of {len(cases)} calls differ, e.g. {bad[:15]}"
