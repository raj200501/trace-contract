"""Hidden behavioural tests for CS-03 (condition full_plain).

The candidate repository is only reached through ``tc_sandbox``: each check
sends a batch of inputs to one fresh interpreter, applies a public
``inflection`` function to every input there and compares the strings that
come back.

The invariant checks (R2, R5, R6, R7) are differential.  Their expected values
come either from hand-picked cases recorded from the base implementation, or,
for generated inputs, from ``_base_underscore``, ``_base_humanize`` and
``_base_titleize`` below, which are verbatim copies of the functions at the
base commit.  Generated inputs are pure ASCII, where those copies behave
identically on every Python 3 version; non-ASCII text only appears in
hand-picked cases with recorded expected values.
"""
import json
import random
import re
import string

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_titleize_keeps_acronyms_in_user_examples": ["R1"],
    "test_titleize_keeps_acronyms_anywhere_in_a_sentence": ["R1"],
    "test_titleize_keeps_acronyms_beside_words_it_transforms": ["R1"],
    "test_titleize_keeps_all_caps_words_once_input_has_lowercase": ["R1", "R5"],
    "test_titleize_unchanged_for_known_inputs_without_all_caps_words": ["R2"],
    "test_titleize_matches_base_for_generated_inputs_without_all_caps_words": ["R2"],
    "test_titleize_unchanged_for_known_shouted_inputs": ["R5"],
    "test_titleize_matches_base_for_generated_inputs_without_lowercase": ["R5"],
    "test_humanize_unchanged_for_known_inputs": ["R6"],
    "test_humanize_matches_base_for_generated_inputs": ["R6"],
    "test_underscore_unchanged_for_known_inputs": ["R7"],
    "test_underscore_matches_base_for_generated_inputs": ["R7"],
}


# ---------------------------------------------------------------------------
# Base-commit behaviour (verbatim copies of inflection at the base commit).
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Talking to the candidate.
# ---------------------------------------------------------------------------

def _snippet(function_name, inputs):
    """Source that applies inflection.<function_name> to every input."""
    return "\n".join([
        "import json",
        "import inflection",
        "_inputs = json.loads(%r)" % json.dumps(inputs),
        "_function = getattr(inflection, %r)" % function_name,
        "_outputs = []",
        "for _text in _inputs:",
        "    try:",
        "        _value = _function(_text)",
        "    except Exception as _exc:",
        "        _outputs.append({'raised': type(_exc).__name__ + ': ' + str(_exc)})",
        "    else:",
        "        _outputs.append(_value if isinstance(_value, str)",
        "                        else {'returned': repr(_value)})",
        "result = _outputs",
    ]) + "\n"


def _returned(r, inputs):
    """The per-input results of a _snippet run, after sanity checks."""
    assert not r.timed_out, "the candidate code timed out"
    assert r.ok, "the snippet raised %s: %s\nstderr:\n%s" % (
        r.error_type, r.error, (r.stderr or "")[-2000:])
    assert isinstance(r.value, list) and len(r.value) == len(inputs), (
        "unexpected snippet result: %r" % (r.value,))
    return r.value


def _differences(inputs, expected, got, limit=12):
    rows = [
        "    %r -> expected %r, got %r" % (text, want, have)
        for text, want, have in zip(inputs, expected, got)
        if want != have
    ]
    return "%d of %d inputs give a different result:\n%s" % (
        len(rows), len(inputs), "\n".join(rows[:limit]))


# ---------------------------------------------------------------------------
# Deterministic input generators (ASCII only).
# ---------------------------------------------------------------------------

_LOWER = string.ascii_lowercase
_UPPER = string.ascii_uppercase
_PRINTABLE = "".join(chr(code) for code in range(32, 127))
_SEPARATORS = (" ", " ", " ", " ", " ", "_", "_", "-", "  ", ": ", ", ",
               ". ", " - ", "__", "/", " & ")
_SMALL_PLAIN = ("the", "of", "and", "a", "x", "id", "to", "on", "in", "i")
_SMALL_SHOUT = ("THE", "OF", "AND", "A", "X", "ID", "TO", "I", "NASA",
                "HTTP", "API")


def _unique(texts):
    return list(dict.fromkeys(texts))


def _lower_word(rng, low=1, high=8):
    return "".join(rng.choice(_LOWER) for _ in range(rng.randint(low, high)))


def _upper_word(rng, low=1, high=7):
    return "".join(rng.choice(_UPPER) for _ in range(rng.randint(low, high)))


def _capitalised_word(rng):
    return rng.choice(_UPPER) + _lower_word(rng, 1, 7)


def _number(rng):
    return str(rng.choice([rng.randint(0, 9), rng.randint(10, 99),
                           rng.randint(100, 2100)]))


def _join(rng, tokens):
    text = tokens[0]
    for token in tokens[1:]:
        text += rng.choice(_SEPARATORS) + token
    return text


def _decorate(rng, text, suffixes):
    if rng.random() < 0.10:
        text += rng.choice(suffixes)
    if rng.random() < 0.05:
        text = rng.choice(["_", " ", "-"]) + text
    if rng.random() < 0.06:
        text += rng.choice(["!", "?", ".", " ", ":"])
    return text


def _plain_token(rng):
    """A token in which every capital is directly followed by a lowercase."""
    roll = rng.random()
    if roll < 0.30:
        return _lower_word(rng)
    if roll < 0.48:
        return _capitalised_word(rng)
    if roll < 0.62:
        parts = [_capitalised_word(rng) for _ in range(rng.randint(2, 3))]
        if rng.random() < 0.5:
            parts[0] = _lower_word(rng)
        if rng.random() < 0.15:
            parts.append("Id")
        return "".join(parts)
    if roll < 0.72:
        head = rng.choice([_lower_word(rng, 1, 5), _capitalised_word(rng)])
        tail = rng.choice(["", "", _lower_word(rng, 1, 4),
                           _capitalised_word(rng)])
        return head + _number(rng) + tail
    if roll < 0.78:
        return _number(rng) + rng.choice(["", "", "th", "rd", "nd", "px"])
    if roll < 0.86:
        stem = rng.choice([_lower_word(rng, 2, 6), _capitalised_word(rng)])
        return stem + "'" + rng.choice(["s", "t", "re", "ll", "d", "ve"])
    if roll < 0.89:
        return "'" + _lower_word(rng, 1, 5) + rng.choice(["", "'"])
    if roll < 0.91:
        return "(" + _lower_word(rng, 1, 6) + ")"
    return rng.choice(_SMALL_PLAIN)


def _plain_text(rng):
    tokens = [_plain_token(rng) for _ in range(rng.randint(1, 5))]
    return _decorate(rng, _join(rng, tokens), ["_id"])


def _plain_noise(rng):
    """Unstructured text; every capital is followed by a lowercase letter."""
    chars = []
    for _ in range(rng.randint(1, 14)):
        char = rng.choice("abcxyz  ABXZ 019 _-'.:,")
        chars.append(char)
        if char.isupper():
            chars.append(rng.choice("aeiouxyz"))
    return "".join(chars)


def _shout_token(rng):
    """A token without lowercase letters."""
    roll = rng.random()
    if roll < 0.50:
        return _upper_word(rng)
    if roll < 0.60:
        return _number(rng)
    if roll < 0.70:
        return _upper_word(rng, 1, 4) + _number(rng)
    if roll < 0.78:
        return (rng.choice([_upper_word(rng, 1, 3), ""]) + _number(rng)
                + _upper_word(rng, 1, 6))
    if roll < 0.88:
        return (_upper_word(rng, 2, 6) + "'"
                + rng.choice(["S", "T", "RE", "LL", "D"]))
    return rng.choice(_SMALL_SHOUT)


def _shout_text(rng):
    tokens = [_shout_token(rng) for _ in range(rng.randint(1, 5))]
    return _decorate(rng, _join(rng, tokens), ["_ID"])


def _shout_noise(rng):
    return "".join(rng.choice("ABCXYZ  ABQ 019 _-'.:,")
                   for _ in range(rng.randint(1, 14)))


def _mixed_text(rng):
    tokens = [rng.choice([_plain_token, _shout_token])(rng)
              for _ in range(rng.randint(1, 5))]
    return _decorate(rng, _join(rng, tokens), ["_id", "_ID", "_Id", "-id"])


def _identifier(rng):
    parts = []
    for _ in range(rng.randint(1, 4)):
        roll = rng.random()
        if roll < 0.45:
            parts.append(_capitalised_word(rng))
        elif roll < 0.70:
            parts.append(_upper_word(rng, 2, 5))
        elif roll < 0.85:
            parts.append(_lower_word(rng))
        else:
            parts.append(_number(rng))
    return rng.choice(["", "", "", "_", "-"]).join(parts)


def _printable_noise(rng):
    return "".join(rng.choice(_PRINTABLE) for _ in range(rng.randint(0, 16)))


def _caps_followed_by_lowercase(text):
    return all(not char.isupper() or text[index + 1:index + 2].islower()
               for index, char in enumerate(text))


def _assorted_inputs(seed):
    """Varied ASCII inputs for functions that must not change at all."""
    rng = random.Random(seed)
    texts = [""]
    texts += [_plain_text(rng) for _ in range(120)]
    texts += [_shout_text(rng) for _ in range(80)]
    texts += [_mixed_text(rng) for _ in range(120)]
    texts += [_identifier(rng) for _ in range(100)]
    texts += [_printable_noise(rng) for _ in range(60)]
    return _unique(texts)


# ---------------------------------------------------------------------------
# R1: all-caps acronyms are kept when the input also has lowercase letters.
# ---------------------------------------------------------------------------

def test_titleize_keeps_acronyms_in_user_examples():
    cases = [
        ("NASA rocket launch", "NASA Rocket Launch"),
        ("read the HTTP spec", "Read The HTTP Spec"),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_titleize_keeps_acronyms_anywhere_in_a_sentence():
    cases = [
        ("launch by NASA", "Launch By NASA"),
        ("the FBI and the CIA", "The FBI And The CIA"),
        ("an API for the web", "An API For The Web"),
        ("Read the HTTP spec", "Read The HTTP Spec"),
        ("the AI revolution", "The AI Revolution"),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_titleize_keeps_acronyms_beside_words_it_transforms():
    # The other words still get today's treatment (underscores and dashes
    # become spaces, CamelCase is split, "'s" stays lowercase).
    cases = [
        ("rocket_launch by NASA", "Rocket Launch By NASA"),
        ("x-men and the FBI", "X Men And The FBI"),
        ("ActiveRecord for NASA", "Active Record For NASA"),
        ("david's HTTP code", "David's HTTP Code"),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_titleize_keeps_all_caps_words_once_input_has_lowercase():
    # Whether all-caps words are kept depends on the whole input: a single
    # lowercase word is enough, while the fully shouted version is
    # titleized as before (R5).
    cases = [
        ("NASA ROCKET launch", "NASA ROCKET Launch"),
        ("NASA ROCKET LAUNCH", "Nasa Rocket Launch"),
        ("READ THE HTTP spec", "READ THE HTTP Spec"),
        ("READ THE HTTP SPEC", "Read The Http Spec"),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


# ---------------------------------------------------------------------------
# R2: unchanged when every capital is directly followed by a lowercase letter.
# ---------------------------------------------------------------------------

def test_titleize_unchanged_for_known_inputs_without_all_caps_words():
    # Expected values are what the base implementation returns.
    cases = [
        ("man from the boondocks", "Man From The Boondocks"),
        ("x-men: the last stand", "X Men: The Last Stand"),
        ("ActiveRecord", "Active Record"),
        ("raiders_of_the_lost_ark", "Raiders Of The Lost Ark"),
        ("active_record", "Active Record"),
        ("action web service", "Action Web Service"),
        ("Action Web Service", "Action Web Service"),
        ("Action web service", "Action Web Service"),
        ("actionwebservice", "Actionwebservice"),
        ("Actionwebservice", "Actionwebservice"),
        ("david's code", "David's Code"),
        ("David's code", "David's Code"),
        ("david's Code", "David's Code"),
        ("ana índia", "Ana Índia"),
        ("Ana Índia", "Ana Índia"),
        ("author_id", "Author"),
        ("employee_salary", "Employee Salary"),
        ("fancyCategory", "Fancy Category"),
        ("Area51Controller", "Area51 Controller"),
        ("userId", "User"),
        ("the man-eating plant's revenge", "The Man Eating Plant's Revenge"),
        ("", ""),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_titleize_matches_base_for_generated_inputs_without_all_caps_words():
    rng = random.Random(3022)
    texts = [_plain_text(rng) for _ in range(400)]
    texts += [_plain_noise(rng) for _ in range(80)]
    inputs = _unique(texts)
    assert all(_caps_followed_by_lowercase(text) for text in inputs)
    expected = [_base_titleize(text) for text in inputs]
    r = run_python(_snippet("titleize", inputs), timeout=60.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


# ---------------------------------------------------------------------------
# R5: unchanged when the input has no lowercase letters at all.
# ---------------------------------------------------------------------------

def test_titleize_unchanged_for_known_shouted_inputs():
    # Expected values are what the base implementation returns.
    cases = [
        ("HELLO WORLD", "Hello World"),
        ("NASA ROCKET LAUNCH", "Nasa Rocket Launch"),
        ("READ THE HTTP SPEC", "Read The Http Spec"),
        ("SCREAMING_SNAKE_CASE", "Screaming Snake Case"),
        ("X-MEN: THE LAST STAND", "X Men: The Last Stand"),
        ("DON'T PANIC", "Don't Panic"),
        ("HTTP", "Http"),
        ("USER_ID", "User"),
        ("TOP 10 LIST", "Top 10 List"),
    ]
    inputs = [text for text, _ in cases]
    expected = [title for _, title in cases]
    r = run_python(_snippet("titleize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_titleize_matches_base_for_generated_inputs_without_lowercase():
    rng = random.Random(5005)
    texts = [_shout_text(rng) for _ in range(300)]
    texts += [_shout_noise(rng) for _ in range(60)]
    inputs = _unique(texts)
    assert not any(char.islower() for text in inputs for char in text)
    expected = [_base_titleize(text) for text in inputs]
    r = run_python(_snippet("titleize", inputs), timeout=60.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


# ---------------------------------------------------------------------------
# R6: humanize() is unchanged.
# ---------------------------------------------------------------------------

def test_humanize_unchanged_for_known_inputs():
    # Expected values are what the base implementation returns.
    cases = [
        ("employee_salary", "Employee salary"),
        ("employee_id", "Employee"),
        ("author_id", "Author"),
        ("underground", "Underground"),
        ("NASA_rocket_launch", "Nasa rocket launch"),
        ("read the HTTP spec", "Read the http spec"),
        ("NASA rocket launch", "Nasa rocket launch"),
        ("HTTPRequest", "Httprequest"),
        ("ActiveRecord", "Activerecord"),
        ("HELLO_WORLD", "Hello world"),
        ("employee_ID", "Employee id"),
        ("user_Id", "User id"),
        ("Mixed_Case_Words", "Mixed case words"),
        ("x-men", "X-men"),
        ("_id", ""),
        ("", ""),
    ]
    inputs = [text for text, _ in cases]
    expected = [human for _, human in cases]
    r = run_python(_snippet("humanize", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_humanize_matches_base_for_generated_inputs():
    inputs = _assorted_inputs(6006)
    expected = [_base_humanize(text) for text in inputs]
    r = run_python(_snippet("humanize", inputs), timeout=60.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


# ---------------------------------------------------------------------------
# R7: underscore() is unchanged.
# ---------------------------------------------------------------------------

def test_underscore_unchanged_for_known_inputs():
    # Expected values are what the base implementation returns.
    cases = [
        ("NASARocket", "nasa_rocket"),
        ("DeviceType", "device_type"),
        ("HTMLTidy", "html_tidy"),
        ("HTMLTidyGenerator", "html_tidy_generator"),
        ("FreeBSD", "free_bsd"),
        ("HTML", "html"),
        ("Area51Controller", "area51_controller"),
        ("IOError", "io_error"),
        ("MP3Player", "mp3_player"),
        ("ABC123Def-ghi", "abc123_def_ghi"),
        ("x-men", "x_men"),
        ("NASA rocket launch", "nasa rocket launch"),
        ("read the HTTP spec", "read the http spec"),
        ("Product", "product"),
        ("SpecialGuest", "special_guest"),
        ("already_snake_case", "already_snake_case"),
        ("", ""),
    ]
    inputs = [text for text, _ in cases]
    expected = [snake for _, snake in cases]
    r = run_python(_snippet("underscore", inputs), timeout=20.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)


def test_underscore_matches_base_for_generated_inputs():
    inputs = _assorted_inputs(7007)
    expected = [_base_underscore(text) for text in inputs]
    r = run_python(_snippet("underscore", inputs), timeout=60.0)
    got = _returned(r, inputs)
    assert got == expected, _differences(inputs, expected, got)
