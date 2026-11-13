"""Hidden behavioural tests for CS-01, condition initial_plain.

Requirements checked (initial contract): with the default format,
``naturalsize`` no longer prints a trailing ".0" for a whole-number value in
decimal mode (R1) and binary mode (R2), for every unit and without touching
zeros of the integer part (R4). The decision follows the printed, rounded
one-decimal value rather than the raw value being an exact integer (R5).
Results whose printed decimal digit is non-zero are unchanged (R3).

All candidate code runs in the sandbox through ``tc_sandbox.run_python``.
Two things are deliberately left unchecked because the requirements do not
cover them: GNU mode (``gnu=True``) and custom ``format`` strings.
"""

import inspect
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_r1_decimal_whole_number_has_no_trailing_zero": ["R1"],
    "test_r2_binary_whole_number_has_no_trailing_zero": ["R2"],
    "test_r3_contract_examples_keep_their_decimal": ["R3"],
    "test_r3_other_nonzero_decimals_unchanged": ["R3"],
    "test_r4_contract_examples": ["R4"],
    "test_r4_every_decimal_unit": ["R4"],
    "test_r4_every_binary_unit": ["R4"],
    "test_r4_integer_part_zeros_are_kept": ["R4"],
    "test_r5_contract_examples": ["R5"],
    "test_r5_values_that_round_to_whole_numbers": ["R5"],
    "test_sweep_decimal_mode_matches_rule": ["R3", "R4", "R5"],
    "test_sweep_binary_mode_matches_rule": ["R3", "R4", "R5"],
    "test_negative_sizes": ["R3", "R4", "R5"],
    "test_float_and_string_inputs": ["R3", "R4", "R5"],
}

DECIMAL_UNITS = ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB")
BINARY_UNITS = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB")


def _calls_snippet(calls):
    """Build a snippet whose ``result`` is naturalsize() for each (value, binary).

    Decimal calls are ``naturalsize(value)`` and binary calls are
    ``naturalsize(value, binary=True)``, as the requirements phrase them. An
    exception is recorded as a string so that one input cannot hide the others.
    """
    return (
        "from humanize import naturalsize\n"
        f"calls = {list(calls)!r}\n"
        "out = []\n"
        "for value, binary in calls:\n"
        "    try:\n"
        "        if binary:\n"
        "            out.append(naturalsize(value, binary=True))\n"
        "        else:\n"
        "            out.append(naturalsize(value))\n"
        "    except Exception as exc:\n"
        "        out.append('raised ' + type(exc).__name__ + ': ' + str(exc))\n"
        "result = out\n"
    )


def _mismatches(cases, got):
    """Describe every (value, binary) case whose output differs from expected."""
    if not isinstance(got, list) or len(got) != len(cases):
        return f"unexpected result: {got!r}"
    return [
        (value, "binary" if binary else "decimal", out, expected)
        for ((value, binary), expected), out in zip(cases, got)
        if out != expected
    ]


def _sweep_values(binary):
    """Deterministic sizes of at least one unit (1 kB / 1 KiB) up to the last unit."""
    base = 1024 if binary else 1000
    values = list(range(base, 12 * base + 1))
    values.extend(range(base**2 - 2 * base, base**2 + 2 * base))
    mantissas = [1, 1.001, 1.04, 1.05, 1.06, 1.5, 2, 2.25, 2.95, 2.96, 2.999999,
                 3, 9.94, 9.95, 9.96, 10, 10.04, 99.94, 99.95, 99.96, 100, 512,
                 999.9, 999.94, 999.95, 999.96, 999.999]
    for k in range(1, 11):
        values.extend(int(m * base**k) for m in mantissas)
        values.extend((base**k - 1, base**k + 1))
    rnd = random.Random(20261113 + base)
    for _ in range(2000):
        k = rnd.randint(1, 10)
        values.append(rnd.randint(base**k, base ** (k + 1) - 1))
    for _ in range(500):
        values.append(base ** rnd.uniform(1.0, 11.0))
    return [v for v in values if abs(v) >= base]


def _expected_naturalsize(value, binary):
    """Oracle for sizes of at least one unit: the base-commit output of
    ``naturalsize(value[, binary=True])`` with a printed trailing ".0" removed.

    Unit selection (including the carry to the next unit when rounding reaches
    the base) and the default "%.1f" rounding are the base commit's, which the
    requirements leave unchanged; only a printed ".0" is dropped.
    """
    from math import log

    if binary:
        units = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB")
        base = 1024
    else:
        units = ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB")
        base = 1000
    number = float(value)
    magnitude = abs(number)
    exp = int(min(log(magnitude, base), len(units)))
    if exp < len(units) and abs(float("%.1f" % (magnitude / base**exp))) >= base:
        exp += 1
    text = "%.1f" % (number / base**exp)
    if text.endswith(".0"):
        text = text[:-2]
    return text + " " + units[exp - 1]


def _sweep_snippet(binaries, negate):
    """Build a snippet comparing naturalsize() with the oracle over the sweep."""
    return (
        "import random\n"
        "from humanize import naturalsize\n"
        + inspect.getsource(_sweep_values)
        + inspect.getsource(_expected_naturalsize)
        + f"binaries = {list(binaries)!r}\n"
        + f"negate = {negate!r}\n"
        + "checked = 0\n"
        "bad = 0\n"
        "mismatches = []\n"
        "dot_zero = []\n"
        "for binary in binaries:\n"
        "    for value in _sweep_values(binary):\n"
        "        if negate:\n"
        "            value = -value\n"
        "        checked += 1\n"
        "        want = _expected_naturalsize(value, binary)\n"
        "        try:\n"
        "            got = naturalsize(value, binary=True) if binary else naturalsize(value)\n"
        "        except Exception as exc:\n"
        "            got = 'raised ' + type(exc).__name__ + ': ' + str(exc)\n"
        "        if got != want:\n"
        "            bad += 1\n"
        "            if len(mismatches) < 15:\n"
        "                mismatches.append([repr(value), binary, got, want])\n"
        "        if isinstance(got, str) and got.split(' ')[0].endswith('.0'):\n"
        "            if len(dot_zero) < 15:\n"
        "                dot_zero.append([repr(value), binary, got])\n"
        "result = {'checked': checked, 'bad': bad, 'mismatches': mismatches,\n"
        "          'dot_zero': dot_zero}\n"
    )


def test_r1_decimal_whole_number_has_no_trailing_zero():
    r = run_python("from humanize import naturalsize\nresult = naturalsize(3000000)\n")
    assert r.ok, (r.error_type, r.error)
    assert r.value == "3 MB"


def test_r2_binary_whole_number_has_no_trailing_zero():
    r = run_python(
        "from humanize import naturalsize\nresult = naturalsize(1024, binary=True)\n"
    )
    assert r.ok, (r.error_type, r.error)
    assert r.value == "1 KiB"


def test_r3_contract_examples_keep_their_decimal():
    cases = [
        ((3000, True), "2.9 KiB"),
        ((1536, True), "1.5 KiB"),
        ((2500000, False), "2.5 MB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r3_other_nonzero_decimals_unchanged():
    # Each expectation is the base commit's output (one non-zero decimal kept).
    cases = [
        ((999949, False), "999.9 kB"),
        ((1100, False), "1.1 kB"),
        ((100100, False), "100.1 kB"),
        ((123456789, False), "123.5 MB"),
        ((7 * 10**18 + 3 * 10**17, False), "7.3 EB"),
        ((10**33 + 5 * 10**29, False), "1000.5 QB"),
        ((1250, False), "1.2 kB"),  # exact half: "%.1f" rounds half to even
        ((1076, True), "1.1 KiB"),
        ((31 * 1000, True), "30.3 KiB"),
        ((1023 * 1024 + 512, True), "1023.5 KiB"),
        ((int(1.5 * 1024**10), True), "1.5 QiB"),
        ((40 * 1000**10, True), "31.6 QiB"),
        ((2304, True), "2.2 KiB"),  # exact half: "%.1f" rounds half to even
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r4_contract_examples():
    cases = [
        ((1000, False), "1 kB"),
        ((10000000, False), "10 MB"),
        ((10**9, False), "1 GB"),
        ((2048, True), "2 KiB"),
        ((102400, True), "100 KiB"),
        ((1048576, True), "1 MiB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r4_every_decimal_unit():
    cases = []
    for k, unit in enumerate(DECIMAL_UNITS, start=1):
        cases.append(((1000**k, False), f"1 {unit}"))
        cases.append(((7 * 1000**k, False), f"7 {unit}"))
        cases.append((((30 + k) * 1000**k, False), f"{30 + k} {unit}"))
        cases.append(((250 * 1000**k, False), f"250 {unit}"))
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r4_every_binary_unit():
    cases = []
    for k, unit in enumerate(BINARY_UNITS, start=1):
        cases.append(((1024**k, True), f"1 {unit}"))
        cases.append(((7 * 1024**k, True), f"7 {unit}"))
        cases.append((((30 + k) * 1024**k, True), f"{30 + k} {unit}"))
        cases.append(((1000 * 1024**k, True), f"1000 {unit}"))
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r4_integer_part_zeros_are_kept():
    cases = [
        ((20000, False), "20 kB"),
        ((100000, False), "100 kB"),
        ((10000000, False), "10 MB"),
        ((500 * 10**6, False), "500 MB"),
        ((120 * 10**9, False), "120 GB"),
        # Beyond the largest unit the number keeps growing in QB / QiB.
        ((10**33, False), "1000 QB"),
        ((3 * 10**34, False), "30000 QB"),
        ((10**36, False), "1000000 QB"),
        ((102400, True), "100 KiB"),
        ((10 * 1024**2, True), "10 MiB"),
        ((200 * 1024**3, True), "200 GiB"),
        ((1024**11, True), "1024 QiB"),
        ((10 * 1024**11, True), "10240 QiB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r5_contract_examples():
    cases = [
        ((1040000, False), "1 MB"),
        ((2999999, False), "3 MB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_r5_values_that_round_to_whole_numbers():
    # None of these is an exact multiple of its unit; each prints as N.0 at one
    # decimal place (in the base commit) and must therefore print as N.
    cases = [
        ((3000001, False), "3 MB"),
        ((1001, False), "1 kB"),
        ((1049, False), "1 kB"),
        ((9960, False), "10 kB"),  # 9.96 rounds up into the next integer
        ((99950, False), "100 kB"),  # 99.95 rounds up to 100.0
        ((999950, False), "1 MB"),  # 999.95 kB rounds to 1000.0 -> next unit
        ((999999, False), "1 MB"),
        ((999999999, False), "1 GB"),
        ((int(10.04 * 1000**4), False), "10 TB"),
        ((1074, True), "1 KiB"),
        ((2 * 1024**2 + 1000, True), "2 MiB"),
        ((1048575, True), "1 MiB"),  # 1023.999 KiB -> next unit
        ((1024**3 - 1, True), "1 GiB"),
        ((int(2.96 * 1024**5), True), "3 PiB"),
        ((int(5.04 * 1024**8), True), "5 YiB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)


def test_sweep_decimal_mode_matches_rule():
    expected_count = len(_sweep_values(False))
    r = run_python(_sweep_snippet([False], negate=False), timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {
        "checked": expected_count,
        "bad": 0,
        "mismatches": [],
        "dot_zero": [],
    }


def test_sweep_binary_mode_matches_rule():
    expected_count = len(_sweep_values(True))
    r = run_python(_sweep_snippet([True], negate=False), timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {
        "checked": expected_count,
        "bad": 0,
        "mismatches": [],
        "dot_zero": [],
    }


def test_negative_sizes():
    cases = [
        ((-3000000, False), "-3 MB"),
        ((-4096, True), "-4 KiB"),
        ((-1040000, False), "-1 MB"),
        ((-2999999, False), "-3 MB"),
        ((-10**9, False), "-1 GB"),
        ((-102400, True), "-100 KiB"),
        ((-1048575, True), "-1 MiB"),
        ((-3000, True), "-2.9 KiB"),
        ((-2500000, False), "-2.5 MB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)

    expected_count = len(_sweep_values(False)) + len(_sweep_values(True))
    sweep = run_python(_sweep_snippet([False, True], negate=True), timeout=60.0)
    assert sweep.ok, (sweep.error_type, sweep.error)
    assert sweep.value == {
        "checked": expected_count,
        "bad": 0,
        "mismatches": [],
        "dot_zero": [],
    }


def test_float_and_string_inputs():
    cases = [
        ((3e6, False), "3 MB"),
        (("3000000", False), "3 MB"),
        (("1024", True), "1 KiB"),
        (("1e9", False), "1 GB"),
        ((1.04e6, False), "1 MB"),
        ((2047.9, True), "2 KiB"),
        (("-4096", True), "-4 KiB"),
        (("2500000", False), "2.5 MB"),
        ((1536.0, True), "1.5 KiB"),
        ((1.123456789e6, False), "1.1 MB"),
    ]
    r = run_python(_calls_snippet(c for c, _ in cases))
    assert r.ok, (r.error_type, r.error)
    assert r.value == [e for _, e in cases], _mismatches(cases, r.value)
