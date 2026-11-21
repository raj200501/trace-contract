"""Independent checks for naturalsize's strip_trailing_zero option (CS-01).

Every check calls the candidate only through tc_sandbox.run_python. The base
behaviour is copied from the base snapshot (src/humanize/filesize.py) as an
oracle; gettext is the identity under the default (English) locale.
"""

import re

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_default_examples_unchanged": ["R-default-unchanged"],
    "test_default_matches_base": ["R-default-unchanged"],
    "test_default_flag_false_matches_base": ["R-opt-in"],
    "test_opt_in_examples": ["R-opt-in"],
    "test_opt_in_matches_rule": ["R-opt-in"],
    "test_keep_meaningful_examples": ["R-keep-meaningful"],
    "test_keep_meaningful_differential": ["R-keep-meaningful"],
    "test_custom_format_examples": ["R-custom-format-unchanged"],
    "test_custom_format_matches_base": ["R-custom-format-unchanged"],
}

VALUES = [
    0, 1, -1, 2, 300, 999, 1000, 1023, 1024, 1500, 2900, 3000, 3072, 999999,
    1000000, 2900000, 3000000, 10**9, 10**12, 10**28, 10**34 * 3, -4096, -3000,
    0.5, 12345.678, "1000", "2.5e6",
]
FLAGS = [(False, False), (True, False), (False, True), (True, True)]
FORMATS = ["%.3f", "%.2f", "%.0f", "%.4f", "%.1e"]

_SUFFIXES = {
    "decimal": ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"),
    "binary": ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB"),
    "gnu": "KMGTPEZYRQ",
}


def _base_naturalsize(value, binary=False, gnu=False, format="%.1f"):
    # Copied from the base snapshot, src/humanize/filesize.py, with gettext as identity.
    if gnu:
        suffix = _SUFFIXES["gnu"]
    elif binary:
        suffix = _SUFFIXES["binary"]
    else:
        suffix = _SUFFIXES["decimal"]

    base = 1024 if (gnu or binary) else 1000
    bytes_ = float(value)
    abs_bytes = abs(bytes_)

    if abs_bytes == 1 and not gnu:
        return "%d Byte" % int(bytes_)

    if abs_bytes < base:
        return f"{int(bytes_)}B" if gnu else "%d Bytes" % int(bytes_)

    from math import log

    exp = int(min(log(abs_bytes, base), len(suffix)))
    if exp < len(suffix) and abs(float(format % (abs_bytes / (base**exp)))) >= base:
        exp += 1
    space = "" if gnu else " "
    return format % (bytes_ / (base**exp)) + space + suffix[exp - 1]


_POINT_ZERO = re.compile(r"^(-?\d+)\.0(\D.*)?$")


def _expected_strip(text):
    # A trailing ".0" of the mantissa is dropped; any other text is unchanged.
    m = _POINT_ZERO.match(text)
    if m is None:
        return text
    return m.group(1) + (m.group(2) or "")


def test_default_examples_unchanged():
    r = run_python(
        "from humanize import naturalsize\n"
        "result = [naturalsize(3000000), naturalsize(1024, binary=True), naturalsize(3000, gnu=True),\n"
        "          naturalsize(300), naturalsize(1), naturalsize(3000, True)]\n"
    )
    assert r.ok, r
    assert r.value == ["3.0 MB", "1.0 KiB", "2.9K", "300 Bytes", "1 Byte", "2.9 KiB"], r.value


def test_default_matches_base():
    snippet = (
        "from humanize import naturalsize\n"
        f"VALUES = {VALUES!r}\n"
        f"FLAGS = {FLAGS!r}\n"
        "result = [naturalsize(v, b, g) for v in VALUES for (b, g) in FLAGS]\n"
    )
    r = run_python(snippet)
    assert r.ok, r
    expected = [_base_naturalsize(v, b, g) for v in VALUES for (b, g) in FLAGS]
    assert r.value == expected, [(i, a, e) for i, (a, e) in enumerate(zip(r.value, expected)) if a != e][:5]


def test_default_flag_false_matches_base():
    snippet = (
        "from humanize import naturalsize\n"
        f"VALUES = {VALUES!r}\n"
        f"FLAGS = {FLAGS!r}\n"
        "result = [naturalsize(v, binary=b, gnu=g, strip_trailing_zero=False)\n"
        "          for v in VALUES for (b, g) in FLAGS]\n"
    )
    r = run_python(snippet)
    assert r.ok, r
    expected = [_base_naturalsize(v, b, g) for v in VALUES for (b, g) in FLAGS]
    assert r.value == expected, [(i, a, e) for i, (a, e) in enumerate(zip(r.value, expected)) if a != e][:5]


def test_opt_in_examples():
    r = run_python(
        "from humanize import naturalsize\n"
        "result = [naturalsize(3000000, strip_trailing_zero=True),\n"
        "          naturalsize(1024, binary=True, strip_trailing_zero=True)]\n"
    )
    assert r.ok, r
    assert r.value == ["3 MB", "1 KiB"], r.value


def test_opt_in_matches_rule():
    snippet = (
        "from humanize import naturalsize\n"
        f"VALUES = {VALUES!r}\n"
        f"FLAGS = {FLAGS!r}\n"
        "result = [naturalsize(v, binary=b, gnu=g, strip_trailing_zero=True)\n"
        "          for v in VALUES for (b, g) in FLAGS]\n"
    )
    r = run_python(snippet)
    assert r.ok, r
    expected = [_expected_strip(_base_naturalsize(v, b, g)) for v in VALUES for (b, g) in FLAGS]
    assert r.value == expected, [(i, a, e) for i, (a, e) in enumerate(zip(r.value, expected)) if a != e][:5]


def test_keep_meaningful_examples():
    r = run_python(
        "from humanize import naturalsize\n"
        "result = [naturalsize(3000, binary=True),\n"
        "          naturalsize(3000, binary=True, strip_trailing_zero=True),\n"
        "          naturalsize(3000, gnu=True, strip_trailing_zero=True),\n"
        "          naturalsize(1500, strip_trailing_zero=True),\n"
        "          naturalsize(2900000, strip_trailing_zero=True),\n"
        "          naturalsize(300, strip_trailing_zero=True),\n"
        "          naturalsize(1, strip_trailing_zero=True)]\n"
    )
    assert r.ok, r
    assert r.value == ["2.9 KiB", "2.9 KiB", "2.9K", "1.5 kB", "2.9 MB", "300 Bytes", "1 Byte"], r.value


def test_keep_meaningful_differential():
    snippet = (
        "from humanize import naturalsize\n"
        f"VALUES = {VALUES!r}\n"
        f"FLAGS = {FLAGS!r}\n"
        "result = [[naturalsize(v, binary=b, gnu=g), naturalsize(v, binary=b, gnu=g, strip_trailing_zero=True)]\n"
        "          for v in VALUES for (b, g) in FLAGS]\n"
    )
    r = run_python(snippet)
    assert r.ok, r
    base_defaults = [_base_naturalsize(v, b, g) for v in VALUES for (b, g) in FLAGS]
    assert [pair[0] for pair in r.value] == base_defaults
    for (default, stripped), base_default in zip(r.value, base_defaults):
        # The default output is the base output. A stripped output may differ only by
        # the removal of a ".0" mantissa; a meaningful decimal such as "2.9" is never removed.
        if stripped != default:
            assert _POINT_ZERO.match(default) is not None, (default, stripped)
            assert stripped == _expected_strip(default), (default, stripped)


def test_custom_format_examples():
    r = run_python(
        "from humanize import naturalsize\n"
        "result = [naturalsize(3000, False, True, '%.3f'), naturalsize(3000000, format='%.2f')]\n"
    )
    assert r.ok, r
    assert r.value == ["2.930K", "3.00 MB"], r.value


def test_custom_format_matches_base():
    snippet = (
        "from humanize import naturalsize\n"
        f"VALUES = {VALUES!r}\n"
        f"FLAGS = {FLAGS!r}\n"
        f"FORMATS = {FORMATS!r}\n"
        "result = []\n"
        "for fmt in FORMATS:\n"
        "    for v in VALUES:\n"
        "        for (b, g) in FLAGS:\n"
        "            result.append(naturalsize(v, b, g, fmt))\n"
        "            result.append(naturalsize(v, binary=b, gnu=g, format=fmt))\n"
    )
    r = run_python(snippet)
    assert r.ok, r
    expected = []
    for fmt in FORMATS:
        for v in VALUES:
            for b, g in FLAGS:
                expected.append(_base_naturalsize(v, b, g, fmt))
                expected.append(_base_naturalsize(v, b, g, fmt))
    assert r.value == expected, [(i, a, e) for i, (a, e) in enumerate(zip(r.value, expected)) if a != e][:5]
