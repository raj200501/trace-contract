"""Reference checks for R-all-caps-input.

If the entire input is uppercase, ``titleize`` behaves as at the base commit
(contract example: 'HELLO WORLD' -> 'Hello World').  In particular all-caps
words are NOT kept as acronyms when there is no lowercase letter anywhere in
the input.

Every input used here contains at least one uppercase ASCII letter and no
lowercase letter, and every whitespace-separated chunk contains letters, so
the input is uppercase under any reasonable reading ("no lowercase letters",
``str.isupper()``, ``s == s.upper()`` or "every word is uppercase").

Expected values are the base-commit outputs: hand-derived values for the
curated cases, and for generated inputs a verbatim copy of the base-commit
``titleize`` (with its ``humanize``/``underscore`` helpers) evaluated in the
sandbox before the candidate package is imported.
"""
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_titleize_all_caps_contract_example": ["R-all-caps-input"],
    "test_titleize_all_caps_input_does_not_keep_capitals": [
        "R-all-caps-input"
    ],
    "test_titleize_all_caps_with_separators_matches_base": [
        "R-all-caps-input"
    ],
    "test_titleize_all_caps_generated_inputs_match_base": [
        "R-all-caps-input"
    ],
}

# Verbatim behaviour of inflection.underscore / humanize / titleize at the
# base commit.
BASE_ORACLE = r'''
import re as _re


def _base_underscore(word):
    word = _re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)
    word = _re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)
    word = word.replace("-", "_")
    return word.lower()


def _base_humanize(word):
    word = _re.sub(r"_id$", "", word)
    word = word.replace('_', ' ')
    word = _re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = _re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word


def _base_titleize(word):
    return _re.sub(
        r"\b('?\w)",
        lambda match: match.group(1).capitalize(),
        _base_humanize(_base_underscore(word)).title()
    )
'''

CAPS_WORDS = (
    "HELLO", "WORLD", "NASA", "ROCKET", "LAUNCH", "HTTP", "API", "SPEC",
    "THE", "OF", "UK", "AI", "MEN", "DON'T", "IT'S", "DEVIL'S", "EMPLOYEE",
    "ID", "SCREAMING", "SNAKE", "CASE", "JSON", "READ",
)

SEPARATORS = (" ", " ", " ", "_", "-", ", ", ": ")


def _titleize_snippet(inputs):
    return (
        "import inflection\n"
        "INPUTS = " + ascii(list(inputs)) + "\n"
        "result = {s: inflection.titleize(s) for s in INPUTS}\n"
    )


def _differential_snippet(inputs):
    return (
        BASE_ORACLE
        + "\nINPUTS = " + ascii(list(inputs)) + "\n"
        + "EXPECTED = [_base_titleize(s) for s in INPUTS]\n"
        + "import inflection\n"
        + "ACTUAL = [inflection.titleize(s) for s in INPUTS]\n"
        + "result = {\n"
        + "    'checked': len(INPUTS),\n"
        + "    'mismatches': [\n"
        + "        [s, e, a] for s, e, a in zip(INPUTS, EXPECTED, ACTUAL)\n"
        + "        if e != a\n"
        + "    ],\n"
        + "}\n"
    )


def _is_entirely_uppercase(text):
    return (
        any(c.isupper() for c in text)
        and not any(c.islower() for c in text)
    )


def _generated_all_caps_inputs():
    rng = random.Random(4242)
    inputs = []
    while len(inputs) < 150:
        text = rng.choice(CAPS_WORDS)
        for _ in range(rng.randint(0, 4)):
            text += rng.choice(SEPARATORS) + rng.choice(CAPS_WORDS)
        if rng.random() < 0.15:
            text += "_ID"
        if text not in inputs:
            inputs.append(text)
    return inputs


def test_titleize_all_caps_contract_example():
    expected = {"HELLO WORLD": "Hello World"}
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_all_caps_input_does_not_keep_capitals():
    # The fully-uppercase versions of the acronym examples are titleized as
    # at the base commit, i.e. nothing is kept as an acronym.
    expected = {
        "NASA ROCKET LAUNCH": "Nasa Rocket Launch",
        "READ THE HTTP SPEC": "Read The Http Spec",
        "THE NASA ESA PARTNERSHIP": "The Nasa Esa Partnership",
        "HTTP API": "Http Api",
        "NASA": "Nasa",
        "UK": "Uk",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_all_caps_with_separators_matches_base():
    # Base-commit outputs for uppercase inputs with underscores, hyphens,
    # punctuation, apostrophes and a trailing "_ID".
    expected = {
        "SCREAMING_SNAKE_CASE": "Screaming Snake Case",
        "HELLO-WORLD": "Hello World",
        "HELLO, WORLD": "Hello, World",
        "X-MEN: THE LAST STAND": "X Men: The Last Stand",
        "EMPLOYEE_ID": "Employee",
        "DON'T PANIC": "Don't Panic",
        "THE DEVIL'S ADVOCATE": "The Devil's Advocate",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_all_caps_generated_inputs_match_base():
    inputs = _generated_all_caps_inputs()
    assert all(_is_entirely_uppercase(text) for text in inputs)
    r = run_python(_differential_snippet(inputs), timeout=30.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == {"checked": len(inputs), "mismatches": []}
