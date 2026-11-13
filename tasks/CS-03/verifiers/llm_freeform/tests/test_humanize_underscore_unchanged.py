# Hidden behavioural tests for CS-03 (condition: llm_freeform).
#
# Requirement labels (shared with test_titleize_acronyms.py):
#   B1  titleize() keeps all-caps words (acronyms) when the input also
#       contains lowercase letters.
#   B2  ... also when joined by underscores or hyphens.
#   B3  Input without lowercase letters is titleized exactly as before.
#   B4  Next to acronyms, the other words keep titleize's normal treatment.
#   B5  Input without all-caps words is titleized exactly as before.
#   B6  humanize() behaves exactly as before; other code relies on it
#       (e.g. humanize('employee_salary') == 'Employee salary').
#   B7  underscore() behaves exactly as before; other code relies on it
#       (e.g. underscore('NASARocket') == 'nasa_rocket').
#
# Expected values were produced by running the repository at its base commit.

import json

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_humanize_unchanged_examples": ["B6"],
    "test_underscore_unchanged_examples": ["B7"],
    "test_humanize_and_underscore_match_original_on_many_inputs": ["B6", "B7"],
}


def _apply_snippet(func_names, inputs):
    """Source for run_python: for each input, the outputs of the functions."""
    return "\n".join([
        "import json",
        "import inflection",
        "funcs = [getattr(inflection, name) for name in "
        + repr(list(func_names)) + "]",
        "outputs = []",
        "for text in json.loads(" + repr(json.dumps(list(inputs))) + "):",
        "    row = []",
        "    for func in funcs:",
        "        try:",
        "            row.append(func(text))",
        "        except Exception as exc:",
        "            row.append('<raised ' + type(exc).__name__ + '>')",
        "    outputs.append(row)",
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


def test_humanize_unchanged_examples():
    cases = [
        ("employee_salary", "Employee salary"),
        ("author_id", "Author"),
        ("employee_id", "Employee"),
        ("underground", "Underground"),
        ("NASA rocket launch", "Nasa rocket launch"),
        ("read the HTTP spec", "Read the http spec"),
        ("NASA_rocket_launch", "Nasa rocket launch"),
        ("read_the_HTTP_spec", "Read the http spec"),
        ("the USA and the UK", "The usa and the uk"),
        ("HELLO WORLD", "Hello world"),
    ]
    inputs = [c[0] for c in cases]
    expected = [[c[1]] for c in cases]
    r = run_python(_apply_snippet(["humanize"], inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


def test_underscore_unchanged_examples():
    cases = [
        ("NASARocket", "nasa_rocket"),
        ("DeviceType", "device_type"),
        ("Product", "product"),
        ("SpecialGuest", "special_guest"),
        ("ApplicationController", "application_controller"),
        ("Area51Controller", "area51_controller"),
        ("HTMLTidy", "html_tidy"),
        ("HTMLTidyGenerator", "html_tidy_generator"),
        ("FreeBSD", "free_bsd"),
        ("HTML", "html"),
        ("IOError", "io_error"),
        ("getHTTPResponse", "get_http_response"),
        ("NASA rocket launch", "nasa rocket launch"),
        ("read the HTTP spec", "read the http spec"),
        ("NASA_rocket_launch", "nasa_rocket_launch"),
        ("x-men", "x_men"),
    ]
    inputs = [c[0] for c in cases]
    expected = [[c[1]] for c in cases]
    r = run_python(_apply_snippet(["underscore"], inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)


# Seeded sample of mixed inputs (acronyms, CamelCase, digits, "id"/"ID",
# apostrophes, repeated separators) with the base commit's outputs:
# (input, humanize(input), underscore(input)).
HUMANIZED_AND_UNDERSCORED = [
    ('xMAN_a1', 'Xman a1', 'x_man_a1'),
    (' ', ' ', ' '),
    ('salary', 'Salary', 'salary'),
    ('spec  rocket', 'Spec  rocket', 'spec  rocket'),
    ('b_A', 'B a', 'b_a'),
    ("B2_Controller'HTTP_area51", "B2 controller'http area51", "b2_controller'http_area51"),
    ('HTTP__X', 'Http  x', 'http__x'),
    ("0 '-", "0 '-", "0 '_"),
    ('employee', 'Employee', 'employee'),
    ('html5__html5-a1', 'Html5  html5-a1', 'html5__html5_a1'),
    ('HTTP-id_MAN The:Server', 'Http-id man the:server', 'http_id_man the:server'),
    ("x-spec:'S__id", "X-spec:'s ", "x_spec:'s__id"),
    ("NASAThe'spec  FreeBSD", "Nasathe'spec  freebsd", "nasa_the'spec  free_bsd"),
    ('Rocket_XNASA', 'Rocket xnasa', 'rocket_xnasa'),
    ("Server__'s", "Server  's", "server__'s"),
    ('a', 'A', 'a'),
    ("The__x'Server-a1'IOError", "The  x'server-a1'ioerror", "the__x'server_a1'io_error"),
    ("ZB'B", "Zb'b", "zb'b"),
    ('id:FreeBSD HTTP-The-Id', 'Id:freebsd http-the-id', 'id:free_bsd http_the_id'),
    ('area51  HTTPServer', 'Area51  httpserver', 'area51  http_server'),
    ('B2:IOError-Server_x:Id', 'B2:ioerror-server x:id', 'b2:io_error_server_x:id'),
    ("x  'S", "X  's", "x  's"),
    ('FreeBSD', 'Freebsd', 'free_bsd'),
    ("'bB-0ZBAz", "'bb-0zbaz", "'b_b_0_zb_az"),
    ("'S", "'s", "'s"),
    ('Controllerid-employee-employee_NASA', 'Controllerid-employee-employee nasa', 'controllerid_employee_employee_nasa'),
    ('salary id', 'Salary id', 'salary id'),
    ("'S B2-FreeBSD", "'s b2-freebsd", "'s b2_free_bsd"),
    ("rocket'Server'id", "Rocket'server'id", "rocket'server'id"),
    ("area51'B2 IOError__'s__id", "Area51'b2 ioerror  's ", "area51'b2 io_error__'s__id"),
    ('Z  b_', 'Z  b ', 'z  b_'),
    ('X', 'X', 'x'),
    ("Id'Xid__employee:spec", "Id'xid  employee:spec", "id'xid__employee:spec"),
    ('B2__salary-rocket', 'B2  salary-rocket', 'b2__salary_rocket'),
    ('Controller', 'Controller', 'controller'),
    ("'s__employee:rocket_X", "'s  employee:rocket x", "'s__employee:rocket_x"),
    ('- -0', '- -0', '_ _0'),
    ('NASA IOErrorRocketThe', 'Nasa ioerrorrocketthe', 'nasa io_error_rocket_the'),
    ("0 Z'_0'", "0 z' 0'", "0 z'_0'"),
    ("b-z0'_Zab", "B-z0' zab", "b_z0'_zab"),
    (' aa b BAB', ' aa b bab', ' aa b bab'),
    ('spec-MAN-MAN The', 'Spec-man-man the', 'spec_man_man the'),
    ('a1a1get:html5_html5', 'A1a1get:html5 html5', 'a1a1get:html5_html5'),
    ("'S html5__Id", "'s html5  id", "'s html5__id"),
    ('Id', 'Id', 'id'),
    ('NASA', 'Nasa', 'nasa'),
    ("Z'Z b9B", "Z'z b9b", "z'z b9_b"),
    ('a1 MAN_employee', 'A1 man employee', 'a1 man_employee'),
    ('aaAzz -', 'Aaazz -', 'aa_azz _'),
    ('HTTPServer', 'Httpserver', 'http_server'),
    ('Rocket', 'Rocket', 'rocket'),
    ('z0Abz b', 'Z0abz b', 'z0_abz b'),
    ("B2-x 's", "B2-x 's", "b2_x 's"),
    ('Controller Server_HTTPServer', 'Controller server httpserver', 'controller server_http_server'),
    ('salaryID', 'Salaryid', 'salary_id'),
    ('html5__X:employee', 'Html5  x:employee', 'html5__x:employee'),
    (" 9'09ZA", " 9'09za", " 9'09_za"),
    ('idhtml5', 'Idhtml5', 'idhtml5'),
    ("salary__'S", "Salary  's", "salary__'s"),
    ('area51_HTTPServer', 'Area51 httpserver', 'area51_http_server'),
]


def test_humanize_and_underscore_match_original_on_many_inputs():
    inputs = [c[0] for c in HUMANIZED_AND_UNDERSCORED]
    expected = [[c[1], c[2]] for c in HUMANIZED_AND_UNDERSCORED]
    r = run_python(
        _apply_snippet(["humanize", "underscore"], inputs), timeout=20.0)
    assert r.ok, _failure(r)
    assert r.value == expected, _mismatches(inputs, r.value, expected)
