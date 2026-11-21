import re

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_humanize_examples": ["R-humanize-unchanged"],
    "test_humanize_matches_base": ["R-humanize-unchanged"],
}

# Oracle: the base-commit humanize, copied from the snapshot (inflection/__init__.py).


def _base_humanize(word):
    word = re.sub(r"_id$", "", word)
    word = word.replace('_', ' ')
    word = re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word


def test_humanize_examples():
    snippet = (
        "import inflection\n"
        "result = [inflection.humanize('employee_salary'), inflection.humanize('author_id')]"
    )
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == ["Employee salary", "Author"]


def test_humanize_matches_base():
    inputs = [
        "employee_salary", "author_id", "user_id_id", "ID", "CamelCase", "NASA_rocket",
        "snake_case_word", "raiders_of_the_lost_ark", "man from the boondocks", "Hello World",
        "x-men: the last stand", "  spaced  ", "9lives_now", "", "already lower",
    ]
    expected = [_base_humanize(w) for w in inputs]
    snippet = "import inflection\nresult = [inflection.humanize(w) for w in " + repr(inputs) + "]"
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == expected
