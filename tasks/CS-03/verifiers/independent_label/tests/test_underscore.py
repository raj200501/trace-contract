import re

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_underscore_example": ["R-underscore-unchanged"],
    "test_underscore_matches_base": ["R-underscore-unchanged"],
}

# Oracle: the base-commit underscore, copied from the snapshot (inflection/__init__.py).


def _base_underscore(word):
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)
    word = re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)
    word = word.replace("-", "_")
    return word.lower()


def test_underscore_example():
    r = run_python("import inflection\nresult = inflection.underscore('NASARocket')")
    assert r.ok, r
    assert r.value == _base_underscore("NASARocket")
    assert r.value == "nasa_rocket"


def test_underscore_matches_base():
    inputs = [
        "DeviceType", "IOError", "NASARocket", "device-type", "HTTPServerError", "fancyCategory",
        "already_snake", "ABC", "a1B2", "x-men", "RawScaledScorer", "", "Hello World", "9Lives",
        "HELLO WORLD",
    ]
    expected = [_base_underscore(w) for w in inputs]
    snippet = "import inflection\nresult = [inflection.underscore(w) for w in " + repr(inputs) + "]"
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == expected
