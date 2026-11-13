# Hidden behavioural tests for CS-04 (condition llm_freeform):
# a `step` option for more_itertools.consecutive_groups.
#
# Requirement labels (inferred from the whole session, including the
# coordinator's follow-up message):
#   B1  consecutive_groups(iterable, step=k) groups runs whose successive items
#       increase by exactly k (e.g. [2, 4, 6, 10, 12], step=2 -> [2, 4, 6] and
#       [10, 12]); a difference of any other amount starts a new group.  Any
#       iterable is accepted.
#   B2  A negative step groups descending runs (e.g. [9, 8, 7, 3, 2], step=-1
#       -> [9, 8, 7] and [3, 2]); increasing items are then not grouped.
#   B3  step=0 raises ValueError (either when called or once iterated) instead
#       of producing groups.
#   B4  Without step (and with an explicit step=1) grouping is unchanged.
#   B5  ordering still works as the second positional argument (and as a
#       keyword argument), exactly as before.
#   B6  step combines with ordering: the positions returned by the ordering
#       function must differ by exactly step.
#   B7  Groups are still lazy iterators: each group is an iterator object, and
#       both the result and each group are produced incrementally, so they work
#       on unbounded input.
#   B8  As before, moving on to the next group works whether or not the
#       current group was (fully) consumed.
#
# Deliberately NOT checked (not asked for, or several reasonable answers):
# whether step is keyword-only, non-integer steps (floats, Fractions), whether
# step=0 raises at call time rather than on iteration, the error message,
# whether earlier groups become empty once the result is advanced, input
# consumption at call time, docs and type stubs.
#
# Every snippet does its work inside a function (_main) so that helper
# functions resolve names through closures, whatever namespace the sandbox
# executes the snippet in.

import json
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_user_example_step_two": ["B1"],
    "test_positive_step_requires_exact_difference": ["B1"],
    "test_random_steps_match_pairwise_definition": ["B1", "B2"],
    "test_negative_step_groups_descending_runs": ["B2"],
    "test_zero_step_raises_value_error": ["B3"],
    "test_default_grouping_unchanged": ["B4"],
    "test_explicit_step_one_matches_default_grouping": ["B4"],
    "test_ordering_as_second_positional_argument": ["B5"],
    "test_step_combined_with_ordering": ["B6"],
    "test_random_step_with_ordering_matches_pairwise_definition": ["B6", "B2"],
    "test_groups_are_iterators": ["B7"],
    "test_lazy_on_unbounded_run": ["B7"],
    "test_lazy_on_unbounded_sequence_of_runs": ["B7"],
    "test_next_group_without_consuming_current_group": ["B8"],
}

# Nonzero integer steps used by the randomised cross-checks.
STEPS = [1, 2, 3, 5, 10, -1, -2, -3, -5]


def _pairwise_groups(items, step, position=lambda x: x):
    """Trusted reference: start a new group wherever the position of an item
    minus the position of the item before it is not exactly ``step``."""
    groups = []
    prev = None
    for item in items:
        if groups and position(item) - position(prev) == step:
            groups[-1].append(item)
        else:
            groups.append([item])
        prev = item
    return groups


def _random_walk(rng, step, length):
    """Integer sequence that mostly moves by ``step`` (so runs occur), with
    repeats, reversals and random jumps mixed in."""
    values = []
    current = rng.randint(-25, 25)
    for _ in range(length):
        values.append(current)
        roll = rng.random()
        if roll < 0.6:
            current += step
        elif roll < 0.7:
            pass  # repeat the same value
        elif roll < 0.8:
            current -= step
        else:
            current += rng.randint(-12, 12)
    return values


def _first_mismatches(cases, expected, actual, limit=3):
    if not isinstance(actual, list) or len(actual) != len(expected):
        return ["unexpected result shape: %r" % (actual,)]
    return [
        {"case": case, "expected": exp, "actual": got}
        for case, exp, got in zip(cases, expected, actual)
        if exp != got
    ][:limit]


def test_user_example_step_two():
    snippet = """
def _main():
    from more_itertools import consecutive_groups
    return [list(g) for g in consecutive_groups([2, 4, 6, 10, 12], step=2)]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [[2, 4, 6], [10, 12]]


def test_positive_step_requires_exact_difference():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def groups(iterable, step):
        return [list(g) for g in consecutive_groups(iterable, step=step)]

    return [
        groups([2, 4, 6, 10, 12, 15, 17, 20], 2),
        groups([0, 3, 6, 7, 10, 14], 3),
        groups([100, 110, 120, 125, 135], 10),
        groups([-4, -2, 0, 2, 5, 7], 2),
        groups([1, 2, 3], 2),
        groups([6, 4, 2], 2),
        groups([4, 4, 6], 2),
        groups([7], 5),
        groups([], 2),
        groups((x for x in [1, 3, 5, 6, 8]), 2),
        groups(range(0, 20, 5), 5),
        groups((9, 12, 15, 16, 19), 3),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [[2, 4, 6], [10, 12], [15, 17], [20]],
        [[0, 3, 6], [7, 10], [14]],
        [[100, 110, 120], [125, 135]],
        [[-4, -2, 0, 2], [5, 7]],
        [[1], [2], [3]],
        [[6], [4], [2]],
        [[4], [4, 6]],
        [[7]],
        [],
        [[1, 3, 5], [6, 8]],
        [[0, 5, 10, 15]],
        [[9, 12, 15], [16, 19]],
    ]


def test_random_steps_match_pairwise_definition():
    rng = random.Random(4021)
    cases = []
    for _ in range(400):
        step = rng.choice(STEPS)
        length = rng.randint(0, 14)
        cases.append([_random_walk(rng, step, length), step])
    expected = [_pairwise_groups(values, step) for values, step in cases]
    snippet = (
        "def _main():\n"
        "    import json\n"
        "    from more_itertools import consecutive_groups\n"
        "    cases = json.loads(%r)\n"
        "    return [[list(g) for g in consecutive_groups(values, step=step)]\n"
        "            for values, step in cases]\n"
        "\n"
        "result = _main()\n" % json.dumps(cases)
    )
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected, _first_mismatches(cases, expected, r.value)


def test_negative_step_groups_descending_runs():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def groups(iterable, step):
        return [list(g) for g in consecutive_groups(iterable, step=step)]

    return [
        groups([9, 8, 7, 3, 2], -1),
        groups([1, 2, 3], -1),
        groups([10, 8, 6, 5, 3, 1], -2),
        groups([0, -3, -6, 1, -2], -3),
        groups([5, 4, 4, 3], -1),
        groups(iter([20, 15, 10, 11, 6]), -5),
        groups([], -1),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [[9, 8, 7], [3, 2]],
        [[1], [2], [3]],
        [[10, 8, 6], [5, 3, 1]],
        [[0, -3, -6], [1, -2]],
        [[5, 4], [4, 3]],
        [[20, 15, 10], [11, 6]],
        [],
    ]


def test_zero_step_raises_value_error():
    # The error may be raised by the call itself or once the result is
    # iterated; both are accepted.
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def outcome(call):
        try:
            groups = [list(g) for g in call()]
        except ValueError:
            return 'ValueError'
        except Exception as e:
            return 'other exception: ' + type(e).__name__
        return 'no error: %r' % (groups,)

    return [
        outcome(lambda: consecutive_groups([1, 1, 2], step=0)),
        outcome(lambda: consecutive_groups([1, 2, 3], step=0)),
        outcome(lambda: consecutive_groups([5, 5, 5, 6], step=0)),
        outcome(lambda: consecutive_groups(iter([4, 4]), step=0)),
        outcome(lambda: consecutive_groups('aab', ordering=ord, step=0)),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == ["ValueError"] * 5


def test_default_grouping_unchanged():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def groups(iterable):
        return [list(g) for g in consecutive_groups(iterable)]

    return [
        groups([1, 10, 11, 12, 20, 30, 31, 32, 33, 40]),
        groups([-10, -8, -7, -6, 1, 2, 4, 5, -1, 7]),
        groups([1, 1, 2]),
        groups([3, 2, 1]),
        groups(iter([1, 2, 11, 12, 21, 22])),
        groups([]),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [[1], [10, 11, 12], [20], [30, 31, 32, 33], [40]],
        [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        [[1], [1, 2]],
        [[3], [2], [1]],
        [[1, 2], [11, 12], [21, 22]],
        [],
    ]


def test_explicit_step_one_matches_default_grouping():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def groups(iterable):
        return [list(g) for g in consecutive_groups(iterable, step=1)]

    return [
        groups([1, 10, 11, 12, 20, 30, 31, 32, 33, 40]),
        groups([-10, -8, -7, -6, 1, 2, 4, 5, -1, 7]),
        groups([1, 1, 2]),
        groups([3, 2, 1]),
        groups(iter([1, 2, 11, 12, 21, 22])),
        groups([]),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [[1], [10, 11, 12], [20], [30, 31, 32, 33], [40]],
        [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        [[1], [1, 2]],
        [[3], [2], [1]],
        [[1, 2], [11, 12], [21, 22]],
        [],
    ]


def test_ordering_as_second_positional_argument():
    snippet = """
def _main():
    from itertools import permutations
    from more_itertools import consecutive_groups

    perms = list(permutations('abcd'))
    exotic = [tuple(s) for s in ['abcd', 'acbd', 'acdb', 'adbc', 'dbca', 'dcab']]
    numbers = ['1', '10', '11', '20', '21', '22', '30', '31']

    return [
        [list(g) for g in consecutive_groups('abcdfgilmnop', ord)],
        [list(g) for g in consecutive_groups(numbers, int)],
        [[''.join(t) for t in g] for g in consecutive_groups(exotic, perms.index)],
        [list(g) for g in consecutive_groups('abcdfgilmnop', ordering=ord)],
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [["a", "b", "c", "d"], ["f", "g"], ["i"], ["l", "m", "n", "o", "p"]],
        [["1"], ["10", "11"], ["20", "21", "22"], ["30", "31"]],
        [["abcd"], ["acbd", "acdb", "adbc"], ["dbca", "dcab"]],
        [["a", "b", "c", "d"], ["f", "g"], ["i"], ["l", "m", "n", "o", "p"]],
    ]


def test_step_combined_with_ordering():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    words = ['a', 'aaa', 'aaaaa', 'aa', 'aaaa']
    return [
        [list(g) for g in consecutive_groups('acegjlmo', ord, step=2)],
        [list(g) for g in consecutive_groups('adgjkn', ordering=ord, step=3)],
        [list(g) for g in consecutive_groups(['5', '10', '15', '16', '21'], int, step=5)],
        [list(g) for g in consecutive_groups(words, ordering=len, step=2)],
        [list(g) for g in consecutive_groups('abcde', ord, step=2)],
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [["a", "c", "e", "g"], ["j", "l"], ["m", "o"]],
        [["a", "d", "g", "j"], ["k", "n"]],
        [["5", "10", "15"], ["16", "21"]],
        [["a", "aaa", "aaaaa"], ["aa", "aaaa"]],
        [["a"], ["b"], ["c"], ["d"], ["e"]],
    ]


def test_random_step_with_ordering_matches_pairwise_definition():
    # Items are (label, position) pairs; the ordering function returns the
    # position, and the groups must contain the original items.
    rng = random.Random(77)
    cases = []
    for _ in range(250):
        step = rng.choice(STEPS)
        length = rng.randint(0, 12)
        positions = _random_walk(rng, step, length)
        items = [["i%d" % k, p] for k, p in enumerate(positions)]
        cases.append([items, step])
    expected = [
        [
            [item[0] for item in group]
            for group in _pairwise_groups(items, step, lambda it: it[1])
        ]
        for items, step in cases
    ]
    snippet = (
        "def _main():\n"
        "    import json\n"
        "    from more_itertools import consecutive_groups\n"
        "    cases = json.loads(%r)\n"
        "    out = []\n"
        "    for items, step in cases:\n"
        "        items = [tuple(item) for item in items]\n"
        "        res = consecutive_groups(items, ordering=lambda it: it[1], step=step)\n"
        "        out.append([[item[0] for item in g] for g in res])\n"
        "    return out\n"
        "\n"
        "result = _main()\n" % json.dumps(cases)
    )
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected, _first_mismatches(cases, expected, r.value)


def test_groups_are_iterators():
    snippet = """
def _main():
    from more_itertools import consecutive_groups

    def describe(res):
        info = {'outer_is_iterator': iter(res) is res, 'groups': []}
        for g in res:
            is_iterator = iter(g) is g and hasattr(g, '__next__')
            first = next(g)
            rest = list(g)
            info['groups'].append([is_iterator, first, rest])
        return info

    return [
        describe(consecutive_groups([1, 2, 3, 10, 11])),
        describe(consecutive_groups([2, 4, 6, 10, 12], step=2)),
        describe(consecutive_groups([0, 3, 6, 9, 20], step=3)),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        {"outer_is_iterator": True, "groups": [[True, 1, [2, 3]], [True, 10, [11]]]},
        {"outer_is_iterator": True, "groups": [[True, 2, [4, 6]], [True, 10, [12]]]},
        {"outer_is_iterator": True, "groups": [[True, 0, [3, 6, 9]], [True, 20, []]]},
    ]


def test_lazy_on_unbounded_run():
    # The input is endless (one run that never ends); it fails loudly if the
    # consumer reads far more than it asked for, so an eager implementation
    # fails fast instead of hanging.
    snippet = """
def _main():
    from itertools import count, islice
    from more_itertools import consecutive_groups

    class InputOverConsumed(Exception):
        pass

    def unbounded(start, delta, limit=2000):
        for i, value in enumerate(count(start, delta)):
            if i >= limit:
                raise InputOverConsumed(i)
            yield value

    def head_of_first_group(source, n, **kwargs):
        try:
            groups = consecutive_groups(source, **kwargs)
            first = next(groups)
            return list(islice(first, n))
        except Exception as e:
            return 'raised ' + type(e).__name__

    return [
        head_of_first_group(unbounded(0, 1), 6),
        head_of_first_group(unbounded(5, 3), 6, step=3),
        head_of_first_group(unbounded(0, 10), 4, step=10),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert not r.timed_out
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [0, 1, 2, 3, 4, 5],
        [5, 8, 11, 14, 17, 20],
        [0, 10, 20, 30],
    ]


def test_lazy_on_unbounded_sequence_of_runs():
    # Endless input made of infinitely many finite runs; only the first few
    # groups are requested.
    snippet = """
def _main():
    from itertools import count
    from more_itertools import consecutive_groups

    class InputOverConsumed(Exception):
        pass

    def unbounded(values, limit=2000):
        for i, value in enumerate(values):
            if i >= limit:
                raise InputOverConsumed(i)
            yield value

    def first_groups(source, n, **kwargs):
        try:
            groups = consecutive_groups(source, **kwargs)
            return [list(next(groups)) for _ in range(n)]
        except Exception as e:
            return 'raised ' + type(e).__name__

    return [
        first_groups(unbounded(x for x in count(1) if x % 5), 3),
        first_groups(unbounded(x for x in count(0, 2) if x % 10 != 8), 4, step=2),
        first_groups(unbounded(x for x in count(0, 3) if x % 12 != 9), 3, step=3),
    ]

result = _main()
"""
    r = run_python(snippet)
    assert not r.timed_out
    assert r.ok, (r.error_type, r.error)
    assert r.value == [
        [[1, 2, 3, 4], [6, 7, 8, 9], [11, 12, 13, 14]],
        [[0, 2, 4, 6], [10, 12, 14, 16], [20, 22, 24, 26], [30, 32, 34, 36]],
        [[0, 3, 6], [12, 15, 18], [24, 27, 30]],
    ]


def test_next_group_without_consuming_current_group():
    snippet = """
def _main():
    from itertools import islice
    from more_itertools import consecutive_groups

    data = [2, 4, 6, 10, 12, 15, 17, 20]
    spaced = [0, 3, 6, 9, 20, 23, 26, 40]
    plain = [1, 2, 3, 10, 11, 20]
    return {
        'heads_step_2': [next(g) for g in consecutive_groups(data, step=2)],
        'count_step_2': sum(1 for _ in consecutive_groups(data, step=2)),
        'pairs_step_3': [list(islice(g, 2)) for g in consecutive_groups(spaced, step=3)],
        'heads_default': [next(g) for g in consecutive_groups(plain)],
        'count_default': sum(1 for _ in consecutive_groups(plain)),
    }

result = _main()
"""
    r = run_python(snippet)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {
        "heads_step_2": [2, 10, 15, 20],
        "count_step_2": 4,
        "pairs_step_3": [[0, 3], [20, 23], [40]],
        "heads_default": [1, 10, 20],
        "count_default": 3,
    }
