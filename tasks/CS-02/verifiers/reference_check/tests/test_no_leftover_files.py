"""Reference checks for CS-02: successful writes leave no temporary files.

After every successful write (with the database still open) and after
closing, the database directory must hold no file other than the database
file(s). The listing checks (R-no-temp-files) look at the listings only: the
snippets catch errors per operation and return the file bytes as hex, so
neither a failing operation nor a file that can't be decoded aborts them.

The file contents are checked separately (R-new-content), decoded here in the
grader. TinyDB operations whose file contents are checked each run in a new
TinyDB instance, so the expected contents don't depend on reads through an
instance that has already written.
(Leftovers after failed writes are checked in test_failed_writes.py.)
"""

import json
import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    'test_tinydb_operations_leave_only_database_file':
        ['R-no-temp-files'],
    'test_tinydb_operations_file_contents':
        ['R-new-content'],
    'test_storage_writes_leave_only_database_files':
        ['R-no-temp-files'],
    'test_storage_writes_file_contents':
        ['R-new-content'],
}

PRELUDE = textwrap.dedent('''
    import json
    import os
    import tempfile

    from tinydb import TinyDB, Query
    from tinydb.storages import JSONStorage

    BASE_DIR = tempfile.mkdtemp(prefix='cs02_refcheck_', dir='/tmp')

    def fresh_dir(name):
        path = os.path.join(BASE_DIR, name)
        os.makedirs(path)
        return path

    def read_hex(path):
        try:
            with open(path, 'rb') as handle:
                return handle.read().hex()
        except OSError:
            return None

    def attempt(action):
        """Call action(); return the name of the exception it raised."""
        try:
            action()
            return None
        except Exception as exc:
            return type(exc).__name__
''')


def _embed(name, value):
    """Python source that recreates a JSON value inside the snippet."""
    return '%s = json.loads(%r)\n' % (name, json.dumps(value))


def _decode(hex_data, encoding='utf-8'):
    """The JSON data of a file the snippet returned as hex (None: no file)."""
    if hex_data is None:
        return {'valid': False, 'error': 'no file'}
    try:
        text = bytes.fromhex(hex_data).decode(encoding)
        return {'valid': True, 'data': json.loads(text)}
    except ValueError as exc:
        return {'valid': False, 'error': type(exc).__name__}


def _other_files(listing, db_names):
    """The files in a listing other than the database files."""
    return sorted(set(listing) - set(db_names))


TINYDB_SNIPPET = PRELUDE + textwrap.dedent('''
    q = Query()
    COMMON_START = [
        ('insert', lambda db: db.insert({'a': 1})),
        ('insert_multiple',
         lambda db: db.insert_multiple([{'a': 2}, {'a': 3}])),
        ('update', lambda db: db.update({'b': True}, q.a >= 2)),
    ]
    COMMON_END = [
        ('remove', lambda db: db.remove(doc_ids=[1])),
        ('other_table', lambda db: db.table('extra').insert({'x': 'y'})),
        ('drop_table', lambda db: db.drop_table('extra')),
        ('truncate', lambda db: db.truncate()),
        ('drop_tables', lambda db: db.drop_tables()),
        ('big_insert', lambda db: db.insert({'z': 'last' * 500})),
    ]

    # All operations through one TinyDB instance (only listings are used)
    d = fresh_dir('same')
    path = os.path.join(d, 'db.json')
    db = TinyDB(path)
    same = []
    for name, operation in COMMON_START + [
            ('upsert', lambda db: db.upsert({'a': 4}, q.a == 4))] + COMMON_END:
        error = attempt(lambda: operation(db))
        same.append({'name': name, 'error': error,
                     'listing': sorted(os.listdir(d))})
    same_close_error = attempt(db.close)
    same_after_close = sorted(os.listdir(d))

    # A new TinyDB instance for every operation. upsert() without a match
    # writes and then reads through the same instance, so it is replaced by
    # a plain insert here.
    d = fresh_dir('reopened')
    path = os.path.join(d, 'db.json')
    reopened = []
    for name, operation in COMMON_START + [
            ('insert_4', lambda db: db.insert({'a': 4}))] + COMMON_END:
        db = TinyDB(path)
        step = {'name': name, 'error': attempt(lambda: operation(db))}
        step['listing'] = sorted(os.listdir(d))
        step['hex'] = read_hex(path)
        step['close_error'] = attempt(db.close)
        step['listing_after_close'] = sorted(os.listdir(d))
        reopened.append(step)

    result = {
        'same': same,
        'same_close_error': same_close_error,
        'same_after_close': same_after_close,
        'reopened': reopened,
    }
''')

SAME_STEPS = ['insert', 'insert_multiple', 'update', 'upsert', 'remove',
              'other_table', 'drop_table', 'truncate', 'drop_tables',
              'big_insert']

_TWO_THREE = {'2': {'a': 2, 'b': True}, '3': {'a': 3, 'b': True}}
REOPENED_CONTENTS = [
    ['insert', {'_default': {'1': {'a': 1}}}],
    ['insert_multiple', {'_default': {'1': {'a': 1}, '2': {'a': 2},
                                      '3': {'a': 3}}}],
    ['update', {'_default': dict({'1': {'a': 1}}, **_TWO_THREE)}],
    ['insert_4', {'_default': dict({'1': {'a': 1}}, **_TWO_THREE,
                                   **{'4': {'a': 4}})}],
    ['remove', {'_default': dict(_TWO_THREE, **{'4': {'a': 4}})}],
    ['other_table', {'_default': dict(_TWO_THREE, **{'4': {'a': 4}}),
                     'extra': {'1': {'x': 'y'}}}],
    ['drop_table', {'_default': dict(_TWO_THREE, **{'4': {'a': 4}})}],
    ['truncate', {'_default': {}}],
    ['drop_tables', {}],
    ['big_insert', {'_default': {'1': {'z': 'last' * 500}}}],
]

# Two databases in one nested directory (created by the snippet), with
# different encodings and json kwargs, written alternately
STORAGE_SEQUENCE = [
    {'_default': {str(i): {'n': i, 's': 'é世' * i}
                  for i in range(1, k + 1)}}
    for k in [1, 25, 3, 0, 60, 2]
]
STORAGE_ENCODINGS = {'a': 'utf-8', 'b': 'utf-16'}

STORAGE_SNIPPET = PRELUDE + _embed('SEQ', STORAGE_SEQUENCE) + textwrap.dedent(
    '''
    d = fresh_dir(os.path.join('nested', 'deeper'))
    path_a = os.path.join(d, 'a.json')
    path_b = os.path.join(d, 'b.json')
    a = JSONStorage(path_a, indent=2)
    b = JSONStorage(path_b, encoding='utf-16', ensure_ascii=False,
                    sort_keys=True)
    steps = []
    for i, data in enumerate(SEQ):
        error = attempt(lambda: a.write(data))
        steps.append({'who': 'a', 'i': i, 'error': error,
                      'listing': sorted(os.listdir(d)),
                      'hex': read_hex(path_a)})
        error = attempt(lambda: b.write(SEQ[-1 - i]))
        steps.append({'who': 'b', 'i': i, 'error': error,
                      'listing': sorted(os.listdir(d)),
                      'hex': read_hex(path_b)})
    close_errors = [attempt(a.close), attempt(b.close)]
    result = {'steps': steps, 'close_errors': close_errors,
              'after_close': sorted(os.listdir(d))}
''')

SNIPPETS = {'tinydb': TINYDB_SNIPPET, 'storage': STORAGE_SNIPPET}
_RUNS = {}
_CALLS = {}


def _run(name, check):
    """Run a snippet; its listing and content check share a run.

    The n-th call of each check uses the snippet's n-th run, so both checks
    judge the same run, and repeating the tests in one process still runs
    the snippet again.
    """
    n = _CALLS.get((name, check), 0)
    _CALLS[(name, check)] = n + 1
    if (name, n) not in _RUNS:
        _RUNS[(name, n)] = run_python(SNIPPETS[name], timeout=60.0)
    return _RUNS[(name, n)]


def test_tinydb_operations_leave_only_database_file():
    r = _run('tinydb', 'listing')
    assert r.ok, (r.error_type, r.error)
    same = r.value['same']
    reopened = r.value['reopened']
    assert [step['name'] for step in same] == SAME_STEPS, same
    assert [step['name'] for step in reopened] == [
        name for name, _ in REOPENED_CONTENTS], reopened
    listings = (
        [['same', step['name'], step['listing']] for step in same]
        + [['same', 'after_close', r.value['same_after_close']]]
        + [['reopened', step['name'], step['listing']] for step in reopened]
        + [['reopened', step['name'] + ' (closed)',
            step['listing_after_close']] for step in reopened]
    )
    for run, name, listing in listings:
        assert _other_files(listing, ['db.json']) == [], (
            run, name, listing)


def test_tinydb_operations_file_contents():
    r = _run('tinydb', 'content')
    assert r.ok, (r.error_type, r.error)
    contents = [[step['name'], _decode(step['hex'])]
                for step in r.value['reopened']]
    assert contents == [[name, {'valid': True, 'data': data}]
                        for name, data in REOPENED_CONTENTS], (
        r.value['reopened'])


def test_storage_writes_leave_only_database_files():
    r = _run('storage', 'listing')
    assert r.ok, (r.error_type, r.error)
    steps = r.value['steps']
    assert [[step['who'], step['i']] for step in steps] == [
        [who, i] for i in range(len(STORAGE_SEQUENCE)) for who in 'ab']
    # The contract does not say whether constructing a JSONStorage creates
    # its file, and whether a database file exists is up to the content
    # check: only files other than the two database files count here.
    for step in steps:
        assert _other_files(step['listing'], ['a.json', 'b.json']) == [], (
            step['who'], step['i'], step['listing'])
    assert _other_files(r.value['after_close'],
                        ['a.json', 'b.json']) == [], r.value['after_close']


def test_storage_writes_file_contents():
    r = _run('storage', 'content')
    assert r.ok, (r.error_type, r.error)
    contents = [[step['who'], step['i'],
                 _decode(step['hex'], STORAGE_ENCODINGS[step['who']])]
                for step in r.value['steps']]
    expected = []
    for i, data in enumerate(STORAGE_SEQUENCE):
        expected.append(['a', i, {'valid': True, 'data': data}])
        expected.append(['b', i, {'valid': True,
                                  'data': STORAGE_SEQUENCE[-1 - i]}])
    assert contents == expected, r.value['steps']
