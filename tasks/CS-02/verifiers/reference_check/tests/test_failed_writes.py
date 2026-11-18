"""Reference checks for CS-02: writes that fail partway.

The failure is injected inside the snippet's own process by lowering
RLIMIT_FSIZE (with SIGXFSZ ignored), so that any write to any file past the
limit fails with EFBIG, whatever way the candidate writes its data. A control
write in a separate scratch directory proves that the limit is in effect.

Each scenario seeds the database file with known old bytes (written by the
snippet with plain file I/O, not through the candidate), then opens it with
TinyDB/JSONStorage and makes the first write after opening fail. So the state
before the failure doesn't depend on how the candidate writes or reads.

Each scenario runs once and is checked twice:

- the content check (R-atomic, R-original-intact): the database file is
  byte-for-byte unchanged and still valid JSON holding the old data, before
  and after closing;
- the listing check (R-no-temp-files): the database directory holds no file
  other than the database file, before and after closing.

Whether (and which) exception is raised is not specified, so it is only
recorded, never asserted.
"""

import json
import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    'test_failed_insert_keeps_previous_file':
        ['R-atomic', 'R-original-intact'],
    'test_failed_insert_leaves_no_temp_files':
        ['R-no-temp-files'],
    'test_failed_remove_below_current_size_keeps_file':
        ['R-atomic', 'R-original-intact'],
    'test_failed_remove_below_current_size_leaves_no_temp_files':
        ['R-no-temp-files'],
    'test_failed_table_update_keeps_file':
        ['R-atomic', 'R-original-intact'],
    'test_failed_table_update_leaves_no_temp_files':
        ['R-no-temp-files'],
    'test_failed_storage_write_with_encoding_and_kwargs':
        ['R-atomic', 'R-original-intact'],
    'test_failed_storage_write_with_encoding_leaves_no_temp_files':
        ['R-no-temp-files'],
    'test_failure_at_various_offsets_keeps_file':
        ['R-atomic', 'R-original-intact'],
    'test_failure_at_various_offsets_leaves_no_temp_files':
        ['R-no-temp-files'],
    'test_failed_first_write_leaves_file_as_it_was':
        ['R-atomic', 'R-original-intact'],
    'test_failed_first_write_leaves_no_temp_files':
        ['R-no-temp-files'],
}

PRELUDE = textwrap.dedent('''
    import errno
    import json
    import os
    import resource
    import signal
    import tempfile

    from tinydb import TinyDB, Query
    from tinydb.storages import JSONStorage

    BASE_DIR = tempfile.mkdtemp(prefix='cs02_refcheck_', dir='/tmp')
    CONTROL_DIR = os.path.join(BASE_DIR, '_control')
    os.mkdir(CONTROL_DIR)

    def fresh_dir(name):
        path = os.path.join(BASE_DIR, name)
        os.mkdir(path)
        return path

    def seed(path, data, encoding='utf-8', **kwargs):
        """Write the old database file directly, not through TinyDB."""
        raw = json.dumps(data, **kwargs).encode(encoding)
        with open(path, 'wb') as handle:
            handle.write(raw)
        return raw

    def read_bytes(path):
        try:
            with open(path, 'rb') as handle:
                return handle.read()
        except OSError:
            return None

    def parse(raw, encoding='utf-8'):
        if raw is None:
            return {'valid': False, 'data': None, 'error': 'no file'}
        try:
            return {'valid': True, 'data': json.loads(raw.decode(encoding))}
        except Exception as exc:
            return {'valid': False, 'data': None, 'error': type(exc).__name__}

    def control_write(limit):
        # Proves that the lowered limit is in effect for this process
        path = os.path.join(CONTROL_DIR, 'control.bin')
        data = b'x' * (limit + 1)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            return 'no-error'
        except OSError as exc:
            return errno.errorcode.get(exc.errno, str(exc.errno))
        finally:
            os.close(fd)
            os.remove(path)

    def with_fsize_limit(limit, action):
        """Call action() while RLIMIT_FSIZE is lowered to limit bytes."""
        try:
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        except (ValueError, OSError, AttributeError):
            pass
        soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        outcome = {'control': None, 'raised': None}
        resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
        try:
            outcome['control'] = control_write(limit)
            try:
                action()
            except Exception as exc:
                outcome['raised'] = type(exc).__name__
        finally:
            resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
        return outcome

    def close_quietly(obj):
        try:
            obj.close()
            return None
        except Exception as exc:
            return type(exc).__name__

    def size(raw):
        return None if raw is None else len(raw)

    def failure_report(directory, path, before, outcome, closable,
                       encoding='utf-8'):
        after = read_bytes(path)
        report = {
            'control': outcome['control'],
            'raised': outcome['raised'],
            'unchanged': after == before,
            'sizes': [size(before), size(after)],
            'parsed': parse(after, encoding),
            'listing': sorted(os.listdir(directory)),
        }
        report['close_error'] = close_quietly(closable)
        report['unchanged_after_close'] = read_bytes(path) == before
        report['listing_after_close'] = sorted(os.listdir(directory))
        return report
''')


def _embed(name, value):
    """Python source that recreates a JSON value inside the snippet."""
    return '%s = json.loads(%r)\n' % (name, json.dumps(value))


INSERT_OLD = {'_default': {'1': {'name': 'alice', 'n': 1},
                           '2': {'name': 'bob', 'n': 2}}}

REMOVE_OLD = {'_default': {str(i + 1): {'idx': i,
                                        'text': 'row-%03d-' % i + '.' * 40}
                           for i in range(40)}}

TABLE_OLD = {
    '_default': {'1': {'kind': 'meta', 'version': 1}},
    'items': {str(i + 1): {'sku': 'A%02d' % i, 'qty': i} for i in range(12)},
}

UTF16_OLD = {'_default': {
    '1': {'greeting': 'こんにちは', 'city': 'Zürich'},
    '2': {'greeting': 'привет'},
}}
UTF16_NEW = {'_default': dict(UTF16_OLD['_default'],
                              **{'3': {'text': '世界' * 2000}})}

OFFSETS_OLD = {'_default': {str(i): {'v': 'old-%d' % i}
                            for i in range(1, 15)}}
OFFSETS_NEW = {'_default': {str(i): {'v': 'new-%d' % i, 'pad': 'p' * 60}
                            for i in range(1, 40)}}
OFFSET_CASES = ['forty', 'half_new', 'last_byte', 'one', 'zero']

SCENARIOS = {
    # The limit lies between the old and the new file size
    'insert': _embed('OLD', INSERT_OLD) + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'db.json')
        seeded = seed(path, OLD)
        db = TinyDB(path)
        before = read_bytes(path)
        outcome = with_fsize_limit(
            len(seeded) + 16,
            lambda: db.insert({'name': 'carol', 'blob': 'c' * 6000}))
        result = failure_report(d, path, before, outcome, db)
    '''),
    # The new data is smaller than the old file, the limit smaller than both
    'remove': _embed('OLD', REMOVE_OLD) + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'db.json')
        seed(path, OLD)
        db = TinyDB(path)
        before = read_bytes(path)
        outcome = with_fsize_limit(
            256, lambda: db.remove(doc_ids=[1, 2]))
        result = failure_report(d, path, before, outcome, db)
    '''),
    # Several tables, indented output, limit at half the old file size
    'table_update': _embed('OLD', TABLE_OLD) + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'store.json')
        seeded = seed(path, OLD, indent=2)
        db = TinyDB(path, indent=2)
        items = db.table('items')
        before = read_bytes(path)
        outcome = with_fsize_limit(
            len(seeded) // 2,
            lambda: items.update({'note': 'n' * 300}, Query().qty >= 0))
        result = failure_report(d, path, before, outcome, db)
    '''),
    # A storage with an encoding and json kwargs
    'utf16_storage': (_embed('OLD', UTF16_OLD) + _embed('NEW', UTF16_NEW)
                      + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'data.json')
        seeded = seed(path, OLD, encoding='utf-16', indent=2,
                      ensure_ascii=False)
        storage = JSONStorage(path, encoding='utf-16', indent=2,
                              ensure_ascii=False)
        before = read_bytes(path)
        outcome = with_fsize_limit(len(seeded) + 8,
                                   lambda: storage.write(NEW))
        result = failure_report(d, path, before, outcome, storage,
                                encoding='utf-16')
    ''')),
    # The write fails at the very first byte, right after it, within the old
    # size, in the middle of the new size and at its last byte. The new size
    # is that of the file the same storage configuration writes for NEW in a
    # scratch directory, so the last two limits fall inside what the
    # candidate actually writes.
    'offsets': (_embed('OLD', OFFSETS_OLD) + _embed('NEW', OFFSETS_NEW)
                + textwrap.dedent('''
        sizing_path = os.path.join(fresh_dir('_sizing'), 'db.json')
        new_size = None
        sizing_error = None
        try:
            sizing = JSONStorage(sizing_path, indent=1)
            sizing.write(NEW)
            new_size = os.path.getsize(sizing_path)
            close_quietly(sizing)
        except Exception as exc:
            sizing_error = type(exc).__name__
        if not new_size:
            new_size = len(json.dumps(NEW, indent=1).encode('utf-8'))
        cases = {'zero': 0, 'one': 1, 'forty': 40,
                 'half_new': new_size // 2, 'last_byte': new_size - 1}
        result = {'new_size': new_size, 'sizing_error': sizing_error,
                  'cases': {}}
        for name, limit in sorted(cases.items()):
            d = fresh_dir(name)
            path = os.path.join(d, 'db.json')
            seed(path, OLD, indent=1)
            storage = JSONStorage(path, indent=1)
            before = read_bytes(path)
            outcome = with_fsize_limit(
                limit, lambda: storage.write(NEW))
            result['cases'][name] = failure_report(
                d, path, before, outcome, storage)
    ''')),
    # The very first write into a newly created (empty) database fails
    'first_write': textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'fresh.json')
        db = TinyDB(path)

        def state():
            raw = read_bytes(path)
            return None if raw is None else raw.hex()

        before = state()
        outcome = with_fsize_limit(
            64, lambda: db.insert({'payload': 'p' * 5000}))
        result = {
            'control': outcome['control'],
            'raised': outcome['raised'],
            'before': before,
            'after': state(),
            'listing': sorted(os.listdir(d)),
            'close_error': close_quietly(db),
        }
        result['after_close'] = state()
        result['listing_after_close'] = sorted(os.listdir(d))
    '''),
}

_RUNS = {}
_CALLS = {}


def _run(scenario, check):
    """Run a scenario's snippet; its content and listing check share a run.

    The n-th call of each check uses the scenario's n-th run, so both checks
    judge the same run, and repeating the tests in one process still runs
    the snippet again.
    """
    n = _CALLS.get((scenario, check), 0)
    _CALLS[(scenario, check)] = n + 1
    if (scenario, n) not in _RUNS:
        _RUNS[(scenario, n)] = run_python(PRELUDE + SCENARIOS[scenario],
                                          timeout=60.0)
    return _RUNS[(scenario, n)]


def _content(report):
    """The part of a failure report the content check looks at."""
    return {key: report[key] for key in
            ('control', 'unchanged', 'parsed', 'unchanged_after_close')}


def _expected_content(old):
    return {
        'control': 'EFBIG',
        'unchanged': True,
        'parsed': {'valid': True, 'data': old},
        'unchanged_after_close': True,
    }


def _other_files(report, db_name):
    """The part of a failure report the listing check looks at: the files
    in the database directory other than the database file itself."""
    return {
        'control': report['control'],
        'other_files': sorted(set(report['listing']) - {db_name}),
        'other_files_after_close':
            sorted(set(report['listing_after_close']) - {db_name}),
    }


NO_OTHER_FILES = {'control': 'EFBIG', 'other_files': [],
                  'other_files_after_close': []}


def test_failed_insert_keeps_previous_file():
    r = _run('insert', 'content')
    assert r.ok, (r.error_type, r.error)
    assert _content(r.value) == _expected_content(INSERT_OLD), r.value


def test_failed_insert_leaves_no_temp_files():
    r = _run('insert', 'listing')
    assert r.ok, (r.error_type, r.error)
    assert _other_files(r.value, 'db.json') == NO_OTHER_FILES, r.value


def test_failed_remove_below_current_size_keeps_file():
    r = _run('remove', 'content')
    assert r.ok, (r.error_type, r.error)
    assert _content(r.value) == _expected_content(REMOVE_OLD), r.value
    assert r.value['sizes'][0] > 256, r.value


def test_failed_remove_below_current_size_leaves_no_temp_files():
    r = _run('remove', 'listing')
    assert r.ok, (r.error_type, r.error)
    assert _other_files(r.value, 'db.json') == NO_OTHER_FILES, r.value


def test_failed_table_update_keeps_file():
    r = _run('table_update', 'content')
    assert r.ok, (r.error_type, r.error)
    assert _content(r.value) == _expected_content(TABLE_OLD), r.value


def test_failed_table_update_leaves_no_temp_files():
    r = _run('table_update', 'listing')
    assert r.ok, (r.error_type, r.error)
    assert _other_files(r.value, 'store.json') == NO_OTHER_FILES, r.value


def test_failed_storage_write_with_encoding_and_kwargs():
    r = _run('utf16_storage', 'content')
    assert r.ok, (r.error_type, r.error)
    assert _content(r.value) == _expected_content(UTF16_OLD), r.value


def test_failed_storage_write_with_encoding_leaves_no_temp_files():
    r = _run('utf16_storage', 'listing')
    assert r.ok, (r.error_type, r.error)
    assert _other_files(r.value, 'data.json') == NO_OTHER_FILES, r.value


def test_failure_at_various_offsets_keeps_file():
    r = _run('offsets', 'content')
    assert r.ok, (r.error_type, r.error)
    cases = r.value['cases']
    assert sorted(cases) == OFFSET_CASES, r.value
    for name in OFFSET_CASES:
        assert _content(cases[name]) == _expected_content(OFFSETS_OLD), (
            name, r.value['new_size'], cases[name])


def test_failure_at_various_offsets_leaves_no_temp_files():
    r = _run('offsets', 'listing')
    assert r.ok, (r.error_type, r.error)
    cases = r.value['cases']
    assert sorted(cases) == OFFSET_CASES, r.value
    for name in OFFSET_CASES:
        assert _other_files(cases[name], 'db.json') == NO_OTHER_FILES, (
            name, cases[name])


def test_failed_first_write_leaves_file_as_it_was():
    r = _run('first_write', 'content')
    assert r.ok, (r.error_type, r.error)
    res = r.value
    assert res['control'] == 'EFBIG', res
    assert res['after'] == res['before'], res
    assert res['after_close'] == res['before'], res


def test_failed_first_write_leaves_no_temp_files():
    # Whether the database file exists (before and after) is up to the
    # content check; here only files other than it count
    r = _run('first_write', 'listing')
    assert r.ok, (r.error_type, r.error)
    assert _other_files(r.value, 'fresh.json') == NO_OTHER_FILES, r.value
