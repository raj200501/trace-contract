from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_acronym_examples": ["R-acronym"],
    "test_acronym_position": ["R-acronym"],
    "test_acronym_two_letters": ["R-acronym"],
}


def _titleize_many(words):
    snippet = "import inflection\nresult = [inflection.titleize(w) for w in " + repr(list(words)) + "]"
    return run_python(snippet)


def test_acronym_examples():
    r = _titleize_many(["NASA rocket launch", "read the HTTP spec"])
    assert r.ok, r
    assert r.value == ["NASA Rocket Launch", "Read The HTTP Spec"]


def test_acronym_position():
    r = _titleize_many(["launch NASA now", "the rocket is NASA"])
    assert r.ok, r
    assert r.value == ["Launch NASA Now", "The Rocket Is NASA"]


def test_acronym_two_letters():
    r = _titleize_many(["the OS kernel", "read the HTTP and XML specs"])
    assert r.ok, r
    assert r.value == ["The OS Kernel", "Read The HTTP And XML Specs"]
