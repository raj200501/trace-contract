"""Hidden behavioural tests for CS-03 (condition initial_plain): the change.

titleize() must output every standalone all-caps word of two or more letters
(an acronym such as NASA, HTTP, FBI, AI) exactly as written, wherever it
appears, as long as the input also contains non-uppercase words.  All other
words are still capitalized as before.

The candidate repository is reached only through tc_sandbox.run_python; it is
never imported into this process.

Deliberately NOT checked, because the requirements leave them open:
  * inputs with no lowercase word at all ("HELLO WORLD", "HTTP");
  * acronyms glued to other text by underscores, hyphens, camelCase, digits
    or punctuation ("NASA_rocket", "HTMLTidy", "HTML5", "NASA's", "NASA:");
  * acronym strings whose other words are camelCase / snake_case / kebab-case
    or oddly cased ("NASA rocketLaunch", "NASA x-men", "NASA rOCKET").
"""
from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_nasa_rocket_launch_keeps_nasa": ["R1"],
    "test_read_the_http_spec_keeps_http": ["R2"],
    "test_acronym_as_first_word_is_kept": ["R3"],
    "test_acronym_as_middle_word_is_kept": ["R3"],
    "test_acronym_as_last_word_is_kept": ["R3"],
    "test_several_acronyms_in_one_string_are_kept": ["R3"],
    "test_two_letter_and_uncommon_acronyms_are_kept": ["R3"],
    "test_acronyms_kept_alongside_capitalized_words": ["R3"],
    "test_other_words_in_acronym_strings_titleized_as_before": ["R3", "R4"],
}


def _titleize_snippet(inputs):
    """Return a snippet whose ``result`` is [titleize(s) for s in inputs].

    Everything runs inside a function so the snippet does not depend on how
    the sandbox sets up globals/locals.  An exception for one input is turned
    into a marker string so that the other inputs are still reported.
    """
    return (
        "def _run(inputs):\n"
        "    import inflection\n"
        "    out = []\n"
        "    for s in inputs:\n"
        "        try:\n"
        "            out.append(inflection.titleize(s))\n"
        "        except Exception as exc:\n"
        "            out.append('<raised %s: %s>' % (type(exc).__name__, exc))\n"
        "    return out\n"
        "result = _run(" + ascii(list(inputs)) + ")\n"
    )


def _failure(r):
    return "snippet did not run cleanly: %s: %s (timed out: %s)\nstdout:\n%s\nstderr:\n%s" % (
        r.error_type, r.error, r.timed_out, r.stdout, r.stderr)


def test_nasa_rocket_launch_keeps_nasa():
    r = run_python(_titleize_snippet(["NASA rocket launch"]))
    assert r.ok, _failure(r)
    assert r.value == ["NASA Rocket Launch"]


def test_read_the_http_spec_keeps_http():
    r = run_python(_titleize_snippet(["read the HTTP spec"]))
    assert r.ok, _failure(r)
    assert r.value == ["Read The HTTP Spec"]


def test_acronym_as_first_word_is_kept():
    cases = {
        "FBI agents arrived": "FBI Agents Arrived",
        "HTTP is a protocol": "HTTP Is A Protocol",
        "GPU prices fell again": "GPU Prices Fell Again",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_acronym_as_middle_word_is_kept():
    cases = {
        "the FBI agents arrived": "The FBI Agents Arrived",
        "a new GPU driver": "A New GPU Driver",
        "my HTTP client library": "My HTTP Client Library",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_acronym_as_last_word_is_kept():
    cases = {
        "launch by NASA": "Launch By NASA",
        "a letter from the IRS": "A Letter From The IRS",
        "drivers for the GPU": "Drivers For The GPU",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_several_acronyms_in_one_string_are_kept():
    cases = {
        "the FBI and the CIA": "The FBI And The CIA",
        "HTTP and FTP specs": "HTTP And FTP Specs",
        "NASA and ESA plan a mission with JAXA":
            "NASA And ESA Plan A Mission With JAXA",
        "compare TCP UDP and QUIC": "Compare TCP UDP And QUIC",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_two_letter_and_uncommon_acronyms_are_kept():
    # Not only well-known acronyms: any all-caps word of >= 2 letters.
    cases = {
        "an AI model": "An AI Model",
        "made in the UK": "Made In The UK",
        "OK then": "OK Then",
        "the QZX protocol": "The QZX Protocol",
        "notes on the WXYZQV format": "Notes On The WXYZQV Format",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_acronyms_kept_alongside_capitalized_words():
    # The other words are already capitalized (so they are not uppercase).
    cases = {
        "NASA Rocket Launch": "NASA Rocket Launch",
        "Read The HTTP Spec": "Read The HTTP Spec",
        "Launch By NASA": "Launch By NASA",
        "The FBI And The CIA": "The FBI And The CIA",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_other_words_in_acronym_strings_titleized_as_before():
    # Only the all-caps spelling is kept; the same letters written in another
    # case are an ordinary word, and ordinary words (including apostrophe
    # words) are capitalized exactly as before.
    cases = {
        "nasa and NASA": "Nasa And NASA",
        "Nasa is not NASA": "Nasa Is Not NASA",
        "the Cia and the CIA": "The Cia And The CIA",
        "NASA and david's code": "NASA And David's Code",
        "don't trust the CIA": "Don't Trust The CIA",
    }
    r = run_python(_titleize_snippet(cases))
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases
