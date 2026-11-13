# Hidden behavioural tests for CS-03 (condition: llm_freeform).
#
# Requirement labels (inferred from the whole session, including the
# coordinator's later refinements):
#   B1  titleize() keeps words written in capitals (acronyms such as NASA,
#       HTTP) exactly as written when the input also contains lowercase
#       letters; the other words are capitalized as usual.
#       titleize('NASA rocket launch') == 'NASA Rocket Launch'
#       titleize('read the HTTP spec') == 'Read The HTTP Spec'
#   B2  The same holds when the acronym is joined to other words by
#       titleize's other word separators (underscores, hyphens).
#   B3  Input without lowercase letters (e.g. a shouted heading) is
#       titleized exactly as before: titleize('HELLO WORLD') == 'Hello World'.
#   B4  Next to acronyms, the remaining words keep titleize's normal
#       treatment (CamelCase split, underscores/hyphens become spaces,
#       possessive "'s" stays lowercase).
#   B5  Input that contains no all-caps words is titleized exactly as before
#       (documented/tested examples, trailing "_id" dropped, and a seeded
#       sample compared with the original implementation's output).
#   B6  humanize() behaves exactly as before.
#   B7  underscore() behaves exactly as before.
#
# Expected values for "as before" checks were produced by running the
# repository at its base commit.

import json

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_titleize_keeps_acronyms_in_reported_examples": ["B1"],
    "test_titleize_keeps_acronyms_at_any_position": ["B1"],
    "test_titleize_keeps_acronyms_next_to_punctuation": ["B1"],
    "test_titleize_keeps_acronyms_joined_by_underscores_or_hyphens": ["B2"],
    "test_titleize_other_words_still_titleized_next_to_acronyms": ["B1", "B4"],
    "test_titleize_all_uppercase_input_titleized_as_before": ["B3"],
    "test_titleize_all_uppercase_input_matches_original_on_many_inputs": ["B3"],
    "test_titleize_existing_examples_unchanged": ["B5"],
    "test_titleize_still_drops_trailing_id": ["B5"],
    "test_titleize_input_without_capital_words_matches_original": ["B5"],
}


def _apply_snippet(func_name, inputs):
    """Source for run_python: apply inflection.<func_name> to each input."""
    return "\n".join([
        "import json",
        "import inflection",
        "func = getattr(inflection, " + repr(func_name) + ")",
        "outputs = []",
        "for text in json.loads(" + repr(json.dumps(list(inputs))) + "):",
        "    try:",
        "        outputs.append(func(text))",
        "    except Exception as exc:",
        "        outputs.append('<raised ' + type(exc).__name__ + '>')",
        "result = outputs",
    ]) + "\n"


def _mismatches(inputs, got, expected):
    if not isinstance(got, list) or len(got) != len(expected):
        return "unexpected result: %r" % (got,)
    rows = [
        "%r -> got %r, expected %r" % (text, out, exp)
        for text, out, exp in zip(inputs, got, expected)
        if out != exp
    ]
    return "mismatches:\n" + "\n".join(rows)


def _failure(r):
    return "snippet failed: %s: %s\n%s" % (r.error_type, r.error, r.stderr)


# --------------------------------------------------------------------------
# B1: acronyms are kept in mixed-case input
# --------------------------------------------------------------------------

def test_titleize_keeps_acronyms_in_reported_examples():
    cases = [
        ("NASA rocket launch", "NASA Rocket Launch"),
        ("read the HTTP spec", "Read The HTTP Spec"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


def test_titleize_keeps_acronyms_at_any_position():
    cases = [
        ("rocket NASA", "Rocket NASA"),
        ("the USA and the UK", "The USA And The UK"),
        ("an API for JSON and XML data", "An API For JSON And XML Data"),
        ("my CPU is hot", "My CPU Is Hot"),
        ("Read The HTTP Spec", "Read The HTTP Spec"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


def test_titleize_keeps_acronyms_next_to_punctuation():
    cases = [
        ("the NASA, ESA and JAXA missions", "The NASA, ESA And JAXA Missions"),
        ("a guide (PDF)", "A Guide (PDF)"),
        ("is it HTTP? yes", "Is It HTTP? Yes"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# --------------------------------------------------------------------------
# B2: acronyms joined by underscores / hyphens
# --------------------------------------------------------------------------

def test_titleize_keeps_acronyms_joined_by_underscores_or_hyphens():
    cases = [
        ("NASA_rocket_launch", "NASA Rocket Launch"),
        ("read_the_HTTP_spec", "Read The HTTP Spec"),
        ("NASA-backed plan", "NASA Backed Plan"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# --------------------------------------------------------------------------
# B4: the rest of the title is still handled as before
# --------------------------------------------------------------------------

def test_titleize_other_words_still_titleized_next_to_acronyms():
    cases = [
        ("the NASA guide to david's code", "The NASA Guide To David's Code"),
        ("ActiveRecord and the HTTP spec", "Active Record And The HTTP Spec"),
        ("raiders_of_the_lost_ark by NASA", "Raiders Of The Lost Ark By NASA"),
        ("x-men: the NASA files", "X Men: The NASA Files"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# --------------------------------------------------------------------------
# B3: input without lowercase letters is titleized as before
# --------------------------------------------------------------------------

def test_titleize_all_uppercase_input_titleized_as_before():
    cases = [
        ("HELLO WORLD", "Hello World"),
        ("SCREAMING_SNAKE_CASE", "Screaming Snake Case"),
        ("NASA ROCKET LAUNCH", "Nasa Rocket Launch"),
        ("READ THE HTTP SPEC", "Read The Http Spec"),
        ("NASA", "Nasa"),
        ("DON'T PANIC", "Don't Panic"),
        ("X-MEN: THE LAST STAND", "X Men: The Last Stand"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# Seeded sample of all-uppercase inputs with the base commit's titleize output.
ALL_UPPERCASE_TITLEIZED = [
    ('ACTIVE_THE_PLAN TO', 'Active The Plan To'),
    ("LAUNCH'S FREE", "Launch's Free"),
    ('MAP DATA_NAME_TYPE', 'Map Data Name Type'),
    ('A ANA WITH-SERVICE SKY', 'A Ana With Service Sky'),
    ('RAIDERS', 'Raiders'),
    ('OVER A: TO', 'Over A: To'),
    ('LAST SERVICE-SPACE SKY', 'Last Service Space Sky'),
    ('OVER WEB_BIG_ACTIVE-SPACE', 'Over Web Big Active Space'),
    ('ACTION_RECORD MAN_STAND_LAUNCH', 'Action Record Man Stand Launch'),
    ('DATA', 'Data'),
    ('FROM-WEB NAME PLAN', 'From Web Name Plan'),
    ('FROM_WEB-ARK_NAME', 'From Web Ark Name'),
    ('USER_TIDY LOST', 'User Tidy Lost'),
    ('LAST', 'Last'),
    ('FREE_LAST TO_UNDER', 'Free Last To Under'),
    ('USER RECORD', 'User Record'),
    ('RAIDERS LAST DAVID', 'Raiders Last David'),
    ('OVER WITH MAP-SPEC PLAN', 'Over With Map Spec Plan'),
    ('A MAN_RAIDERS', 'A Man Raiders'),
    ('REPORT_UNDER', 'Report Under'),
    ('USER_MAN-SPEC_ARK NAME', 'User Man Spec Ark Name'),
    ('GUIDE_RAIDERS-FROM TIDY_STATION', 'Guide Raiders From Tidy Station'),
    ('STATION_WITH DATA_I-WITH', 'Station With Data I With'),
    ('LOST_BOONDOCKS_MAP', 'Lost Boondocks Map'),
    ('THE USER_SKY-RAIDERS THE', 'The User Sky Raiders The'),
    ('GUIDE CODE ROCKET ROCKET_TYPE', 'Guide Code Rocket Rocket Type'),
    ('RECORD_MAN THE_THE', 'Record Man The The'),
    ('THE_OVER_SKY', 'The Over Sky'),
    ('TIDY-TYPE AND_MAN_ROCKET', 'Tidy Type And Man Rocket'),
    ('SERVICE GUIDE_TYPE_READ', 'Service Guide Type Read'),
]


def test_titleize_all_uppercase_input_matches_original_on_many_inputs():
    inputs = [c[0] for c in ALL_UPPERCASE_TITLEIZED]
    expected = [c[1] for c in ALL_UPPERCASE_TITLEIZED]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# --------------------------------------------------------------------------
# B5: input without all-caps words is titleized as before
# --------------------------------------------------------------------------

def test_titleize_existing_examples_unchanged():
    cases = [
        # documented examples
        ("man from the boondocks", "Man From The Boondocks"),
        ("x-men: the last stand", "X Men: The Last Stand"),
        ("TheManWithoutAPast", "The Man Without A Past"),
        ("raiders_of_the_lost_ark", "Raiders Of The Lost Ark"),
        # the repository's existing titleize table
        ("active_record", "Active Record"),
        ("ActiveRecord", "Active Record"),
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
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


def test_titleize_still_drops_trailing_id():
    cases = [
        ("employee_id", "Employee"),
        ("author_id", "Author"),
    ]
    inputs = [c[0] for c in cases]
    expected = [c[1] for c in cases]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# Seeded sample of inputs without any all-caps word (lowercase, Capitalized
# and camelCase words, " ", "_" and "-" separators, possessive "'s") with the
# base commit's titleize output.
NO_CAPITAL_WORDS_TITLEIZED = [
    ('launch x', 'Launch X'),
    ('Raiders And_stand Launch Report', 'Raiders And Stand Launch Report'),
    ("from-And's", "From And's"),
    ("tidy's i big's spec", "Tidy's I Big's Spec"),
    ("User's plan", "User's Plan"),
    ('Name', 'Name'),
    ('guide type from launch_under', 'Guide Type From Launch Under'),
    ('map', 'Map'),
    ("record's and user man Read", "Record's And User Man Read"),
    ('a from Web-code-Sky', 'A From Web Code Sky'),
    ('ana', 'Ana'),
    ('Raiders-last free guide lost', 'Raiders Last Free Guide Lost'),
    ('aUnder', 'A Under'),
    ('Tidy', 'Tidy'),
    ("OverRecord raiders-Service's read", "Over Record Raiders Service's Read"),
    ('Code rocket', 'Code Rocket'),
    ('tidy', 'Tidy'),
    ('name-man', 'Name Man'),
    ('and-a active under-Guide', 'And A Active Under Guide'),
    ('Launch', 'Launch'),
    ('Lost i launch', 'Lost I Launch'),
    ('david Last', 'David Last'),
    ('david-david tidy_type Read', 'David David Tidy Type Read'),
    ('launch_tidy Boondocks the the', 'Launch Tidy Boondocks The The'),
    ('activeNet', 'Active Net'),
    ('free-and a', 'Free And A'),
    ('Launch moon with', 'Launch Moon With'),
    ('i-a Map_Sky', 'I A Map Sky'),
    ('Name-net', 'Name Net'),
    ('netLost', 'Net Lost'),
    ('launch', 'Launch'),
    ('Read action Big', 'Read Action Big'),
    ('Type i', 'Type I'),
    ('free', 'Free'),
    ('raiders name', 'Raiders Name'),
    ("blue's", "Blue's"),
    ("data-of_moon-ReadBig's", "Data Of Moon Read Big's"),
    ("Net's", "Net's"),
    ("SkyRocket to-men's", "Sky Rocket To Men's"),
    ('lost data to', 'Lost Data To'),
]


def test_titleize_input_without_capital_words_matches_original():
    inputs = [c[0] for c in NO_CAPITAL_WORDS_TITLEIZED]
    expected = [c[1] for c in NO_CAPITAL_WORDS_TITLEIZED]
    r = run_python(_apply_snippet("titleize", inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)
