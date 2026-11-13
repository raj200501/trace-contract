"""Hidden behavioural tests for CS-04 (initial contract).

Feature under test: ``more_itertools.consecutive_groups`` gains an optional
``step`` keyword.  With ``step=k`` the input is split, in order, into maximal
runs in which every item is exactly ``k`` greater than the item before it.
Calls that omit ``step`` must behave exactly as before (i.e. like ``step=1``).

The candidate package is never imported here: every check runs a snippet in
the sandbox through ``tc_sandbox.run_python`` and inspects ``result``.
Groups are always copied with ``list(group)`` as soon as they are produced,
because (as documented) a group may share its source with the input.
"""

import random
import textwrap

from tc_sandbox import run_python


CHECK_REQUIREMENTS = {
    "test_step_keyword_is_accepted": ["R1"],
    "test_user_example_step_two": ["R1", "R2"],
    "test_step_splits_where_difference_is_not_step": ["R2"],
    "test_step_groups_only_increases_of_exactly_step": ["R2"],
    "test_step_various_step_sizes": ["R2"],
    "test_step_empty_and_single_item_inputs": ["R2"],
    "test_step_accepts_any_iterable": ["R2"],
    "test_step_randomized_inputs_match_definition": ["R2"],
    "test_existing_consecutive_groups_tests_still_pass": ["R3"],
    "test_default_matches_base_outputs": ["R3"],
    "test_default_equals_explicit_step_one": ["R3"],
    "test_ordering_argument_still_supported": ["R3"],
}


# --------------------------------------------------------------------------
# helpers (pure test-side code; nothing here touches the candidate)
# --------------------------------------------------------------------------


def _failure(r):
    return (
        "snippet did not complete: "
        f"timed_out={r.timed_out} error={r.error_type}: {r.error}\n"
        f"stderr:\n{r.stderr}"
    )


def _split_runs(items, step):
    """Reference partition: start a new group wherever an item is not
    exactly ``step`` greater than the previous item."""
    groups = []
    for item in items:
        if groups and item - groups[-1][-1] == step:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _first_mismatch(cases, actual, expected):
    for index, (case, got, want) in enumerate(zip(cases, actual, expected)):
        if got != want:
            return f"case #{index} {case!r}: got {got!r}, expected {want!r}"
    return None


def _cases_snippet(cases):
    """Snippet that groups each (items, step) case with the step keyword."""
    return textwrap.dedent(
        f"""
        import more_itertools
        cases = {cases!r}
        result = [
            [list(group) for group in
             more_itertools.consecutive_groups(items, step=step)]
            for items, step in cases
        ]
        """
    )


def _random_step_cases(seed, count):
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        step = rng.choice([1, 2, 3, 4, 5, 6, 7, 10, 25])
        items = []
        for _ in range(rng.randint(1, 6)):
            roll = rng.random()
            start = rng.randint(-60, 60)
            if roll < 0.55:
                # a run that goes up by exactly ``step``
                length = rng.randint(1, 5)
                items.extend(start + step * j for j in range(length))
            elif roll < 0.75:
                # a near miss: the difference is one off from ``step``
                items.extend([start, start + step + rng.choice([-1, 1])])
            elif roll < 0.9:
                # extend the previous run, so neighbouring runs must merge
                items.append(items[-1] + step if items else start)
            else:
                items.append(start)
        cases.append((items, step))
    return cases


def _random_default_samples(seed, count):
    rng = random.Random(seed)
    samples = []
    for _ in range(count):
        items = []
        for _ in range(rng.randint(0, 6)):
            roll = rng.random()
            start = rng.randint(-40, 40)
            if roll < 0.6:
                items.extend(range(start, start + rng.randint(1, 6)))
            elif roll < 0.8:
                items.extend([start, start])
            else:
                items.extend(range(start, start - rng.randint(1, 4), -1))
        samples.append(items)
    return samples


# --------------------------------------------------------------------------
# R1: the ``step`` keyword is accepted
# --------------------------------------------------------------------------


def test_step_keyword_is_accepted():
    snippet = textwrap.dedent(
        """
        import more_itertools
        outcomes = []
        for step in (2, 1, 3, 4, 10):
            try:
                groups = more_itertools.consecutive_groups(
                    [2, 4, 6, 10, 12], step=step
                )
                for group in groups:
                    list(group)
                outcomes.append([step, None])
            except Exception as exc:
                outcomes.append([step, type(exc).__name__ + ': ' + str(exc)])
        result = outcomes
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == [[2, None], [1, None], [3, None], [4, None], [10, None]]


# --------------------------------------------------------------------------
# R2: grouping semantics with a step
# --------------------------------------------------------------------------


def test_user_example_step_two():
    snippet = textwrap.dedent(
        """
        import more_itertools
        result = [
            list(group)
            for group in more_itertools.consecutive_groups(
                [2, 4, 6, 10, 12], step=2
            )
        ]
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == [[2, 4, 6], [10, 12]]


def test_step_splits_where_difference_is_not_step():
    # Differences smaller than, larger than, or a multiple of the step must
    # all start a new group.
    cases = [
        ([2, 3, 4, 5], 2),
        ([1, 2, 3], 2),
        ([3, 4, 6], 2),
        ([1, 3, 5, 6, 8], 2),
        ([2, 4, 8, 10], 2),
        ([0, 3, 9, 12, 13, 16], 3),
        ([1, 4, 7, 8, 11], 3),
        ([0, 5, 10, 14, 19, 25], 5),
    ]
    expected = [
        [[2], [3], [4], [5]],
        [[1], [2], [3]],
        [[3], [4, 6]],
        [[1, 3, 5], [6, 8]],
        [[2, 4], [8, 10]],
        [[0, 3], [9, 12], [13, 16]],
        [[1, 4, 7], [8, 11]],
        [[0, 5, 10], [14, 19], [25]],
    ]
    r = run_python(_cases_snippet(cases), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _first_mismatch(cases, r.value, expected)


def test_step_groups_only_increases_of_exactly_step():
    # "Each item is exactly k greater than the previous": decreases and
    # repeats break a run; negative numbers are fine with a positive step.
    cases = [
        ([6, 4, 2], 2),
        ([9, 6, 3, 0], 3),
        ([10, 8, 10, 12], 2),
        ([5, 5, 7, 9, 9], 2),
        ([3, 3, 3], 3),
        ([-6, -4, -2, 0, 2, 5], 2),
    ]
    expected = [
        [[6], [4], [2]],
        [[9], [6], [3], [0]],
        [[10], [8, 10, 12]],
        [[5], [5, 7, 9], [9]],
        [[3], [3], [3]],
        [[-6, -4, -2, 0, 2], [5]],
    ]
    r = run_python(_cases_snippet(cases), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _first_mismatch(cases, r.value, expected)


def test_step_various_step_sizes():
    big = 10**15
    cases = [
        ([0, 3, 6, 9, 12], 3),
        ([10, 15, 20, 26, 31, 40], 5),
        ([100, 200, 300, 301], 100),
        ([1, 11, 21, 22, 32], 10),
        ([4, 8, 12, 16, 15, 19, 23], 4),
        ([-20, -13, -6, 1], 7),
        ([big, big + 7, big + 14, big + 15], 7),
        ([1, 2, 3, 5, 6], 1),
    ]
    expected = [
        [[0, 3, 6, 9, 12]],
        [[10, 15, 20], [26, 31], [40]],
        [[100, 200, 300], [301]],
        [[1, 11, 21], [22, 32]],
        [[4, 8, 12, 16], [15, 19, 23]],
        [[-20, -13, -6, 1]],
        [[big, big + 7, big + 14], [big + 15]],
        [[1, 2, 3], [5, 6]],
    ]
    r = run_python(_cases_snippet(cases), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _first_mismatch(cases, r.value, expected)


def test_step_empty_and_single_item_inputs():
    snippet = textwrap.dedent(
        """
        import more_itertools
        cg = more_itertools.consecutive_groups
        result = {
            'empty_list': [list(g) for g in cg([], step=2)],
            'empty_iterator': [list(g) for g in cg(iter([]), step=4)],
            'single': [list(g) for g in cg([7], step=3)],
            'single_step_one': [list(g) for g in cg([42], step=1)],
        }
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == {
        "empty_list": [],
        "empty_iterator": [],
        "single": [[7]],
        "single_step_one": [[42]],
    }


def test_step_accepts_any_iterable():
    snippet = textwrap.dedent(
        """
        import more_itertools
        cg = more_itertools.consecutive_groups

        def gen():
            yield from [2, 4, 6, 10, 12]

        result = {
            'generator': [list(g) for g in cg(gen(), step=2)],
            'genexpr': [
                list(g) for g in cg((x * 3 for x in [1, 2, 3, 5]), step=3)
            ],
            'iterator': [list(g) for g in cg(iter((1, 4, 7, 8)), step=3)],
            'tuple': [list(g) for g in cg((5, 10, 15, 16), step=5)],
            'range': [list(g) for g in cg(range(0, 20, 4), step=4)],
            'range_unit': [list(g) for g in cg(range(0, 4), step=2)],
        }
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == {
        "generator": [[2, 4, 6], [10, 12]],
        "genexpr": [[3, 6, 9], [15]],
        "iterator": [[1, 4, 7], [8]],
        "tuple": [[5, 10, 15], [16]],
        "range": [[0, 4, 8, 12, 16]],
        "range_unit": [[0], [1], [2], [3]],
    }


def test_step_randomized_inputs_match_definition():
    # For integer inputs and positive integer steps the maximal-run partition
    # is unique: groups concatenate to the input, adjacent items inside a
    # group differ by exactly ``step``, and the boundary items do not.
    cases = _random_step_cases(seed=40421, count=250)
    expected = [_split_runs(items, step) for items, step in cases]
    r = run_python(_cases_snippet(cases), timeout=20.0)
    assert r.ok, _failure(r)
    assert isinstance(r.value, list) and len(r.value) == len(cases)
    assert r.value == expected, _first_mismatch(cases, r.value, expected)


# --------------------------------------------------------------------------
# R3: behaviour without ``step`` is unchanged
# --------------------------------------------------------------------------


def test_existing_consecutive_groups_tests_still_pass():
    # Bodies of the repository's pre-existing ConsecutiveGroupsTest cases and
    # the consecutive_groups docstring examples, as they are at the base
    # commit.
    snippet = textwrap.dedent(
        """
        from itertools import permutations
        import more_itertools as mi

        checks = {}

        iterable = [-10, -8, -7, -6, 1, 2, 4, 5, -1, 7]
        checks['test_numbers'] = [
            list(g) for g in mi.consecutive_groups(iterable)
        ]

        iterable = ['1', '10', '11', '20', '21', '22', '30', '31']
        ordering = lambda x: int(x)
        checks['test_custom_ordering'] = [
            list(g) for g in mi.consecutive_groups(iterable, ordering)
        ]

        iterable = [
            ('a', 'b', 'c', 'd'),
            ('a', 'c', 'b', 'd'),
            ('a', 'c', 'd', 'b'),
            ('a', 'd', 'b', 'c'),
            ('d', 'b', 'c', 'a'),
            ('d', 'c', 'a', 'b'),
        ]
        ordering = list(permutations('abcd')).index
        checks['test_exotic_ordering'] = [
            [''.join(t) for t in g]
            for g in mi.consecutive_groups(iterable, ordering)
        ]

        checks['doc_numbers'] = [
            list(g)
            for g in mi.consecutive_groups(
                [1, 10, 11, 12, 20, 30, 31, 32, 33, 40]
            )
        ]
        checks['doc_letters'] = [
            list(g) for g in mi.consecutive_groups('abcdfgilmnop', ord)
        ]
        saved_groups = []
        for group in mi.consecutive_groups([1, 2, 11, 12, 21, 22]):
            saved_groups.append(list(group))
        checks['doc_saved_groups'] = saved_groups

        result = checks
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == {
        "test_numbers": [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        "test_custom_ordering": [
            ["1"],
            ["10", "11"],
            ["20", "21", "22"],
            ["30", "31"],
        ],
        "test_exotic_ordering": [
            ["abcd"],
            ["acbd", "acdb", "adbc"],
            ["dbca", "dcab"],
        ],
        "doc_numbers": [[1], [10, 11, 12], [20], [30, 31, 32, 33], [40]],
        "doc_letters": [
            ["a", "b", "c", "d"],
            ["f", "g"],
            ["i"],
            ["l", "m", "n", "o", "p"],
        ],
        "doc_saved_groups": [[1, 2], [11, 12], [21, 22]],
    }


def test_default_matches_base_outputs():
    # Expected values were produced by the base (pre-change) implementation.
    snippet = textwrap.dedent(
        """
        import more_itertools
        cg = more_itertools.consecutive_groups

        def groups(iterable, *args, **kwargs):
            return [list(g) for g in cg(iterable, *args, **kwargs)]

        result = {
            'empty': groups([]),
            'single': groups([5]),
            'descending': groups([3, 2, 1]),
            'duplicates': groups([1, 1, 2, 2, 3, 5, 6, 6]),
            'evens': groups([0, 2, 4, 6]),
            'one_run': groups([7, 8, 9, 10, 11, 12]),
            'through_zero': groups([-3, -2, -1, 0, 1, 3]),
            'big': groups([10**15, 10**15 + 1, 10**15 + 3]),
            'generator': groups(x for x in [4, 5, 6, 8, 9]),
            'range': groups(range(3, 9)),
            'tuple': groups((1, 2, 4)),
            'iterator': groups(iter([-10, -8, -7, -6, 1, 2, 4, 5, -1, 7])),
            'ordering_none_positional': groups([3, 1, 2, 5], None),
            'ordering_none_keyword': groups([3, 1, 2, 5], ordering=None),
        }
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    big = 10**15
    assert r.value == {
        "empty": [],
        "single": [[5]],
        "descending": [[3], [2], [1]],
        "duplicates": [[1], [1, 2], [2, 3], [5, 6], [6]],
        "evens": [[0], [2], [4], [6]],
        "one_run": [[7, 8, 9, 10, 11, 12]],
        "through_zero": [[-3, -2, -1, 0, 1], [3]],
        "big": [[big, big + 1], [big + 3]],
        "generator": [[4, 5, 6], [8, 9]],
        "range": [[3, 4, 5, 6, 7, 8]],
        "tuple": [[1, 2], [4]],
        "iterator": [[-10], [-8, -7, -6], [1, 2], [4, 5], [-1], [7]],
        "ordering_none_positional": [[3], [1, 2], [5]],
        "ordering_none_keyword": [[3], [1, 2], [5]],
    }


def test_default_equals_explicit_step_one():
    samples = [
        [1, 10, 11, 12, 20, 30, 31, 32, 33, 40],
        [-10, -8, -7, -6, 1, 2, 4, 5, -1, 7],
        [2, 4, 6, 10, 12],
        [5, 4, 3, 4, 5],
        [],
    ] + _random_default_samples(seed=1113, count=120)
    snippet = textwrap.dedent(
        f"""
        import more_itertools
        cg = more_itertools.consecutive_groups
        samples = {samples!r}
        result = {{
            'default': [[list(g) for g in cg(x)] for x in samples],
            'step_one': [[list(g) for g in cg(x, step=1)] for x in samples],
        }}
        """
    )
    expected = [_split_runs(x, 1) for x in samples]
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert sorted(r.value) == ["default", "step_one"]
    assert r.value["default"] == expected, _first_mismatch(
        samples, r.value["default"], expected
    )
    assert r.value["step_one"] == expected, _first_mismatch(
        samples, r.value["step_one"], expected
    )


def test_ordering_argument_still_supported():
    snippet = textwrap.dedent(
        """
        import more_itertools
        cg = more_itertools.consecutive_groups
        result = {
            'int_keyword': [
                list(g)
                for g in cg(
                    ['1', '10', '11', '20', '21', '22', '30', '31'],
                    ordering=int,
                )
            ],
            'ord_keyword': [list(g) for g in cg('abcdfgilmnop', ordering=ord)],
            'len_keyword': [
                list(g) for g in cg(['a', 'bb', 'ccc', 'e', 'ff'], ordering=len)
            ],
            'negate_positional': [
                list(g) for g in cg([5, 4, 3, 7, 6], lambda x: -x)
            ],
            'iterator_positional': [list(g) for g in cg(iter('xyzab'), ord)],
        }
        """
    )
    r = run_python(snippet, timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == {
        "int_keyword": [["1"], ["10", "11"], ["20", "21", "22"], ["30", "31"]],
        "ord_keyword": [
            ["a", "b", "c", "d"],
            ["f", "g"],
            ["i"],
            ["l", "m", "n", "o", "p"],
        ],
        "len_keyword": [["a", "bb", "ccc"], ["e", "ff"]],
        "negate_positional": [[5, 4, 3], [7, 6]],
        "iterator_positional": [["x", "y", "z"], ["a", "b"]],
    }
