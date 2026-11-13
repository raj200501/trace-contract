"""
Hidden behavioural tests for CS-02 (condition full_plain): atomic writes of
tinydb's ``JSONStorage``.

All candidate code runs in the sandbox through ``tc_sandbox.run_python``.  Each
snippet is wrapped into a ``_main()`` function so it does not depend on how the
sandbox executes it, and it only returns small summaries (booleans, short
strings) of what it observed.

Failures are injected without relying on how a candidate writes its files:

* Disk full: ``RLIMIT_FSIZE`` is lowered (with SIGXFSZ ignored, which is
  CPython's default) so that *any* ``write(2)`` beyond the limit fails with
  ``OSError(EFBIG)``, whichever Python API the candidate uses to write.  In a
  child process with SIGXFSZ at its default action, the same limit kills the
  process in the middle of writing the data.
* ``os.fsync``/``os.fdatasync`` and ``os.replace``/``os.rename`` are wrapped
  *before* tinydb is imported (so ``from os import replace`` is wrapped too)
  and only fail (or kill the process) while armed.
"""

import json
import textwrap

from tc_sandbox import run_python


CHECK_REQUIREMENTS = {
    "test_process_killed_mid_write_leaves_complete_old_or_new_json": ["R1"],
    "test_failed_write_never_leaves_partial_json": ["R1"],
    "test_write_swaps_in_temporary_file_via_rename": ["R2"],
    "test_read_after_write_on_long_lived_storage": ["R3"],
    "test_tinydb_changes_immediately_visible_on_same_instance": ["R3"],
    "test_encoding_bytes_identical_to_original_implementation": ["R4"],
    "test_json_kwargs_forwarded_exactly": ["R5"],
    "test_successful_writes_leave_no_temporary_files": ["R6"],
    "test_failed_write_leaves_no_temporary_files": ["R7"],
    "test_failed_write_keeps_database_file_byte_identical": ["R8"],
    "test_storage_usable_after_failed_write": ["R9"],
    "test_tinydb_usable_after_failed_write": ["R9"],
    "test_no_file_descriptor_leak_over_many_writes": ["R10"],
}


# ---------------------------------------------------------------------------
# Snippet building blocks (plain code, wrapped into ``def _main():``)
# ---------------------------------------------------------------------------

PIECE_COMMON = r'''
import errno
import gc
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile

ARMED = set()


def make_failing(real, kind):
    def wrapper(*args, **kwargs):
        if kind in ARMED:
            raise OSError(errno.ENOSPC, 'No space left on device')
        return real(*args, **kwargs)
    return wrapper


def install_failure_hooks():
    # Called before tinydb is imported, so that names bound with
    # "from os import ..." are wrapped as well.
    for name in ('fsync', 'fdatasync'):
        if hasattr(os, name):
            setattr(os, name, make_failing(getattr(os, name), 'fsync'))
    for name in ('replace', 'rename'):
        setattr(os, name, make_failing(getattr(os, name), 'rename'))


class FileSizeLimit(object):
    # Any write beyond `limit` bytes of a file fails with OSError(EFBIG).
    def __init__(self, limit):
        self.limit = limit
        self.handler = None
        self.soft = None
        self.hard = None

    def __enter__(self):
        try:
            self.handler = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        except ValueError:
            self.handler = None
        self.soft, self.hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        resource.setrlimit(resource.RLIMIT_FSIZE, (self.limit, self.hard))
        return self

    def __exit__(self, *exc_info):
        resource.setrlimit(resource.RLIMIT_FSIZE, (self.soft, self.hard))
        if self.handler is not None:
            signal.signal(signal.SIGXFSZ, self.handler)
        return False


def read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def load_json(path):
    try:
        return True, json.loads(read_bytes(path).decode('utf-8'))
    except Exception:
        return False, None


def classify(path, old, new):
    if not os.path.exists(path):
        return 'missing'
    valid, value = load_json(path)
    if not valid:
        return 'invalid'
    if value == old:
        return 'old'
    if new is not None and value == new:
        return 'new'
    return 'other'


def head_of(path):
    if not os.path.exists(path):
        return ''
    return read_bytes(path)[:60].decode('utf-8', 'replace')


def docs_of(state):
    return list(state.get('_default', {}).values())


def make_state(count, pad, tag):
    return {'_default': {
        str(i): {'n': i, 'tag': tag, 'pad': pad * (1 + i % 3)}
        for i in range(1, count + 1)
    }}


def describe(exc):
    return '%s: %s' % (type(exc).__name__, str(exc)[:200])


def attempt(func):
    try:
        func()
    except Exception as exc:
        return describe(exc)
    return None


def short(value):
    text = repr(value)
    return text if len(text) <= 160 else text[:160] + '...'


def new_dir(tag):
    return tempfile.mkdtemp(prefix='cs02-%s-' % tag)


def tinydb_docs(TinyDB, path):
    try:
        db = TinyDB(path)
        try:
            return [dict(doc) for doc in db.all()]
        finally:
            db.close()
    except Exception as exc:
        return 'error: ' + describe(exc)


OLD_BIG = make_state(60, 'x' * 150, 'old')
OLD_SMALL = {'_default': {'1': {'n': 1, 'tag': 'old', 'pad': 'tiny'}}}
NEW_EMPTY = {'_default': {}}
NEW_MID = make_state(12, 'y' * 120, 'new')
NEW_BIG = make_state(80, 'z' * 200, 'new')
'''


PIECE_FAILURE_SCENARIOS = r'''
install_failure_hooks()
from tinydb import TinyDB
from tinydb.storages import JSONStorage

UNSERIALIZABLE = make_state(30, 'u' * 40, 'bad')
UNSERIALIZABLE['_default']['31'] = {'n': 31, 'bad': object()}

SCENARIOS = {
    # smaller new state over a larger old one, the disk fills up while
    # writing the new data
    'disk_full_shrinking': (OLD_BIG, NEW_MID, 'fsize', 1024),
    # larger new state over a smaller old one
    'disk_full_growing': (OLD_SMALL, NEW_BIG, 'fsize', 4096),
    'fsync_fails': (OLD_BIG, NEW_EMPTY, 'fsync', None),
    'rename_fails': (OLD_BIG, NEW_EMPTY, 'rename', None),
    'unserializable': (OLD_BIG, UNSERIALIZABLE, 'value', None),
}


def run_scenario(name):
    old, new, how, limit = SCENARIOS[name]
    directory = new_dir('fail')
    path = os.path.join(directory, 'db.json')
    storage = JSONStorage(path)
    storage.write(old)
    before = read_bytes(path)
    stat_before = os.stat(path)
    listing_before = sorted(os.listdir(directory))
    error = None
    try:
        if how == 'fsize':
            with FileSizeLimit(limit):
                storage.write(new)
        elif how in ('fsync', 'rename'):
            ARMED.add(how)
            try:
                storage.write(new)
            finally:
                ARMED.discard(how)
        else:
            storage.write(new)
    except Exception as exc:
        error = describe(exc)
    listing_after = sorted(os.listdir(directory))
    exists = os.path.exists(path)
    after = read_bytes(path) if exists else b''
    stat_after = os.stat(path) if exists else None
    state = classify(path, old, None if how == 'value' else new)
    head = head_of(path)
    try:
        storage.close()
    except Exception:
        pass
    docs = tinydb_docs(TinyDB, path)
    shutil.rmtree(directory, ignore_errors=True)
    return {
        'raised': error is not None,
        'error': error,
        'listing_before': listing_before,
        'listing_after': listing_after,
        'exists': exists,
        'bytes_same': after == before,
        'inode_same': stat_after is not None and (
            (stat_after.st_dev, stat_after.st_ino)
            == (stat_before.st_dev, stat_before.st_ino)),
        'size_same': stat_after is not None
        and stat_after.st_size == stat_before.st_size,
        'state': state,
        'tinydb_loads_old': docs == docs_of(old),
        'tinydb_loads_new': how != 'value' and docs == docs_of(new),
        'tinydb_result': short(docs),
        'file_head': head,
    }


return {name: run_scenario(name) for name in PARAMS['scenarios']}
'''


CRASH_CHILD = r'''
import json
import os
import resource
import signal
import sys

mode, path, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
states = json.loads(sys.stdin.read())
armed = []


def die_when_armed(real):
    def wrapper(*args, **kwargs):
        if armed:
            os._exit(23)
        return real(*args, **kwargs)
    return wrapper


hooked = {'fsync': ('fsync', 'fdatasync'), 'rename': ('replace', 'rename')}
for name in hooked.get(mode, ()):
    if hasattr(os, name):
        setattr(os, name, die_when_armed(getattr(os, name)))

from tinydb.storages import JSONStorage

storage = JSONStorage(path)
storage.write(states['old'])

if mode == 'fsize':
    # SIGXFSZ with its default action (no core dump): the process dies as
    # soon as any file is written beyond `limit` bytes, i.e. in the middle of
    # writing the new data.
    soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
    resource.setrlimit(resource.RLIMIT_CORE, (0, hard))
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
else:
    armed.append(True)

try:
    storage.write(states['new'])
except BaseException:
    os._exit(3)
os._exit(0)
'''


PIECE_CRASH = r'''
from tinydb import TinyDB

CASES = [
    ('fsync', OLD_BIG, NEW_EMPTY, 0),
    ('rename', OLD_BIG, NEW_EMPTY, 0),
    ('fsize', OLD_BIG, NEW_MID, 1024),
    ('fsize', OLD_SMALL, NEW_BIG, 4096),
]
outcomes = []
for mode, old, new, limit in CASES:
    directory = new_dir('crash')
    path = os.path.join(directory, 'db.json')
    proc = subprocess.run(
        [sys.executable, '-c', PARAMS['child'], mode, path, str(limit)],
        input=json.dumps({'old': old, 'new': new}).encode('utf-8'),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    )
    state = classify(path, old, new)
    head = head_of(path)
    docs = tinydb_docs(TinyDB, path)
    outcomes.append({
        'mode': mode,
        'limit': limit,
        'returncode': proc.returncode,
        'stderr': proc.stderr.decode('utf-8', 'replace')[-600:],
        'state': state,
        'file_head': head,
        'tinydb_loads_old': docs == docs_of(old),
        'tinydb_loads_new': docs == docs_of(new),
        'tinydb_result': short(docs),
    })
    shutil.rmtree(directory, ignore_errors=True)
return outcomes
'''


PIECE_RENAME = r'''
CALLS = []
FAIL = []


def resolve(name, dir_fd):
    name = os.fsdecode(os.fspath(name))
    if dir_fd is not None and not os.path.isabs(name):
        name = os.path.join(os.readlink('/proc/self/fd/%d' % dir_fd), name)
    return os.path.realpath(name)


def recording(real, label):
    def wrapper(src, dst, *args, **kwargs):
        try:
            source = resolve(src, kwargs.get('src_dir_fd'))
            target = resolve(dst, kwargs.get('dst_dir_fd'))
            try:
                content = read_bytes(source)
            except OSError:
                content = None
            CALLS.append((label, source, target, content))
        except Exception:
            pass
        if FAIL:
            raise OSError(errno.ENOSPC, 'No space left on device')
        return real(src, dst, *args, **kwargs)
    return wrapper


os.replace = recording(os.replace, 'replace')
os.rename = recording(os.rename, 'rename')

from tinydb.storages import JSONStorage

directory = new_dir('rename')
path = os.path.join(directory, 'db.json')
real_path = os.path.realpath(path)
storage = JSONStorage(path)
records = []
for data in (OLD_BIG, NEW_MID, NEW_BIG, OLD_SMALL):
    inode_before = os.stat(path).st_ino
    del CALLS[:]
    storage.write(data)
    inode_after = os.stat(path).st_ino
    final = read_bytes(path)
    swaps = [call for call in CALLS
             if call[2] == real_path and call[1] != real_path]
    records.append({
        'inode_changed': inode_before != inode_after,
        'calls': [[call[0], call[1], call[2]] for call in CALLS][:6],
        'swap_count': len(swaps),
        'swap_source_held_new_data': any(call[3] == final for call in swaps),
        'file_holds_data': load_json(path) == (True, data),
    })
old_bytes = read_bytes(path)
FAIL.append(True)
try:
    failed_write_error = attempt(lambda: storage.write(NEW_EMPTY))
finally:
    del FAIL[:]
kept = read_bytes(path) == old_bytes
try:
    storage.close()
except Exception:
    pass
shutil.rmtree(directory, ignore_errors=True)
return {
    'records': records,
    'failed_write_error': failed_write_error,
    'old_kept_after_failed_rename': kept,
}
'''


PIECE_READ_AFTER_WRITE = r'''
from tinydb.storages import JSONStorage

directory = new_dir('rw')
path = os.path.join(directory, 'db.json')
storage = JSONStorage(path)
sequence = [
    OLD_BIG,
    NEW_EMPTY,
    {'_default': {'1': {
        'text': 'Grüße 日本 \U0001f600',
        'list': [1, 2.5, None, True, 'x'],
        'nested': {'a': {'b': []}},
    }}},
    NEW_BIG,
    {},
    OLD_SMALL,
    {'_default': {'1': {'v': 1}}, 'second': {'1': {'v': 2}, '2': {'v': 3}}},
    NEW_MID,
    {'_default': {'1': {'v': 1}}},
]
for i in range(40):
    sequence.append(make_state(i % 11, 'r' * (i * 7 % 50 + 1), 'loop-%d' % i))
mismatches = []
for index, data in enumerate(sequence):
    storage.write(data)
    first = storage.read()
    second = storage.read()
    if first != data or second != data:
        mismatches.append({
            'index': index,
            'expected': short(data),
            'first_read': short(first),
            'second_read': short(second),
        })
storage.close()
shutil.rmtree(directory, ignore_errors=True)
return {'checked': len(sequence), 'mismatches': mismatches[:5],
        'mismatch_count': len(mismatches)}
'''


PIECE_TINYDB_VISIBLE = r'''
from tinydb import TinyDB, Query

directory = new_dir('db')
path = os.path.join(directory, 'db.json')
db = TinyDB(path)
query = Query()
log = []


def check(label, expected_docs, expected_tables=None):
    docs = [dict(doc) for doc in db.all()]
    ids = [str(doc.doc_id) for doc in db.all()]
    stored = db.storage.read()
    table = (stored or {}).get('_default', {})
    entry = {
        'label': label,
        'docs_ok': docs == expected_docs,
        'storage_docs_ok': list(table.values()) == expected_docs,
        'storage_ids_ok': list(table.keys()) == ids,
        'len_ok': len(db) == len(expected_docs),
        'docs': short(docs),
        'stored': short(stored),
    }
    if expected_tables is not None:
        entry['tables_ok'] = (sorted(stored or {}) == sorted(expected_tables)
                              and sorted(db.tables()) == sorted(expected_tables))
    log.append(entry)


zoe = 'Zoë'
db.insert({'a': 1})
check('insert', [{'a': 1}])
db.insert({'a': 2, 'name': zoe})
check('second insert', [{'a': 1}, {'a': 2, 'name': zoe}])
db.update({'flag': True}, query.a == 1)
check('update', [{'a': 1, 'flag': True}, {'a': 2, 'name': zoe}])
db.insert_multiple([{'a': 3}, {'a': 4}])
check('insert_multiple', [{'a': 1, 'flag': True}, {'a': 2, 'name': zoe},
                          {'a': 3}, {'a': 4}])
db.remove(query.a == 2)
check('remove', [{'a': 1, 'flag': True}, {'a': 3}, {'a': 4}])
db.table('other').insert({'x': [1, 2, 3]})
check('other table', [{'a': 1, 'flag': True}, {'a': 3}, {'a': 4}],
      ['_default', 'other'])
search = [dict(doc) for doc in db.search(query.a >= 3)]
db.upsert({'a': 5}, query.a == 4)
check('upsert', [{'a': 1, 'flag': True}, {'a': 3}, {'a': 5}])
search_after = [dict(doc) for doc in db.search(query.a >= 3)]
db.truncate()
check('truncate', [])
db.insert({'a': 6})
check('insert after truncate', [{'a': 6}])
other = [dict(doc) for doc in db.table('other').all()]
db.close()
shutil.rmtree(directory, ignore_errors=True)
return {'log': log, 'search': search, 'search_after': search_after,
        'other': other}
'''


PIECE_ENCODINGS = r'''
from tinydb.storages import JSONStorage

UNICODE_TEXT = ('Grüße, 日本語のテキス'
                'ト, emoji \U0001f600, ñ, “quotes”')
LATIN_TEXT = ('Grüße, café, señor, ¿qué?, '
              '© £ µ ß ÿ')
CP1252_TEXT = ('Grüße, café, € 10, „quote“ '
               '– dash, œ')
CASES = [
    (None, UNICODE_TEXT),
    ('utf-8', UNICODE_TEXT),
    ('utf-8-sig', UNICODE_TEXT),
    ('utf-16', UNICODE_TEXT),
    ('utf-16-le', UNICODE_TEXT),
    ('latin-1', LATIN_TEXT),
    ('cp1252', CP1252_TEXT),
]
KWARGS = {'ensure_ascii': False}


def states_for(text):
    first = {
        '_default': {str(i): {'text': text, 'n': i, 'part': text[:i]}
                     for i in range(1, 7)},
        'extra': {'1': {text[:4]: text}},
    }
    second = {'_default': {'1': {'text': text[:6]}}}
    third = {'_default': {str(i): {'text': text + text, 'n': i}
                          for i in range(1, 4)}}
    return [first, second, third]


def original_bytes(sequence, encoding):
    # The bytes the original in-place JSONStorage.write produced for this
    # sequence of writes (same handle, seek(0) + write + flush + truncate).
    directory = new_dir('orig')
    path = os.path.join(directory, 'orig.json')
    with open(path, 'a'):
        pass
    handle = open(path, mode='r+', encoding=encoding)
    produced = []
    try:
        for data in sequence:
            handle.seek(0)
            handle.write(json.dumps(data, **KWARGS))
            handle.flush()
            handle.truncate()
            produced.append(read_bytes(path))
    finally:
        handle.close()
        shutil.rmtree(directory, ignore_errors=True)
    return produced


report = []
for encoding, text in CASES:
    sequence = states_for(text)
    expected = original_bytes(sequence, encoding)
    directory = new_dir('enc')
    path = os.path.join(directory, 'db.json')
    storage = JSONStorage(path, encoding=encoding, **KWARGS)
    steps = []
    for index, data in enumerate(sequence):
        error = attempt(lambda: storage.write(data))
        actual = read_bytes(path)
        try:
            own = storage.read() == data
        except Exception as exc:
            own = 'error: ' + describe(exc)
        try:
            fresh_storage = JSONStorage(path, encoding=encoding)
            try:
                fresh = fresh_storage.read() == data
            finally:
                fresh_storage.close()
        except Exception as exc:
            fresh = 'error: ' + describe(exc)
        steps.append({
            'write_error': error,
            'bytes_equal': actual == expected[index],
            'actual_len': len(actual),
            'expected_len': len(expected[index]),
            'actual_head': actual[:16].hex(),
            'expected_head': expected[index][:16].hex(),
            'expected_is_plain_encode': expected[index] == json.dumps(
                data, **KWARGS).encode(encoding or 'utf-8'),
            'read_ok': own,
            'fresh_read_ok': fresh,
        })
    try:
        storage.close()
    except Exception:
        pass
    shutil.rmtree(directory, ignore_errors=True)
    report.append({'encoding': encoding, 'steps': steps})
return report
'''


PIECE_KWARGS = r'''
from tinydb import TinyDB
from tinydb.storages import JSONStorage

TEXT = 'Grüße 日本 \U0001f600'
COMBOS = [
    (None, {'indent': 4, 'sort_keys': True}),
    (None, {'separators': (',', ':')}),
    (None, {'indent': '\t', 'separators': (',', ': '), 'sort_keys': True}),
    ('utf-8', {'ensure_ascii': False, 'indent': 2}),
    ('utf-8', {'ensure_ascii': False, 'sort_keys': True,
               'separators': (', ', ': ')}),
]
SEQUENCE = [
    {
        '_default': {str(i): {'zeta': i, 'alpha': TEXT,
                              'mid': [i, {'y': 1, 'b': 2}]}
                     for i in range(1, 9)},
        'b_table': {'1': {'k': 'v'}},
        'a_table': {},
    },
    {'_default': {'2': {'zeta': 2, 'alpha': 'short'}}},
    {'_default': {str(i): {'b': i, 'a': TEXT} for i in range(1, 4)}},
]

storage_report = []
for encoding, kwargs in COMBOS:
    directory = new_dir('kw')
    path = os.path.join(directory, 'db.json')
    storage = JSONStorage(path, encoding=encoding, **kwargs)
    steps = []
    for data in SEQUENCE:
        error = attempt(lambda: storage.write(data))
        actual = read_bytes(path)
        expected = json.dumps(data, **kwargs).encode(encoding or 'utf-8')
        try:
            readback = storage.read() == data
        except Exception as exc:
            readback = 'error: ' + describe(exc)
        steps.append({
            'write_error': error,
            'bytes_equal': actual == expected,
            'actual_len': len(actual),
            'expected_len': len(expected),
            'actual_head': actual[:50].decode('utf-8', 'replace'),
            'expected_head': expected[:50].decode('utf-8', 'replace'),
            'read_ok': readback,
        })
    try:
        storage.close()
    except Exception:
        pass
    shutil.rmtree(directory, ignore_errors=True)
    storage_report.append({'kwargs': repr(kwargs), 'encoding': encoding,
                           'steps': steps})

tinydb_report = []
for options in ({'indent': 4, 'sort_keys': True},
                {'encoding': 'utf-8', 'ensure_ascii': False,
                 'separators': (',', ':')}):
    directory = new_dir('kwdb')
    path = os.path.join(directory, 'db.json')
    dump_kwargs = dict(options)
    encoding = dump_kwargs.pop('encoding', None)
    db = TinyDB(path, **options)
    first = {'zeta': 1, 'alpha': TEXT, 'mid': {'b': 2, 'a': 1}}
    second = {'name': 'second', 'n': 2}
    first_id = db.insert(first)
    states = [{'_default': {str(first_id): first}}]
    files = [read_bytes(path)]
    second_id = db.insert(second)
    states.append({'_default': {str(first_id): first,
                                str(second_id): second}})
    files.append(read_bytes(path))
    db.remove(doc_ids=[first_id])
    states.append({'_default': {str(second_id): second}})
    files.append(read_bytes(path))
    db.close()
    shutil.rmtree(directory, ignore_errors=True)
    tinydb_report.append({
        'options': repr(options),
        'bytes_equal': [
            actual == json.dumps(state, **dump_kwargs).encode(
                encoding or 'utf-8')
            for actual, state in zip(files, states)
        ],
        'heads': [actual[:50].decode('utf-8', 'replace') for actual in files],
    })
return {'storage': storage_report, 'tinydb': tinydb_report}
'''


PIECE_NO_TEMP_AFTER_SUCCESS = r'''
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage

listings = []
directory = new_dir('clean')
path = os.path.join(directory, 'db.json')
storage = JSONStorage(path)
for index, data in enumerate([OLD_BIG, NEW_EMPTY, NEW_BIG, OLD_SMALL, NEW_MID]):
    storage.write(data)
    listings.append(['JSONStorage write %d' % index,
                     sorted(os.listdir(directory))])
    storage.read()
storage.close()
listings.append(['JSONStorage close', sorted(os.listdir(directory))])
shutil.rmtree(directory, ignore_errors=True)

directory = new_dir('clean-db')
path = os.path.join(directory, 'db.json')
db = TinyDB(path)
query = Query()
operations = [
    ('insert', lambda: db.insert({'a': 1})),
    ('insert_multiple', lambda: db.insert_multiple(
        [{'a': i, 'pad': 'p' * 500} for i in range(2, 30)])),
    ('update', lambda: db.update({'b': True}, query.a == 1)),
    ('remove', lambda: db.remove(query.a > 5)),
    ('insert into other table', lambda: db.table('other').insert({'x': 1})),
    ('truncate', lambda: db.truncate()),
    ('insert after truncate', lambda: db.insert({'a': 99})),
]
for label, operation in operations:
    operation()
    listings.append(['TinyDB ' + label, sorted(os.listdir(directory))])
db.close()
listings.append(['TinyDB close', sorted(os.listdir(directory))])
shutil.rmtree(directory, ignore_errors=True)
return listings
'''


PIECE_USABLE_STORAGE = r'''
install_failure_hooks()
from tinydb.storages import JSONStorage

directory = new_dir('usable')
path = os.path.join(directory, 'db.json')
storage = JSONStorage(path)
KNOWN = [
    ('A', make_state(8, 'a' * 40, 'A')),
    ('B', make_state(2, 'b', 'B')),
    ('C', make_state(3, 'c' * 30, 'C')),
    ('D', make_state(60, 'd' * 300, 'D')),
    ('E', make_state(5, 'e' * 10, 'E')),
    ('F', {'_default': {'1': {'tag': 'F'}}, 'other': {'7': {'x': [1, 2]}}}),
    ('G', make_state(4, 'g' * 5, 'G')),
    ('BAD', {'_default': {'1': {'bad': object()}}}),
]
S = dict(KNOWN)


def which(value):
    # Name of the known state `value` equals, or a short description.
    if isinstance(value, str):
        return value
    for name, state in KNOWN:
        if value == state:
            return name
    return 'unknown: ' + short(value)


def read_state():
    try:
        return which(storage.read())
    except Exception as exc:
        return 'error: ' + describe(exc)


def file_state():
    valid, value = load_json(path)
    return which(value) if valid else 'invalid: ' + head_of(path)


STEPS = [
    ('rename fails', 'rename', 'B'),
    ('write after rename failure', None, 'C'),
    ('disk full', 'fsize', 'D'),
    ('write after disk full', None, 'E'),
    ('unserializable data', None, 'BAD'),
    ('fsync fails', 'fsync', 'F'),
    ('write after fsync failure', None, 'G'),
]
storage.write(S['A'])
current = ['A']
log = []
for label, inject, name in STEPS:
    data = S[name]
    if inject in ('rename', 'fsync'):
        ARMED.add(inject)
        try:
            error = attempt(lambda: storage.write(data))
        finally:
            ARMED.discard(inject)
    elif inject == 'fsize':
        with FileSizeLimit(2048):
            error = attempt(lambda: storage.write(data))
    else:
        error = attempt(lambda: storage.write(data))
    if error is None:
        current[0] = name
    log.append({
        'label': label,
        'error': error,
        # a failed write must leave the previous data readable, a
        # successful one must be visible right away
        'expected': current[0],
        'read': read_state(),
        'file': file_state(),
    })
try:
    storage.close()
except Exception:
    pass
shutil.rmtree(directory, ignore_errors=True)
return log
'''


PIECE_USABLE_TINYDB = r'''
install_failure_hooks()
from tinydb import TinyDB

directory = new_dir('usable-db')
path = os.path.join(directory, 'db.json')
db = TinyDB(path)
model = {}
holder = {}


def docs():
    try:
        return [dict(doc) for doc in db.all()]
    except Exception as exc:
        return 'error: ' + describe(exc)


def stored():
    try:
        return db.storage.read()
    except Exception as exc:
        return 'error: ' + describe(exc)


def on_disk():
    valid, value = load_json(path)
    return value if valid else 'invalid: ' + head_of(path)


def insert(doc):
    def run():
        holder['id'] = db.insert(doc)

    def applied():
        model[holder['id']] = dict(doc)
    return run, applied


def update_first(fields):
    def run():
        db.update(fields, doc_ids=[min(model)])

    def applied():
        model[min(model)].update(fields)
    return run, applied


def remove_first():
    def run():
        db.remove(doc_ids=[min(model)])

    def applied():
        del model[min(model)]
    return run, applied


OPERATIONS = [
    ('insert', None, insert({'name': 'first', 'n': 1})),
    ('insert, rename fails', 'rename', insert({'name': 'second', 'n': 2})),
    ('insert after failure', None, insert({'name': 'third', 'n': 3})),
    ('update, disk full', 'fsize', update_first({'blob': 'q' * 20000})),
    ('remove after failure', None, remove_first()),
    ('insert, fsync fails', 'fsync', insert({'name': 'fourth', 'n': 4})),
    ('insert after fsync failure', None, insert({'name': 'fifth', 'n': 5})),
]
log = []
for label, inject, (run, applied) in OPERATIONS:
    if inject in ('rename', 'fsync'):
        ARMED.add(inject)
        try:
            error = attempt(run)
        finally:
            ARMED.discard(inject)
    elif inject == 'fsize':
        with FileSizeLimit(2048):
            error = attempt(run)
    else:
        error = attempt(run)
    if error is None:
        applied()
    expected_docs = list(model.values())
    expected_state = {'_default': {str(key): value
                                   for key, value in model.items()}}
    current_docs = docs()
    log.append({
        'label': label,
        'error': error,
        'docs_ok': current_docs == expected_docs,
        'storage_ok': stored() == expected_state,
        'disk_ok': on_disk() == expected_state,
        'docs': short(current_docs),
        'expected_docs': short(expected_docs),
    })
try:
    db.close()
except Exception:
    pass
shutil.rmtree(directory, ignore_errors=True)
return log
'''


PIECE_FD_LEAK = r'''
from tinydb.storages import JSONStorage

directory = new_dir('fd')
path = os.path.join(directory, 'db.json')
storage = JSONStorage(path)


def open_fds():
    gc.collect()
    return len(os.listdir('/proc/self/fd'))


def data_for(i):
    return {'_default': {
        str(j): {'i': i, 'j': j, 'pad': 'p' * ((i * 13 + j) % 97)}
        for j in range(1, i % 9 + 2)
    }}


for i in range(5):
    storage.write(data_for(i))
    storage.read()
baseline = open_fds()
counts = {}
wrong_reads = 0
error = None
done = 0
try:
    for i in range(5, 2005):
        data = data_for(i)
        storage.write(data)
        if storage.read() != data:
            wrong_reads += 1
        done += 1
        if done == 500:
            counts['after_500'] = open_fds()
except Exception as exc:
    error = describe(exc)
counts['after_all'] = open_fds()
try:
    storage.close()
except Exception:
    pass
shutil.rmtree(directory, ignore_errors=True)
return {'baseline': baseline, 'counts': counts, 'wrong_reads': wrong_reads,
        'error': error, 'cycles': done}
'''


# ---------------------------------------------------------------------------
# Helpers (test process side)
# ---------------------------------------------------------------------------

ALL_SCENARIOS = ['disk_full_shrinking', 'disk_full_growing', 'fsync_fails',
                 'rename_fails', 'unserializable']


def _snippet(*pieces, **params):
    code = '\n'.join(
        [PIECE_COMMON, 'PARAMS = json.loads(%r)' % json.dumps(params)]
        + list(pieces)
    )
    return 'def _main():\n' + textwrap.indent(code, '    ') + \
        '\n\nresult = _main()\n'


def _value(r):
    assert not r.timed_out, 'sandbox snippet timed out'
    assert r.ok, 'sandbox snippet raised %s: %s\nstderr:\n%s' % (
        r.error_type, r.error, (r.stderr or '')[-3000:])
    return r.value


# ---------------------------------------------------------------------------
# R1: atomicity
# ---------------------------------------------------------------------------

def test_process_killed_mid_write_leaves_complete_old_or_new_json():
    r = run_python(_snippet(PIECE_CRASH, child=CRASH_CHILD), timeout=120.0)
    outcomes = _value(r)
    assert [o['mode'] for o in outcomes] == ['fsync', 'rename', 'fsize',
                                            'fsize']
    for outcome in outcomes:
        # After the writer died, the database file is a complete JSON
        # document holding exactly the old or the new state (never a
        # half-written mix)...
        assert outcome['state'] in ('old', 'new'), outcome
        # ...and TinyDB loads one of them.
        assert outcome['tinydb_loads_old'] or outcome['tinydb_loads_new'], (
            outcome)


def test_failed_write_never_leaves_partial_json():
    names = ['disk_full_shrinking', 'disk_full_growing', 'fsync_fails',
             'rename_fails']
    r = run_python(_snippet(PIECE_FAILURE_SCENARIOS, scenarios=names),
                   timeout=60.0)
    facts = _value(r)
    for name in names:
        scenario = facts[name]
        # The database file is a complete JSON document holding exactly the
        # old or the new state, and TinyDB loads it.
        assert scenario['exists'], (name, scenario)
        assert scenario['state'] in ('old', 'new'), (name, scenario)
        assert scenario['tinydb_loads_old'] or scenario['tinydb_loads_new'], (
            name, scenario)


# ---------------------------------------------------------------------------
# R2: temporary file + rename
# ---------------------------------------------------------------------------

def test_write_swaps_in_temporary_file_via_rename():
    r = run_python(_snippet(PIECE_RENAME), timeout=60.0)
    value = _value(r)
    assert len(value['records']) == 4
    for index, record in enumerate(value['records']):
        # A new file replaced the database file (no in-place rewrite)...
        assert record['inode_changed'], (index, record)
        # ...through os.replace/os.rename onto the database path, from a
        # different file that already held the complete new contents.
        assert record['swap_count'] >= 1, (index, record)
        assert record['swap_source_held_new_data'], (index, record)
        assert record['file_holds_data'], (index, record)
    # If the rename step fails, the database file keeps its old contents.
    assert value['old_kept_after_failed_rename'], value


# ---------------------------------------------------------------------------
# R3: reads see what was just written
# ---------------------------------------------------------------------------

def test_read_after_write_on_long_lived_storage():
    r = run_python(_snippet(PIECE_READ_AFTER_WRITE), timeout=60.0)
    value = _value(r)
    assert value['checked'] == 49
    assert value['mismatch_count'] == 0, value['mismatches']


def test_tinydb_changes_immediately_visible_on_same_instance():
    r = run_python(_snippet(PIECE_TINYDB_VISIBLE), timeout=60.0)
    value = _value(r)
    labels = [entry['label'] for entry in value['log']]
    assert labels == ['insert', 'second insert', 'update', 'insert_multiple',
                      'remove', 'other table', 'upsert', 'truncate',
                      'insert after truncate']
    for entry in value['log']:
        assert entry['docs_ok'], entry
        assert entry['storage_docs_ok'], entry
        assert entry['storage_ids_ok'], entry
        assert entry['len_ok'], entry
        assert entry.get('tables_ok', True), entry
    assert value['search'] == [{'a': 3}, {'a': 4}]
    assert value['search_after'] == [{'a': 3}, {'a': 5}]
    assert value['other'] == [{'x': [1, 2, 3]}]


# ---------------------------------------------------------------------------
# R4 / R5: identical bytes on disk
# ---------------------------------------------------------------------------

def test_encoding_bytes_identical_to_original_implementation():
    r = run_python(_snippet(PIECE_ENCODINGS), timeout=60.0)
    report = _value(r)
    assert [case['encoding'] for case in report] == [
        None, 'utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'latin-1',
        'cp1252']
    for case in report:
        assert len(case['steps']) == 3
        for index, step in enumerate(case['steps']):
            where = (case['encoding'], index, step)
            assert step['write_error'] is None, where
            assert step['bytes_equal'], where
            assert step['read_ok'] is True, where
            assert step['fresh_read_ok'] is True, where


def test_json_kwargs_forwarded_exactly():
    r = run_python(_snippet(PIECE_KWARGS), timeout=60.0)
    value = _value(r)
    assert len(value['storage']) == 5
    for case in value['storage']:
        assert len(case['steps']) == 3
        for index, step in enumerate(case['steps']):
            where = (case['kwargs'], case['encoding'], index, step)
            assert step['write_error'] is None, where
            assert step['bytes_equal'], where
            assert step['read_ok'] is True, where
    assert len(value['tinydb']) == 2
    for case in value['tinydb']:
        assert case['bytes_equal'] == [True, True, True], case


# ---------------------------------------------------------------------------
# R6 / R7: no temporary files left behind
# ---------------------------------------------------------------------------

def test_successful_writes_leave_no_temporary_files():
    r = run_python(_snippet(PIECE_NO_TEMP_AFTER_SUCCESS), timeout=60.0)
    listings = _value(r)
    assert len(listings) == 14
    for label, listing in listings:
        assert listing == ['db.json'], (label, listing)


def test_failed_write_leaves_no_temporary_files():
    r = run_python(_snippet(PIECE_FAILURE_SCENARIOS,
                            scenarios=ALL_SCENARIOS), timeout=60.0)
    facts = _value(r)
    for name in ALL_SCENARIOS:
        scenario = facts[name]
        # The directory holds exactly the files it held before the write.
        assert scenario['listing_after'] == scenario['listing_before'], (
            name, scenario)


# ---------------------------------------------------------------------------
# R8: failed write leaves the database file untouched
# ---------------------------------------------------------------------------

def test_failed_write_keeps_database_file_byte_identical():
    r = run_python(_snippet(PIECE_FAILURE_SCENARIOS,
                            scenarios=ALL_SCENARIOS), timeout=60.0)
    facts = _value(r)
    # These writes cannot succeed with any implementation: the disk is
    # full or the data can't be serialized.
    failed = ['disk_full_shrinking', 'disk_full_growing', 'unserializable']
    # When the failing rename/replace or fsync step made the write fail, the
    # same guarantees apply.
    for name in ('rename_fails', 'fsync_fails'):
        if facts[name]['raised']:
            failed.append(name)
    for name in failed:
        scenario = facts[name]
        assert scenario['exists'], (name, scenario)
        assert scenario['bytes_same'], (name, scenario)
        assert scenario['inode_same'], (name, scenario)
        assert scenario['size_same'], (name, scenario)
        assert scenario['tinydb_loads_old'], (name, scenario)


# ---------------------------------------------------------------------------
# R9: instance stays usable after a failed write
# ---------------------------------------------------------------------------

def test_storage_usable_after_failed_write():
    r = run_python(_snippet(PIECE_USABLE_STORAGE), timeout=60.0)
    log = _value(r)
    assert [step['label'] for step in log] == [
        'rename fails', 'write after rename failure', 'disk full',
        'write after disk full', 'unserializable data', 'fsync fails',
        'write after fsync failure']
    steps = {step['label']: step for step in log}
    # Writing more data than fits on the disk, or data json can't
    # serialize, fails with every implementation.
    assert steps['disk full']['error'] is not None, log
    assert steps['unserializable data']['error'] is not None, log
    for step in log:
        # After a failed write the same instance still reads the previous
        # data; after a successful one it reads the new data.
        assert step['read'] == step['expected'], (step, log)
        if step['error'] is None:
            # ...and a successful write is persisted.
            assert step['file'] == step['expected'], (step, log)
    # The writes after the failures succeed.
    for label in ('write after rename failure', 'write after disk full',
                  'write after fsync failure'):
        assert steps[label]['error'] is None, (label, log)


def test_tinydb_usable_after_failed_write():
    r = run_python(_snippet(PIECE_USABLE_TINYDB), timeout=60.0)
    log = _value(r)
    assert [entry['label'] for entry in log] == [
        'insert', 'insert, rename fails', 'insert after failure',
        'update, disk full', 'remove after failure', 'insert, fsync fails',
        'insert after fsync failure']
    entries = {entry['label']: entry for entry in log}
    # An update that doesn't fit on the disk fails with every implementation.
    assert entries['update, disk full']['error'] is not None, log
    for label in ('insert', 'insert after failure', 'remove after failure',
                  'insert after fsync failure'):
        assert entries[label]['error'] is None, (label, log)
    for entry in log:
        # The same TinyDB instance (and the file) show exactly the
        # operations that succeeded; failed ones left the old data.
        assert entry['docs_ok'], (entry, log)
        assert entry['storage_ok'], (entry, log)
        assert entry['disk_ok'], (entry, log)


# ---------------------------------------------------------------------------
# R10: no file descriptor leak
# ---------------------------------------------------------------------------

def test_no_file_descriptor_leak_over_many_writes():
    r = run_python(_snippet(PIECE_FD_LEAK), timeout=180.0)
    value = _value(r)
    assert value['error'] is None, value
    assert value['cycles'] == 2000, value
    assert value['wrong_reads'] == 0, value
    assert value['counts']['after_500'] - value['baseline'] <= 2, value
    assert value['counts']['after_all'] - value['baseline'] <= 2, value
