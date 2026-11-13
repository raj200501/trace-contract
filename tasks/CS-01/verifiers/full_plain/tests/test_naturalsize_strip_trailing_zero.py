"""Hidden behavioural tests for CS-01 (condition full_plain).

The change under test gives ``humanize.naturalsize`` an opt-in keyword argument
``strip_trailing_zero`` (default ``False``) that drops a trailing ".0" from the
rendered number, while every existing call keeps its exact output.

Candidate code is reached only through the sandbox: each check sends a batch of
``naturalsize`` calls to ``run_python`` and compares the returned strings with
expectations that are either written out below or computed in this (trusted)
process by ``_base_naturalsize``, a copy of the base-commit algorithm.
"""

from __future__ import annotations

import functools
import json
import math
import random
import re

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_strip_true_spec_examples": ["R5"],
    "test_strip_false_is_the_default_behaviour": ["R5"],
    "test_default_output_matches_base_examples": ["R4"],
    "test_default_output_matches_jinja2_filesizeformat": ["R4"],
    "test_default_output_matches_base_sweep": ["R4"],
    "test_default_output_keeps_translated_units": ["R4"],
    "test_custom_format_calls_unchanged": ["R6"],
    "test_strip_keeps_meaningful_decimal": ["R2"],
    "test_strip_in_gnu_mode": ["R8"],
    "test_strip_negative_sizes": ["R8"],
    "test_strip_decides_on_rounded_one_decimal_number": ["R9"],
    "test_strip_keeps_integer_digits": ["R9"],
    "test_strip_leaves_outputs_without_decimal_part_unchanged": ["R9"],
    "test_strip_sweep_removes_only_trailing_dot_zero": ["R9", "R8", "R2"],
}

STRIP = {"strip_trailing_zero": True}

# ---------------------------------------------------------------------------
# Snippets executed in the sandbox
# ---------------------------------------------------------------------------

# Runs an explicit list of [args, kwargs] calls; one output string per call.
_CALLS_SNIPPET = """
import json
from humanize import naturalsize

calls = json.loads(__PAYLOAD__)
out = []
for args, kwargs in calls:
    try:
        out.append(naturalsize(*args, **kwargs))
    except Exception as exc:
        out.append("<raised %s: %s>" % (type(exc).__name__, exc))
result = out
"""

# Runs naturalsize(value, *extra, **kwargs) for every value and every variant;
# one row of output strings per variant.
_BATCH_SNIPPET = """
import json
from humanize import naturalsize

payload = json.loads(__PAYLOAD__)
out = []
for extra, kwargs in payload["variants"]:
    row = []
    for value in payload["inputs"]:
        try:
            row.append(naturalsize(value, *extra, **kwargs))
        except Exception as exc:
            row.append("<raised %s: %s>" % (type(exc).__name__, exc))
    out.append(row)
result = out
"""

# Builds a tiny gettext catalog under /tmp and activates it through the public
# humanize.activate(locale, path) API, mirroring tests/test_i18n.py for fr_FR.
_I18N_SNIPPET = r'''
import os
import struct
import tempfile

import humanize
from humanize import naturalsize


def write_mo(path, messages):
    keys = sorted(messages)
    ids = b""
    strs = b""
    offsets = []
    for key in keys:
        k = key.encode("utf-8")
        v = messages[key].encode("utf-8")
        offsets.append((len(ids), len(k), len(strs), len(v)))
        ids += k + b"\0"
        strs += v + b"\0"
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    table = []
    for o1, l1, _o2, _l2 in offsets:
        table += [l1, o1 + keystart]
    for _o1, _l1, o2, l2 in offsets:
        table += [l2, o2 + valuestart]
    header = struct.pack(
        "<7I", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + 8 * len(keys), 0, 0
    )
    with open(path, "wb") as handle:
        handle.write(header + struct.pack("<%dI" % len(table), *table) + ids + strs)


catalog = {
    "": "Content-Type: text/plain; charset=UTF-8\n",
    "kB": "Ko",
    "MB": "Mo",
    "GB": "Go",
    "KiB": "Kio",
    "MiB": "Mio",
    "%d Byte": "%d octet",
    "%d Bytes": "%d octets",
}
out = {}
with tempfile.TemporaryDirectory(dir="/tmp") as root:
    folder = os.path.join(root, "fr_FR", "LC_MESSAGES")
    os.makedirs(folder)
    write_mo(os.path.join(folder, "humanize.mo"), catalog)
    humanize.activate("fr_FR", path=root)
    try:
        out["translated"] = [
            naturalsize(42000),
            naturalsize(42000000),
            naturalsize(42000000000),
            naturalsize(-42000),
            naturalsize(3000, binary=True),
            naturalsize(3000000, binary=True),
            naturalsize(1),
            naturalsize(42),
            naturalsize(-42),
            naturalsize(1024, gnu=True),
        ]
    finally:
        humanize.deactivate()
out["after_deactivate"] = [naturalsize(42000), naturalsize(1), naturalsize(42)]
result = out
'''


def _c(*args, **kwargs):
    """One naturalsize call: positional args and keyword args."""
    return (list(args), kwargs)


def _calls_snippet(cases):
    calls = [[args, kwargs] for (args, kwargs), _expected in cases]
    return _CALLS_SNIPPET.replace("__PAYLOAD__", repr(json.dumps(calls)))


def _batch_snippet(inputs, variants):
    payload = {"inputs": inputs, "variants": [[e, k] for e, k in variants]}
    return _BATCH_SNIPPET.replace("__PAYLOAD__", repr(json.dumps(payload)))


def _describe(args, kwargs):
    parts = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    return "naturalsize(" + ", ".join(parts) + ")"


def _report(lines, limit=15):
    shown = "\n".join(lines[:limit])
    if len(lines) > limit:
        shown += f"\n... {len(lines)} mismatches in total"
    return shown


def _case_mismatches(cases, got):
    if not isinstance(got, list) or len(got) != len(cases):
        return f"unexpected result shape: {got!r:.500}"
    lines = []
    for ((args, kwargs), expected), actual in zip(cases, got):
        if actual != expected:
            lines.append(f"{_describe(args, kwargs)} -> {actual!r}, expected {expected!r}")
    return _report(lines)


def _batch_mismatches(inputs, variants, got, expected):
    if not isinstance(got, list) or len(got) != len(expected):
        return f"unexpected result shape: {got!r:.500}"
    lines = []
    for (extra, kwargs), got_row, exp_row in zip(variants, got, expected):
        if not isinstance(got_row, list) or len(got_row) != len(exp_row):
            lines.append(f"variant {extra!r} {kwargs!r}: bad row {got_row!r:.200}")
            continue
        for value, actual, want in zip(inputs, got_row, exp_row):
            if actual != want:
                call = _describe([value, *extra], kwargs)
                lines.append(f"{call} -> {actual!r}, expected {want!r}")
    return _report(lines)


def _outputs(cases):
    """The expected output strings of a list of cases, in order."""
    return [expected for _call, expected in cases]


# ---------------------------------------------------------------------------
# Expected behaviour, computed in this trusted process
# ---------------------------------------------------------------------------

_DECIMAL = ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB")
_BINARY = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB")
_GNU = "KMGTPEZYRQ"


def _base_naturalsize(value, binary=False, gnu=False, format="%.1f"):
    """naturalsize exactly as at the base commit (no locale active)."""
    if gnu:
        suffix = _GNU
    elif binary:
        suffix = _BINARY
    else:
        suffix = _DECIMAL
    base = 1024 if (gnu or binary) else 1000
    bytes_ = float(value)
    abs_bytes = abs(bytes_)
    if abs_bytes == 1 and not gnu:
        return "%d Byte" % int(bytes_)
    if abs_bytes < base:
        return f"{int(bytes_)}B" if gnu else "%d Bytes" % int(bytes_)
    exp = int(min(math.log(abs_bytes, base), len(suffix)))
    if exp < len(suffix) and abs(float(format % (abs_bytes / (base**exp)))) >= base:
        exp += 1
    space = "" if gnu else " "
    return format % (bytes_ / (base**exp)) + space + suffix[exp - 1]


# A default-format output with a ".0" decimal part, e.g. "-30000.0 QB" or "1.0K".
_DOT_ZERO = re.compile(r"^(-?\d+)\.0(?=[^\d.]*$)")


def _strip_dot_zero(text):
    """Expected strip_trailing_zero=True output for a default-format output."""
    return _DOT_ZERO.sub(r"\1", text)


def _expected(value, extra, kwargs):
    kwargs = dict(kwargs)
    strip = kwargs.pop("strip_trailing_zero", False)
    text = _base_naturalsize(value, *extra, **kwargs)
    return _strip_dot_zero(text) if strip else text


def _batch_expected(inputs, variants):
    return [[_expected(v, extra, kwargs) for v in inputs] for extra, kwargs in variants]


@functools.lru_cache(maxsize=None)
def _sweep_inputs_cached():
    rng = random.Random(20261113)
    values = [
        0, 1, 2, 10, 100, 999, 1000, 1001, 1023, 1024, 1025, 1500, 1536, 2048,
        3000, 4096, 10240, 102400, 100500, 999949, 999950, 999999, 1000000,
        1048575, 1048576, 2900000, 2950000, 3000000, 3000001, 3049999, 3050000,
        10500000, 10**7, 10**8, 10**28, 10**33, 3 * 10**34, 10**36,
    ]  # fmt: skip
    for base in (1000, 1024):
        for k in range(1, 12):
            power = base**k
            values += [power - 1, power, power + 1]
    for _ in range(100):
        values.append(int(rng.uniform(1.0, 10.0) * 10 ** rng.randint(0, 35)))
    for _ in range(60):
        base = rng.choice((1000, 1024))
        k = rng.randint(1, 10)
        mantissa = rng.randint(1, 999)
        frac = rng.choice((0.0, 0.04, 0.049, 0.05, 0.051, 0.5, 0.949, 0.95, 0.96))
        values.append(int((mantissa + frac) * base**k))
    for _ in range(25):
        values.append(round(rng.uniform(0.0, 5000.0), 3))
    values += [1.0, 1.5, 0.5, 1.123456789, 1.123456789e3, 1.123456789e6, 2.5e9]
    inputs = []
    for v in values:
        inputs += [v, -v]
    for s in ("1000", "1", "1.5", "3000000", "999999", "1048575", "2.5e6", "4096"):
        inputs += [s, "-" + s]
    return tuple(inputs)


def _sweep_inputs():
    """Deterministic ints, floats and strings (each also negated) over all units."""
    return list(_sweep_inputs_cached())


# Rows of the base repository's tests/test_filesize.py that use the default
# format; each is also checked negated, exactly as that test does.
_ORIGINAL_DEFAULT_ROWS = [
    ([300], "300 Bytes"),
    (["1000"], "1.0 kB"),
    ([10**3], "1.0 kB"),
    ([10**6], "1.0 MB"),
    ([10**9], "1.0 GB"),
    ([10**12], "1.0 TB"),
    ([10**15], "1.0 PB"),
    ([10**18], "1.0 EB"),
    ([10**21], "1.0 ZB"),
    ([10**24], "1.0 YB"),
    ([10**27], "1.0 RB"),
    ([10**30], "1.0 QB"),
    ([1000**1 * 31], "31.0 kB"),
    ([1000**2 * 32], "32.0 MB"),
    ([1000**3 * 33], "33.0 GB"),
    ([1000**4 * 34], "34.0 TB"),
    ([1000**5 * 35], "35.0 PB"),
    ([1000**6 * 36], "36.0 EB"),
    ([1000**7 * 37], "37.0 ZB"),
    ([1000**8 * 38], "38.0 YB"),
    ([1000**9 * 39], "39.0 RB"),
    ([1000**10 * 40], "40.0 QB"),
    ([300, True], "300 Bytes"),
    ([1024**1 * 31, True], "31.0 KiB"),
    ([1024**2 * 32, True], "32.0 MiB"),
    ([1024**3 * 33, True], "33.0 GiB"),
    ([1024**4 * 34, True], "34.0 TiB"),
    ([1024**5 * 35, True], "35.0 PiB"),
    ([1024**6 * 36, True], "36.0 EiB"),
    ([1024**7 * 37, True], "37.0 ZiB"),
    ([1024**8 * 38, True], "38.0 YiB"),
    ([1024**9 * 39, True], "39.0 RiB"),
    ([1024**10 * 40, True], "40.0 QiB"),
    ([1000**1 * 31, True], "30.3 KiB"),
    ([1000**2 * 32, True], "30.5 MiB"),
    ([1000**3 * 33, True], "30.7 GiB"),
    ([1000**4 * 34, True], "30.9 TiB"),
    ([1000**5 * 35, True], "31.1 PiB"),
    ([1000**6 * 36, True], "31.2 EiB"),
    ([1000**7 * 37, True], "31.3 ZiB"),
    ([1000**8 * 38, True], "31.4 YiB"),
    ([1000**9 * 39, True], "31.5 RiB"),
    ([1000**10 * 40, True], "31.6 QiB"),
    ([1000**1 * 31, False, True], "30.3K"),
    ([1000**2 * 32, False, True], "30.5M"),
    ([1000**3 * 33, False, True], "30.7G"),
    ([1000**4 * 34, False, True], "30.9T"),
    ([1000**5 * 35, False, True], "31.1P"),
    ([1000**6 * 36, False, True], "31.2E"),
    ([1000**7 * 37, False, True], "31.3Z"),
    ([1000**8 * 38, False, True], "31.4Y"),
    ([1000**9 * 39, False, True], "31.5R"),
    ([1000**10 * 40, False, True], "31.6Q"),
    ([300, False, True], "300B"),
    ([3000, False, True], "2.9K"),
    ([3000000, False, True], "2.9M"),
    ([1024, False, True], "1.0K"),
    ([1, False, False], "1 Byte"),
    ([1.0, False, False], "1 Byte"),
    (["1", False, False], "1 Byte"),
    ([1.123456789], "1 Bytes"),
    ([1.123456789 * 10**3], "1.1 kB"),
    ([1.123456789 * 10**6], "1.1 MB"),
    ([1.123456789, False, True], "1B"),
    ([1.123456789 * 10**3, False, True], "1.1K"),
    ([1.123456789 * 10**6, False, True], "1.1M"),
    ([999999], "1.0 MB"),
    ([999999999], "1.0 GB"),
    ([999999999999], "1.0 TB"),
    ([1024**2 - 1, True], "1.0 MiB"),
    ([1024**3 - 1, True], "1.0 GiB"),
    ([1024**2 - 1, False, True], "1.0M"),
]


def _negated(args):
    first = args[0]
    first = -first if isinstance(first, int) else f"-{first}"
    return [first, *args[1:]]


# ---------------------------------------------------------------------------
# R5: the new opt-in keyword argument
# ---------------------------------------------------------------------------


def test_strip_true_spec_examples():
    cases = [
        (_c(3000000, **STRIP), "3 MB"),
        (_c(1024, binary=True, **STRIP), "1 KiB"),
        (_c(3000, binary=True, **STRIP), "2.9 KiB"),
        (_c(1000, **STRIP), "1 kB"),
        (_c(10**6, **STRIP), "1 MB"),
        (_c(10**9, **STRIP), "1 GB"),
        (_c(1024**2, binary=True, **STRIP), "1 MiB"),
        (_c("1000", **STRIP), "1 kB"),
        (_c(3000000.0, **STRIP), "3 MB"),
        (_c(3000000, False, **STRIP), "3 MB"),
        (_c(3000, True, **STRIP), "2.9 KiB"),
        (_c(1024, True, False, **STRIP), "1 KiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_strip_false_is_the_default_behaviour():
    off = {"strip_trailing_zero": False}
    cases = [
        (_c(3000000), "3.0 MB"),
        (_c(3000000, **off), "3.0 MB"),
        (_c(1024, binary=True, **off), "1.0 KiB"),
        (_c(3000, binary=True, **off), "2.9 KiB"),
        (_c(1024, gnu=True, **off), "1.0K"),
        (_c(-3000000, **off), "-3.0 MB"),
        (_c(-4096, True, **off), "-4.0 KiB"),
        (_c(10**7, **off), "10.0 MB"),
        (_c(999999, **off), "1.0 MB"),
        (_c(3 * 10**34, **off), "30000.0 QB"),
        (_c(100, **off), "100 Bytes"),
        (_c(1, **off), "1 Byte"),
        (_c(300, gnu=True, **off), "300B"),
        (_c("3000000", **off), "3.0 MB"),
        (_c(3000000, False, False, "%.2f", **off), "3.00 MB"),
        (_c(3000, False, True, "%.3f", **off), "2.930K"),
        (_c(3000000, format="%.2f", **off), "3.00 MB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


# ---------------------------------------------------------------------------
# R4: default output (no strip_trailing_zero, default format) is unchanged
# ---------------------------------------------------------------------------


def test_default_output_matches_base_examples():
    cases = []
    for args, expected in _ORIGINAL_DEFAULT_ROWS:
        cases.append((_c(*args), expected))
        cases.append((_c(*_negated(args)), "-" + expected))
    cases += [
        (_c(3000000), "3.0 MB"),
        (_c(1024, binary=True), "1.0 KiB"),
        (_c(3000, binary=True), "2.9 KiB"),
        (_c(1024, gnu=True), "1.0K"),
        (_c(3000, gnu=True), "2.9K"),
        (_c(10**28), "10.0 RB"),
        (_c(10**34 * 3), "30000.0 QB"),
        (_c(-4096, True), "-4.0 KiB"),
        (_c(999999, gnu=True), "976.6K"),
        (_c(1024**2 - 1, gnu=True), "1.0M"),
        (_c("1048575", binary=True), "1.0 MiB"),
        (_c(2900000), "2.9 MB"),
        (_c(10**7), "10.0 MB"),
        (_c(0), "0 Bytes"),
        (_c(0, gnu=True), "0B"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_default_output_matches_jinja2_filesizeformat():
    # Values of jinja2's do_filesizeformat(value) / do_filesizeformat(value, True)
    # (one decimal place), which the base version already matched.
    jinja2_outputs = [
        (0, "0 Bytes", "0 Bytes"),
        (1, "1 Byte", "1 Byte"),
        (2, "2 Bytes", "2 Bytes"),
        (300, "300 Bytes", "300 Bytes"),
        (1000, "1.0 kB", "1000 Bytes"),
        (1024, "1.0 kB", "1.0 KiB"),
        (3000, "3.0 kB", "2.9 KiB"),
        (10**6, "1.0 MB", "976.6 KiB"),
        (2900000, "2.9 MB", "2.8 MiB"),
        (3000000, "3.0 MB", "2.9 MiB"),
        (123456789, "123.5 MB", "117.7 MiB"),
        (5 * 1000**8, "5.0 YB", "4.1 YiB"),
        ("3000", "3.0 kB", "2.9 KiB"),
    ]
    cases = []
    for value, decimal, binary in jinja2_outputs:
        cases.append((_c(value), decimal))
        cases.append((_c(value, binary=True), binary))
        cases.append((_c(value, True), binary))
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_default_output_matches_base_sweep():
    inputs = _sweep_inputs()
    variants = [
        ([], {}),
        ([], {"binary": False, "gnu": False}),
        ([], {"binary": True}),
        ([], {"gnu": True}),
        ([], {"binary": True, "gnu": True}),
    ]
    expected = _batch_expected(inputs, variants)
    r = run_python(_batch_snippet(inputs, variants), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == expected, _batch_mismatches(inputs, variants, r.value, expected)


def test_default_output_keeps_translated_units():
    r = run_python(_I18N_SNIPPET, timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == {
        "translated": [
            "42.0 Ko",
            "42.0 Mo",
            "42.0 Go",
            "-42.0 Ko",
            "2.9 Kio",
            "2.9 Mio",
            "1 octet",
            "42 octets",
            "-42 octets",
            "1.0K",
        ],
        "after_deactivate": ["42.0 kB", "1 Byte", "42 Bytes"],
    }


# ---------------------------------------------------------------------------
# R6: custom formats and the positional parameter order are unchanged
# ---------------------------------------------------------------------------


def test_custom_format_calls_unchanged():
    cases = [
        (_c(3000, False, True, "%.3f"), "2.930K"),
        (_c(3000000, format="%.2f"), "3.00 MB"),
        (_c(3141592, False, False, "%.2f"), "3.14 MB"),
        (_c(-3141592, False, False, "%.2f"), "-3.14 MB"),
        (_c(-3000, False, True, "%.3f"), "-2.930K"),
        (_c(3000000000, False, True, "%.0f"), "3G"),
        (_c(-3000000000, False, True, "%.0f"), "-3G"),
        (_c(10**26 * 30, True, False, "%.3f"), "2.423 RiB"),
        (_c(-(10**26) * 30, True, False, "%.3f"), "-2.423 RiB"),
        (_c(3000, gnu=True, format="%.3f"), "2.930K"),
        (_c(3141592, format="%.2f"), "3.14 MB"),
        (_c(10**26 * 30, binary=True, format="%.3f"), "2.423 RiB"),
        (_c(3000000, False, False, "%.1f"), "3.0 MB"),
        (_c(1024, True, False, "%.2f"), "1.00 KiB"),
        (_c(3000000, False, False, "%.2e"), "3.00e+00 MB"),
        (_c(999999, format="%.3f"), "999.999 kB"),
        (_c(999999.9, format="%.0f"), "1 MB"),
        (_c(1, format="%.2f"), "1 Byte"),
        (_c(100, format="%.2f"), "100 Bytes"),
        (_c(300, False, True, "%.3f"), "300B"),
        (_c(3000, True), "2.9 KiB"),
        (_c(300, False, True), "300B"),
        (_c(3000, False, True), "2.9K"),
        (_c(-4096, True), "-4.0 KiB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)

    # Differential sweep: positional and keyword spellings of custom formats.
    inputs = _sweep_inputs()[::7]
    modes = [(False, False), (True, False), (False, True), (True, True)]
    variants = []
    for fmt in ("%.0f", "%.2f", "%.3f", "%.2e"):
        for binary, gnu in modes:
            variants.append(([binary, gnu, fmt], {}))
            variants.append(([], {"binary": binary, "gnu": gnu, "format": fmt}))
    expected = _batch_expected(inputs, variants)
    r = run_python(_batch_snippet(inputs, variants), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == expected, _batch_mismatches(inputs, variants, r.value, expected)


# ---------------------------------------------------------------------------
# R2: a meaningful (non-zero) decimal is kept
# ---------------------------------------------------------------------------


def test_strip_keeps_meaningful_decimal():
    cases = [
        (_c(3000, binary=True), "2.9 KiB"),
        (_c(3000, binary=True, **STRIP), "2.9 KiB"),
        (_c(3000, True, **STRIP), "2.9 KiB"),
        (_c(2900000), "2.9 MB"),
        (_c(2900000, **STRIP), "2.9 MB"),
        (_c(1500, **STRIP), "1.5 kB"),
        (_c(10500000, **STRIP), "10.5 MB"),
        (_c(100500, **STRIP), "100.5 kB"),
        (_c(1.123456789e6, **STRIP), "1.1 MB"),
        (_c(123456789, **STRIP), "123.5 MB"),
        (_c(31000, binary=True, **STRIP), "30.3 KiB"),
        (_c(1000**10 * 40, binary=True, **STRIP), "31.6 QiB"),
        (_c(2900000, gnu=True, **STRIP), "2.8M"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


# ---------------------------------------------------------------------------
# R8: trimming works in every mode and for negative sizes
# ---------------------------------------------------------------------------


def test_strip_in_gnu_mode():
    cases = [
        (_c(1024, gnu=True, **STRIP), "1K"),
        (_c(3000, gnu=True, **STRIP), "2.9K"),
        (_c(1024, gnu=True), "1.0K"),
        (_c(3000, gnu=True), "2.9K"),
        (_c(1024, False, True, **STRIP), "1K"),
        (_c(1024, binary=True, gnu=True, **STRIP), "1K"),
        (_c(1024**2, gnu=True, **STRIP), "1M"),
        (_c(1024**2 - 1, gnu=True, **STRIP), "1M"),
        (_c(3 * 1024**3, gnu=True, **STRIP), "3G"),
        (_c(3000000000, gnu=True, **STRIP), "2.8G"),
        (_c(100 * 1024, gnu=True, **STRIP), "100K"),
        (_c(31000, gnu=True, **STRIP), "30.3K"),
        (_c(1024**10 * 40, gnu=True, **STRIP), "40Q"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_strip_negative_sizes():
    cases = [
        (_c(-3000000, **STRIP), "-3 MB"),
        (_c(-4096, binary=True, **STRIP), "-4 KiB"),
        (_c(-3000, binary=True, **STRIP), "-2.9 KiB"),
        (_c(-4096, True, **STRIP), "-4 KiB"),
        (_c(-4096, True), "-4.0 KiB"),
        (_c(-1024, gnu=True, **STRIP), "-1K"),
        (_c(-3000, gnu=True, **STRIP), "-2.9K"),
        (_c(-999999, **STRIP), "-1 MB"),
        (_c(-2900000, **STRIP), "-2.9 MB"),
        (_c(-(10**7), **STRIP), "-10 MB"),
        (_c(-3 * 10**34, **STRIP), "-30000 QB"),
        (_c(-4096, **STRIP), "-4.1 kB"),
        (_c("-3000000", **STRIP), "-3 MB"),
        (_c(-3000000.0, **STRIP), "-3 MB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


# ---------------------------------------------------------------------------
# R9: decision on the rendered one-decimal number; only ".0" is removed
# ---------------------------------------------------------------------------


def test_strip_decides_on_rounded_one_decimal_number():
    cases = [
        (_c(3000001, **STRIP), "3 MB"),
        (_c(999999, **STRIP), "1 MB"),
        (_c(2999999, **STRIP), "3 MB"),
        (_c(3049999, **STRIP), "3 MB"),
        (_c(2950001, **STRIP), "3 MB"),
        (_c(1049000, **STRIP), "1 MB"),
        (_c(3000000.4, **STRIP), "3 MB"),
        (_c(999999999, **STRIP), "1 GB"),
        (_c(10**30 - 1, **STRIP), "1 QB"),
        (_c(1024**2 - 1, binary=True, **STRIP), "1 MiB"),
        (_c(1024**3 - 1, binary=True, **STRIP), "1 GiB"),
        (_c(1024**2 - 1, gnu=True, **STRIP), "1M"),
        (_c(3050001, **STRIP), "3.1 MB"),
        (_c(1050000, **STRIP), "1.1 MB"),
        (_c(2940000, **STRIP), "2.9 MB"),
        (_c(999949999, **STRIP), "999.9 MB"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_strip_keeps_integer_digits():
    cases = [
        (_c(10**7, **STRIP), "10 MB"),
        (_c(10**8, **STRIP), "100 MB"),
        (_c(3 * 10**34, **STRIP), "30000 QB"),
        (_c(10**28, **STRIP), "10 RB"),
        (_c(10**33, **STRIP), "1000 QB"),
        (_c(10**36, **STRIP), "1000000 QB"),
        (_c(20000, **STRIP), "20 kB"),
        (_c(100000, **STRIP), "100 kB"),
        (_c(1000**10 * 40, **STRIP), "40 QB"),
        (_c(-(10**8), **STRIP), "-100 MB"),
        (_c(10 * 1024, binary=True, **STRIP), "10 KiB"),
        (_c(200 * 1024**2, binary=True, **STRIP), "200 MiB"),
        (_c(1024**10 * 40, binary=True, **STRIP), "40 QiB"),
        (_c(100 * 1024, gnu=True, **STRIP), "100K"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_strip_leaves_outputs_without_decimal_part_unchanged():
    cases = [
        (_c(100, **STRIP), "100 Bytes"),
        (_c(1, **STRIP), "1 Byte"),
        (_c(0, **STRIP), "0 Bytes"),
        (_c(10, **STRIP), "10 Bytes"),
        (_c(999, **STRIP), "999 Bytes"),
        (_c(-1, **STRIP), "-1 Byte"),
        (_c(-100, **STRIP), "-100 Bytes"),
        (_c(1.0, **STRIP), "1 Byte"),
        (_c("1", **STRIP), "1 Byte"),
        (_c("100", **STRIP), "100 Bytes"),
        (_c(1.123456789, **STRIP), "1 Bytes"),
        (_c(1000, binary=True, **STRIP), "1000 Bytes"),
        (_c(1023, binary=True, **STRIP), "1023 Bytes"),
        (_c(300, gnu=True, **STRIP), "300B"),
        (_c(1000, gnu=True, **STRIP), "1000B"),
        (_c(-300, gnu=True, **STRIP), "-300B"),
        (_c(1, gnu=True, **STRIP), "1B"),
    ]
    r = run_python(_calls_snippet(cases), timeout=30.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == _outputs(cases), _case_mismatches(cases, r.value)


def test_strip_sweep_removes_only_trailing_dot_zero():
    # For the default format, strip_trailing_zero=True must give the default
    # output with a ".0" decimal part removed and be identical otherwise.
    inputs = _sweep_inputs()
    variants = [
        ([], dict(STRIP)),
        ([], {"binary": True, **STRIP}),
        ([], {"gnu": True, **STRIP}),
        ([], {"binary": True, "gnu": True, **STRIP}),
    ]
    expected = _batch_expected(inputs, variants)
    r = run_python(_batch_snippet(inputs, variants), timeout=60.0)
    assert r.ok, f"{r.error_type}: {r.error}"
    assert r.value == expected, _batch_mismatches(inputs, variants, r.value, expected)
