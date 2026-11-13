"""
Hidden behavioural tests for task CS-02 (condition initial_plain).

The change under test: ``JSONStorage.write`` no longer rewrites the database
file in place. It writes the complete new contents to a temporary file on the
same file system, flushes and fsyncs it, and atomically swaps it over the
database path (``os.replace``/``os.rename``). Existing behaviour must be
preserved.

All interaction with the candidate happens inside the sandbox through
``tc_sandbox.run_python``:

* every snippet wraps its code in a function, so it does not depend on how the
  sandbox executes the snippet;
* spies/fault injectors for ``os.replace``, ``os.rename``, ``os.fsync`` and
  ``os.fdatasync`` are installed *before* ``tinydb`` is imported, so they also
  see functions a candidate imported with ``from os import ...``;
* scenarios that need signals or resource limits run in a child interpreter
  started from the snippet.
"""

import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_write_swaps_new_file_into_place": ["R1", "R5"],
    "test_shrinking_contents_and_no_leftover_files": ["R1", "R6"],
    "test_disk_full_while_writing_keeps_old_file": ["R2", "R6", "R7"],
    "test_failed_swap_keeps_old_file": ["R2", "R6", "R7"],
    "test_unserializable_document_keeps_old_file": ["R2", "R4", "R6", "R7"],
    "test_killed_during_write_leaves_complete_file": ["R2"],
    "test_instance_reads_its_own_successive_writes": ["R3"],
    "test_serialized_text_matches_base_format": ["R4"],
    "test_read_only_storage_refuses_writes": ["R4"],
    "test_create_dirs_relative_and_pathlib_paths": ["R4", "R1"],
    "test_system_temp_dir_on_other_filesystem": ["R5", "R1"],
    "test_new_contents_synced_before_swap": ["R8"],
    "test_sync_failure_aborts_write": ["R8", "R2", "R6", "R7"],
}


def _program(*parts, **values):
    """Build a snippet: the parts form the body of ``_main``; ``@NAME@``
    placeholders are replaced by ``ascii(values[NAME])``."""
    body = "".join(textwrap.dedent(part) for part in parts)
    for key, value in values.items():
        body = body.replace("@" + key + "@", ascii(value))
    return ("def _main():\n" + textwrap.indent(body, "    ")
            + "\n\nresult = _main()\n")


def _value(r):
    """Return the snippet's result after checking that it ran to the end."""
    assert not r.timed_out, "snippet timed out"
    assert r.ok, "snippet raised %s: %s\n%s" % (
        r.error_type, r.error, (r.stderr or "")[-3000:])
    return r.value


# --------------------------------------------------------------------------
# Snippet building blocks
# --------------------------------------------------------------------------

# Records every os.replace/os.rename call (resolved source/destination, the
# source's device/inode and its contents at the time of the call) in
# ``events``. Never interferes with the call itself.
_SPY_SWAPS = r'''
import os

events = []
_real_replace = os.replace
_real_rename = os.rename


def _resolve(name, dir_fd):
    name = os.fsdecode(name)
    if dir_fd is not None and not os.path.isabs(name):
        name = os.path.join(os.readlink('/proc/self/fd/%d' % dir_fd), name)
    return os.path.realpath(name)


def _record_swap(kind, src, dst, src_dir_fd, dst_dir_fd):
    entry = {'kind': kind, 'src': None, 'dst': None, 'dev': None,
             'ino': None, 'content': None}
    try:
        entry['src'] = _resolve(src, src_dir_fd)
        entry['dst'] = _resolve(dst, dst_dir_fd)
        st = os.stat(entry['src'])
        entry['dev'], entry['ino'] = st.st_dev, st.st_ino
        with open(entry['src'], 'rb') as fh:
            entry['content'] = fh.read()
    except Exception:
        pass
    events.append(entry)


def _spy_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    _record_swap('replace', src, dst, src_dir_fd, dst_dir_fd)
    return _real_replace(src, dst, src_dir_fd=src_dir_fd,
                         dst_dir_fd=dst_dir_fd)


def _spy_rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    _record_swap('rename', src, dst, src_dir_fd, dst_dir_fd)
    return _real_rename(src, dst, src_dir_fd=src_dir_fd,
                        dst_dir_fd=dst_dir_fd)


os.replace = _spy_replace
os.rename = _spy_rename
'''

# Records every os.fsync/os.fdatasync call (device/inode of the descriptor)
# in the same ``events`` list. Must come after _SPY_SWAPS.
_SPY_SYNCS = r'''
_real_fsync = os.fsync
_real_fdatasync = getattr(os, 'fdatasync', None)


def _record_sync(kind, fd):
    entry = {'kind': kind, 'dev': None, 'ino': None}
    try:
        st = os.fstat(fd if isinstance(fd, int) else fd.fileno())
        entry['dev'], entry['ino'] = st.st_dev, st.st_ino
    except Exception:
        pass
    events.append(entry)


def _spy_fsync(fd):
    _record_sync('fsync', fd)
    return _real_fsync(fd)


def _spy_fdatasync(fd):
    _record_sync('fdatasync', fd)
    return _real_fdatasync(fd)


os.fsync = _spy_fsync
if _real_fdatasync is not None:
    os.fdatasync = _spy_fdatasync
'''

# Environment for child interpreters: the candidate repository (the working
# directory of the snippet) stays importable.
_CHILD_ENV = r'''
child_env = dict(os.environ)
child_env['PYTHONPATH'] = os.pathsep.join(
    [os.getcwd()] + ([child_env['PYTHONPATH']]
                     if child_env.get('PYTHONPATH') else []))
'''


# --------------------------------------------------------------------------
# R1 / R5: the new contents are swapped into place
# --------------------------------------------------------------------------

_WRITE_SWAP = _program(_SPY_SWAPS, r'''
import json
import tempfile

from tinydb import TinyDB, where

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
real = os.path.realpath(path)
dir_dev = os.stat(d).st_dev
db = TinyDB(path)
steps = []
operations = [
    ('insert a', lambda: db.insert({'a': 1})),
    ('insert b', lambda: db.insert({'b': 2})),
    ('update a', lambda: db.update({'a': 10}, where('a') == 1)),
    ('remove b', lambda: db.remove(where('b') == 2)),
]
for name, operation in operations:
    inode_before = os.stat(path).st_ino
    del events[:]
    operation()
    st = os.stat(path)
    swaps = [e for e in events if e['dst'] == real]
    last = swaps[-1] if swaps else None
    with open(path, encoding='utf-8') as fh:
        content = json.load(fh)
    steps.append({
        'name': name,
        'content': content,
        'inode_changed': st.st_ino != inode_before,
        'swapped_onto_db': last is not None,
        'source_is_other_file': last is not None and last['src'] != real,
        'source_on_same_device': last is not None and last['dev'] == dir_dev,
        'source_became_db_file': (last is not None
                                  and last['ino'] == st.st_ino
                                  and last['dev'] == st.st_dev),
    })
db.close()
return steps
''')


def test_write_swaps_new_file_into_place():
    steps = _value(run_python(_WRITE_SWAP, timeout=60.0))
    assert [s["name"] for s in steps] == [
        "insert a", "insert b", "update a", "remove b"]
    assert [s["content"] for s in steps] == [
        {"_default": {"1": {"a": 1}}},
        {"_default": {"1": {"a": 1}, "2": {"b": 2}}},
        {"_default": {"1": {"a": 10}, "2": {"b": 2}}},
        {"_default": {"1": {"a": 10}}},
    ]
    for s in steps:
        assert s["inode_changed"] is True, (
            "%s: the database file was rewritten in place (same inode)"
            % s["name"])
        assert s["swapped_onto_db"] is True, (
            "%s: no os.replace/os.rename onto the database path" % s["name"])
        assert s["source_is_other_file"] is True, s
        assert s["source_on_same_device"] is True, (
            "%s: the swapped-in file is not on the database's file system"
            % s["name"])
        assert s["source_became_db_file"] is True, s


_SHRINK = _program(r'''
import json
import os
import tempfile

from tinydb import TinyDB, where

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
db = TinyDB(path)
text = 'some longer text ' * 20
listing_changes = []


def run(name, operation):
    before = sorted(os.listdir(d))
    operation()
    after = sorted(os.listdir(d))
    if after != before:
        listing_changes.append([name, before, after])


run('insert_multiple',
    lambda: db.insert_multiple([{'n': i, 'text': text} for i in range(60)]))
size_full = os.path.getsize(path)
run('update', lambda: db.update({'flag': True}, where('n') < 10))
run('remove most', lambda: db.remove(where('n') >= 5))
run('insert', lambda: db.insert({'n': 'last'}))
other = db.table('other')
run('insert into other table', lambda: other.insert({'x': 1}))
run('truncate other table', lambda: other.truncate())
run('drop other table', lambda: db.drop_table('other'))
size_final = os.path.getsize(path)
with open(path, encoding='utf-8') as fh:
    raw = fh.read()
try:
    parsed = json.loads(raw)
    parse_error = None
except ValueError as exc:
    parsed = None
    parse_error = str(exc)[:300]
docs = [dict(x) for x in db.all()]
db.close()
reopened = [dict(x) for x in TinyDB(path).all()]
return {
    'listing_changes': listing_changes,
    'shrunk': size_final < size_full,
    'parse_error': parse_error,
    'parsed': parsed,
    'exact_serialization': parsed is not None and raw == json.dumps(parsed),
    'docs': docs,
    'reopened': reopened,
}
''')


def test_shrinking_contents_and_no_leftover_files():
    v = _value(run_python(_SHRINK, timeout=60.0))
    text = "some longer text " * 20
    kept = [{"n": i, "text": text, "flag": True} for i in range(5)]
    expected = {str(i + 1): doc for i, doc in enumerate(kept)}
    expected["61"] = {"n": "last"}
    assert v["parse_error"] is None, (
        "database file is not valid JSON after it got shorter: "
        + str(v["parse_error"]))
    assert v["shrunk"] is True
    assert v["parsed"] == {"_default": expected}
    assert v["exact_serialization"] is True, (
        "file does not contain exactly json.dumps(data)")
    assert v["docs"] == kept + [{"n": "last"}]
    assert v["reopened"] == kept + [{"n": "last"}]
    assert v["listing_changes"] == [], (
        "successful writes changed the directory contents: %r"
        % v["listing_changes"])


# --------------------------------------------------------------------------
# R2 / R6 / R7: failed writes keep the old file, clean up and raise
# --------------------------------------------------------------------------

# Child: a write that exceeds RLIMIT_FSIZE (simulated full disk) with SIGXFSZ
# ignored, so the write fails with EFBIG instead of killing the process.
_CHILD_DISK_FULL = r'''
import json
import os
import resource
import signal
import sys

from tinydb import TinyDB

path = sys.argv[1]
directory = os.path.dirname(path)
db = TinyDB(path)
listing_before = sorted(os.listdir(directory))
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
resource.setrlimit(resource.RLIMIT_FSIZE, (os.path.getsize(path) + 1024, hard))
try:
    try:
        db.insert({'n': 'big', 'value': 'x' * 300000})
        outcome = 'returned normally'
    except Exception as exc:
        outcome = 'raised ' + type(exc).__name__
finally:
    resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
listing_after = sorted(os.listdir(directory))
print(json.dumps({'outcome': outcome, 'listing_before': listing_before,
                  'listing_after': listing_after}))
'''

_DISK_FULL = _program(r'''
import json
import os
import subprocess
import sys
import tempfile

from tinydb import TinyDB
''', _CHILD_ENV, r'''
d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
old_docs = [{'n': i, 'value': 'old value %d' % i} for i in range(20)]
db = TinyDB(path)
db.insert_multiple(old_docs)
db.close()
with open(path, 'rb') as fh:
    before = fh.read()
proc = subprocess.run([sys.executable, '-c', @CHILD@, path], cwd=d,
                      env=child_env, capture_output=True, text=True,
                      timeout=120)
try:
    child = json.loads(proc.stdout.strip().splitlines()[-1])
except Exception:
    child = None
with open(path, 'rb') as fh:
    after = fh.read()
try:
    reopened = [dict(x) for x in TinyDB(path).all()]
except Exception as exc:
    reopened = 'error: ' + type(exc).__name__
return {
    'child': child,
    'returncode': proc.returncode,
    'stderr': proc.stderr[-2000:],
    'bytes_unchanged': after == before,
    'reopened_is_old': reopened == old_docs,
    'reopened': reopened if reopened != old_docs else None,
}
''', CHILD=_CHILD_DISK_FULL)


def test_disk_full_while_writing_keeps_old_file():
    v = _value(run_python(_DISK_FULL, timeout=180.0))
    assert v["child"] is not None, (
        "child process failed (rc=%r): %s" % (v["returncode"], v["stderr"]))
    assert v["child"]["outcome"].startswith("raised"), (
        "insert that could not be written returned normally")
    assert v["bytes_unchanged"] is True, (
        "database file changed although the write failed (disk full)")
    assert v["reopened_is_old"] is True, v["reopened"]
    assert v["child"]["listing_after"] == v["child"]["listing_before"], (
        "temporary file left behind after a failed write: %r" % v["child"])


_SWAP_FAILS = _program(r'''
import errno
import os
import tempfile

_real_replace = os.replace
_real_rename = os.rename
armed = []
attempts = []


def _failing(real):
    def wrapper(*args, **kwargs):
        if armed:
            attempts.append(1)
            raise OSError(errno.EIO, 'injected failure while swapping')
        return real(*args, **kwargs)
    return wrapper


os.replace = _failing(_real_replace)
os.rename = _failing(_real_rename)

from tinydb import TinyDB, where

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
old_docs = [{'n': i, 'value': 'value %d' % i} for i in range(10)]
db = TinyDB(path)
db.insert_multiple(old_docs)
with open(path, 'rb') as fh:
    before = fh.read()
listing_before = sorted(os.listdir(d))
outcomes = []
armed.append(True)
try:
    for operation in (lambda: db.insert({'n': 'new'}),
                      lambda: db.update({'value': 'changed'}),
                      lambda: db.remove(where('n') == 3)):
        try:
            operation()
            outcomes.append('returned normally')
        except Exception as exc:
            outcomes.append('raised ' + type(exc).__name__)
finally:
    del armed[:]
listing_after = sorted(os.listdir(d))
with open(path, 'rb') as fh:
    after = fh.read()
try:
    reopened = [dict(x) for x in TinyDB(path).all()]
except Exception as exc:
    reopened = 'error: ' + type(exc).__name__
return {
    'outcomes': outcomes,
    'swap_attempted': len(attempts) > 0,
    'bytes_unchanged': after == before,
    'listing_before': listing_before,
    'listing_after': listing_after,
    'reopened_is_old': reopened == old_docs,
    'reopened': reopened if reopened != old_docs else None,
}
''')


def test_failed_swap_keeps_old_file():
    v = _value(run_python(_SWAP_FAILS, timeout=60.0))
    assert v["swap_attempted"] is True, (
        "the write never called os.replace/os.rename")
    for outcome in v["outcomes"]:
        assert outcome.startswith("raised"), (
            "a write whose swap failed returned normally: %r" % v["outcomes"])
    assert v["bytes_unchanged"] is True, (
        "database file changed although the swap failed")
    assert v["reopened_is_old"] is True, v["reopened"]
    assert v["listing_after"] == v["listing_before"], (
        "temporary file left behind after a failed swap: %r -> %r"
        % (v["listing_before"], v["listing_after"]))


_UNSERIALIZABLE = _program(r'''
import os
import tempfile

from tinydb import TinyDB

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
old_docs = [{'int': 1}, {'int': 2}]
db = TinyDB(path)
db.insert_multiple(old_docs)
with open(path, 'rb') as fh:
    before = fh.read()
listing_before = sorted(os.listdir(d))
outcomes = []
for document in ({'int': object()},
                 {'big': 'x' * 200000, 'bad': {1, 2, 3}}):
    try:
        db.insert(document)
        outcomes.append('returned normally')
    except Exception as exc:
        outcomes.append('raised ' + type(exc).__name__)
listing_after = sorted(os.listdir(d))
with open(path, 'rb') as fh:
    after = fh.read()
try:
    same_instance = [dict(x) for x in db.all()]
except Exception as exc:
    same_instance = 'error: ' + type(exc).__name__
try:
    reopened = [dict(x) for x in TinyDB(path).all()]
except Exception as exc:
    reopened = 'error: ' + type(exc).__name__
try:
    db.insert({'int': 3})
    after_valid_insert = [dict(x) for x in TinyDB(path).all()]
except Exception as exc:
    after_valid_insert = 'error: ' + type(exc).__name__
return {
    'outcomes': outcomes,
    'bytes_unchanged': after == before,
    'listing_before': listing_before,
    'listing_after': listing_after,
    'same_instance': same_instance,
    'reopened': reopened,
    'after_valid_insert': after_valid_insert,
}
''')


def test_unserializable_document_keeps_old_file():
    v = _value(run_python(_UNSERIALIZABLE, timeout=60.0))
    # The existing test suite expects the original TypeError here.
    assert v["outcomes"][0] == "raised TypeError", v["outcomes"]
    assert v["outcomes"][1].startswith("raised"), v["outcomes"]
    assert v["bytes_unchanged"] is True, (
        "database file changed although serialization failed")
    assert v["listing_after"] == v["listing_before"], (
        "temporary file left behind after a failed write: %r -> %r"
        % (v["listing_before"], v["listing_after"]))
    assert v["reopened"] == [{"int": 1}, {"int": 2}]
    assert v["same_instance"] == [{"int": 1}, {"int": 2}]
    assert v["after_valid_insert"] == [{"int": 1}, {"int": 2}, {"int": 3}]


# Child 1: dies (SIGKILL) as soon as the write syncs its data, i.e. after the
# new contents have been written but before the write is finished. The new
# contents are much shorter than the old ones.
_CHILD_KILL_AT_SYNC = r'''
import os
import signal
import sys

_real_fsync = os.fsync
_real_fdatasync = getattr(os, 'fdatasync', None)
_armed = []


def _die_if_armed():
    if _armed:
        os.kill(os.getpid(), signal.SIGKILL)


def _fsync(fd):
    _die_if_armed()
    return _real_fsync(fd)


def _fdatasync(fd):
    _die_if_armed()
    return _real_fdatasync(fd)


os.fsync = _fsync
if _real_fdatasync is not None:
    os.fdatasync = _fdatasync

from tinydb import TinyDB

db = TinyDB(sys.argv[1])
db.insert_multiple([{'n': i, 'value': 'old' * 100} for i in range(30)])
_armed.append(True)
db.truncate()
sys.stdout.write('write completed\n')
'''

# Child 2: dies (SIGKILL) in the middle of writing large new contents: the
# write exceeds RLIMIT_FSIZE and the SIGXFSZ handler kills the process.
_CHILD_KILL_MID_WRITE = r'''
import os
import resource
import signal
import sys

from tinydb import TinyDB

path = sys.argv[1]
db = TinyDB(path)
db.insert_multiple([{'n': i, 'value': 'old' * 20} for i in range(10)])


def _die(signum, frame):
    os.kill(os.getpid(), signal.SIGKILL)


signal.signal(signal.SIGXFSZ, _die)
soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
resource.setrlimit(resource.RLIMIT_FSIZE, (os.path.getsize(path) + 4096, hard))
db.insert({'n': 'big', 'value': 'new' * 100000})
sys.stdout.write('write completed\n')
'''

_KILLED = _program(r'''
import json
import os
import signal
import subprocess
import sys
import tempfile

from tinydb import TinyDB
''', _CHILD_ENV, r'''
old_1 = {'_default': {str(i + 1): {'n': i, 'value': 'old' * 100}
                      for i in range(30)}}
new_1 = {'_default': {}}
old_2 = {'_default': {str(i + 1): {'n': i, 'value': 'old' * 20}
                      for i in range(10)}}
new_2 = {'_default': dict(old_2['_default'])}
new_2['_default']['11'] = {'n': 'big', 'value': 'new' * 100000}
runs = {}
for name, code, old, new in (('kill_at_sync', @KILL_AT_SYNC@, old_1, new_1),
                             ('kill_mid_write', @KILL_MID_WRITE@, old_2,
                              new_2)):
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'db.json')
    proc = subprocess.run([sys.executable, '-c', code, path], cwd=d,
                          env=child_env, capture_output=True, text=True,
                          timeout=120)
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        state = 'old' if data == old else ('new' if data == new else 'other')
    except Exception as exc:
        state = 'unparsable (%s)' % type(exc).__name__
    reopened_ok = None
    if state in ('old', 'new'):
        expected = list((old if state == 'old' else new)['_default'].values())
        try:
            reopened_ok = [dict(x) for x in TinyDB(path).all()] == expected
        except Exception as exc:
            reopened_ok = 'error: ' + type(exc).__name__
    runs[name] = {
        'state': state,
        'killed': proc.returncode == -signal.SIGKILL,
        'returncode': proc.returncode,
        'completed': 'write completed' in proc.stdout,
        'reopened_ok': reopened_ok,
        'stderr': proc.stderr[-2000:],
    }
return runs
''', KILL_AT_SYNC=_CHILD_KILL_AT_SYNC, KILL_MID_WRITE=_CHILD_KILL_MID_WRITE)


def test_killed_during_write_leaves_complete_file():
    runs = _value(run_python(_KILLED, timeout=240.0))
    at_sync = runs["kill_at_sync"]
    assert at_sync["killed"] or at_sync["completed"], at_sync
    assert at_sync["state"] in ("old", "new"), (
        "process killed during a write left a %s database file"
        % at_sync["state"])
    assert at_sync["reopened_ok"] is True, at_sync
    mid_write = runs["kill_mid_write"]
    assert mid_write["killed"] is True, mid_write
    assert mid_write["state"] in ("old", "new"), (
        "process killed in the middle of a write left a %s database file"
        % mid_write["state"])
    assert mid_write["reopened_ok"] is True, mid_write


# --------------------------------------------------------------------------
# R3: the same instance keeps working on the swapped-in file
# --------------------------------------------------------------------------

_SUCCESSIVE_WRITES = _program(r'''
import os
import tempfile

from tinydb import TinyDB, where
from tinydb.storages import JSONStorage

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
db = TinyDB(path)
model = {}
problems = []


def check(label):
    expected = [[k, model[k]] for k in model]
    actual = [[doc.doc_id, dict(doc)] for doc in db.all()]
    if actual != expected:
        problems.append('%s: all() returned %d documents, expected %d; '
                        'first: %r, expected first: %r'
                        % (label, len(actual), len(expected), actual[:2],
                           expected[:2]))
    if len(db) != len(model):
        problems.append('%s: len(db) == %d, expected %d'
                        % (label, len(db), len(model)))
    for k in model:
        got = db.get(doc_id=k)
        if got is None or dict(got) != model[k]:
            problems.append('%s: get(doc_id=%d) returned %r, expected %r'
                            % (label, k, got, model[k]))
            break


for i in range(1, 21):
    doc_id = db.insert({'n': i, 'sq': i * i})
    if doc_id != i:
        problems.append('insert number %d returned id %r' % (i, doc_id))
    model[doc_id] = {'n': i, 'sq': i * i}
    check('after insert %d' % i)

evens = list(range(2, 21, 2))
db.update({'even': True}, doc_ids=evens)
for k in evens:
    model[k]['even'] = True
check('after update by ids')
if db.count(where('even') == True) != 10:
    problems.append('count(even) == %d' % db.count(where('even') == True))

db.update({'sq': -1}, where('n') == 7)
model[7]['sq'] = -1
check('after update by query')

db.remove(doc_ids=[1, 2, 3])
for k in (1, 2, 3):
    del model[k]
check('after remove by ids')

db.remove(where('n') > 15)
for k in range(16, 21):
    del model[k]
check('after remove by query')

new_id = db.insert({'n': 21})
if new_id != 21:
    problems.append('insert after removals returned id %r' % new_id)
model[new_id] = {'n': 21}
check('after insert following removals')

db.upsert({'n': 5, 'sq': 0}, where('n') == 5)
model[5]['sq'] = 0
check('after upsert')

other = db.table('other')
other.insert({'x': 1})
other.insert({'x': 2})
check('after inserts into another table')
other_docs = [dict(x) for x in other.all()]
db.close()

reopened = TinyDB(path)
reopened_docs = [[doc.doc_id, dict(doc)] for doc in reopened.all()]
reopened_other = [dict(x) for x in reopened.table('other').all()]
reopened_tables = sorted(reopened.tables())
reopened.close()

storage_path = os.path.join(d, 'storage.json')
storage = JSONStorage(storage_path)
datasets = [
    {'_default': {'1': {'v': 'first ' * 50}}},
    {'_default': {'1': {'v': 'second'}, '2': {'v': 'more'}},
     't': {'1': {'z': None}}},
    {'_default': {}},
]
storage_reads = []
for data in datasets:
    storage.write(data)
    storage_reads.append(storage.read() == data)
    storage_reads.append(storage.read() == data)
storage.close()
fresh = JSONStorage(storage_path)
fresh_read_ok = fresh.read() == datasets[-1]
fresh.close()
return {
    'problems': problems,
    'model': [[k, model[k]] for k in model],
    'other_docs': other_docs,
    'reopened_docs': reopened_docs,
    'reopened_other': reopened_other,
    'reopened_tables': reopened_tables,
    'storage_reads': storage_reads,
    'fresh_read_ok': fresh_read_ok,
}
''')


def test_instance_reads_its_own_successive_writes():
    v = _value(run_python(_SUCCESSIVE_WRITES, timeout=60.0))
    assert v["problems"] == [], v["problems"][:5]
    assert len(v["model"]) == 13
    assert v["other_docs"] == [{"x": 1}, {"x": 2}]
    assert v["reopened_docs"] == v["model"]
    assert v["reopened_other"] == [{"x": 1}, {"x": 2}]
    assert v["reopened_tables"] == ["_default", "other"]
    assert v["storage_reads"] == [True] * 6, (
        "JSONStorage.read() did not return the data just written: %r"
        % v["storage_reads"])
    assert v["fresh_read_ok"] is True


# --------------------------------------------------------------------------
# R4: existing behaviour is preserved
# --------------------------------------------------------------------------

_SERIALIZATION = _program(r'''
import datetime
import json
import os
import tempfile

from tinydb import TinyDB
from tinydb.storages import JSONStorage

d = tempfile.mkdtemp()
out = {}

path = os.path.join(d, 'kwargs.json')
db = TinyDB(path, sort_keys=True, indent=4, separators=(',', ': '))
db.insert({'b': 1})
db.insert({'a': 1})
with open(path, 'rb') as fh:
    out['kwargs_text'] = fh.read().decode('utf-8')
db.close()

text = '\u4f60\u597d\uff0c\u4e16\u754c \u3053\u3093\u306b\u3061\u306f'
cases = [
    ['utf-8', {'ensure_ascii': False, 'indent': 2}],
    ['utf-16', {'ensure_ascii': False}],
    ['cp936', {'ensure_ascii': False, 'separators': (',', ':')}],
    ['cp936', {}],
]
encoding_results = []
for index, (encoding, kwargs) in enumerate(cases):
    path = os.path.join(d, 'encoding%d.json' % index)
    storage = JSONStorage(path, encoding=encoding, **kwargs)
    writes = []
    data = None
    for count in (3, 8, 0, 5, 1):
        data = {'_default': {str(i): {'text': text, 'i': i}
                             for i in range(count)}}
        storage.write(data)
        with open(path, 'rb') as fh:
            raw = fh.read()
        writes.append([raw == json.dumps(data, **kwargs).encode(encoding),
                       storage.read() == data])
    storage.close()
    fresh = JSONStorage(path, encoding=encoding)
    encoding_results.append({'case': '%s %r' % (encoding, kwargs),
                             'writes': writes,
                             'fresh_read_back': fresh.read() == data})
    fresh.close()
out['encodings'] = encoding_results

path = os.path.join(d, 'tinydb_cp936.json')
db = TinyDB(path, encoding='cp936', ensure_ascii=False)
db.insert({'t': text})
db.close()
with open(path, 'rb') as fh:
    out['tinydb_cp936_bytes_match'] = fh.read() == json.dumps(
        {'_default': {'1': {'t': text}}}, ensure_ascii=False).encode('cp936')
db = TinyDB(path, encoding='cp936')
out['tinydb_cp936_docs_match'] = [dict(x) for x in db.all()] == [{'t': text}]
db.close()

path = os.path.join(d, 'default.json')
db = TinyDB(path, default=str)
db.insert({'day': datetime.date(2020, 1, 2)})
with open(path, 'rb') as fh:
    out['default_text'] = fh.read().decode('utf-8')
db.close()
return out
''')


def test_serialized_text_matches_base_format():
    v = _value(run_python(_SERIALIZATION, timeout=60.0))
    assert v["kwargs_text"] == (
        '{\n'
        '    "_default": {\n'
        '        "1": {\n'
        '            "b": 1\n'
        '        },\n'
        '        "2": {\n'
        '            "a": 1\n'
        '        }\n'
        '    }\n'
        '}')
    assert len(v["encodings"]) == 4
    for case in v["encodings"]:
        assert case["writes"] == [[True, True]] * 5, (
            "%s: file bytes differ from json.dumps(...).encode(encoding) or "
            "data does not read back: %r" % (case["case"], case["writes"]))
        assert case["fresh_read_back"] is True, case
    assert v["tinydb_cp936_bytes_match"] is True
    assert v["tinydb_cp936_docs_match"] is True
    assert v["default_text"] == '{"_default": {"1": {"day": "2020-01-02"}}}'


_READ_ONLY = _program(r'''
import os
import tempfile

from tinydb import TinyDB, where

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
try:
    TinyDB(os.path.join(d, 'missing.json'), access_mode='r')
    missing = 'opened'
except Exception as exc:
    missing = type(exc).__name__
db = TinyDB(path)
db.insert({'b': 1})
db.insert({'a': 1})
db.close()
with open(path, 'rb') as fh:
    before = fh.read()
ro = TinyDB(path, access_mode='r')
listing_before = sorted(os.listdir(d))
found = ro.get(where('a') == 1)
found = dict(found) if found is not None else None
outcomes = []
for operation in (lambda: ro.insert({'c': 1}),
                  lambda: ro.update({'b': 2}),
                  lambda: ro.truncate()):
    try:
        operation()
        outcomes.append('returned normally')
    except OSError:
        outcomes.append('OSError')
    except Exception as exc:
        outcomes.append('raised ' + type(exc).__name__)
listing_after = sorted(os.listdir(d))
ro.close()
with open(path, 'rb') as fh:
    after = fh.read()
reopened = [dict(x) for x in TinyDB(path).all()]
return {
    'missing': missing,
    'found': found,
    'outcomes': outcomes,
    'bytes_unchanged': after == before,
    'listing_before': listing_before,
    'listing_after': listing_after,
    'reopened': reopened,
}
''')


def test_read_only_storage_refuses_writes():
    v = _value(run_python(_READ_ONLY, timeout=60.0))
    assert v["missing"] == "FileNotFoundError"
    assert v["found"] == {"a": 1}
    assert v["outcomes"] == ["OSError"] * 3, (
        "writes through a storage opened with access_mode='r' must raise "
        "IOError/OSError: %r" % v["outcomes"])
    assert v["bytes_unchanged"] is True, (
        "read-only storage modified the database file")
    assert v["listing_after"] == v["listing_before"]
    assert v["reopened"] == [{"b": 1}, {"a": 1}]


_PATHS = _program(r'''
import json
import os
import tempfile
from pathlib import Path

from tinydb import TinyDB, where
from tinydb.storages import JSONStorage

out = {}
base = tempfile.mkdtemp()
nested = os.path.join(base, 'a', 'b', 'db.json')
try:
    JSONStorage(nested).close()
    out['without_create_dirs'] = 'opened'
except OSError:
    out['without_create_dirs'] = 'OSError'
except Exception as exc:
    out['without_create_dirs'] = 'raised ' + type(exc).__name__
storage = JSONStorage(nested, create_dirs=True)
storage.write({'_default': {'1': {'x': 1}}})
out['create_dirs_read'] = storage.read()
storage.close()
db = TinyDB(nested, create_dirs=True)
db.insert({'y': 2})
out['create_dirs_docs'] = [dict(x) for x in db.all()]
db.close()
with open(nested, encoding='utf-8') as fh:
    out['create_dirs_file'] = json.load(fh)

workdir = tempfile.mkdtemp()
previous_cwd = os.getcwd()
os.chdir(workdir)
try:
    db = TinyDB('db.json')
    listing_before = sorted(os.listdir('.'))
    inode_changes = []
    for operation in (lambda: db.insert({'rel': 1}),
                      lambda: db.insert({'rel': 2}),
                      lambda: db.update({'rel': 3}, where('rel') == 1)):
        before = os.stat('db.json').st_ino
        operation()
        inode_changes.append(os.stat('db.json').st_ino != before)
    out['relative_docs'] = [dict(x) for x in db.all()]
    out['relative_inode_changes'] = inode_changes
    out['relative_listing_unchanged'] = (
        sorted(os.listdir('.')) == listing_before)
    db.close()
    with open('db.json', encoding='utf-8') as fh:
        out['relative_file'] = json.load(fh)
    out['relative_reopened'] = [dict(x) for x in TinyDB('db.json').all()]
finally:
    os.chdir(previous_cwd)

folder = Path(tempfile.mkdtemp())
db = TinyDB(folder / 'db.json')
before = os.stat(folder / 'db.json').st_ino
db.insert({'p': 1})
db.insert({'p': 2})
db.remove(where('p') == 1)
out['pathlib_inode_changed'] = os.stat(folder / 'db.json').st_ino != before
out['pathlib_docs'] = [dict(x) for x in db.all()]
db.close()
out['pathlib_reopened'] = [dict(x) for x in TinyDB(folder / 'db.json').all()]
storage = JSONStorage(folder / 'sub' / 'storage.json', create_dirs=True)
storage.write({'_default': {'7': {'q': 7}}})
out['pathlib_storage_read'] = storage.read()
storage.close()
return out
''')


def test_create_dirs_relative_and_pathlib_paths():
    v = _value(run_python(_PATHS, timeout=60.0))
    assert v["without_create_dirs"] == "OSError"
    assert v["create_dirs_read"] == {"_default": {"1": {"x": 1}}}
    assert v["create_dirs_docs"] == [{"x": 1}, {"y": 2}]
    assert v["create_dirs_file"] == {"_default": {"1": {"x": 1},
                                                  "2": {"y": 2}}}
    assert v["relative_docs"] == [{"rel": 3}, {"rel": 2}]
    assert v["relative_inode_changes"] == [True, True, True], (
        "writes to a relative database path were not swapped into place")
    assert v["relative_listing_unchanged"] is True
    assert v["relative_file"] == {"_default": {"1": {"rel": 3},
                                               "2": {"rel": 2}}}
    assert v["relative_reopened"] == [{"rel": 3}, {"rel": 2}]
    assert v["pathlib_inode_changed"] is True
    assert v["pathlib_docs"] == [{"p": 2}]
    assert v["pathlib_reopened"] == [{"p": 2}]
    assert v["pathlib_storage_read"] == {"_default": {"7": {"q": 7}}}


# --------------------------------------------------------------------------
# R5 / R1: the temporary file lives on the database's file system
# --------------------------------------------------------------------------

_OTHER_FILESYSTEM = _program(_SPY_SWAPS, r'''
import json
import shutil
import tempfile

from tinydb import TinyDB, where

default_root = tempfile.gettempdir()
other_root = None
for candidate in ('/dev/shm', '/run/shm'):
    try:
        if (os.path.isdir(candidate) and os.access(candidate, os.W_OK)
                and os.stat(candidate).st_dev
                != os.stat(default_root).st_dev):
            other_root = candidate
            break
    except OSError:
        pass
first = tempfile.mkdtemp(dir=default_root)
second = tempfile.mkdtemp(dir=other_root or default_root)
runs = []
saved_tempdir = tempfile.tempdir
saved_env = os.environ.get('TMPDIR')
try:
    for db_dir, temp_dir in ((first, second), (second, first)):
        # The system temp directory points to the other file system.
        tempfile.tempdir = temp_dir
        os.environ['TMPDIR'] = temp_dir
        path = os.path.join(db_dir, 'db.json')
        real = os.path.realpath(path)
        db_dev = os.stat(db_dir).st_dev
        run = {'different_devices': db_dev != os.stat(temp_dir).st_dev,
               'errors': [], 'writes': []}
        db = TinyDB(path)
        operations = (lambda: db.insert({'k': 1}),
                      lambda: db.insert({'k': 2}),
                      lambda: db.update({'k': 3}, where('k') == 1),
                      lambda: db.remove(where('k') == 2))
        for operation in operations:
            before = os.stat(path).st_ino
            del events[:]
            try:
                operation()
            except Exception as exc:
                run['errors'].append('%s: %s' % (type(exc).__name__,
                                                 str(exc)[:200]))
                continue
            st = os.stat(path)
            swaps = [e for e in events if e['dst'] == real]
            run['writes'].append({
                'inode_changed': st.st_ino != before,
                'swapped_onto_db': bool(swaps),
                'source_on_same_device': (bool(swaps)
                                          and swaps[-1]['dev'] == db_dev),
            })
        try:
            run['docs'] = [dict(x) for x in db.all()]
        except Exception as exc:
            run['docs'] = 'error: ' + type(exc).__name__
        db.close()
        try:
            with open(path, encoding='utf-8') as fh:
                run['file'] = json.load(fh)
        except Exception as exc:
            run['file'] = 'error: ' + type(exc).__name__
        runs.append(run)
finally:
    tempfile.tempdir = saved_tempdir
    if saved_env is None:
        os.environ.pop('TMPDIR', None)
    else:
        os.environ['TMPDIR'] = saved_env
    if other_root is not None:
        shutil.rmtree(second, ignore_errors=True)
return {'other_root': other_root, 'runs': runs}
''')


def test_system_temp_dir_on_other_filesystem():
    v = _value(run_python(_OTHER_FILESYSTEM, timeout=60.0))
    assert len(v["runs"]) == 2
    for run in v["runs"]:
        assert run["errors"] == [], (
            "writes failed while the system temp directory is on another "
            "file system: %r" % run["errors"])
        assert len(run["writes"]) == 4
        for write in run["writes"]:
            assert write["inode_changed"] is True, (
                "database file was not replaced (non-atomic copy or in-place "
                "write): %r" % run)
            assert write["swapped_onto_db"] is True, run
            assert write["source_on_same_device"] is True, run
        assert run["docs"] == [{"k": 3}]
        assert run["file"] == {"_default": {"1": {"k": 3}}}


# --------------------------------------------------------------------------
# R8: the new contents reach the disk before the swap
# --------------------------------------------------------------------------

_SYNC_BEFORE_SWAP = _program(_SPY_SWAPS, _SPY_SYNCS, r'''
import tempfile

from tinydb import TinyDB, where
from tinydb.storages import JSONStorage

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
real = os.path.realpath(path)
checks = []


def run(name, operation):
    del events[:]
    operation()
    st = os.stat(path)
    with open(path, 'rb') as fh:
        final = fh.read()
    positions = [i for i, e in enumerate(events)
                 if e['kind'] in ('replace', 'rename') and e['dst'] == real]
    if not positions:
        checks.append({'name': name, 'swapped_onto_db': False})
        return
    i = positions[-1]
    checks.append({
        'name': name,
        'swapped_onto_db': True,
        'synced_before_swap': any(
            e['kind'] in ('fsync', 'fdatasync')
            and e['dev'] == st.st_dev and e['ino'] == st.st_ino
            for e in events[:i]),
        'complete_at_swap': events[i]['content'] == final,
    })


db = TinyDB(path)
run('insert', lambda: db.insert({'a': 1}))
run('insert_multiple',
    lambda: db.insert_multiple([{'n': i, 'v': 'x' * 100} for i in range(50)]))
run('update', lambda: db.update({'a': 2}, where('a') == 1))
run('remove', lambda: db.remove(where('n') > 10))
db.close()
storage = JSONStorage(path)
run('JSONStorage.write', lambda: storage.write({'_default': {'1': {'z': 1}}}))
storage.close()
return checks
''')


def test_new_contents_synced_before_swap():
    checks = _value(run_python(_SYNC_BEFORE_SWAP, timeout=60.0))
    assert [c["name"] for c in checks] == [
        "insert", "insert_multiple", "update", "remove", "JSONStorage.write"]
    for c in checks:
        assert c["swapped_onto_db"] is True, (
            "%s: no os.replace/os.rename onto the database path" % c["name"])
        assert c["synced_before_swap"] is True, (
            "%s: the swapped-in file was not fsync'ed/fdatasync'ed before "
            "the swap" % c["name"])
        assert c["complete_at_swap"] is True, (
            "%s: the swapped-in file did not hold the complete new contents "
            "when it was swapped into place" % c["name"])


_SYNC_FAILURE = _program(r'''
import errno
import os
import tempfile

_real_fsync = os.fsync
_real_fdatasync = getattr(os, 'fdatasync', None)
armed = []
attempts = []


def _failing(real):
    def wrapper(fd):
        if armed:
            attempts.append(1)
            raise OSError(errno.EIO, 'injected fsync failure')
        return real(fd)
    return wrapper


os.fsync = _failing(_real_fsync)
if _real_fdatasync is not None:
    os.fdatasync = _failing(_real_fdatasync)

from tinydb import TinyDB, where

d = tempfile.mkdtemp()
path = os.path.join(d, 'db.json')
old_docs = [{'n': i, 'value': 'old value %d' % i} for i in range(25)]
db = TinyDB(path)
db.insert_multiple(old_docs)
with open(path, 'rb') as fh:
    before = fh.read()
listing_before = sorted(os.listdir(d))
outcomes = []
armed.append(True)
try:
    for operation in (lambda: db.insert({'n': 'new'}),
                      lambda: db.truncate(),
                      lambda: db.remove(where('n') == 1)):
        try:
            operation()
            outcomes.append('returned normally')
        except Exception as exc:
            outcomes.append('raised ' + type(exc).__name__)
finally:
    del armed[:]
listing_after = sorted(os.listdir(d))
with open(path, 'rb') as fh:
    after = fh.read()
try:
    reopened = [dict(x) for x in TinyDB(path).all()]
except Exception as exc:
    reopened = 'error: ' + type(exc).__name__
return {
    'outcomes': outcomes,
    'sync_attempted': len(attempts) > 0,
    'bytes_unchanged': after == before,
    'listing_before': listing_before,
    'listing_after': listing_after,
    'reopened_is_old': reopened == old_docs,
    'reopened': reopened if reopened != old_docs else None,
}
''')


def test_sync_failure_aborts_write():
    v = _value(run_python(_SYNC_FAILURE, timeout=60.0))
    assert v["sync_attempted"] is True, (
        "the write never called os.fsync/os.fdatasync")
    for outcome in v["outcomes"]:
        assert outcome.startswith("raised"), (
            "a write whose fsync failed returned normally: %r"
            % v["outcomes"])
    assert v["bytes_unchanged"] is True, (
        "database file changed although fsync of the new contents failed")
    assert v["reopened_is_old"] is True, v["reopened"]
    assert v["listing_after"] == v["listing_before"], (
        "temporary file left behind after a failed write: %r -> %r"
        % (v["listing_before"], v["listing_after"]))
