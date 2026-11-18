"""Reference checks for CS-02: reads after successful writes.

Reads through the same JSONStorage object / TinyDB instance must return what
was just written, after every one of several writes (growing and shrinking
the file), and a new instance opened on the same path must see it as well.
These checks only look at what is read. The file contents are checked
separately (R-new-content), with every TinyDB operation run in a new TinyDB
instance, so that they don't depend on reads after writes.
"""

import json
import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    'test_storage_reads_return_latest_write':
        ['R-read-after-write'],
    'test_tinydb_reads_after_writes_same_instance':
        ['R-read-after-write'],
    'test_tinydb_reads_with_utf16_and_kwargs':
        ['R-read-after-write'],
    'test_multiple_tables_reads':
        ['R-read-after-write'],
    'test_multiple_tables_file_contents':
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
        os.mkdir(path)
        return path

    def docs(documents):
        return [[doc.doc_id, dict(doc)]
                for doc in sorted(documents, key=lambda doc: doc.doc_id)]

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


def test_storage_reads_return_latest_write():
    sequence = [
        {'_default': {'1': {'a': 1}}},
        {'_default': {str(i): {'v': 'x' * 50} for i in range(1, 41)},
         'log': {'1': {'msg': 'hello'}}},
        {'_default': {'2': {'a': 2}}},
        {},
        {'_default': {'5': {'final': True}}, 'log': {'3': {'msg': 'bye'}}},
    ]
    body = _embed('SEQ', sequence) + textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        storage = JSONStorage(path)
        reads = []
        for data in SEQ:
            storage.write(data)
            reads.append([storage.read(), storage.read()])
        storage.close()
        fresh = JSONStorage(path)
        fresh_read = fresh.read()
        fresh.close()
        db = TinyDB(path)
        result = {
            'reads': reads,
            'fresh_read': fresh_read,
            'tables': sorted(db.tables()),
            'default_docs': docs(db.table('_default').all()),
            'log_docs': docs(db.table('log').all()),
        }
        db.close()
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    assert r.value['reads'] == [[data, data] for data in sequence]
    assert r.value['fresh_read'] == sequence[-1]
    assert r.value['tables'] == ['_default', 'log']
    assert r.value['default_docs'] == [[5, {'final': True}]]
    assert r.value['log_docs'] == [[3, {'msg': 'bye'}]]


def test_tinydb_reads_after_writes_same_instance():
    body = textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        db = TinyDB(path)
        q = Query()
        reads = {}
        db.insert({'k': 1, 'v': 'a'})
        reads['after_insert'] = docs(db.all())
        db.insert_multiple([{'k': 2, 'v': 'b'}, {'k': 3, 'v': 'c'}])
        reads['after_insert_multiple'] = docs(db.all())
        reads['search'] = docs(db.search(q.k >= 2))
        db.update({'v': 'B'}, q.k == 2)
        reads['search_after_update'] = docs(db.search(q.k >= 2))
        reads['get_2'] = dict(db.get(doc_id=2))
        db.remove(q.k == 1)
        reads['after_remove'] = docs(db.all())
        reads['len_after_remove'] = len(db)
        reads['contains_1'] = db.contains(doc_id=1)
        db.upsert({'k': 3, 'v': 'C'}, q.k == 3)
        reads['after_upsert'] = docs(db.all())
        db.truncate()
        reads['after_truncate'] = docs(db.all())
        db.insert({'k': 9, 'v': 'z' * 3000})
        reads['after_big_insert'] = docs(db.all())
        db.update({'v': 'short'}, doc_ids=[1])
        reads['after_shrink'] = docs(db.all())
        db.close()
        other = TinyDB(path)
        reads['new_instance'] = docs(other.all())
        other.close()
        result = reads
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    a = {'k': 1, 'v': 'a'}
    b = {'k': 2, 'v': 'b'}
    big_b = {'k': 2, 'v': 'B'}
    c = {'k': 3, 'v': 'c'}
    assert r.value == {
        'after_insert': [[1, a]],
        'after_insert_multiple': [[1, a], [2, b], [3, c]],
        'search': [[2, b], [3, c]],
        'search_after_update': [[2, big_b], [3, c]],
        'get_2': big_b,
        'after_remove': [[2, big_b], [3, c]],
        'len_after_remove': 2,
        'contains_1': False,
        'after_upsert': [[2, big_b], [3, {'k': 3, 'v': 'C'}]],
        'after_truncate': [],
        'after_big_insert': [[1, {'k': 9, 'v': 'z' * 3000}]],
        'after_shrink': [[1, {'k': 9, 'v': 'short'}]],
        'new_instance': [[1, {'k': 9, 'v': 'short'}]],
    }


def test_tinydb_reads_with_utf16_and_kwargs():
    # Re-reading has to keep using the storage's encoding
    words = ['こんにちは', '世界',
             'Grüße', 'привет']
    body = _embed('WORDS', words) + textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        db = TinyDB(path, encoding='utf-16', indent=2, ensure_ascii=False)
        reads = {}
        db.insert({'word': WORDS[0]})
        reads['one'] = docs(db.all())
        db.insert({'word': WORDS[1], 'n': 2})
        reads['two'] = docs(db.all())
        db.update({'word': WORDS[2]}, doc_ids=[1])
        reads['search'] = docs(db.search(Query().word == WORDS[2]))
        db.insert_multiple([{'word': WORDS[3] * 400}, {'word': WORDS[0]}])
        reads['four'] = docs(db.all())
        db.remove(doc_ids=[3])
        reads['three'] = docs(db.all())
        db.close()
        other = TinyDB(path, encoding='utf-16')
        reads['new_instance'] = docs(other.all())
        other.close()
        result = reads
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    first = [1, {'word': words[2]}]
    second = [2, {'word': words[1], 'n': 2}]
    assert r.value == {
        'one': [[1, {'word': words[0]}]],
        'two': [[1, {'word': words[0]}], second],
        'search': [first],
        'four': [first, second, [3, {'word': words[3] * 400}],
                 [4, {'word': words[0]}]],
        'three': [first, second, [4, {'word': words[0]}]],
        'new_instance': [first, second, [4, {'word': words[0]}]],
    }


def test_multiple_tables_reads():
    body = textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        db = TinyDB(path)
        users = db.table('users')
        logs = db.table('logs')
        steps = []

        def snapshot(*names):
            steps.append({
                'tables': sorted(db.tables()),
                'docs': {name: docs(db.table(name).all()) for name in names},
            })

        users.insert({'name': 'ann'})
        logs.insert({'msg': 'created ann'})
        users.insert({'name': 'ben'})
        snapshot('users', 'logs')
        db.drop_table('logs')
        snapshot('users', 'logs')
        db.drop_tables()
        snapshot()
        db.table('users').insert({'name': 'cy'})
        snapshot('users')
        db.close()
        other = TinyDB(path)
        result = {
            'steps': steps,
            'new_instance': {'tables': sorted(other.tables()),
                             'users': docs(other.table('users').all())},
        }
        other.close()
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    ann = {'name': 'ann'}
    ben = {'name': 'ben'}
    cy = {'name': 'cy'}
    log = {'msg': 'created ann'}
    assert r.value['steps'] == [
        {'tables': ['logs', 'users'],
         'docs': {'users': [[1, ann], [2, ben]], 'logs': [[1, log]]}},
        {'tables': ['users'],
         'docs': {'users': [[1, ann], [2, ben]], 'logs': []}},
        {'tables': [], 'docs': {}},
        {'tables': ['users'],
         'docs': {'users': [[1, cy]]}},
    ]
    assert r.value['new_instance'] == {'tables': ['users'],
                                       'users': [[1, cy]]}


def test_multiple_tables_file_contents():
    # The operations of test_multiple_tables_reads, each in a new TinyDB
    # instance; the file is read right after each, with the database open
    body = textwrap.dedent('''
        path = os.path.join(fresh_dir('db'), 'db.json')
        operations = [
            ('insert_ann',
             lambda db: db.table('users').insert({'name': 'ann'})),
            ('insert_log',
             lambda db: db.table('logs').insert({'msg': 'created ann'})),
            ('insert_ben',
             lambda db: db.table('users').insert({'name': 'ben'})),
            ('drop_logs', lambda db: db.drop_table('logs')),
            ('drop_tables', lambda db: db.drop_tables()),
            ('insert_cy',
             lambda db: db.table('users').insert({'name': 'cy'})),
        ]
        result = []
        for name, operation in operations:
            db = TinyDB(path)
            step = {'name': name, 'error': attempt(lambda: operation(db))}
            step['hex'] = read_hex(path)
            step['close_error'] = attempt(db.close)
            result.append(step)
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    ann = {'name': 'ann'}
    ben = {'name': 'ben'}
    cy = {'name': 'cy'}
    log = {'msg': 'created ann'}
    contents = [[step['name'], _decode(step['hex'])] for step in r.value]
    assert contents == [
        ['insert_ann', {'valid': True, 'data': {'users': {'1': ann}}}],
        ['insert_log', {'valid': True,
                        'data': {'users': {'1': ann}, 'logs': {'1': log}}}],
        ['insert_ben', {'valid': True,
                        'data': {'users': {'1': ann, '2': ben},
                                 'logs': {'1': log}}}],
        ['drop_logs', {'valid': True,
                       'data': {'users': {'1': ann, '2': ben}}}],
        ['drop_tables', {'valid': True, 'data': {}}],
        ['insert_cy', {'valid': True, 'data': {'users': {'1': cy}}}],
    ], r.value
