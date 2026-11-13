"""Reference checks for R-humanize-unchanged.

``humanize()`` output is unchanged for all inputs (contract examples:
'employee_salary' -> 'Employee salary', 'author_id' -> 'Author').

Expected values are the base-commit outputs: hand-derived values for the
curated cases (including inputs with all-caps words, which a solution of the
titleize change might be tempted to preserve), and for generated inputs a
verbatim copy of the base-commit ``humanize`` evaluated in the sandbox before
the candidate package is imported.
"""
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_humanize_contract_examples": ["R-humanize-unchanged"],
    "test_humanize_inputs_with_capitals_unchanged": ["R-humanize-unchanged"],
    "test_humanize_generated_inputs_match_base": ["R-humanize-unchanged"],
}

# Verbatim behaviour of inflection.humanize at the base commit.
BASE_ORACLE = r'''
import re as _re


def _base_humanize(word):
    word = _re.sub(r"_id$", "", word)
    word = word.replace('_', ' ')
    word = _re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = _re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word
'''

PIECES = (
    "a", "b", "x", "Z", "Q", "id", "ID", "Id", "iD", "_id", "_ID", "_", "__",
    "-", " ", "'", ".", ":", "NASA", "Rocket", "rocket", "HTTPServer",
    "IOError", "html", "HTML5", "v2", "9", "42", "é", "Índia",
    "ñ", "Ö", "camelCase", "snake_case", "SCREAMING", "iPhone",
    "McDonald", "AB", "Ab", "aB",
)


def _humanize_snippet(inputs):
    return (
        "import inflection\n"
        "INPUTS = " + ascii(list(inputs)) + "\n"
        "result = {s: inflection.humanize(s) for s in INPUTS}\n"
    )


def _differential_snippet(inputs):
    return (
        BASE_ORACLE
        + "\nINPUTS = " + ascii(list(inputs)) + "\n"
        + "EXPECTED = [_base_humanize(s) for s in INPUTS]\n"
        + "import inflection\n"
        + "ACTUAL = [inflection.humanize(s) for s in INPUTS]\n"
        + "result = {\n"
        + "    'checked': len(INPUTS),\n"
        + "    'mismatches': [\n"
        + "        [s, e, a] for s, e, a in zip(INPUTS, EXPECTED, ACTUAL)\n"
        + "        if e != a\n"
        + "    ],\n"
        + "}\n"
    )


def _generated_inputs():
    rng = random.Random(7331)
    inputs = ["", "_", "id", "_id", "_ID", "a_id_id", "employee_id"]
    while len(inputs) < 300:
        text = "".join(rng.choice(PIECES) for _ in range(rng.randint(1, 6)))
        if text not in inputs:
            inputs.append(text)
    return inputs


def test_humanize_contract_examples():
    expected = {
        "employee_salary": "Employee salary",
        "author_id": "Author",
    }
    r = run_python(_humanize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_humanize_inputs_with_capitals_unchanged():
    expected = {
        "NASA_rocket_launch": "Nasa rocket launch",
        "read the HTTP spec": "Read the http spec",
        "NASA rocket launch": "Nasa rocket launch",
        "HELLO WORLD": "Hello world",
        "employee_ID": "Employee id",
        "HTTP_API_id": "Http api",
        "ActiveRecord": "Activerecord",
        "employee_id": "Employee",
        "underground": "Underground",
    }
    r = run_python(_humanize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_humanize_generated_inputs_match_base():
    inputs = _generated_inputs()
    r = run_python(_differential_snippet(inputs), timeout=30.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {"checked": len(inputs), "mismatches": []}
