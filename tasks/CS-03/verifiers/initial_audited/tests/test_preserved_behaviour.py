"""Hidden behavioural tests for CS-03 (condition initial_audited): invariants.

Apart from keeping all-caps acronyms in titleize(), nothing may change:
titleize() must give the base output for inputs without an all-caps word, and
every other public function of the package must behave exactly as at the base
commit (also for inputs that contain all-caps words), with the expectations of
the original test-suite still holding.

The candidate repository is reached only through tc_sandbox.run_python.  The
base implementation of the package is embedded below (docstrings removed,
code unchanged) and executed inside the same sandboxed interpreter as the
candidate, as the oracle for the differential tests.
"""
import random
import string

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_plain_words_capitalized_without_small_word_exceptions": ["R4"],
    "test_original_titleize_examples_unchanged": ["R4", "R5"],
    "test_titleize_matches_base_on_inputs_without_acronyms": ["R4"],
    "test_trailing_id_suffix_dropped_as_before": ["R4"],
    "test_other_functions_match_base_including_all_caps_inputs": ["R5"],
    "test_original_suite_expectations_for_other_functions_hold": ["R5"],
}

# inflection/__init__.py at the base commit, docstrings removed.
BASE_INFLECTION_SOURCE = r'''
import re
import typing
import unicodedata

__version__ = '0.5.1'

RegexReplaceList = typing.List[typing.Tuple[str, str]]

PLURALS: RegexReplaceList = [
    (r"(?i)(quiz)$", r'\1zes'),
    (r"(?i)^(oxen)$", r'\1'),
    (r"(?i)^(ox)$", r'\1en'),
    (r"(?i)(m|l)ice$", r'\1ice'),
    (r"(?i)(m|l)ouse$", r'\1ice'),
    (r"(?i)(passer)s?by$", r'\1sby'),
    (r"(?i)(matr|vert|ind)(?:ix|ex)$", r'\1ices'),
    (r"(?i)(x|ch|ss|sh)$", r'\1es'),
    (r"(?i)([^aeiouy]|qu)y$", r'\1ies'),
    (r"(?i)(hive)$", r'\1s'),
    (r"(?i)([lr])f$", r'\1ves'),
    (r"(?i)([^f])fe$", r'\1ves'),
    (r"(?i)sis$", 'ses'),
    (r"(?i)([ti])a$", r'\1a'),
    (r"(?i)([ti])um$", r'\1a'),
    (r"(?i)(buffal|potat|tomat)o$", r'\1oes'),
    (r"(?i)(bu)s$", r'\1ses'),
    (r"(?i)(alias|status)$", r'\1es'),
    (r"(?i)(octop|vir)i$", r'\1i'),
    (r"(?i)(octop|vir)us$", r'\1i'),
    (r"(?i)^(ax|test)is$", r'\1es'),
    (r"(?i)s$", 's'),
    (r"$", 's'),
]

SINGULARS: RegexReplaceList = [
    (r"(?i)(database)s$", r'\1'),
    (r"(?i)(quiz)zes$", r'\1'),
    (r"(?i)(matr)ices$", r'\1ix'),
    (r"(?i)(vert|ind)ices$", r'\1ex'),
    (r"(?i)(passer)sby$", r'\1by'),
    (r"(?i)^(ox)en", r'\1'),
    (r"(?i)(alias|status)(es)?$", r'\1'),
    (r"(?i)(octop|vir)(us|i)$", r'\1us'),
    (r"(?i)^(a)x[ie]s$", r'\1xis'),
    (r"(?i)(cris|test)(is|es)$", r'\1is'),
    (r"(?i)(shoe)s$", r'\1'),
    (r"(?i)(o)es$", r'\1'),
    (r"(?i)(bus)(es)?$", r'\1'),
    (r"(?i)(m|l)ice$", r'\1ouse'),
    (r"(?i)(x|ch|ss|sh)es$", r'\1'),
    (r"(?i)(m)ovies$", r'\1ovie'),
    (r"(?i)(s)eries$", r'\1eries'),
    (r"(?i)([^aeiouy]|qu)ies$", r'\1y'),
    (r"(?i)([lr])ves$", r'\1f'),
    (r"(?i)(tive)s$", r'\1'),
    (r"(?i)(hive)s$", r'\1'),
    (r"(?i)([^f])ves$", r'\1fe'),
    (r"(?i)(t)he(sis|ses)$", r"\1hesis"),
    (r"(?i)(s)ynop(sis|ses)$", r"\1ynopsis"),
    (r"(?i)(p)rogno(sis|ses)$", r"\1rognosis"),
    (r"(?i)(p)arenthe(sis|ses)$", r"\1arenthesis"),
    (r"(?i)(d)iagno(sis|ses)$", r"\1iagnosis"),
    (r"(?i)(b)a(sis|ses)$", r"\1asis"),
    (r"(?i)(a)naly(sis|ses)$", r"\1nalysis"),
    (r"(?i)([ti])a$", r'\1um'),
    (r"(?i)(n)ews$", r'\1ews'),
    (r"(?i)(ss)$", r'\1'),
    (r"(?i)s$", ''),
]

UNCOUNTABLES: typing.Set[str] = {
    'equipment',
    'fish',
    'information',
    'jeans',
    'money',
    'rice',
    'series',
    'sheep',
    'species'}

def _irregular(singular: str, plural: str) -> None:
    def caseinsensitive(string: str) -> str:
        return ''.join('[' + char + char.upper() + ']' for char in string)

    if singular[0].upper() == plural[0].upper():
        PLURALS.insert(0, (
            r"(?i)({}){}$".format(singular[0], singular[1:]),
            r'\1' + plural[1:]
        ))
        PLURALS.insert(0, (
            r"(?i)({}){}$".format(plural[0], plural[1:]),
            r'\1' + plural[1:]
        ))
        SINGULARS.insert(0, (
            r"(?i)({}){}$".format(plural[0], plural[1:]),
            r'\1' + singular[1:]
        ))
    else:
        PLURALS.insert(0, (
            r"{}{}$".format(singular[0].upper(),
                            caseinsensitive(singular[1:])),
            plural[0].upper() + plural[1:]
        ))
        PLURALS.insert(0, (
            r"{}{}$".format(singular[0].lower(),
                            caseinsensitive(singular[1:])),
            plural[0].lower() + plural[1:]
        ))
        PLURALS.insert(0, (
            r"{}{}$".format(plural[0].upper(), caseinsensitive(plural[1:])),
            plural[0].upper() + plural[1:]
        ))
        PLURALS.insert(0, (
            r"{}{}$".format(plural[0].lower(), caseinsensitive(plural[1:])),
            plural[0].lower() + plural[1:]
        ))
        SINGULARS.insert(0, (
            r"{}{}$".format(plural[0].upper(), caseinsensitive(plural[1:])),
            singular[0].upper() + singular[1:]
        ))
        SINGULARS.insert(0, (
            r"{}{}$".format(plural[0].lower(), caseinsensitive(plural[1:])),
            singular[0].lower() + singular[1:]
        ))

def camelize(string: str, uppercase_first_letter: bool = True) -> str:
    if uppercase_first_letter:
        return re.sub(r"(?:^|_)(.)", lambda m: m.group(1).upper(), string)
    else:
        return string[0].lower() + camelize(string)[1:]

def dasherize(word: str) -> str:
    return word.replace('_', '-')

def humanize(word: str) -> str:
    word = re.sub(r"_id$", "", word)
    word = word.replace('_', ' ')
    word = re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word

def ordinal(number: int) -> str:
    number = abs(int(number))
    if number % 100 in (11, 12, 13):
        return "th"
    else:
        return {
            1: "st",
            2: "nd",
            3: "rd",
        }.get(number % 10, "th")

def ordinalize(number: int) -> str:
    return "{}{}".format(number, ordinal(number))

def parameterize(string: str, separator: str = '-') -> str:
    string = transliterate(string)
    # Turn unwanted chars into the separator
    string = re.sub(r"(?i)[^a-z0-9\-_]+", separator, string)
    if separator:
        re_sep = re.escape(separator)
        # No more than one of the separator in a row.
        string = re.sub(r'%s{2,}' % re_sep, separator, string)
        # Remove leading/trailing separator.
        string = re.sub(r"(?i)^{sep}|{sep}$".format(sep=re_sep), '', string)

    return string.lower()

def pluralize(word: str) -> str:
    if not word or word.lower() in UNCOUNTABLES:
        return word
    else:
        for rule, replacement in PLURALS:
            if re.search(rule, word):
                return re.sub(rule, replacement, word)
        return word

def singularize(word: str) -> str:
    for inflection in UNCOUNTABLES:
        if re.search(r'(?i)\b(%s)\Z' % inflection, word):
            return word

    for rule, replacement in SINGULARS:
        if re.search(rule, word):
            return re.sub(rule, replacement, word)
    return word

def tableize(word: str) -> str:
    return pluralize(underscore(word))

def titleize(word: str) -> str:
    return re.sub(
        r"\b('?\w)",
        lambda match: match.group(1).capitalize(),
        humanize(underscore(word)).title()
    )

def transliterate(string: str) -> str:
    normalized = unicodedata.normalize('NFKD', string)
    return normalized.encode('ascii', 'ignore').decode('ascii')

def underscore(word: str) -> str:
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)
    word = re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)
    word = word.replace("-", "_")
    return word.lower()

_irregular('person', 'people')
_irregular('man', 'men')
_irregular('human', 'humans')
_irregular('child', 'children')
_irregular('sex', 'sexes')
_irregular('move', 'moves')
_irregular('cow', 'kine')
_irregular('zombie', 'zombies')
'''


def _failure(r):
    return "snippet did not run cleanly: %s: %s (timed out: %s)\nstdout:\n%s\nstderr:\n%s" % (
        r.error_type, r.error, r.timed_out, r.stdout, r.stderr)


def _has_adjacent_uppercase(text):
    return any(a.isupper() and b.isupper() for a, b in zip(text, text[1:]))


# --------------------------------------------------------------------------
# titleize on inputs without all-caps acronyms (R4)
# --------------------------------------------------------------------------

_TITLEIZE_SNIPPET = r'''
def _run(inputs):
    import inflection
    out = []
    for s in inputs:
        try:
            out.append(inflection.titleize(s))
        except Exception as exc:
            out.append('<raised %s: %s>' % (type(exc).__name__, exc))
    return out
'''

# Original MIXTURE_TO_TITLEIZED cases plus the examples of the original
# titleize docstring.
ORIGINAL_TITLEIZE_EXAMPLES = {
    "active_record": "Active Record",
    "ActiveRecord": "Active Record",
    "action web service": "Action Web Service",
    "Action Web Service": "Action Web Service",
    "Action web service": "Action Web Service",
    "actionwebservice": "Actionwebservice",
    "Actionwebservice": "Actionwebservice",
    "david's code": "David's Code",
    "David's code": "David's Code",
    "david's Code": "David's Code",
    "ana \xedndia": "Ana \xcdndia",
    "Ana \xcdndia": "Ana \xcdndia",
    "man from the boondocks": "Man From The Boondocks",
    "x-men: the last stand": "X Men: The Last Stand",
    "TheManWithoutAPast": "The Man Without A Past",
    "raiders_of_the_lost_ark": "Raiders Of The Lost Ark",
}

# Inputs without two consecutive uppercase letters, hence without any
# all-caps acronym: titleize must return exactly the base result for them.
_NO_ACRONYM_SAMPLES = [
    # named in the requirements / original tests / original docstring
    "action web service", "Action Web Service", "Action web service",
    "actionwebservice", "Actionwebservice", "ActiveRecord", "active_record",
    "x-men: the last stand", "man from the boondocks",
    "raiders_of_the_lost_ark", "david's code", "David's code",
    "david's Code", "David'S code", "ana \xedndia", "Ana \xcdndia",
    # ordinary words, no small-word exceptions
    "rocket launch", "read the spec", "the", "a", "x", "X",
    "the lord of the rings", "a tale of two cities", "Hello World",
    "hello world",
    # acronym-like words that are not written in capitals
    "Nasa rocket launch", "read the Http spec", "the Fbi and the Cia",
    "Http and Ftp specs", "nasa", "Nasa",
    # camelCase, snake_case, kebab-case, "_id" suffix
    "SpecialGuest", "ApplicationController", "Area51Controller",
    "area51 controller", "device_type", "DeviceType", "Product",
    "employee_id", "author_id", "employee_salary", "EmployeeSalary",
    "camelCase words", "snake_case_words", "kebab-case-words",
    "mixedCase and snake_case", "the_lord-of the rings", "iPhone sales",
    "McDonald farm",
    # punctuation, apostrophes, digits, single capitals
    "o.k. computer", "U.S. army", "don't stop me now", "rock'n'roll",
    "o'neil and o'brien", "'tis the season", "hello, world.",
    "well-known facts", "rock & roll", "question? answer!",
    "slash/separated words", "dot.separated.words", "(parenthesised) words",
    "1st place", "top 10 tips", "plan B", "I am here", "A B C",
    "3d model", "mp3player", "4x4 truck", "covid19 cases",
    # non-ASCII letters
    "caf\xe9 au lait", "S\xe3o Paulo", "\xfcber cool", "na\xefve approach",
    "stra\xdfe",
    # a trailing "_id" is dropped whatever its case and however it is joined
    "authorId", "AuthorId", "author-id", "author_Id", "Author_Id",
    "author-Id", "Author-Id", "EmployeeId", "postAuthorId", "the parentId",
    "the parent-Id", "area51Id", "user_id_number", "userIdNumber",
    "authorIds", "author Id", "valid_id", "_id", "id", "Id", "idea", "squid",
    # empty input, blanks and irregular whitespace
    "", " ", "  leading spaces", "trailing spaces  ", "double  space",
    "tab\tseparated", "  padded  words  ", "123", "42 is the answer", "___",
    "---",
]

_PLAIN_WORDS = [
    "action", "web", "service", "active", "record", "rocket", "launch",
    "read", "the", "spec", "a", "of", "and", "man", "from", "boondocks",
    "last", "stand", "raiders", "lost", "ark", "code", "david's", "o'neil",
    "employee", "salary", "device", "type", "user", "name", "table", "x",
    "men", "lord", "rings", "war", "peace", "nasa", "http", "fbi", "id",
    "author",
]
_NON_ASCII_WORDS = [
    "\xedndia", "caf\xe9", "\xfcber", "na\xefve", "stra\xdfe", "\xe9lan",
]


def _random_texts_without_acronyms(count, seed):
    """Deterministic phrases (spaces, snake_case, kebab-case, camelCase)
    that never contain two consecutive uppercase letters."""
    rng = random.Random(seed)
    texts = []
    while len(texts) < count:
        words = []
        for _ in range(rng.randint(1, 5)):
            if rng.random() < 0.85:
                word = rng.choice(_PLAIN_WORDS)
            else:
                word = rng.choice(_NON_ASCII_WORDS)
            if rng.random() < 0.3:
                word = word[0].upper() + word[1:]
            words.append(word)
        text = words[0]
        for word in words[1:]:
            sep = rng.choice([" ", " ", " ", "_", "-", ""])
            if sep == "":
                # camelCase join, only between plain ASCII letters
                if (text[-1] in string.ascii_lowercase
                        and word[0] in string.ascii_letters):
                    word = word[0].upper() + word[1:]
                else:
                    sep = " "
            text += sep + word
        if not _has_adjacent_uppercase(text):
            texts.append(text)
    return texts


_TITLEIZE_DIFF_SNIPPET = r'''
def _run(base_source, inputs):
    import inflection
    base = {'__name__': 'base_inflection'}
    exec(compile(base_source, '<base inflection>', 'exec'), base)
    mismatches = []
    for s in inputs:
        want = base['titleize'](s)
        try:
            got = inflection.titleize(s)
        except Exception as exc:
            got = '<raised %s: %s>' % (type(exc).__name__, exc)
        if got != want:
            mismatches.append([s, want, got])
    return {'checked': len(inputs), 'mismatch_count': len(mismatches),
            'mismatches': mismatches[:25]}
'''


def test_plain_words_capitalized_without_small_word_exceptions():
    cases = {
        "rocket launch": "Rocket Launch",
        "read the spec": "Read The Spec",
        "the": "The",
        "the lord of the rings": "The Lord Of The Rings",
        "war and peace": "War And Peace",
        "a tale of two cities": "A Tale Of Two Cities",
        "gone with the wind": "Gone With The Wind",
        # words that are not written in all caps are not acronyms
        "Nasa rocket launch": "Nasa Rocket Launch",
        "read the Http spec": "Read The Http Spec",
    }
    r = run_python(_TITLEIZE_SNIPPET + "result = _run(" + ascii(list(cases)) + ")\n")
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_original_titleize_examples_unchanged():
    cases = ORIGINAL_TITLEIZE_EXAMPLES
    r = run_python(_TITLEIZE_SNIPPET + "result = _run(" + ascii(list(cases)) + ")\n")
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


def test_titleize_matches_base_on_inputs_without_acronyms():
    inputs = list(_NO_ACRONYM_SAMPLES)
    inputs += _random_texts_without_acronyms(300, seed=20261113)
    assert not [s for s in inputs if _has_adjacent_uppercase(s)]
    snippet = (_TITLEIZE_DIFF_SNIPPET + "result = _run("
               + ascii(BASE_INFLECTION_SOURCE) + ", " + ascii(inputs) + ")\n")
    r = run_python(snippet, timeout=60.0)
    assert r.ok, _failure(r)
    assert r.value["checked"] == len(inputs)
    assert r.value["mismatch_count"] == 0, (
        "titleize differs from the base implementation "
        "([input, base, candidate]): %r" % (r.value["mismatches"],))


def test_trailing_id_suffix_dropped_as_before():
    # The original titleize drops a trailing "_id" (humanize) after
    # underscore() has split camelCase and turned hyphens into underscores and
    # lowercased everything, so a final "Id" / "_Id" / "-id" word is dropped
    # whatever its case.  "id" anywhere else is an ordinary word.  None of
    # these inputs has two consecutive capitals; the expected values are the
    # base outputs.
    cases = {
        "author_id": "Author",
        "authorId": "Author",
        "AuthorId": "Author",
        "author-id": "Author",
        "author_Id": "Author",
        "Author-Id": "Author",
        "EmployeeId": "Employee",
        "postAuthorId": "Post Author",
        "the parentId": "The Parent",
        "the parent-Id": "The Parent",
        "area51Id": "Area51",
        "valid_id": "Valid",
        "user_id_number": "User Id Number",
        "userIdNumber": "User Id Number",
        "author Id": "Author Id",
        "authorIds": "Author Ids",
        "idea": "Idea",
        "squid": "Squid",
    }
    r = run_python(_TITLEIZE_SNIPPET + "result = _run(" + ascii(list(cases)) + ")\n")
    assert r.ok, _failure(r)
    assert dict(zip(cases, r.value)) == cases


# --------------------------------------------------------------------------
# the other public functions (R5)
# --------------------------------------------------------------------------

_ALL_CAPS_PROBES = [
    "NASA rocket launch", "read the HTTP spec", "launch by NASA",
    "the FBI and the CIA", "HTTP and FTP specs", "HTTPServer",
    "HTTP_server", "http_server", "NASA_rocket_launch", "NASARocket",
    "HELLO WORLD", "SCREAMING_SNAKE_CASE", "HTMLTidy", "HTMLTidyGenerator",
    "FreeBSD", "IOError", "HTML", "HTML5 spec", "NASA's rocket",
    "DON'T panic", "employee_ID", "user_id", "UserID", "ALL_CAPS_ID",
    "x-men: the last stand", "Donald E. Knuth", "David's code",
    "\xc6r\xf8sk\xf8bing", "NASA", "CIA", "GPUs", "URLs", "APIs",
    "CamelOctopus", "LOUSE", "MOUSE", "OCTOPI", "INDEX", "NEWS", "SHEEP",
    "PERSON", "PEOPLE", "ChildToy", "_RecipeIngredient", "device_type",
    "DeviceType", "Area51Controller", "  padded  HTTP  words  ",
    "dash-HTTP-case", "Malm\xf6 HTTP gar\xe7ons", "Camel_Case", "Capital",
    "status_code", "matrix_fu", "old_news",
]

_MIXED_TOKENS = [
    "NASA", "HTTP", "FBI", "ID", "Id", "id", "XML", "A", "I", "x", "rocket",
    "launch", "spec", "the", "and", "Server", "server", "Record", "active",
    "status", "octopus", "person", "child", "mouse", "matrix", "news",
    "sheep", "quiz", "\xedndia", "Malm\xf6", "51", "3rd", "don't",
    "HTMLTidy", "camelCase",
]
_MIXED_SEPARATORS = [" ", " ", " ", "  ", "_", "_", "-", "", ".", ": ", "/"]


def _random_texts_with_acronyms(count, seed):
    rng = random.Random(seed)
    texts = []
    for _ in range(count):
        text = rng.choice(_MIXED_TOKENS)
        for _ in range(rng.randint(0, 4)):
            text += rng.choice(_MIXED_SEPARATORS) + rng.choice(_MIXED_TOKENS)
        roll = rng.random()
        if roll < 0.05:
            text = " " + text
        elif roll < 0.10:
            text = text + " "
        elif roll < 0.15:
            text = "_" + text
        texts.append(text)
    return texts


_STRING_OPERATIONS = [
    "camelize", "camelize(lower)", "dasherize", "humanize", "parameterize",
    "parameterize('_')", "parameterize('')", "pluralize", "singularize",
    "tableize", "transliterate", "underscore",
]
_NUMBER_OPERATIONS = ["ordinal", "ordinalize"]

_OTHER_FUNCTIONS_DIFF_SNIPPET = r'''
def _run(base_source, texts, numbers):
    import types
    import inflection
    namespace = {'__name__': 'base_inflection'}
    exec(compile(base_source, '<base inflection>', 'exec'), namespace)
    base = types.SimpleNamespace(**namespace)
    string_ops = [
        ('camelize', lambda m, s: m.camelize(s)),
        ('camelize(lower)', lambda m, s: m.camelize(s, False)),
        ('dasherize', lambda m, s: m.dasherize(s)),
        ('humanize', lambda m, s: m.humanize(s)),
        ('parameterize', lambda m, s: m.parameterize(s)),
        ("parameterize('_')", lambda m, s: m.parameterize(s, '_')),
        ("parameterize('')", lambda m, s: m.parameterize(s, '')),
        ('pluralize', lambda m, s: m.pluralize(s)),
        ('singularize', lambda m, s: m.singularize(s)),
        ('tableize', lambda m, s: m.tableize(s)),
        ('transliterate', lambda m, s: m.transliterate(s)),
        ('underscore', lambda m, s: m.underscore(s)),
    ]
    number_ops = [
        ('ordinal', lambda m, n: m.ordinal(n)),
        ('ordinalize', lambda m, n: m.ordinalize(n)),
    ]

    def outcome(fn, module, arg):
        try:
            return ['value', fn(module, arg)]
        except Exception as exc:
            return ['raised', type(exc).__name__]

    checked = 0
    mismatches = []
    for name, fn in string_ops:
        for s in texts:
            checked += 1
            want = outcome(fn, base, s)
            got = outcome(fn, inflection, s)
            if got != want:
                mismatches.append([name, s, want, got])
    for name, fn in number_ops:
        for n in numbers:
            checked += 1
            want = outcome(fn, base, n)
            got = outcome(fn, inflection, n)
            if got != want:
                mismatches.append([name, n, want, got])
    return {'checked': checked, 'mismatch_count': len(mismatches),
            'mismatches': mismatches[:25]}
'''


def test_other_functions_match_base_including_all_caps_inputs():
    texts = list(_ALL_CAPS_PROBES) + _random_texts_with_acronyms(250, seed=303)
    numbers = list(range(-1100, 1101))
    snippet = (_OTHER_FUNCTIONS_DIFF_SNIPPET + "result = _run("
               + ascii(BASE_INFLECTION_SOURCE) + ", " + ascii(texts) + ", "
               + ascii(numbers) + ")\n")
    r = run_python(snippet, timeout=90.0)
    assert r.ok, _failure(r)
    assert r.value["checked"] == (len(texts) * len(_STRING_OPERATIONS)
                                  + len(numbers) * len(_NUMBER_OPERATIONS))
    assert r.value["mismatch_count"] == 0, (
        "functions other than titleize differ from the base implementation "
        "([function, input, base, candidate]): %r" % (r.value["mismatches"],))


# --------------------------------------------------------------------------
# expectations of the original test_inflection.py (R5)
# --------------------------------------------------------------------------

ORIG_UNCOUNTABLES = [
    "equipment", "fish", "information", "jeans", "money", "rice", "series",
    "sheep", "species",
]

ORIG_SINGULAR_TO_PLURAL = [
    ('search', 'searches'), ('switch', 'switches'), ('fix', 'fixes'),
    ('box', 'boxes'), ('process', 'processes'), ('address', 'addresses'),
    ('case', 'cases'), ('stack', 'stacks'), ('wish', 'wishes'),
    ('fish', 'fish'), ('jeans', 'jeans'), ('funky jeans', 'funky jeans'),
    ('category', 'categories'), ('query', 'queries'), ('ability', 'abilities'),
    ('agency', 'agencies'), ('movie', 'movies'), ('archive', 'archives'),
    ('index', 'indices'), ('wife', 'wives'), ('safe', 'saves'),
    ('half', 'halves'), ('move', 'moves'), ('salesperson', 'salespeople'),
    ('person', 'people'), ('spokesman', 'spokesmen'), ('man', 'men'),
    ('woman', 'women'), ('basis', 'bases'), ('diagnosis', 'diagnoses'),
    ('diagnosis_a', 'diagnosis_as'), ('datum', 'data'), ('medium', 'media'),
    ('stadium', 'stadia'), ('analysis', 'analyses'),
    ('node_child', 'node_children'), ('child', 'children'),
    ('experience', 'experiences'), ('day', 'days'), ('comment', 'comments'),
    ('foobar', 'foobars'), ('newsletter', 'newsletters'),
    ('old_news', 'old_news'), ('news', 'news'), ('series', 'series'),
    ('species', 'species'), ('quiz', 'quizzes'),
    ('perspective', 'perspectives'), ('ox', 'oxen'), ('passerby', 'passersby'),
    ('photo', 'photos'), ('buffalo', 'buffaloes'), ('tomato', 'tomatoes'),
    ('potato', 'potatoes'), ('dwarf', 'dwarves'), ('elf', 'elves'),
    ('information', 'information'), ('equipment', 'equipment'),
    ('bus', 'buses'), ('status', 'statuses'), ('status_code', 'status_codes'),
    ('mouse', 'mice'), ('louse', 'lice'), ('house', 'houses'),
    ('octopus', 'octopi'), ('virus', 'viri'), ('alias', 'aliases'),
    ('portfolio', 'portfolios'), ('vertex', 'vertices'),
    ('matrix', 'matrices'), ('matrix_fu', 'matrix_fus'), ('axis', 'axes'),
    ('testis', 'testes'), ('crisis', 'crises'), ('rice', 'rice'),
    ('shoe', 'shoes'), ('horse', 'horses'), ('prize', 'prizes'),
    ('edge', 'edges'), ('cow', 'kine'), ('database', 'databases'),
    ('human', 'humans'),
]

ORIG_CAMEL_TO_UNDERSCORE = [
    ('Product', 'product'), ('SpecialGuest', 'special_guest'),
    ('ApplicationController', 'application_controller'),
    ('Area51Controller', 'area51_controller'),
]

ORIG_CAMEL_TO_UNDERSCORE_WITHOUT_REVERSE = [
    ('HTMLTidy', 'html_tidy'), ('HTMLTidyGenerator', 'html_tidy_generator'),
    ('FreeBSD', 'free_bsd'), ('HTML', 'html'),
]

ORIG_STRING_TO_PARAMETERIZED = [
    ('Donald E. Knuth', 'donald-e-knuth'),
    ('Random text with *(bad)* characters', 'random-text-with-bad-characters'),
    ('Allow_Under_Scores', 'allow_under_scores'),
    ('Trailing bad characters!@#', 'trailing-bad-characters'),
    ('!@#Leading bad characters', 'leading-bad-characters'),
    ('Squeeze   separators', 'squeeze-separators'),
    ('Test with + sign', 'test-with-sign'),
    ('Test with malformed utf8 \xa9', 'test-with-malformed-utf8'),
]

ORIG_STRING_TO_PARAMETERIZE_WITH_NO_SEPARATOR = [
    ('Donald E. Knuth', 'donaldeknuth'),
    ('With-some-dashes', 'with-some-dashes'),
    ('Random text with *(bad)* characters', 'randomtextwithbadcharacters'),
    ('Trailing bad characters!@#', 'trailingbadcharacters'),
    ('!@#Leading bad characters', 'leadingbadcharacters'),
    ('Squeeze   separators', 'squeezeseparators'),
    ('Test with + sign', 'testwithsign'),
    ('Test with malformed utf8 \xa9', 'testwithmalformedutf8'),
]

ORIG_STRING_TO_PARAMETERIZE_WITH_UNDERSCORE = [
    ('Donald E. Knuth', 'donald_e_knuth'),
    ('Random text with *(bad)* characters', 'random_text_with_bad_characters'),
    ('With-some-dashes', 'with-some-dashes'),
    ('Retain_underscore', 'retain_underscore'),
    ('Trailing bad characters!@#', 'trailing_bad_characters'),
    ('!@#Leading bad characters', 'leading_bad_characters'),
    ('Squeeze   separators', 'squeeze_separators'),
    ('Test with + sign', 'test_with_sign'),
    ('Test with malformed utf8 \xa9', 'test_with_malformed_utf8'),
]

ORIG_STRING_TO_PARAMETERIZED_AND_NORMALIZED = [
    ('Malm\xf6', 'malmo'), ('Gar\xe7ons', 'garcons'), ('Ops\xd9', 'opsu'),
    ('\xc6r\xf8sk\xf8bing', 'rskbing'), ('A\xdflar', 'alar'),
    ('Japanese: 日本語', 'japanese'),
]

ORIG_UNDERSCORE_TO_HUMAN = [
    ('employee_salary', 'Employee salary'), ('employee_id', 'Employee'),
    ('underground', 'Underground'),
]

ORIG_ORDINAL_NUMBERS = [
    ('-1', '-1st'), ('-2', '-2nd'), ('-3', '-3rd'), ('-4', '-4th'),
    ('-5', '-5th'), ('-6', '-6th'), ('-7', '-7th'), ('-8', '-8th'),
    ('-9', '-9th'), ('-10', '-10th'), ('-11', '-11th'), ('-12', '-12th'),
    ('-13', '-13th'), ('-14', '-14th'), ('-20', '-20th'), ('-21', '-21st'),
    ('-22', '-22nd'), ('-23', '-23rd'), ('-24', '-24th'), ('-100', '-100th'),
    ('-101', '-101st'), ('-102', '-102nd'), ('-103', '-103rd'),
    ('-104', '-104th'), ('-110', '-110th'), ('-111', '-111th'),
    ('-112', '-112th'), ('-113', '-113th'), ('-1000', '-1000th'),
    ('-1001', '-1001st'), ('0', '0th'), ('1', '1st'), ('2', '2nd'),
    ('3', '3rd'), ('4', '4th'), ('5', '5th'), ('6', '6th'), ('7', '7th'),
    ('8', '8th'), ('9', '9th'), ('10', '10th'), ('11', '11th'), ('12', '12th'),
    ('13', '13th'), ('14', '14th'), ('20', '20th'), ('21', '21st'),
    ('22', '22nd'), ('23', '23rd'), ('24', '24th'), ('100', '100th'),
    ('101', '101st'), ('102', '102nd'), ('103', '103rd'), ('104', '104th'),
    ('110', '110th'), ('111', '111th'), ('112', '112th'), ('113', '113th'),
    ('1000', '1000th'), ('1001', '1001st'),
]

ORIG_UNDERSCORES_TO_DASHES = [
    ('street', 'street'), ('street_address', 'street-address'),
    ('person_street_address', 'person-street-address'),
]

ORIG_STRING_TO_TABLEIZE = [
    ('person', 'people'), ('Country', 'countries'), ('ChildToy', 'child_toys'),
    ('_RecipeIngredient', '_recipe_ingredients'),
]

_ORIGINAL_SUITE_SNIPPET = r'''
def _run(data):
    import inflection
    failures = []
    counter = [0]

    def check(label, fn, want):
        counter[0] += 1
        try:
            got = fn()
        except Exception as exc:
            got = '<raised %s: %s>' % (type(exc).__name__, exc)
        if got != want:
            failures.append([label, want, got])

    check("pluralize('plurals')", lambda: inflection.pluralize('plurals'), 'plurals')
    check("pluralize('Plurals')", lambda: inflection.pluralize('Plurals'), 'Plurals')
    check("pluralize('')", lambda: inflection.pluralize(''), '')

    for w in data['uncountables']:
        check('singularize(%r)' % w, lambda w=w: inflection.singularize(w), w)
        check('pluralize(%r)' % w, lambda w=w: inflection.pluralize(w), w)

    for singular, plural in data['singular_to_plural']:
        cap_s, cap_p = singular.capitalize(), plural.capitalize()
        check('pluralize(%r)' % singular,
              lambda x=singular: inflection.pluralize(x), plural)
        check('pluralize(%r)' % cap_s,
              lambda x=cap_s: inflection.pluralize(x), cap_p)
        check('singularize(%r)' % plural,
              lambda x=plural: inflection.singularize(x), singular)
        check('singularize(%r)' % cap_p,
              lambda x=cap_p: inflection.singularize(x), cap_s)
        check('pluralize(%r) [already plural]' % plural,
              lambda x=plural: inflection.pluralize(x), plural)
        check('pluralize(%r) [already plural]' % cap_p,
              lambda x=cap_p: inflection.pluralize(x), cap_p)

    for camel, under in data['camel_to_underscore']:
        check('camelize(%r)' % under, lambda x=under: inflection.camelize(x), camel)
    check("camelize('Capital', False)",
          lambda: inflection.camelize('Capital', False), 'capital')
    check("camelize('Camel_Case')",
          lambda: inflection.camelize('Camel_Case'), 'CamelCase')

    for camel, under in (data['camel_to_underscore']
                         + data['camel_to_underscore_without_reverse']):
        check('underscore(%r)' % camel, lambda x=camel: inflection.underscore(x), under)

    for text, want in data['parameterized']:
        check('parameterize(%r)' % text,
              lambda x=text: inflection.parameterize(x), want)
        check('parameterize(%r, "__sep__")' % text,
              lambda x=text: inflection.parameterize(x, '__sep__'),
              want.replace('-', '__sep__'))
    for text, want in data['parameterized_and_normalized']:
        check('parameterize(%r)' % text,
              lambda x=text: inflection.parameterize(x), want)
    for text, want in data['parameterize_with_underscore']:
        check('parameterize(%r, "_")' % text,
              lambda x=text: inflection.parameterize(x, '_'), want)
    for text, want in data['parameterize_with_no_separator']:
        check('parameterize(%r, "")' % text,
              lambda x=text: inflection.parameterize(x, ''), want)

    for under, human in data['underscore_to_human']:
        check('humanize(%r)' % under, lambda x=under: inflection.humanize(x), human)

    for number, want in data['ordinal_numbers']:
        check('%s + ordinal(%s)' % (number, number),
              lambda x=number: x + inflection.ordinal(int(x)), want)
        check('ordinalize(%s)' % number,
              lambda x=number: inflection.ordinalize(int(x)), want)

    for text, want in data['underscores_to_dashes']:
        check('dasherize(%r)' % text, lambda x=text: inflection.dasherize(x), want)

    for text, want in data['tableize']:
        check('tableize(%r)' % text, lambda x=text: inflection.tableize(x), want)

    def not_greedy():
        # test_uncountable_word_is_not_greedy of the original suite
        inflection.UNCOUNTABLES.add('ors')
        try:
            return [
                inflection.singularize('ors'),
                inflection.pluralize('ors'),
                inflection.singularize('sponsor'),
                inflection.pluralize('sponsor'),
                inflection.singularize(inflection.pluralize('sponsor')),
            ]
        finally:
            inflection.UNCOUNTABLES.remove('ors')

    check('uncountable word is not greedy', not_greedy,
          ['ors', 'ors', 'sponsor', 'sponsors', 'sponsor'])

    return {'checked': counter[0], 'failure_count': len(failures),
            'failures': failures[:25]}
'''


def test_original_suite_expectations_for_other_functions_hold():
    data = {
        "uncountables": ORIG_UNCOUNTABLES,
        "singular_to_plural": ORIG_SINGULAR_TO_PLURAL,
        "camel_to_underscore": ORIG_CAMEL_TO_UNDERSCORE,
        "camel_to_underscore_without_reverse":
            ORIG_CAMEL_TO_UNDERSCORE_WITHOUT_REVERSE,
        "parameterized": ORIG_STRING_TO_PARAMETERIZED,
        "parameterized_and_normalized":
            ORIG_STRING_TO_PARAMETERIZED_AND_NORMALIZED,
        "parameterize_with_underscore":
            ORIG_STRING_TO_PARAMETERIZE_WITH_UNDERSCORE,
        "parameterize_with_no_separator":
            ORIG_STRING_TO_PARAMETERIZE_WITH_NO_SEPARATOR,
        "underscore_to_human": ORIG_UNDERSCORE_TO_HUMAN,
        "ordinal_numbers": ORIG_ORDINAL_NUMBERS,
        "underscores_to_dashes": ORIG_UNDERSCORES_TO_DASHES,
        "tableize": ORIG_STRING_TO_TABLEIZE,
    }
    expected_checks = (
        3
        + 2 * len(ORIG_UNCOUNTABLES)
        + 6 * len(ORIG_SINGULAR_TO_PLURAL)
        + len(ORIG_CAMEL_TO_UNDERSCORE) + 2
        + len(ORIG_CAMEL_TO_UNDERSCORE) + len(ORIG_CAMEL_TO_UNDERSCORE_WITHOUT_REVERSE)
        + 2 * len(ORIG_STRING_TO_PARAMETERIZED)
        + len(ORIG_STRING_TO_PARAMETERIZED_AND_NORMALIZED)
        + len(ORIG_STRING_TO_PARAMETERIZE_WITH_UNDERSCORE)
        + len(ORIG_STRING_TO_PARAMETERIZE_WITH_NO_SEPARATOR)
        + len(ORIG_UNDERSCORE_TO_HUMAN)
        + 2 * len(ORIG_ORDINAL_NUMBERS)
        + len(ORIG_UNDERSCORES_TO_DASHES)
        + len(ORIG_STRING_TO_TABLEIZE)
        + 1
    )
    r = run_python(_ORIGINAL_SUITE_SNIPPET + "result = _run(" + ascii(data) + ")\n",
                   timeout=60.0)
    assert r.ok, _failure(r)
    assert r.value["checked"] == expected_checks
    assert r.value["failure_count"] == 0, (
        "expectations of the original test-suite fail "
        "([check, expected, got]): %r" % (r.value["failures"],))
