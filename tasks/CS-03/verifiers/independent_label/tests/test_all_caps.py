import re

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_all_caps_example": ["R-all-caps-input", "R-acronym"],
    "test_all_caps_matches_base": ["R-all-caps-input", "R-acronym"],
}

# Oracle: the base-commit titleize, copied from the snapshot (inflection/__init__.py).


def _base_underscore(word):
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)
    word = re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)
    word = word.replace("-", "_")
    return word.lower()


def _base_humanize(word):
    word = re.sub(r"_id$", "", word)
    word = word.replace('_', ' ')
    word = re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word


def _base_titleize(word):
    return re.sub(
        r"\b('?\w)",
        lambda match: match.group(1).capitalize(),
        _base_humanize(_base_underscore(word)).title()
    )


# The carve-out is a boundary: an all-caps word is kept as an acronym only when the input
# also contains lowercase letters. The mixed-case input below is the other side of that
# boundary (R-acronym); without it these checks would pass on the unchanged base.
MIXED_INPUT = "NASA rocket launch"
MIXED_EXPECTED = "NASA Rocket Launch"


def test_all_caps_example():
    r = run_python(
        "import inflection\n"
        "result = [inflection.titleize('HELLO WORLD'), inflection.titleize('NASA rocket launch')]"
    )
    assert r.ok, r
    assert r.value == ["Hello World", "NASA Rocket Launch"]


def test_all_caps_matches_base():
    inputs = ["NASA", "HELLO WORLD", "HTTP SPEC", "NASA ROCKET LAUNCH", "API_KEY_VALUE", "XML",
              "OS KERNEL", "AI TOOLS", "I AM HERE", "X"]
    expected = [_base_titleize(w) for w in inputs] + [MIXED_EXPECTED]
    snippet = ("import inflection\nresult = [inflection.titleize(w) for w in "
               + repr(inputs + [MIXED_INPUT]) + "]")
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == expected
