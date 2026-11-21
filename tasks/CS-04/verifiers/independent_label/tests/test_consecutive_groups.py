from itertools import groupby
from operator import itemgetter

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_step_example": ["R-step"],
    "test_step_breaks_on_other_gaps": ["R-step"],
    "test_negative_step_example": ["R-negative-step"],
    "test_zero_step_raises": ["R-zero-step"],
    "test_positional_ordering_example": ["R-positional-ordering"],
    "test_positional_ordering_matches_base": ["R-positional-ordering"],
    "test_default_matches_base": ["R-default-unchanged"],
    "test_groups_are_lazy_iterators": ["R-lazy"],
    "test_groups_consume_source_lazily": ["R-lazy"],
}


# Oracle: the base consecutive_groups from the pinned snapshot
# (more_itertools/more.py), copied verbatim in behaviour. It runs only in this
# trusted process and never executes candidate code.
def _base_consecutive_groups(iterable, ordering=None):
    if ordering is None:
        key = lambda x: x[0] - x[1]
    else:
        key = lambda x: x[0] - ordering(x[1])

    for k, g in groupby(enumerate(iterable), key=key):
        yield map(itemgetter(1), g)


def _base_groups(iterable, ordering=None):
    return [list(g) for g in _base_consecutive_groups(iterable, ordering)]


def test_step_example():
    r = run_python(
        "import more_itertools as mi\n"
        "result = [list(g) for g in mi.consecutive_groups([2, 4, 6, 10, 12], step=2)]"
    )
    assert r.ok, r
    assert r.value == [[2, 4, 6], [10, 12]]


def test_step_breaks_on_other_gaps():
    # 5 -> 6 is a gap of 1, not 2, so the run breaks there; 6 -> 8 is a gap of 2.
    r = run_python(
        "import more_itertools as mi\n"
        "result = [list(g) for g in mi.consecutive_groups([1, 3, 5, 6, 8], step=2)]"
    )
    assert r.ok, r
    assert r.value == [[1, 3, 5], [6, 8]]


def test_negative_step_example():
    r = run_python(
        "import more_itertools as mi\n"
        "result = [list(g) for g in mi.consecutive_groups([9, 8, 7, 3, 2], step=-1)]"
    )
    assert r.ok, r
    assert r.value == [[9, 8, 7], [3, 2]]


def test_zero_step_raises():
    # The error may be raised when the function is called or when the groups are iterated.
    r = run_python(
        "import more_itertools as mi\n"
        "try:\n"
        "    groups = mi.consecutive_groups([1, 2, 3], step=0)\n"
        "    result = [list(g) for g in groups]\n"
        "    result = 'no error'\n"
        "except ValueError:\n"
        "    result = 'ValueError'\n"
        "except Exception as e:\n"
        "    result = 'other ' + type(e).__name__"
    )
    assert r.ok, r
    assert r.value == "ValueError"


def test_positional_ordering_example():
    r = run_python(
        "import more_itertools as mi\n"
        "result = [list(g) for g in mi.consecutive_groups('abcdfgilmnop', ord)]"
    )
    assert r.ok, r
    assert r.value == [["a", "b", "c", "d"], ["f", "g"], ["i"], ["l", "m", "n", "o", "p"]]


ORDER_CASES = [
    ("abcdfgilmnop", "ord"),
    ([1, 2, 11, 12, 21, 22], "lambda n: n // 10"),
    ("aceg", "ord"),
]


def test_positional_ordering_matches_base():
    # ordering is passed as the second positional argument, as existing callers do.
    for items, ord_src in ORDER_CASES:
        expected = _base_groups(items, eval(ord_src))
        r = run_python(
            "import more_itertools as mi\n"
            "items = %r\n"
            "ordering = %s\n"
            "result = [list(g) for g in mi.consecutive_groups(items, ordering)]" % (items, ord_src)
        )
        assert r.ok, r
        assert r.value == expected, (items, ord_src, r.value, expected)


DEFAULT_CASES = [
    [1, 2, 3, 5, 6, 8],
    [],
    [1],
    [5, 5, 5],
    [1, 10, 11, 12, 20, 30, 31, 32, 33, 40],
    [2, 4, 6, 10, 12],
    [9, 8, 7, 3, 2],
    [-3, -2, -1, 0, 5],
]


def test_default_matches_base():
    expected = [_base_groups(x) for x in DEFAULT_CASES]
    r = run_python(
        "import more_itertools as mi\n"
        "inputs = %r\n"
        "result = [[list(g) for g in mi.consecutive_groups(x)] for x in inputs]" % (DEFAULT_CASES,)
    )
    assert r.ok, r
    assert r.value == expected, (r.value, expected)


def test_groups_are_lazy_iterators():
    # Each group is an iterator (not a list), as the base behaviour yields.
    r = run_python(
        "import more_itertools as mi\n"
        "result = [[isinstance(g, list), iter(g) is g, hasattr(g, '__next__')]"
        " for g in mi.consecutive_groups([1, 2, 11, 12])]"
    )
    assert r.ok, r
    assert r.value == [[False, True, True], [False, True, True]]


def test_groups_consume_source_lazily():
    # The source is pulled only as far as needed for the first group, and the group
    # still yields its own elements from the shared source.
    r = run_python(
        "import more_itertools as mi\n"
        "pulled = []\n"
        "def source():\n"
        "    for x in [1, 2, 11, 12, 21, 22]:\n"
        "        pulled.append(x)\n"
        "        yield x\n"
        "groups = mi.consecutive_groups(source())\n"
        "g1 = next(groups)\n"
        "lazy = len(pulled) < 6\n"
        "result = [lazy, list(g1)]"
    )
    assert r.ok, r
    assert r.value == [True, [1, 2]]
