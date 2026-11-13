"""Reference checks for CS-04: a ``step`` argument for ``more_itertools.consecutive_groups``.

Black-box checks written from the reference contract only. Candidate code is reached
exclusively through ``tc_sandbox.run_python``. Expected values are literals, or are
computed here, in the trusted grader process, by two small independent oracles:

* ``base_groups``: the base-commit algorithm, for behaviour that must not change when
  no step is given (R-default-unchanged, R-positional-ordering);
* ``step_groups``: the requested meaning of *step*. An item continues the current
  group exactly when its position (``ordering(item)``, or the item itself) equals the
  previous item's position plus *step* (R-step, R-negative-step).

Laziness (R-lazy) is checked separately for default calls, positional-ordering calls,
positive steps and negative steps, so that a missing feature does not show up as a
laziness failure of the default path.

Deliberately not checked, because the contract leaves them open: error messages;
whether *step* is keyword-only (it is always passed by keyword here); whether
``step=0`` fails at call time or during iteration (either is accepted, as is any
``ValueError`` subclass); non-integer steps; *ordering* passed by keyword or as
``None``; the type of the object returned by the call itself (it is wrapped in
``iter``); whether a group that is no longer available is empty or raises; and how
far ahead the source is read.
"""

import itertools
import json
import operator
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_step_two_contract_example": ["R-step"],
    "test_positive_steps_group_runs_of_exactly_that_difference": ["R-step"],
    "test_positive_steps_match_oracle_on_generated_inputs": ["R-step"],
    "test_positive_step_with_positional_ordering": ["R-step"],
    "test_negative_step_contract_example": ["R-negative-step"],
    "test_negative_steps_group_descending_runs_only": ["R-negative-step"],
    "test_negative_steps_match_oracle_on_generated_inputs": ["R-negative-step"],
    "test_negative_step_with_positional_ordering": ["R-negative-step"],
    "test_zero_step_raises_value_error": ["R-zero-step"],
    "test_zero_step_with_positional_ordering_raises_value_error": ["R-zero-step"],
    "test_positional_ordering_contract_example": ["R-positional-ordering", "R-default-unchanged"],
    "test_positional_ordering_matches_base": ["R-positional-ordering", "R-default-unchanged"],
    "test_groups_are_iterators_sharing_their_source": ["R-lazy"],
    "test_groups_are_lazy_on_infinite_sources": ["R-lazy"],
    "test_positional_ordering_groups_are_lazy_and_shared": ["R-lazy", "R-positional-ordering"],
    "test_step_groups_are_lazy_and_shared": ["R-lazy", "R-step"],
    "test_negative_step_groups_are_lazy_and_shared": ["R-lazy", "R-negative-step"],
    "test_default_matches_base_examples": ["R-default-unchanged"],
    "test_default_matches_base_on_generated_inputs": ["R-default-unchanged"],
}

# --------------------------------------------------------------------------- sandbox side

_PRELUDE = '''
import json
from itertools import chain, count, islice

import more_itertools as mi


def _attempt(fn):
    """Run fn(); report an exception as a string instead of aborting the snippet."""
    try:
        return fn()
    except Exception as exc:
        return "raised " + type(exc).__name__ + ": " + str(exc)[:200]


def _groups(*args, **kwargs):
    """Every group of one consecutive_groups call, copied into lists."""
    return _attempt(lambda: [list(g) for g in mi.consecutive_groups(*args, **kwargs)])


def _zero_step_outcome(make):
    """Call and fully iterate; report whether a ValueError was raised at any point."""
    try:
        for g in make():
            list(g)
    except Exception as exc:
        return {"raised": type(exc).__name__, "is_value_error": isinstance(exc, ValueError)}
    return {"raised": None, "is_value_error": False}


def _describe(groups):
    """Iterator-protocol facts and contents of every yielded group."""
    records = []
    for g in groups:
        record = {
            "is_list": isinstance(g, list),
            "iter_returns_itself": iter(g) is g,
            "has_next": callable(getattr(g, "__next__", None)),
        }
        items = []
        while True:
            try:
                items.append(next(g))
            except StopIteration:
                break
        record["items"] = items
        records.append(record)
    return records


def _interleaved(make):
    """Read one item of the first group, move on to the second group, then revisit the first."""
    groups = iter(make())
    first = next(groups)
    head = next(first)
    second = next(groups)
    try:
        rest_of_first = list(first)
    except Exception as exc:
        rest_of_first = "raised " + type(exc).__name__
    return {"head": head, "rest_of_first": rest_of_first, "second": list(second),
            "remaining": [list(g) for g in groups]}


def _first_group_head(groups, n):
    """The first n items of the first group (the group may be infinite)."""
    return list(islice(next(iter(groups)), n))


def _leading_groups(groups, n):
    """The first n groups, copied (the source may be infinite)."""
    return [list(g) for g in islice(groups, n)]
'''


def _snippet(body, **data):
    """The shared prelude, then each keyword bound to a JSON-decoded value, then body."""
    bindings = "".join(f"{name} = json.loads({json.dumps(value)!r})\n" for name, value in data.items())
    return _PRELUDE + bindings + body


# --------------------------------------------------------------------------- trusted oracles


def base_groups(items, ordering=None):
    """The base-commit algorithm, kept here as the oracle for unchanged behaviour."""
    if ordering is None:
        key = lambda x: x[0] - x[1]  # noqa: E731
    else:
        key = lambda x: x[0] - ordering(x[1])  # noqa: E731
    return [list(map(operator.itemgetter(1), g)) for _, g in itertools.groupby(enumerate(items), key=key)]


def step_groups(items, step, ordering=None):
    """Maximal runs in which each position is exactly ``step`` more than the previous one."""
    position = ordering if ordering is not None else (lambda x: x)
    groups = []
    for item in items:
        if groups and position(item) - position(groups[-1][-1]) == step:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _run_lists(seed, steps, n_cases):
    """[items, step] pairs; items are short arithmetic runs, mostly using the step under test."""
    rng = random.Random(seed)
    cases = []
    for i in range(n_cases):
        step = steps[i % len(steps)]
        items = []
        for _ in range(rng.randint(0, 6)):
            start = rng.randint(-25, 25)
            inc = rng.choice([step, step, step, -step, 1, -1, 2, 0])
            items.extend(start + inc * k for k in range(rng.randint(1, 5)))
        cases.append([items, step])
    return cases


def _letter_strings(seed, n_cases):
    """Strings made of short runs of adjacent (or repeated, or skipping) characters."""
    rng = random.Random(seed)
    out = []
    for _ in range(n_cases):
        chars = []
        for _ in range(rng.randint(0, 5)):
            start = rng.randint(4, 21)
            inc = rng.choice([1, 1, 1, 0, 2, -1])
            chars.extend(chr(ord("a") + start + inc * k) for k in range(rng.randint(1, 5)))
        out.append("".join(chars))
    return out


def _mismatches(cases, got, expected):
    return [{"case": c, "got": g, "expected": e} for c, g, e in zip(cases, got, expected) if g != e]


def _iterator_records(groups):
    """What _describe reports for groups that are proper iterators with these contents."""
    return [{"is_list": False, "iter_returns_itself": True, "has_next": True, "items": g} for g in groups]


def _shared_source_view(got):
    """Normalise an _interleaved record: the unread rest of the first group must be unavailable
    (empty, as in the base, or an error); everything else must be intact."""
    if not isinstance(got, dict):
        return got
    rest = got.get("rest_of_first")
    return {
        "head": got.get("head"),
        "rest_of_first_unavailable": rest == [] or (isinstance(rest, str) and rest.startswith("raised ")),
        "second": got.get("second"),
        "remaining": got.get("remaining"),
    }


# --------------------------------------------------------------------------- R-step


def test_step_two_contract_example():
    r = run_python(_snippet("result = _groups([2, 4, 6, 10, 12], step=2)"))
    assert r.ok, r
    assert r.value == [[2, 4, 6], [10, 12]]


POSITIVE_STEP_CASES = [
    # items, step, expected groups
    ([1, 3, 4, 6, 8], 2, [[1, 3], [4, 6, 8]]),
    ([1, 2, 3], 2, [[1], [2], [3]]),  # a difference of 1 is not a step of 2
    ([0, 3, 6, 7, 10, 13, 20], 3, [[0, 3, 6], [7, 10, 13], [20]]),
    ([1, 4, 7, 10, 2, 5], 3, [[1, 4, 7, 10], [2, 5]]),
    ([5, 10, 15, 16, 21], 5, [[5, 10, 15], [16, 21]]),
    ([2, 4, 4, 6], 2, [[2, 4], [4, 6]]),  # a repeated item breaks the run
    ([6, 4, 2], 2, [[6], [4], [2]]),  # a positive step does not group decreasing items
    ([-4, -2, 0, 2], 2, [[-4, -2, 0, 2]]),
    ([7], 3, [[7]]),
    ([], 2, []),
]


def test_positive_steps_group_runs_of_exactly_that_difference():
    body = """
result = {
    "lists": [_groups(items, step=step) for items, step in cases],
    "iterator": _groups(iter([2, 4, 6, 10, 12]), step=2),
    "range": _groups(range(0, 20, 5), step=5),
    "generator": _groups((x * 3 for x in [0, 1, 2, 4, 5]), step=3),
    "tuple": _groups((10, 12, 14, 15), step=2),
}
"""
    r = run_python(_snippet(body, cases=[[items, step] for items, step, _ in POSITIVE_STEP_CASES]))
    assert r.ok, r
    assert r.value == {
        "lists": [expected for _, _, expected in POSITIVE_STEP_CASES],
        "iterator": [[2, 4, 6], [10, 12]],
        "range": [[0, 5, 10, 15]],
        "generator": [[0, 3, 6], [12, 15]],
        "tuple": [[10, 12, 14], [15]],
    }


def test_positive_steps_match_oracle_on_generated_inputs():
    cases = _run_lists(seed=4021, steps=[1, 2, 3, 4, 7], n_cases=150)
    r = run_python(_snippet("result = [_groups(items, step=step) for items, step in cases]", cases=cases))
    assert r.ok, r
    expected = [step_groups(items, step) for items, step in cases]
    assert isinstance(r.value, list) and len(r.value) == len(cases), r
    mismatches = _mismatches(cases, r.value, expected)
    assert mismatches == [], mismatches[:5]


def test_positive_step_with_positional_ordering():
    body = """
result = {
    "letters": _groups("acegjlmo", ord, step=2),
    "numeric_strings": _groups(["10", "20", "30", "35", "45", "46"], int, step=10),
    "negated": _groups([5, 3, 1, 2, 0], lambda x: -x, step=2),
}
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert r.value == {
        "letters": [["a", "c", "e", "g"], ["j", "l"], ["m", "o"]],
        "numeric_strings": [["10", "20", "30"], ["35", "45"], ["46"]],
        "negated": [[5, 3, 1], [2, 0]],
    }


# --------------------------------------------------------------------------- R-negative-step


def test_negative_step_contract_example():
    r = run_python(_snippet("result = _groups([9, 8, 7, 3, 2], step=-1)"))
    assert r.ok, r
    assert r.value == [[9, 8, 7], [3, 2]]


NEGATIVE_STEP_CASES = [
    # items, step, expected groups
    ([1, 2, 3], -1, [[1], [2], [3]]),  # increasing items are not grouped by a negative step
    ([10, 8, 6, 5, 3, 1, 0], -2, [[10, 8, 6], [5, 3, 1], [0]]),
    ([5, 4, 3, 4, 5], -1, [[5, 4, 3], [4], [5]]),
    ([0, -3, -6, -7], -3, [[0, -3, -6], [-7]]),
    ([9, 7, 8, 6], -2, [[9, 7], [8, 6]]),
    ([3, 3, 2, 2], -1, [[3], [3, 2], [2]]),  # a repeated item breaks the run
    ([20, 15, 10, 11, 6], -5, [[20, 15, 10], [11, 6]]),
    ([4], -1, [[4]]),
    ([], -1, []),
]


def test_negative_steps_group_descending_runs_only():
    body = """
result = {
    "lists": [_groups(items, step=step) for items, step in cases],
    "iterator": _groups(iter([9, 8, 7, 3, 2]), step=-1),
    "range": _groups(range(10, 0, -3), step=-3),
}
"""
    r = run_python(_snippet(body, cases=[[items, step] for items, step, _ in NEGATIVE_STEP_CASES]))
    assert r.ok, r
    assert r.value == {
        "lists": [expected for _, _, expected in NEGATIVE_STEP_CASES],
        "iterator": [[9, 8, 7], [3, 2]],
        "range": [[10, 7, 4, 1]],
    }


def test_negative_steps_match_oracle_on_generated_inputs():
    cases = _run_lists(seed=9073, steps=[-1, -2, -3, -4, -7], n_cases=150)
    r = run_python(_snippet("result = [_groups(items, step=step) for items, step in cases]", cases=cases))
    assert r.ok, r
    expected = [step_groups(items, step) for items, step in cases]
    assert isinstance(r.value, list) and len(r.value) == len(cases), r
    mismatches = _mismatches(cases, r.value, expected)
    assert mismatches == [], mismatches[:5]


def test_negative_step_with_positional_ordering():
    body = """
result = {
    "letters": _groups("zyxvutq", ord, step=-1),
    "lengths": _groups(["aaaaa", "ccc", "e", "dddd", "bb"], len, step=-2),
    "negated": _groups([0, 3, 6, 4, 7], lambda x: -x, step=-3),
}
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert r.value == {
        "letters": [["z", "y", "x"], ["v", "u", "t"], ["q"]],
        "lengths": [["aaaaa", "ccc", "e"], ["dddd", "bb"]],
        "negated": [[0, 3, 6], [4, 7]],
    }


# --------------------------------------------------------------------------- R-zero-step


def test_zero_step_raises_value_error():
    # The error may come from the call or from iterating its result; both are allowed.
    body = """
result = [
    _zero_step_outcome(lambda: mi.consecutive_groups([1, 1, 2, 3], step=0)),
    _zero_step_outcome(lambda: mi.consecutive_groups([2, 4, 6, 10], step=0)),
    _zero_step_outcome(lambda: mi.consecutive_groups(iter([5, 5, 6, 8]), step=0)),
    _zero_step_outcome(lambda: mi.consecutive_groups(range(4), step=0)),
]
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert [outcome["is_value_error"] for outcome in r.value] == [True, True, True, True], r.value


def test_zero_step_with_positional_ordering_raises_value_error():
    body = """
result = [
    _zero_step_outcome(lambda: mi.consecutive_groups("aabcd", ord, step=0)),
    _zero_step_outcome(lambda: mi.consecutive_groups(["1", "1", "2", "4"], int, step=0)),
]
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert [outcome["is_value_error"] for outcome in r.value] == [True, True], r.value


# --------------------------------------------------------------------------- R-positional-ordering


def test_positional_ordering_contract_example():
    r = run_python(_snippet('result = _groups("abcdfgilmnop", ord)'))
    assert r.ok, r
    assert r.value == [["a", "b", "c", "d"], ["f", "g"], ["i"], ["l", "m", "n", "o", "p"]]


def test_positional_ordering_matches_base():
    letters = _letter_strings(seed=1187, n_cases=80)
    numbers = [[str(x) for x in items] for items, _ in _run_lists(seed=5521, steps=[1], n_cases=80)]
    body = """
from itertools import permutations

_perms = list(permutations("abcd"))
result = {
    "letters": [_groups(s, ord) for s in letters],
    "numeric_strings": [_groups(items, int) for items in numbers],
    "permutation_index": _groups(["abcd", "acbd", "acdb", "adbc", "dbca", "dcab"], lambda s: _perms.index(tuple(s))),
    "negated": _groups([3, 2, 1, 5, 4], lambda x: -x),
    "lengths": _groups(["a", "bb", "ccc", "x", "yy"], len),
    "iterator": _groups(iter("xyzab"), ord),
}
"""
    r = run_python(_snippet(body, letters=letters, numbers=numbers))
    assert r.ok, r
    assert isinstance(r.value, dict), r
    assert len(r.value["letters"]) == len(letters), r
    assert len(r.value["numeric_strings"]) == len(numbers), r
    letter_mismatches = _mismatches(letters, r.value["letters"], [base_groups(s, ord) for s in letters])
    assert letter_mismatches == [], letter_mismatches[:5]
    number_mismatches = _mismatches(numbers, r.value["numeric_strings"], [base_groups(n, int) for n in numbers])
    assert number_mismatches == [], number_mismatches[:5]
    assert {k: v for k, v in r.value.items() if k not in ("letters", "numeric_strings")} == {
        "permutation_index": [["abcd"], ["acbd", "acdb", "adbc"], ["dbca", "dcab"]],
        "negated": [[3, 2, 1], [5, 4]],
        "lengths": [["a", "bb", "ccc"], ["x", "yy"]],
        "iterator": [["x", "y", "z"], ["a", "b"]],
    }


# --------------------------------------------------------------------------- R-lazy
# Groups must be iterators (not lists) drawing lazily from the shared source: an infinite
# group can be read from, and once the next group is requested the unread rest of the
# previous group is gone. An implementation that materialises groups or the source
# never returns from the infinite-source calls (the sandbox call then times out).


def test_groups_are_iterators_sharing_their_source():
    body = """
result = {
    "list_source": _attempt(lambda: _describe(mi.consecutive_groups([1, 2, 3, 10, 11, 20]))),
    "tuple_source": _attempt(lambda: _describe(mi.consecutive_groups((4, 5, 7)))),
    "generator_source": _attempt(lambda: _describe(mi.consecutive_groups(x for x in [0, 1, 5, 6, 7]))),
    "interleaved": _attempt(lambda: _interleaved(lambda: mi.consecutive_groups(iter([1, 2, 3, 10, 11, 20])))),
}
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert isinstance(r.value, dict), r
    assert {k: v for k, v in r.value.items() if k != "interleaved"} == {
        "list_source": _iterator_records([[1, 2, 3], [10, 11], [20]]),
        "tuple_source": _iterator_records([[4, 5], [7]]),
        "generator_source": _iterator_records([[0, 1], [5, 6, 7]]),
    }
    assert _shared_source_view(r.value.get("interleaved")) == {
        "head": 1, "rest_of_first_unavailable": True, "second": [10, 11], "remaining": [[20]],
    }


def test_groups_are_lazy_on_infinite_sources():
    body = """
result = {
    "first_group": _attempt(lambda: _first_group_head(mi.consecutive_groups(count()), 5)),
    "later_groups": _attempt(lambda: _leading_groups(mi.consecutive_groups(chain([1, 2, 3], count(10, 5))), 4)),
}
"""
    r = run_python(_snippet(body))
    assert r.ok, r
    assert r.value == {"first_group": [0, 1, 2, 3, 4], "later_groups": [[1, 2, 3], [10], [15], [20]]}


def test_positional_ordering_groups_are_lazy_and_shared():
    finite = """
result = {
    "groups": _attempt(lambda: _describe(mi.consecutive_groups("abcxyq", ord))),
    "interleaved": _attempt(lambda: _interleaved(lambda: mi.consecutive_groups(iter("abcxyq"), ord))),
}
"""
    infinite = """
result = {
    "first_group": _attempt(lambda: _first_group_head(mi.consecutive_groups(map(chr, count(97)), ord), 5)),
    "later_groups": _attempt(
        lambda: _leading_groups(mi.consecutive_groups(chain("abc", map(chr, count(110, 2))), ord), 4)
    ),
}
"""
    r = run_python(_snippet(finite))
    assert r.ok, r
    assert isinstance(r.value, dict), r
    assert r.value.get("groups") == _iterator_records([["a", "b", "c"], ["x", "y"], ["q"]])
    assert _shared_source_view(r.value.get("interleaved")) == {
        "head": "a", "rest_of_first_unavailable": True, "second": ["x", "y"], "remaining": [["q"]],
    }
    r = run_python(_snippet(infinite))
    assert r.ok, r
    assert r.value == {
        "first_group": ["a", "b", "c", "d", "e"],
        "later_groups": [["a", "b", "c"], ["n"], ["p"], ["r"]],
    }


def test_step_groups_are_lazy_and_shared():
    finite = """
result = {
    "groups": _attempt(lambda: _describe(mi.consecutive_groups([2, 4, 6, 10, 12, 20], step=2))),
    "interleaved": _attempt(lambda: _interleaved(lambda: mi.consecutive_groups(iter([2, 4, 6, 10, 12, 20]), step=2))),
}
"""
    infinite = """
result = {
    "first_group": _attempt(lambda: _first_group_head(mi.consecutive_groups(count(0, 2), step=2), 5)),
    "later_groups": _attempt(
        lambda: _leading_groups(mi.consecutive_groups(chain([3, 6, 9], count(20, 2)), step=3), 3)
    ),
}
"""
    r = run_python(_snippet(finite))
    assert r.ok, r
    assert isinstance(r.value, dict), r
    assert r.value.get("groups") == _iterator_records([[2, 4, 6], [10, 12], [20]])
    assert _shared_source_view(r.value.get("interleaved")) == {
        "head": 2, "rest_of_first_unavailable": True, "second": [10, 12], "remaining": [[20]],
    }
    r = run_python(_snippet(infinite))
    assert r.ok, r
    assert r.value == {"first_group": [0, 2, 4, 6, 8], "later_groups": [[3, 6, 9], [20], [22]]}


def test_negative_step_groups_are_lazy_and_shared():
    finite = """
result = {
    "groups": _attempt(lambda: _describe(mi.consecutive_groups([9, 8, 7, 3, 2, 0], step=-1))),
    "interleaved": _attempt(lambda: _interleaved(lambda: mi.consecutive_groups(iter([9, 8, 7, 3, 2, 0]), step=-1))),
}
"""
    infinite = """
result = {
    "first_group": _attempt(lambda: _first_group_head(mi.consecutive_groups(count(10, -1), step=-1), 5)),
    "later_groups": _attempt(
        lambda: _leading_groups(mi.consecutive_groups(chain([5, 4], count(0, 3)), step=-1), 3)
    ),
}
"""
    r = run_python(_snippet(finite))
    assert r.ok, r
    assert isinstance(r.value, dict), r
    assert r.value.get("groups") == _iterator_records([[9, 8, 7], [3, 2], [0]])
    assert _shared_source_view(r.value.get("interleaved")) == {
        "head": 9, "rest_of_first_unavailable": True, "second": [3, 2], "remaining": [[0]],
    }
    r = run_python(_snippet(infinite))
    assert r.ok, r
    assert r.value == {"first_group": [10, 9, 8, 7, 6], "later_groups": [[5, 4], [0], [3]]}


# --------------------------------------------------------------------------- R-default-unchanged

DEFAULT_CASES = [
    # items, expected groups (base-commit behaviour)
    ([1, 10, 11, 12, 20, 30, 31, 32, 33, 40], [[1], [10, 11, 12], [20], [30, 31, 32, 33], [40]]),
    ([-10, -8, -7, -6, 1, 2, 4, 5, -1, 7], [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]]),
    ([1, 2, 11, 12, 21, 22], [[1, 2], [11, 12], [21, 22]]),
    ([], []),
    ([5], [[5]]),
    ([3, 2, 1], [[3], [2], [1]]),
    ([1, 1, 2, 2, 3], [[1], [1, 2], [2, 3]]),
    ([0, 2, 4], [[0], [2], [4]]),
    ([-3, -2, -1, 0, 1], [[-3, -2, -1, 0, 1]]),
    ([1.5, 2.5, 3.5, 5.0, 6.0, 6.5], [[1.5, 2.5, 3.5], [5.0, 6.0], [6.5]]),
    ([0.5, 1.0], [[0.5], [1.0]]),
]


def test_default_matches_base_examples():
    body = """
result = {
    "lists": [_groups(items) for items in cases],
    "range": _groups(range(5)),
    "generator": _groups(x for x in [4, 5, 7, 8, 9]),
    "tuple": _groups((7, 8, 10)),
}
"""
    r = run_python(_snippet(body, cases=[items for items, _ in DEFAULT_CASES]))
    assert r.ok, r
    assert r.value == {
        "lists": [expected for _, expected in DEFAULT_CASES],
        "range": [[0, 1, 2, 3, 4]],
        "generator": [[4, 5], [7, 8, 9]],
        "tuple": [[7, 8], [10]],
    }


def test_default_matches_base_on_generated_inputs():
    rng = random.Random(7310)
    lists = [items for items, _ in _run_lists(seed=2208, steps=[1], n_cases=120)]
    lists += [[rng.randint(-4, 4) for _ in range(rng.randint(0, 12))] for _ in range(80)]
    r = run_python(_snippet("result = [_groups(items) for items in lists]", lists=lists))
    assert r.ok, r
    expected = [base_groups(items) for items in lists]
    assert isinstance(r.value, list) and len(r.value) == len(lists), r
    mismatches = _mismatches(lists, r.value, expected)
    assert mismatches == [], mismatches[:5]
