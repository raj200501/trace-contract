"""
Hidden behavioural tests for CS-02 (condition llm_freeform): atomic writes
for ``tinydb.storages.JSONStorage``.

Requirements checked (inferred from the whole session, including the
coordinator's follow-up message):

  B1  A write that fails partway (e.g. the disk / file size limit is hit
      while the new data is being written, or the data can't be serialized
      or encoded) raises an error and leaves the database file
      byte-for-byte unchanged.
  B2  If the writing process is killed in the middle of a write, the
      database file still holds the complete previous version (never a
      half-written or spliced file).
  B3  Reads through the same JSONStorage object / TinyDB instance always
      return what was last successfully written: right after every write,
      and also after a write has failed.
  B4  The ``encoding`` argument and the extra json kwargs are honoured
      exactly as before: the file holds exactly
      ``json.dumps(data, **kwargs)`` encoded with ``encoding``, and it reads
      back correctly.
  B5  No temporary (or other extra) files are left next to the database
      file after successful writes; unrelated files in that directory are
      left untouched.
  B6  No temporary files are left behind when a write fails partway, and the
      same storage / TinyDB instance keeps working afterwards.
  B7  ``access_mode='r'`` still refuses writes with an OSError (IOError) and
      leaves the file unchanged.
  B8  A storage that is kept open for a long time (many writes) does not
      leak file descriptors.
  B9  Ordinary usage keeps working: relative database paths such as
      ``TinyDB('db.json')`` and ``create_dirs=True``.

Failure injection is implementation independent: a "full disk" is simulated
with RLIMIT_FSIZE (every write past the limit fails with EFBIG, whatever API
the implementation uses), and a crash mid-write by letting the kernel kill
the writing process with SIGXFSZ when it hits that limit.
"""

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_disk_full_write_keeps_old_file_and_leaves_no_temp_files": ["B1", "B6"],
    "test_tinydb_instance_keeps_working_after_disk_full_write": ["B1", "B3", "B6"],
    "test_killed_writer_never_leaves_partial_database_file": ["B2"],
    "test_storage_reads_back_every_write": ["B3"],
    "test_tinydb_instance_sees_its_own_writes": ["B3"],
    "test_written_bytes_honor_encoding_and_json_kwargs": ["B4", "B3"],
    "test_tinydb_json_kwargs_and_encoding_file_bytes": ["B4"],
    "test_no_leftover_files_after_successful_writes": ["B5"],
    "test_unserializable_data_leaves_file_and_directory_unchanged": ["B1", "B6"],
    "test_unencodable_data_leaves_file_and_directory_unchanged": ["B1", "B6"],
    "test_read_only_mode_still_rejects_writes": ["B7"],
    "test_long_lived_storage_does_not_leak_file_descriptors": ["B8", "B3"],
    "test_relative_paths_and_create_dirs_keep_working": ["B9", "B5"],
}


# Helpers available to every snippet. Everything is created below /tmp.
PRELUDE = r'''
import json
import os
import resource
import signal
import tempfile

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage


def new_dir():
    return tempfile.mkdtemp(prefix='cs02_', dir='/tmp')


def read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def listing(directory):
    return sorted(os.listdir(directory))


def attempt(fn):
    try:
        fn()
        return 'ok'
    except Exception as exc:
        return 'raised ' + type(exc).__name__


def with_file_size_limit(limit, fn):
    """Run fn() while no file may grow beyond `limit` bytes: every write past
    the limit fails with EFBIG (OSError), like on a full disk."""
    try:
        if signal.getsignal(signal.SIGXFSZ) != signal.SIG_IGN:
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
    try:
        return attempt(fn)
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
'''


SNIPPET_DISK_FULL = PRELUDE + r'''
d = new_dir()
path = os.path.join(d, 'db.json')
old = {'_default': {'1': {'value': 'old'}, '2': {'value': 'data'}}}
new = {'_default': {str(i): {'value': 'n' * 900, 'i': i} for i in range(300)}}

storage = JSONStorage(path)
storage.write(old)
old_bytes = read_bytes(path)

# ~280 KB of new data, but files can't grow beyond 64 KB
outcome = with_file_size_limit(64 * 1024, lambda: storage.write(new))

after = read_bytes(path)
result = {
    'outcome': outcome,
    'unchanged': after == old_bytes,
    'size_before': len(old_bytes),
    'size_after': len(after),
    'files': listing(d),
}
'''


SNIPPET_TINYDB_AFTER_DISK_FULL = PRELUDE + r'''
def names(db):
    try:
        return sorted(doc['name'] for doc in db.all())
    except Exception as exc:
        return 'raised ' + type(exc).__name__

d = new_dir()
path = os.path.join(d, 'db.json')
db = TinyDB(path)
db.insert({'name': 'a'})
db.insert({'name': 'b'})
before = read_bytes(path)

failed = with_file_size_limit(
    64 * 1024, lambda: db.insert({'name': 'big', 'blob': 'x' * 300000}))
unchanged = read_bytes(path) == before
files_after_failure = listing(d)
names_after_failure = names(db)

# The "disk" has space again: the same instance must keep working
second = attempt(lambda: db.insert({'name': 'c', 'blob': 'y' * 300000}))
names_after_success = names(db)
files_after_success = listing(d)
db.close()

reopened = TinyDB(path)
names_reopened = names(reopened)
reopened.close()

result = {
    'failed': failed,
    'unchanged': unchanged,
    'files_after_failure': files_after_failure,
    'names_after_failure': names_after_failure,
    'second': second,
    'names_after_success': names_after_success,
    'files_after_success': files_after_success,
    'names_reopened': names_reopened,
}
'''


SNIPPET_KILLED_WRITER = PRELUDE + r'''
import subprocess
import sys

CHILD = """
import ctypes, os, resource, signal, sys
from tinydb.storages import JSONStorage

storage = JSONStorage(sys.argv[1])
new = {'_default': {str(i): {'value': 'n' * 900, 'i': i} for i in range(300)}}
try:
    ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE=0: no core dump
except Exception:
    pass
# The kernel kills this process (SIGXFSZ) as soon as it writes past 64 KB,
# i.e. while the ~280 KB of new data is being written
signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024, hard))
storage.write(new)
os._exit(0)
"""

scenarios = {
    'small_old_file': {'_default': {'1': {'value': 'old'}}},
    'large_old_file': {'_default': {str(i): {'old': 'o' * 700}
                                    for i in range(400)}},
}
result = {}
for label, old in scenarios.items():
    d = new_dir()
    path = os.path.join(d, 'db.json')
    storage = JSONStorage(path)
    storage.write(old)
    storage.close()
    old_bytes = read_bytes(path)

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-c', CHILD, path], cwd=d,
                          env=env, capture_output=True, text=True,
                          timeout=60)

    after = read_bytes(path)
    try:
        fresh = JSONStorage(path)
        reread_old = fresh.read() == old
        fresh.close()
    except Exception as exc:
        reread_old = 'raised ' + type(exc).__name__

    result[label] = {
        'returncode': proc.returncode,
        'killed_mid_write': proc.returncode == -signal.SIGXFSZ,
        'stderr': proc.stderr[-400:],
        'unchanged': after == old_bytes,
        'reread_old': reread_old,
    }
'''


SNIPPET_STORAGE_READ_BACK = PRELUDE + r'''
d = new_dir()
path = os.path.join(d, 'db.json')
storage = JSONStorage(path)

checks = []
last = None
for round_no, n in enumerate([5, 40, 0, 12, 3, 200, 1]):
    data = {
        '_default': {str(i): {'r': round_no, 'i': i, 'pad': 'p' * (i % 17)}
                     for i in range(n)},
        'other': {'1': {'round': round_no}},
    }
    storage.write(data)
    first = storage.read()
    second = storage.read()
    checks.append([first == data, second == data])
    last = data
storage.close()

again = JSONStorage(path)
persisted = again.read() == last
again.close()

result = {'checks': checks, 'persisted': persisted}
'''


SNIPPET_TINYDB_OWN_WRITES = PRELUDE + r'''
d = new_dir()
path = os.path.join(d, 'db.json')
q = Query()
db = TinyDB(path)
seen = []

db.insert({'name': 'alice', 'n': 1})
seen.append(sorted(doc['name'] for doc in db.all()))
db.insert_multiple([{'name': 'bob', 'n': 2}, {'name': 'carol', 'n': 3}])
seen.append(len(db))
db.update({'n': 20}, q.name == 'bob')
seen.append(db.get(q.name == 'bob')['n'])
db.remove(q.name == 'alice')
seen.append(sorted(doc['name'] for doc in db.all()))
log = db.table('log')
log.insert({'event': 'e' * 5000})
seen.append([len(log), sorted(db.tables())])
log.truncate()
seen.append(len(log))
db.upsert({'name': 'dave', 'n': 4}, q.name == 'dave')
seen.append(sorted([doc['name'], doc['n']] for doc in db.search(q.n > 2)))
db.drop_table('log')
seen.append(sorted(db.tables()))
db.truncate()
seen.append([dict(doc) for doc in db.all()])
db.insert({'name': 'erin', 'n': 5})
seen.append([dict(doc) for doc in db.all()])
db.close()

reopened = TinyDB(path)
final = [dict(doc) for doc in reopened.all()]
reopened.close()

result = {'seen': seen, 'final': final}
'''


SNIPPET_ENCODING_AND_KWARGS = PRELUDE + r'''
import datetime

JAPANESE = 'こんにちは世界'
combos = [
    ('default', None, {}),
    ('default-indent-sorted', None, {'indent': 4, 'sort_keys': True}),
    ('utf-8', 'utf-8', {'ensure_ascii': False, 'indent': 2}),
    ('utf-16', 'utf-16', {'ensure_ascii': False}),
    ('utf-16-indent', 'utf-16', {'ensure_ascii': False, 'indent': 4}),
    ('utf-8-sig', 'utf-8-sig', {'ensure_ascii': False, 'sort_keys': True}),
    ('cp936', 'cp936', {'ensure_ascii': False, 'indent': 2,
                        'separators': (',', ': ')}),
    ('cp037', 'cp037', {'sort_keys': True}),
    ('latin-1', 'latin-1', {'ensure_ascii': False, 'separators': (',', ':')}),
    ('default-callable', 'utf-8', {'default': str, 'sort_keys': True}),
]

result = {}
for label, encoding, kwargs in combos:
    d = new_dir()
    path = os.path.join(d, 'db.json')
    text = 'café ü' if encoding == 'latin-1' else JAPANESE
    storage = JSONStorage(path, encoding=encoding, **kwargs)
    rows = []
    for n in [3, 1, 6, 0, 2]:
        docs = {}
        for k in range(n):
            doc = {'text': text, 'k': k, 'z': [True, None, 1.5], 'a': {'b': k}}
            if label == 'default-callable':
                doc['when'] = datetime.date(2024, 1, k + 1)
            docs[str(k)] = doc
        data = {'_default': docs}
        storage.write(data)

        serialized = json.dumps(data, **kwargs)
        expected = serialized.encode(encoding or 'ascii')
        raw = read_bytes(path)
        try:
            read_back = storage.read() == json.loads(serialized)
        except Exception as exc:
            read_back = 'raised ' + type(exc).__name__
        rows.append({'bytes_equal': raw == expected, 'read_back': read_back,
                     'raw_head': raw[:40].hex(), 'expected_head': expected[:40].hex()})
    storage.close()
    result[label] = rows
'''


SNIPPET_TINYDB_KWARGS = PRELUDE + r'''
d = new_dir()
checks = {}

path = os.path.join(d, 'db.json')
kw = {'sort_keys': True, 'indent': 4, 'separators': (',', ': ')}
db = TinyDB(path, **kw)
db.insert({'b': 1})
db.insert({'a': 1})
checks['two_inserts'] = read_bytes(path) == (
    b'{\n    "_default": {\n        "1": {\n            "b": 1\n        },\n'
    b'        "2": {\n            "a": 1\n        }\n    }\n}')
db.update({'c': 2}, doc_ids=[1])
checks['update'] = read_bytes(path) == json.dumps(
    {'_default': {'1': {'b': 1, 'c': 2}, '2': {'a': 1}}}, **kw).encode('ascii')
db.remove(doc_ids=[2])
checks['remove'] = read_bytes(path) == json.dumps(
    {'_default': {'1': {'b': 1, 'c': 2}}}, **kw).encode('ascii')
checks['read_back'] = [dict(doc) for doc in db.all()] == [{'b': 1, 'c': 2}]
db.close()

path2 = os.path.join(d, 'utf16.json')
kw2 = {'ensure_ascii': False, 'indent': 2}
hello, world = 'こんにちは', '世界'
db2 = TinyDB(path2, encoding='utf-16', **kw2)
db2.insert({'name': hello})
db2.insert({'name': world, 'n': 2})
expected = {'_default': {'1': {'name': hello}, '2': {'name': world, 'n': 2}}}
checks['utf16_inserts'] = (
    read_bytes(path2) == json.dumps(expected, **kw2).encode('utf-16'))
db2.table('extra').insert({'x': 'café'})
expected['extra'] = {'1': {'x': 'café'}}
checks['utf16_second_table'] = (
    read_bytes(path2) == json.dumps(expected, **kw2).encode('utf-16'))
checks['utf16_read_back'] = (
    sorted(doc['name'] for doc in db2.all()) == sorted([hello, world]))
db2.close()

result = checks
'''


SNIPPET_NO_LEFTOVERS = PRELUDE + r'''
d = new_dir()
unrelated = {
    'notes.txt': b'my notes',
    'other.json': b'{"_default": {"1": {"x": 1}}}',
    'scratch.tmp': b'scratch data',
    '.hidden': b'hidden',
}
for name, content in unrelated.items():
    with open(os.path.join(d, name), 'wb') as handle:
        handle.write(content)
expected_listing = sorted(list(unrelated) + ['db.json'])

path = os.path.join(d, 'db.json')
listings = []
storage = JSONStorage(path, indent=2)
for n in [3, 50, 0, 7]:
    storage.write({'_default': {str(i): {'i': i} for i in range(n)}})
    listings.append(listing(d))
storage.close()
listings.append(listing(d))

db = TinyDB(path)
for i in range(5):
    db.insert({'i': i, 'pad': 'x' * (1000 * i)})
    listings.append(listing(d))
db.update({'u': 1})
listings.append(listing(d))
db.remove(doc_ids=[1])
listings.append(listing(d))
db.truncate()
listings.append(listing(d))
db.close()
listings.append(listing(d))

untouched = all(read_bytes(os.path.join(d, name)) == content
                for name, content in unrelated.items())
result = {'listings': listings, 'expected': expected_listing,
          'untouched': untouched}
'''


SNIPPET_UNSERIALIZABLE = PRELUDE + r'''
d = new_dir()
path = os.path.join(d, 'db.json')
old = {'_default': {'1': {'value': 'old'}}}
storage = JSONStorage(path)
storage.write(old)
old_bytes = read_bytes(path)

rounds = []
for bad in (object(), {1, 2, 3}, b'raw bytes'):
    # A large serializable part comes first, so an implementation that
    # streams the JSON into a file fails halfway through the write
    data = {'_default': {'1': {'pad': 'x' * 70000}, '2': {'bad': bad}}}
    outcome = attempt(lambda: storage.write(data))
    try:
        read_old = storage.read() == old
    except Exception as exc:
        read_old = 'raised ' + type(exc).__name__
    rounds.append({'outcome': outcome,
                   'unchanged': read_bytes(path) == old_bytes,
                   'files': listing(d), 'read_old': read_old})

good = {'_default': {'1': {'value': 'good'}, '2': {'value': 'y' * 70000}}}
later = attempt(lambda: storage.write(good))
try:
    read_good = storage.read() == good
except Exception as exc:
    read_good = 'raised ' + type(exc).__name__
good_bytes = read_bytes(path) == json.dumps(good).encode('ascii')
files_after = listing(d)
storage.close()

result = {'rounds': rounds, 'later': later, 'read_good': read_good,
          'good_bytes': good_bytes, 'files_after': files_after}
'''


SNIPPET_UNENCODABLE = PRELUDE + r'''
d = new_dir()
path = os.path.join(d, 'db.json')
storage = JSONStorage(path, encoding='ascii', ensure_ascii=False)
old = {'_default': {'1': {'value': 'plain ascii'}}}
storage.write(old)
old_bytes = read_bytes(path)

# 'e with acute' can't be encoded as ASCII; it comes after a large
# encodable part, so streaming implementations fail halfway through
bad = {'_default': {'1': {'pad': 'x' * 70000}, '2': {'text': 'café'}}}
outcome = attempt(lambda: storage.write(bad))
unchanged = read_bytes(path) == old_bytes
files = listing(d)
try:
    read_old = storage.read() == old
except Exception as exc:
    read_old = 'raised ' + type(exc).__name__

good = {'_default': {'1': {'value': 'still ascii'}}}
later = attempt(lambda: storage.write(good))
try:
    read_good = storage.read() == good
except Exception as exc:
    read_good = 'raised ' + type(exc).__name__
good_bytes = read_bytes(path) == json.dumps(good, ensure_ascii=False).encode('ascii')
files_after = listing(d)
storage.close()

result = {'outcome': outcome, 'unchanged': unchanged, 'files': files,
          'read_old': read_old, 'later': later, 'read_good': read_good,
          'good_bytes': good_bytes, 'files_after': files_after}
'''


SNIPPET_READ_ONLY = PRELUDE + r'''
def write_outcome(fn):
    try:
        fn()
        return 'no error'
    except OSError:
        return 'OSError'
    except Exception as exc:
        return 'other ' + type(exc).__name__

d = new_dir()
path = os.path.join(d, 'db.json')
data = {'_default': {'1': {'a': 1}, '2': {'b': 2}}}
storage = JSONStorage(path)
storage.write(data)
storage.close()
old_bytes = read_bytes(path)

ro = JSONStorage(path, access_mode='r')
read_before = ro.read() == data
storage_write = write_outcome(lambda: ro.write({'_default': {}}))
read_after = ro.read() == data
ro.close()
unchanged_1 = read_bytes(path) == old_bytes
files_1 = listing(d)

db = TinyDB(path, access_mode='r')
insert = write_outcome(lambda: db.insert({'c': 3}))
docs = sorted(sorted(doc.items()) for doc in db.all())
db.close()
unchanged_2 = read_bytes(path) == old_bytes
files_2 = listing(d)

result = {'read_before': read_before, 'storage_write': storage_write,
          'read_after': read_after, 'unchanged_1': unchanged_1,
          'files_1': files_1, 'insert': insert, 'docs': docs,
          'unchanged_2': unchanged_2, 'files_2': files_2}
'''


SNIPPET_FD_LEAK = PRELUDE + r'''
import gc

def open_fds():
    return len(os.listdir('/proc/self/fd'))

d = new_dir()
path = os.path.join(d, 'db.json')
storage = JSONStorage(path)
storage.write({'_default': {}})
storage.read()
gc.collect()
before = open_fds()
mismatches = 0
for i in range(150):
    data = {'_default': {str(j): {'i': i, 'j': j} for j in range(i % 13)}}
    storage.write(data)
    if storage.read() != data:
        mismatches += 1
gc.collect()
after = open_fds()
storage.close()

path2 = os.path.join(d, 'tiny.json')
db = TinyDB(path2)
db.all()
gc.collect()
before_db = open_fds()
for i in range(60):
    db.insert({'i': i})
count = len(db)
gc.collect()
after_db = open_fds()
db.close()

result = {'mismatches': mismatches, 'storage_growth': after - before,
          'count': count, 'tinydb_growth': after_db - before_db}
'''


SNIPPET_RELATIVE_PATHS = PRELUDE + r'''
d = new_dir()
os.chdir(d)

db = TinyDB('db.json')
db.insert({'name': 'relative'})
db.insert({'name': 'path'})
tinydb_docs = [dict(doc) for doc in db.all()]
db.close()
with open(os.path.join(d, 'db.json')) as handle:
    on_disk = json.load(handle)

storage = JSONStorage('db.json', indent=2)
data = {'_default': {'1': {'v': 1}}}
storage.write(data)
storage_read = storage.read() == data
storage.close()
storage_bytes = read_bytes(os.path.join(d, 'db.json')) == json.dumps(
    data, indent=2).encode('ascii')

nested = os.path.join('nested', 'deeper', 'data.json')
db2 = TinyDB(nested, create_dirs=True)
db2.insert({'n': 1})
db2.insert({'n': 2})
nested_docs = [dict(doc) for doc in db2.all()]
db2.close()
with open(os.path.join(d, 'nested', 'deeper', 'data.json')) as handle:
    nested_on_disk = json.load(handle)

result = {
    'tinydb_docs': tinydb_docs,
    'on_disk': on_disk,
    'storage_read': storage_read,
    'storage_bytes': storage_bytes,
    'nested_docs': nested_docs,
    'nested_on_disk': nested_on_disk,
    'root_listing': listing(d),
    'nested_listing': listing(os.path.join(d, 'nested', 'deeper')),
}
'''


def _describe(r):
    return 'error_type=%r error=%r stderr=%r' % (r.error_type, r.error,
                                                 (r.stderr or '')[-2000:])


def test_disk_full_write_keeps_old_file_and_leaves_no_temp_files():
    r = run_python(SNIPPET_DISK_FULL, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    # The write could not complete, so the caller must learn about it...
    assert v['outcome'].startswith('raised'), v
    # ...the database file is exactly the old version...
    assert v['unchanged'] is True, v
    # ...and no temporary file is left next to it
    assert v['files'] == ['db.json'], v


def test_tinydb_instance_keeps_working_after_disk_full_write():
    r = run_python(SNIPPET_TINYDB_AFTER_DISK_FULL, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['failed'].startswith('raised'), v
    assert v['unchanged'] is True, v
    assert v['files_after_failure'] == ['db.json'], v
    # The same instance still reads the last successfully written state
    assert v['names_after_failure'] == ['a', 'b'], v
    # ...and later writes through it work again
    assert v['second'] == 'ok', v
    assert v['names_after_success'] == ['a', 'b', 'c'], v
    assert v['files_after_success'] == ['db.json'], v
    assert v['names_reopened'] == ['a', 'b', 'c'], v


def test_killed_writer_never_leaves_partial_database_file():
    r = run_python(SNIPPET_KILLED_WRITER, timeout=120.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert sorted(v) == ['large_old_file', 'small_old_file'], v
    for label, outcome in v.items():
        # Sanity check: the writer really died while writing the new data
        assert outcome['killed_mid_write'] is True, (label, outcome)
        # The file is still exactly the old version, readable as before
        assert outcome['unchanged'] is True, (label, outcome)
        assert outcome['reread_old'] is True, (label, outcome)


def test_storage_reads_back_every_write():
    r = run_python(SNIPPET_STORAGE_READ_BACK, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['checks'] == [[True, True]] * 7, v
    assert v['persisted'] is True, v


def test_tinydb_instance_sees_its_own_writes():
    r = run_python(SNIPPET_TINYDB_OWN_WRITES, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['seen'] == [
        ['alice'],
        3,
        20,
        ['bob', 'carol'],
        [1, ['_default', 'log']],
        0,
        [['bob', 20], ['carol', 3], ['dave', 4]],
        ['_default'],
        [],
        [{'name': 'erin', 'n': 5}],
    ], v
    assert v['final'] == [{'name': 'erin', 'n': 5}], v


def test_written_bytes_honor_encoding_and_json_kwargs():
    r = run_python(SNIPPET_ENCODING_AND_KWARGS, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert len(v) == 10, sorted(v)
    for label, rows in v.items():
        assert len(rows) == 5, (label, rows)
        for row in rows:
            assert row['bytes_equal'] is True, (label, row)
            assert row['read_back'] is True, (label, row)


def test_tinydb_json_kwargs_and_encoding_file_bytes():
    r = run_python(SNIPPET_TINYDB_KWARGS, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v == {
        'two_inserts': True,
        'update': True,
        'remove': True,
        'read_back': True,
        'utf16_inserts': True,
        'utf16_second_table': True,
        'utf16_read_back': True,
    }, v


def test_no_leftover_files_after_successful_writes():
    r = run_python(SNIPPET_NO_LEFTOVERS, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['expected'] == ['.hidden', 'db.json', 'notes.txt', 'other.json',
                             'scratch.tmp'], v
    assert len(v['listings']) == 14, v
    for observed in v['listings']:
        assert observed == v['expected'], v
    assert v['untouched'] is True, v


def test_unserializable_data_leaves_file_and_directory_unchanged():
    r = run_python(SNIPPET_UNSERIALIZABLE, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert len(v['rounds']) == 3, v
    for round_ in v['rounds']:
        assert round_['outcome'].startswith('raised'), round_
        assert round_['unchanged'] is True, round_
        assert round_['files'] == ['db.json'], round_
        assert round_['read_old'] is True, round_
    assert v['later'] == 'ok', v
    assert v['read_good'] is True, v
    assert v['good_bytes'] is True, v
    assert v['files_after'] == ['db.json'], v


def test_unencodable_data_leaves_file_and_directory_unchanged():
    r = run_python(SNIPPET_UNENCODABLE, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['outcome'].startswith('raised'), v
    assert v['unchanged'] is True, v
    assert v['files'] == ['db.json'], v
    assert v['read_old'] is True, v
    assert v['later'] == 'ok', v
    assert v['read_good'] is True, v
    assert v['good_bytes'] is True, v
    assert v['files_after'] == ['db.json'], v


def test_read_only_mode_still_rejects_writes():
    r = run_python(SNIPPET_READ_ONLY, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['read_before'] is True, v
    assert v['storage_write'] == 'OSError', v
    assert v['read_after'] is True, v
    assert v['unchanged_1'] is True, v
    assert v['files_1'] == ['db.json'], v
    assert v['insert'] == 'OSError', v
    assert v['docs'] == [[['a', 1]], [['b', 2]]], v
    assert v['unchanged_2'] is True, v
    assert v['files_2'] == ['db.json'], v


def test_long_lived_storage_does_not_leak_file_descriptors():
    r = run_python(SNIPPET_FD_LEAK, timeout=90.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['mismatches'] == 0, v
    assert v['count'] == 60, v
    # 150 / 60 writes: the number of open descriptors must not keep growing
    assert v['storage_growth'] <= 3, v
    assert v['tinydb_growth'] <= 3, v


def test_relative_paths_and_create_dirs_keep_working():
    r = run_python(SNIPPET_RELATIVE_PATHS, timeout=60.0)
    assert not r.timed_out
    assert r.ok, _describe(r)
    v = r.value
    assert v['tinydb_docs'] == [{'name': 'relative'}, {'name': 'path'}], v
    assert v['on_disk'] == {'_default': {'1': {'name': 'relative'},
                                         '2': {'name': 'path'}}}, v
    assert v['storage_read'] is True, v
    assert v['storage_bytes'] is True, v
    assert v['nested_docs'] == [{'n': 1}, {'n': 2}], v
    assert v['nested_on_disk'] == {'_default': {'1': {'n': 1},
                                                '2': {'n': 2}}}, v
    assert v['root_listing'] == ['db.json', 'nested'], v
    assert v['nested_listing'] == ['data.json'], v
