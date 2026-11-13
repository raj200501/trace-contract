"""Reference checks for R-acronym.

In input that also contains lowercase letters, ``titleize`` keeps all-caps
words of two or more letters unchanged, while the remaining (lowercase)
words are capitalised as titleize always did (contract examples:
'NASA rocket launch' -> 'NASA Rocket Launch',
'read the HTTP spec' -> 'Read The HTTP Spec').

Every input used here is made only of single-space separated words that are
either entirely lowercase ASCII letters or entirely uppercase ASCII letters
(at least two of them).  Single capital letters, CamelCase, digits,
punctuation, underscores/hyphens and mixed-case words are deliberately
avoided because the contract does not specify how they are treated.
"""
import random

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_titleize_contract_acronym_examples": ["R-acronym"],
    "test_titleize_keeps_acronym_at_start_middle_and_end": ["R-acronym"],
    "test_titleize_keeps_several_and_adjacent_acronyms": ["R-acronym"],
    "test_titleize_keeps_two_letter_and_non_dictionary_all_caps_words": [
        "R-acronym"
    ],
    "test_titleize_acronym_rule_on_generated_inputs": ["R-acronym"],
}

LOWER_WORDS = (
    "rocket", "launch", "read", "the", "spec", "mission", "data", "report",
    "from", "and", "with", "new", "system", "update", "about", "review",
    "team", "guide", "of", "to", "in", "on", "an", "is", "files", "server",
    "model", "notes", "please", "now",
)

UPPER_WORDS = (
    "NASA", "HTTP", "ESA", "API", "JSON", "SQL", "HTML", "CPU", "FBI", "XML",
    "URL", "UK", "US", "AI", "IO", "OK", "ABC", "XYZ", "QWERTY", "VERY",
    "STOP", "UNESCO", "NATO", "TODO", "FAQ",
)


def _titleize_snippet(inputs):
    return (
        "import inflection\n"
        "INPUTS = " + ascii(list(inputs)) + "\n"
        "result = {s: inflection.titleize(s) for s in INPUTS}\n"
    )


def _expected_titleized(text):
    # All-caps words are kept, lowercase words get their first letter
    # capitalised (as in the contract examples).
    return " ".join(
        word if word.isupper() else word[0].upper() + word[1:]
        for word in text.split(" ")
    )


def _generated_mixed_inputs():
    rng = random.Random(20261113)
    inputs = []
    while len(inputs) < 150:
        words = [
            rng.choice(LOWER_WORDS) if rng.random() < 0.5
            else rng.choice(UPPER_WORDS)
            for _ in range(rng.randint(2, 7))
        ]
        if not any(w.islower() for w in words):
            continue
        if not any(w.isupper() for w in words):
            continue
        text = " ".join(words)
        if text not in inputs:
            inputs.append(text)
    return inputs


def test_titleize_contract_acronym_examples():
    expected = {
        "NASA rocket launch": "NASA Rocket Launch",
        "read the HTTP spec": "Read The HTTP Spec",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_keeps_acronym_at_start_middle_and_end():
    expected = {
        "HTTP server notes": "HTTP Server Notes",
        "UNESCO world heritage": "UNESCO World Heritage",
        "notes on HTTP servers": "Notes On HTTP Servers",
        "images from NASA": "Images From NASA",
        "read the docs for the API": "Read The Docs For The API",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_keeps_several_and_adjacent_acronyms():
    expected = {
        "NASA and ESA missions": "NASA And ESA Missions",
        "the NASA ESA partnership": "The NASA ESA Partnership",
        "HTTP API design guide": "HTTP API Design Guide",
        "NASA ESA JAXA joint mission": "NASA ESA JAXA Joint Mission",
        "use JSON over HTTP with SQL": "Use JSON Over HTTP With SQL",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_keeps_two_letter_and_non_dictionary_all_caps_words():
    expected = {
        "the UK and US markets": "The UK And US Markets",
        "an AI model": "An AI Model",
        "this is VERY important": "This Is VERY Important",
        "press ABC then XYZ": "Press ABC Then XYZ",
        "the QWERTY layout": "The QWERTY Layout",
    }
    r = run_python(_titleize_snippet(expected), timeout=20.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected


def test_titleize_acronym_rule_on_generated_inputs():
    inputs = _generated_mixed_inputs()
    expected = {text: _expected_titleized(text) for text in inputs}
    r = run_python(_titleize_snippet(inputs), timeout=30.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value == expected
