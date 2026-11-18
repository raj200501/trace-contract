"""Reference checks for CS-02: what successful writes put into the file.

After every successful write (with the storage still open) the file must
contain exactly json.dumps(data, **kwargs) encoded with the storage's
encoding. The expected bytes are computed here, in the grader process.
TinyDB operations each run in a new TinyDB instance, so the expected bytes
don't depend on reads through an instance that has already written. Reads
after writes are checked separately (R-read-after-write).
"""

import json
import random
import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    'test_default_storage_bytes_match_json_dumps':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_utf8_indent_sort_keys_non_ascii_bytes':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_utf16_bytes':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_cp936_and_latin1_bytes_with_separators':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_tinydb_operations_bytes_with_kwargs':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_random_documents_bytes':
        ['R-bytes-unchanged', 'R-new-content'],
    'test_random_documents_reads':
        ['R-read-after-write'],
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
        os.mkdir(path)
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

    def write_sequence(path, sequence, encoding, kwargs):
        """Write each item, recording the file bytes right after it."""
        storage = JSONStorage(path, encoding=encoding, **kwargs)
        hexes = []
        for data in sequence:
            storage.write(data)
            hexes.append(read_hex(path))
        storage.close()
        return {'hexes': hexes, 'after_close': read_hex(path)}
''')

GROW_SHRINK = [
    {'_default': {'1': {'name': 'Zoë', 'tags': ['a', 'b'], 'score': 1.5,
                        'ok': True, 'none': None}}},
    {'_default': {str(i): {'value': 'x' * i, 'i': i} for i in range(1, 30)},
     'other': {'1': {'k': '世界', 'z': 'last'}}},
    {'_default': {}},
    {},
    {'zeta': {'9': {'b': 2, 'a': 1}},
     '_default': {'7': {'nested': {'deep': [1, 2.25, {'z': 'é'}]}}}},
]

NON_ASCII = [
    {'_default': {'1': {'text': 'こんにちは世界',
                        'n': 1}}},
    {'_default': {str(n): {'text': '中文数据', 'n': n,
                           'kana': 'カタカナ'}
                  for n in range(12)}},
    {'_default': {'3': {'text': '世界', 'b': [True, None]}}},
]


def _embed(name, value):
    """Python source that recreates a JSON value inside the snippet."""
    return '%s = json.loads(%r)\n' % (name, json.dumps(value))


def _expected_hexes(sequence, encoding, kwargs):
    return [json.dumps(data, **kwargs).encode(encoding).hex()
            for data in sequence]


def test_default_storage_bytes_match_json_dumps():
    # No encoding and no json kwargs: the output is plain ASCII json.dumps
    body = _embed('SEQ', GROW_SHRINK) + textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        result = write_sequence(path, SEQ, None, {})
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = _expected_hexes(GROW_SHRINK, 'ascii', {})
    assert r.value['hexes'] == expected
    assert r.value['after_close'] == expected[-1]


def test_utf8_indent_sort_keys_non_ascii_bytes():
    kwargs = {'indent': 4, 'sort_keys': True, 'ensure_ascii': False}
    sequence = GROW_SHRINK + NON_ASCII
    body = _embed('SEQ', sequence) + textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        result = write_sequence(path, SEQ, 'utf-8', %r)
    ''' % (kwargs,))
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = _expected_hexes(sequence, 'utf-8', kwargs)
    assert r.value['hexes'] == expected
    assert r.value['after_close'] == expected[-1]


def test_utf16_bytes():
    kwargs = {'ensure_ascii': False}
    sequence = NON_ASCII + GROW_SHRINK[:3]
    body = _embed('SEQ', sequence) + textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        result = write_sequence(path, SEQ, 'utf-16', %r)
    ''' % (kwargs,))
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = _expected_hexes(sequence, 'utf-16', kwargs)
    assert r.value['hexes'] == expected
    assert r.value['after_close'] == expected[-1]


def test_cp936_and_latin1_bytes_with_separators():
    cp936_kwargs = {'ensure_ascii': False, 'indent': 2,
                    'separators': (',', ': ')}
    latin1_kwargs = {'ensure_ascii': False, 'separators': (',', ':')}
    latin1_seq = [
        {'_default': {'1': {'name': 'Renée', 'city': 'Köln'}}},
        {'_default': {str(i): {'s': 'ßñç' * i}
                      for i in range(1, 20)}},
        {'_default': {'2': {'s': 'å'}}},
    ]
    body = (_embed('CP936_SEQ', NON_ASCII) + _embed('LATIN1_SEQ', latin1_seq)
            + textwrap.dedent('''
        result = {
            'cp936': write_sequence(
                os.path.join(fresh_dir('gbk'), 'gbk.json'),
                CP936_SEQ, 'cp936', %r),
            'latin1': write_sequence(
                os.path.join(fresh_dir('latin'), 'latin.json'),
                LATIN1_SEQ, 'latin-1', %r),
        }
    ''' % (cp936_kwargs, latin1_kwargs)))
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected_cp936 = _expected_hexes(NON_ASCII, 'cp936', cp936_kwargs)
    expected_latin1 = _expected_hexes(latin1_seq, 'latin-1', latin1_kwargs)
    assert r.value['cp936']['hexes'] == expected_cp936
    assert r.value['cp936']['after_close'] == expected_cp936[-1]
    assert r.value['latin1']['hexes'] == expected_latin1
    assert r.value['latin1']['after_close'] == expected_latin1[-1]


def test_tinydb_operations_bytes_with_kwargs():
    # json kwargs and the encoding passed to TinyDB reach the storage. Every
    # operation runs in a new TinyDB instance; the bytes are recorded right
    # after it, with the database still open.
    kwargs = {'indent': 2, 'sort_keys': True, 'ensure_ascii': False}
    body = textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        operations = [
            lambda db: db.insert({'name': 'Zo\\u00eb', 'n': 1}),
            lambda db: db.insert({'name': '\\u674e', 'n': 2}),
            lambda db: db.update({'n': 20}, Query().name == '\\u674e'),
            lambda db: db.remove(doc_ids=[1]),
            lambda db: db.insert_multiple([{'name': 'a'}, {'name': 'b'}]),
            lambda db: db.truncate(),
        ]
        hexes = []
        errors = []
        for operation in operations:
            db = TinyDB(path, encoding='utf-8', **%r)
            errors.append(attempt(lambda: operation(db)))
            hexes.append(read_hex(path))
            errors.append(attempt(db.close))
        result = {'hexes': hexes, 'errors': errors,
                  'after_close': read_hex(path)}
    ''' % (kwargs,))
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    zoe = {'name': 'Zoë', 'n': 1}
    states = [
        {'_default': {'1': zoe}},
        {'_default': {'1': zoe, '2': {'name': '李', 'n': 2}}},
        {'_default': {'1': zoe, '2': {'name': '李', 'n': 20}}},
        {'_default': {'2': {'name': '李', 'n': 20}}},
        {'_default': {'2': {'name': '李', 'n': 20},
                      '3': {'name': 'a'}, '4': {'name': 'b'}}},
        {'_default': {}},
    ]
    expected = _expected_hexes(states, 'utf-8', kwargs)
    assert r.value['hexes'] == expected, r.value['errors']
    assert r.value['after_close'] == expected[-1]


ALPHABET = 'abcxyz XYZ019_-"\\/\n\téßñ中文こ\U0001f600'


def _random_value(rng, depth):
    kinds = ['int', 'float', 'str', 'bool', 'none']
    if depth < 3:
        kinds += ['list', 'dict', 'dict']
    kind = rng.choice(kinds)
    if kind == 'int':
        return rng.randint(-10 ** 12, 10 ** 12)
    if kind == 'float':
        return rng.uniform(-1e6, 1e6)
    if kind == 'str':
        return ''.join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 12)))
    if kind == 'bool':
        return rng.random() < 0.5
    if kind == 'none':
        return None
    if kind == 'list':
        return [_random_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {_random_value_key(rng): _random_value(rng, depth + 1)
            for _ in range(rng.randint(0, 4))}


def _random_value_key(rng):
    return ''.join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 6)))


def _random_database(rng):
    tables = {}
    for name in ['_default'] + ['t%d' % i for i in range(rng.randint(0, 2))]:
        tables[name] = {str(doc_id): {_random_value_key(rng): _random_value(rng, 1)
                                      for _ in range(rng.randint(0, 5))}
                        for doc_id in rng.sample(range(1, 200),
                                                 rng.randint(0, 8))}
    return tables


_RNG = random.Random(20261118)
RANDOM_SEQUENCE = [_random_database(_RNG) for _ in range(14)]
RANDOM_KWARGS = {'indent': 1, 'ensure_ascii': False}

# The bytes and the reads are checked separately, on the same run. Errors of
# reads are recorded, so they can't abort the run.
RANDOM_SNIPPET = PRELUDE + _embed('SEQ', RANDOM_SEQUENCE) + textwrap.dedent(
    '''
    path = os.path.join(fresh_dir('db'), 'db.json')
    storage = JSONStorage(path, encoding='utf-8', **%r)
    hexes = []
    reads = []
    write_errors = []

    def read():
        try:
            return {'value': storage.read()}
        except Exception as exc:
            return {'error': type(exc).__name__}

    for data in SEQ:
        write_errors.append(attempt(lambda: storage.write(data)))
        hexes.append(read_hex(path))
        reads.append(read())
    write_errors.append(attempt(storage.close))
    result = {'hexes': hexes, 'reads': reads, 'write_errors': write_errors}
''' % (RANDOM_KWARGS,))

_RUNS = {}
_CALLS = {}


def _random_run(check):
    """Run RANDOM_SNIPPET; the bytes and the reads check share a run.

    The n-th call of each check uses the n-th run, so both checks judge the
    same run, and repeating the tests in one process still runs the snippet
    again.
    """
    n = _CALLS.get(check, 0)
    _CALLS[check] = n + 1
    if n not in _RUNS:
        _RUNS[n] = run_python(RANDOM_SNIPPET, timeout=60.0)
    return _RUNS[n]


def test_random_documents_bytes():
    r = _random_run('bytes')
    assert r.ok, (r.error_type, r.error)
    assert r.value['hexes'] == _expected_hexes(
        RANDOM_SEQUENCE, 'utf-8', RANDOM_KWARGS), r.value['write_errors']


def test_random_documents_reads():
    r = _random_run('reads')
    assert r.ok, (r.error_type, r.error)
    assert r.value['reads'] == [{'value': data} for data in RANDOM_SEQUENCE]
