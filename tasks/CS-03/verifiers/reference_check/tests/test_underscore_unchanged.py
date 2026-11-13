"""Reference checks for R-underscore-unchanged.

``underscore()`` output is unchanged for all inputs (contract example:
underscore('NASARocket') returns exactly what it returns at the base commit,
which is 'nasa_rocket').

Expected values are the base-commit outputs: hand-derived values for the
curated cases (including acronym and all-caps inputs, which a solution of the
titleize change might be tempted to preserve), and for generated inputs a
verbatim copy of the base-commit ``underscore`` evaluated in the sandbox
before the candidate package is imported.
"""
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_underscore_contract_example": ["R-underscore-unchanged"],
    "test_underscore_camel_and_acronym_inputs_unchanged": [
        "R-underscore-unchanged"
    ],
    "test_underscore_generated_inputs_match_base": ["R-underscore-unchanged"],
}

# Verbatim behaviour of inflection.underscore at the base commit.
BASE_ORACLE = r'''
import re as _re


def _base_underscore(word):
    word = _re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)
    word = _re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)
    word = word.replace("-", "_")
    return word.lower()
'''

PIECES = (
    "a", "b", "x", "Z", "Q", "id", "ID", "Id", "iD", "_id", "_ID", "_", "__",
    "-", " ", "'", ".", ":", "NASA", "Rocket", "rocket", "HTTPServer",
    "IOError", "html", "HTML5", "v2", "9", "42", "é", "Índia",
    "ñ", "Ö", "camelCase", "snake_case", "SCREAMING", "iPhone",
    "McDonald", "AB", "Ab", "aB",
)


def _underscore_snippet(inputs):
    return (
        "import inflection\n"
        "INPUTS = " + ascii(list(inputs)) + "\n"
        "result = {s: inflection.underscore(s) for s in INPUTS}\n"
    )


def _differential_snippet(inputs):
    return (
        BASE_ORACLE
        + "\nINPUTS = " + ascii(list(inputs)) + "\n"
        + "EXPECTED = [_base_underscore(s) for s in INPUTS]\n"
        + "import inflection\n"
        + "ACTUAL = [inflection.underscore(s) for s in INPUTS]\n"
        + "result = {\n"
        + "    'checked': len(INPUTS),\n"
        + "    'mismatches': [\n"
        + "        [s, e, a] for s, e, a in zip(INPUTS, EXPECTED, ACTUAL)\n"
        + "        if e != a\n"
        + "    ],\n"
        + "}\n"
    )


def _generated_inputs():
    rng = random.Random(9001)
    inputs = ["", "_", "-", "NASARocket", "HTMLTidy", "already_snake"]
    while len(inputs) < 300:
        text = "".join(rng.choice(PIECES) for _ in range(rng.randint(1, 6)))
        if text not in inputs:
            inputs.append(text)
    return inputs


def test_underscore_contract_example():
    expected = {"NASARocket": "nasa_rocket"}
    r = run_python(_underscore_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_underscore_camel_and_acronym_inputs_unchanged():
    expected = {
        "NASARocketLaunch": "nasa_rocket_launch",
        "DeviceType": "device_type",
        "HTMLTidyGenerator": "html_tidy_generator",
        "FreeBSD": "free_bsd",
        "IOError": "io_error",
        "HTML": "html",
        "Area51Controller": "area51_controller",
        "HTTPServer-Error": "http_server_error",
        "NASA rocket launch": "nasa rocket launch",
        "read the HTTP spec": "read the http spec",
        "HELLO WORLD": "hello world",
        "x-men": "x_men",
    }
    r = run_python(_underscore_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_underscore_generated_inputs_match_base():
    inputs = _generated_inputs()
    r = run_python(_differential_snippet(inputs), timeout=30.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {"checked": len(inputs), "mismatches": []}
