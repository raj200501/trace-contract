"""Hidden behavioural tests for CS-04 (condition full_plain).

more_itertools.consecutive_groups gains a ``step`` option (passed by
keyword).  Every check runs the candidate only through tc_sandbox.
"""

import random

from tc_sandbox import run_python


CHECK_REQUIREMENTS = {
    "test_step_two_user_examples": ["R1"],
    "test_positive_step_groups_are_maximal_runs": ["R1"],
    "test_negative_step_user_examples": ["R2"],
    "test_negative_step_only_groups_descending_runs": ["R2"],
    "test_zero_step_raises_value_error": ["R3"],
    "test_ordering_still_second_positional_parameter": ["R4"],
    "test_default_step_groups_unchanged": ["R6"],
    "test_explicit_step_one_matches_default": ["R6"],
    "test_step_with_ordering": ["R7", "R2"],
    "test_randomized_runs_match_definition": ["R1", "R2", "R7"],
    "test_groups_are_lazy_iterators_with_step": ["R5"],
    "test_groups_are_lazy_iterators_default_step": ["R5"],
    "test_skipped_groups_still_yield_correct_runs": ["R1", "R2", "R6"],
}


def _describe(r):
    return "snippet failed (timed_out={}): {}: {}\nstderr:\n{}".format(
        r.timed_out, r.error_type, r.error, r.stderr
    )


# Trusted model of the specified semantics: an item continues the current
# group if and only if position(item) - position(previous item) == step.
def _model(items, step, ordering=None):
    position = (lambda x: x) if ordering is None else ordering
    groups = []
    for item in items:
        if groups and position(item) - position(groups[-1][-1]) == step:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _random_items(rng, step):
    items = []
    for _ in range(rng.randint(0, 12)):
        roll = rng.random()
        if items and roll < 0.55:
            items.append(items[-1] + step)
        elif items and roll < 0.8:
            items.append(items[-1] + rng.choice([-step, 0, 1, -1, 2 * step]))
        else:
            items.append(rng.randint(-15, 15))
    return items


_PLAIN_CASES_BODY = """
import more_itertools as mi
result = [
    [list(g) for g in mi.consecutive_groups(items, step=step)]
    for items, step in CASES
]
"""


def _plain_cases_snippet(cases):
    return "CASES = " + repr(cases) + "\n" + _PLAIN_CASES_BODY


def test_step_two_user_examples():
    snippet = """
import more_itertools as mi
result = [
    [list(g) for g in mi.consecutive_groups([2, 4, 6, 10, 12], step=2)],
    [list(g) for g in mi.consecutive_groups([1, 3, 5, 6, 8, 11], step=2)],
    [list(g) for g in mi.consecutive_groups([2, 4, 6, 10, 12, 15, 17, 20], step=2)],
]
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == [
        [[2, 4, 6], [10, 12]],
        [[1, 3, 5], [6, 8], [11]],
        [[2, 4, 6], [10, 12], [15, 17], [20]],
    ]


def test_positive_step_groups_are_maximal_runs():
    cases = [
        ([0, 3, 6, 7, 10, 20, 23], 3, [[0, 3, 6], [7, 10], [20, 23]]),
        ([1, 4, 7, 10], 3, [[1, 4, 7, 10]]),
        ([1, 2, 3], 2, [[1], [2], [3]]),
        ([4, 2, 0], 2, [[4], [2], [0]]),
        ([2, 2, 4, 4, 6], 2, [[2], [2, 4], [4, 6]]),
        ([1, 4, 6, 9], 2, [[1], [4, 6], [9]]),
        ([3, 5, 7, 5, 7, 9], 2, [[3, 5, 7], [5, 7, 9]]),
        ([1, 3, 2, 4, 6], 2, [[1, 3], [2, 4, 6]]),
        ([-6, -4, -2, 0, 2], 2, [[-6, -4, -2, 0, 2]]),
        ([5, 10, 15, 21, 26], 5, [[5, 10, 15], [21, 26]]),
        (
            [10**12, 10**12 + 7, 10**12 + 14, 3],
            7,
            [[10**12, 10**12 + 7, 10**12 + 14], [3]],
        ),
        ([7], 2, [[7]]),
        ([], 2, []),
    ]
    snippet = (
        _plain_cases_snippet([(items, step) for items, step, _ in cases])
        + """
generator_input = [
    list(g)
    for g in mi.consecutive_groups((x for x in [0, 3, 6, 7, 10]), step=3)
]
result = {'cases': result, 'generator_input': generator_input}
"""
    )
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value["cases"] == [expected for _, _, expected in cases]
    assert r.value["generator_input"] == [[0, 3, 6], [7, 10]]


def test_negative_step_user_examples():
    snippet = """
import more_itertools as mi
result = [
    [list(g) for g in mi.consecutive_groups([9, 8, 7, 3, 2], step=-1)],
    [list(g) for g in mi.consecutive_groups([10, 8, 6, 5, 3], step=-2)],
]
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == [
        [[9, 8, 7], [3, 2]],
        [[10, 8, 6], [5, 3]],
    ]


def test_negative_step_only_groups_descending_runs():
    cases = [
        ([1, 2, 3], -1, [[1], [2], [3]]),
        ([2, 4, 6], -2, [[2], [4], [6]]),
        ([5, 4, 3, 4, 5], -1, [[5, 4, 3], [4], [5]]),
        ([0, -3, -6, -5, -8], -3, [[0, -3, -6], [-5, -8]]),
        ([1, 0, -1, -2, 5], -1, [[1, 0, -1, -2], [5]]),
        ([20, 15, 10, 5, 0], -5, [[20, 15, 10, 5, 0]]),
        ([3, 3, 2], -1, [[3], [3, 2]]),
        ([10, 9, 7, 6], -1, [[10, 9], [7, 6]]),
        ([4], -1, [[4]]),
        ([], -2, []),
    ]
    r = run_python(_plain_cases_snippet([(i, s) for i, s, _ in cases]))
    assert r.ok, _describe(r)
    assert r.value == [expected for _, _, expected in cases]


def test_zero_step_raises_value_error():
    snippet = """
import more_itertools as mi

def full_iteration(make):
    try:
        [list(g) for g in make()]
    except ValueError:
        return 'ValueError'
    except Exception as e:
        return 'other: ' + type(e).__name__
    return 'no error'

def first_group(make):
    try:
        next(make())
    except ValueError:
        return 'ValueError'
    except Exception as e:
        return 'other: ' + type(e).__name__
    return 'produced a group'

makers = [
    lambda: mi.consecutive_groups([1, 2, 3], step=0),
    lambda: mi.consecutive_groups([1, 1, 1], step=0),
    lambda: mi.consecutive_groups(iter([4, 4, 5, 9]), step=0),
    lambda: mi.consecutive_groups('aab', ord, step=0),
]
result = {
    'full_iteration': [full_iteration(m) for m in makers],
    'first_group': [first_group(m) for m in makers],
}
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value["full_iteration"] == ["ValueError"] * 4
    assert r.value["first_group"] == ["ValueError"] * 4


def test_ordering_still_second_positional_parameter():
    snippet = """
from itertools import permutations
import more_itertools as mi

numbers_as_text = ['1', '10', '11', '20', '21', '22', '30', '31']
exotic = [
    ('a', 'b', 'c', 'd'),
    ('a', 'c', 'b', 'd'),
    ('a', 'c', 'd', 'b'),
    ('a', 'd', 'b', 'c'),
    ('d', 'b', 'c', 'a'),
    ('d', 'c', 'a', 'b'),
]
result = {
    'ord': [list(g) for g in mi.consecutive_groups('abcdfgi', ord)],
    'ord_long': [list(g) for g in mi.consecutive_groups('abcdfgilmnop', ord)],
    'int': [list(g) for g in mi.consecutive_groups(numbers_as_text, int)],
    'lambda': [
        list(g) for g in mi.consecutive_groups(numbers_as_text, lambda x: int(x))
    ],
    'negated': [list(g) for g in mi.consecutive_groups([3, 2, 1, 5, 4], lambda x: -x)],
    'exotic': [
        [''.join(t) for t in g]
        for g in mi.consecutive_groups(exotic, list(permutations('abcd')).index)
    ],
}
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == {
        "ord": [["a", "b", "c", "d"], ["f", "g"], ["i"]],
        "ord_long": [
            ["a", "b", "c", "d"],
            ["f", "g"],
            ["i"],
            ["l", "m", "n", "o", "p"],
        ],
        "int": [["1"], ["10", "11"], ["20", "21", "22"], ["30", "31"]],
        "lambda": [["1"], ["10", "11"], ["20", "21", "22"], ["30", "31"]],
        "negated": [[3, 2, 1], [5, 4]],
        "exotic": [["abcd"], ["acbd", "acdb", "adbc"], ["dbca", "dcab"]],
    }


def test_default_step_groups_unchanged():
    fixed = [
        ([1, 2, 3, 5, 6, 8], [[1, 2, 3], [5, 6], [8]]),
        (
            [-10, -8, -7, -6, 1, 2, 4, 5, -1, 7],
            [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        ),
        (
            [1, 10, 11, 12, 20, 30, 31, 32, 33, 40],
            [[1], [10, 11, 12], [20], [30, 31, 32, 33], [40]],
        ),
        ([1, 2, 11, 12, 21, 22], [[1, 2], [11, 12], [21, 22]]),
        ([3, 2, 1], [[3], [2], [1]]),
        ([1, 1, 2, 2], [[1], [1, 2], [2]]),
        ([2, 4, 6], [[2], [4], [6]]),
        ([5], [[5]]),
        ([], []),
    ]
    rng = random.Random(4041)
    generated = [_random_items(rng, 1) for _ in range(60)]
    inputs = [items for items, _ in fixed] + generated
    expected = [groups for _, groups in fixed] + [_model(i, 1) for i in generated]
    snippet = (
        "INPUTS = "
        + repr(inputs)
        + "\n"
        + """
import more_itertools as mi
result = [[list(g) for g in mi.consecutive_groups(items)] for items in INPUTS]
"""
    )
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert isinstance(r.value, list) and len(r.value) == len(inputs)
    for items, want, got in zip(inputs, expected, r.value):
        assert got == want, "consecutive_groups({!r})".format(items)


def test_explicit_step_one_matches_default():
    snippet = """
import more_itertools as mi
result = []
for items in ([1, 2, 3, 5, 6, 8], [-10, -8, -7, -6, 1, 2, 4, 5, -1, 7], [3, 2, 1, 1, 2]):
    result.append([
        [list(g) for g in mi.consecutive_groups(items)],
        [list(g) for g in mi.consecutive_groups(items, step=1)],
    ])
for items, ordering in (('abcdfgi', ord), (['1', '10', '11', '20', '21', '22'], int)):
    result.append([
        [list(g) for g in mi.consecutive_groups(items, ordering)],
        [list(g) for g in mi.consecutive_groups(items, ordering, step=1)],
    ])
"""
    expected = [
        [[1, 2, 3], [5, 6], [8]],
        [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        [[3], [2], [1], [1, 2]],
        [["a", "b", "c", "d"], ["f", "g"], ["i"]],
        [["1"], ["10", "11"], ["20", "21", "22"]],
    ]
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == [[groups, groups] for groups in expected]


def test_step_with_ordering():
    snippet = """
import more_itertools as mi
words = ['a', 'abc', 'abcde', 'ab', 'abcd']
result = {
    'user_example': [list(g) for g in mi.consecutive_groups('acegjl', ord, step=2)],
    'longer': [list(g) for g in mi.consecutive_groups('acegjlmo', ord, step=2)],
    'step3': [list(g) for g in mi.consecutive_groups('adgjkn', ord, step=3)],
    'not_step_apart': [list(g) for g in mi.consecutive_groups('abc', ord, step=2)],
    'len': [list(g) for g in mi.consecutive_groups(words, len, step=2)],
    'scaled': [
        list(g) for g in mi.consecutive_groups([1, 2, 3, 5, 6], lambda x: 2 * x, step=2)
    ],
    'negative_ord': [list(g) for g in mi.consecutive_groups('zyxvu', ord, step=-1)],
    'negative_int': [
        list(g)
        for g in mi.consecutive_groups(['30', '20', '10', '5', '-5'], int, step=-10)
    ],
}
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == {
        "user_example": [["a", "c", "e", "g"], ["j", "l"]],
        "longer": [["a", "c", "e", "g"], ["j", "l"], ["m", "o"]],
        "step3": [["a", "d", "g", "j"], ["k", "n"]],
        "not_step_apart": [["a"], ["b"], ["c"]],
        "len": [["a", "abc", "abcde"], ["ab", "abcd"]],
        "scaled": [[1, 2, 3], [5, 6]],
        "negative_ord": [["z", "y", "x"], ["v", "u"]],
        "negative_int": [["30", "20", "10"], ["5", "-5"]],
    }


def test_randomized_runs_match_definition():
    rng = random.Random(20261113)
    plain = []
    for _ in range(150):
        step = rng.choice([-5, -3, -2, -1, 1, 2, 3, 4, 7])
        plain.append((_random_items(rng, step), step))
    ordered = []
    for _ in range(60):
        step = rng.choice([-4, -2, -1, 1, 2, 3])
        ordered.append(([str(v) for v in _random_items(rng, step)], step))
    snippet = (
        "PLAIN = "
        + repr(plain)
        + "\nORDERED = "
        + repr(ordered)
        + "\n"
        + """
import more_itertools as mi
result = {
    'plain': [
        [list(g) for g in mi.consecutive_groups(items, step=step)]
        for items, step in PLAIN
    ],
    'ordered': [
        [list(g) for g in mi.consecutive_groups(items, int, step=step)]
        for items, step in ORDERED
    ],
}
"""
    )
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert len(r.value["plain"]) == len(plain)
    assert len(r.value["ordered"]) == len(ordered)
    for (items, step), got in zip(plain, r.value["plain"]):
        want = _model(items, step)
        assert got == want, "consecutive_groups({!r}, step={!r})".format(items, step)
    for (items, step), got in zip(ordered, r.value["ordered"]):
        want = _model(items, step, int)
        assert got == want, "consecutive_groups({!r}, int, step={!r})".format(
            items, step
        )


_LAZINESS_BODY = """
import itertools
import more_itertools as mi

def call(source):
    if STEP is None:
        return mi.consecutive_groups(source)
    return mi.consecutive_groups(source, step=STEP)

out = {}
groups = call(list(FINITE))
out['outer_is_iterator'] = iter(groups) is groups
g = next(groups)
out['group_is_iterator'] = iter(g) is g
out['group_not_list_or_tuple'] = not isinstance(g, (list, tuple))
out['first_group_items'] = [next(g) for _ in range(3)]
out['rest_of_first_group'] = list(g)
out['next_group'] = list(next(groups))

def failing_source():
    yield FINITE[0]
    yield FINITE[1]
    raise RuntimeError('source was read too far ahead')

try:
    out['first_item_of_failing_source'] = next(next(call(failing_source())))
except Exception as e:
    out['first_item_of_failing_source'] = 'raised ' + type(e).__name__

pulled = []
def endless_source():
    for x in itertools.count(START, STEP if STEP is not None else 1):
        if len(pulled) >= 10000:
            raise RuntimeError('source consumed eagerly')
        pulled.append(x)
        yield x

try:
    endless_group = next(call(endless_source()))
    out['endless_first_items'] = [next(endless_group) for _ in range(3)]
except Exception as e:
    out['endless_first_items'] = 'raised ' + type(e).__name__

consumed = []
def tracked_source():
    for x in FINITE:
        consumed.append(x)
        yield x

source = tracked_source()
unused = call(source)
out['consumed_by_call'] = list(consumed)
out['left_in_source'] = list(source)
result = out
"""


def _laziness_snippet(step, finite, start):
    return (
        "STEP = {!r}\nFINITE = {!r}\nSTART = {!r}\n".format(step, finite, start)
        + _LAZINESS_BODY
    )


def test_groups_are_lazy_iterators_with_step():
    r = run_python(_laziness_snippet(2, [2, 4, 6, 10], 0), timeout=30.0)
    assert r.ok, _describe(r)
    assert r.value == {
        "outer_is_iterator": True,
        "group_is_iterator": True,
        "group_not_list_or_tuple": True,
        "first_group_items": [2, 4, 6],
        "rest_of_first_group": [],
        "next_group": [10],
        "first_item_of_failing_source": 2,
        "endless_first_items": [0, 2, 4],
        "consumed_by_call": [],
        "left_in_source": [2, 4, 6, 10],
    }


def test_groups_are_lazy_iterators_default_step():
    r = run_python(_laziness_snippet(None, [1, 2, 3, 10], 0), timeout=30.0)
    assert r.ok, _describe(r)
    assert r.value == {
        "outer_is_iterator": True,
        "group_is_iterator": True,
        "group_not_list_or_tuple": True,
        "first_group_items": [1, 2, 3],
        "rest_of_first_group": [],
        "next_group": [10],
        "first_item_of_failing_source": 1,
        "endless_first_items": [0, 1, 2],
        "consumed_by_call": [],
        "left_in_source": [1, 2, 3, 10],
    }


def test_skipped_groups_still_yield_correct_runs():
    snippet = """
import more_itertools as mi
out = {}
out['starts_step2'] = [
    next(g) for g in mi.consecutive_groups([2, 4, 6, 10, 12, 20, 22, 24], step=2)
]
out['starts_negative'] = [
    next(g) for g in mi.consecutive_groups([9, 8, 7, 3, 2, 0], step=-1)
]
out['starts_default'] = [next(g) for g in mi.consecutive_groups([1, 2, 3, 10, 11, 20])]

groups = mi.consecutive_groups([2, 4, 6, 10, 12, 20], step=2)
next(groups)
out['second_after_skip'] = list(next(groups))
out['third_after_skip'] = list(next(groups))
out['groups_left'] = len(list(groups))

groups = mi.consecutive_groups([1, 2, 3, 10, 11, 20])
next(groups)
out['default_second_after_skip'] = list(next(groups))
result = out
"""
    r = run_python(snippet)
    assert r.ok, _describe(r)
    assert r.value == {
        "starts_step2": [2, 10, 20],
        "starts_negative": [9, 3, 0],
        "starts_default": [1, 10, 20],
        "second_after_skip": [10, 12],
        "third_after_skip": [20],
        "groups_left": 0,
        "default_second_after_skip": [10, 11],
    }
