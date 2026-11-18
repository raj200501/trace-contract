"""Reference checks for CS-02: writes that fail partway.

The failure is injected inside the snippet's own process by lowering
RLIMIT_FSIZE (with SIGXFSZ ignored), so that any write to any file past the
limit fails with EFBIG, whatever way the candidate writes its data. A control
write in a separate scratch directory proves that the limit is in effect.

After the failed write the database file must be byte-for-byte unchanged,
still valid JSON, and the database directory must hold no other file.
Whether (and which) exception is raised is not specified, so it is only
recorded, never asserted.
"""

import json
import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    'test_failed_insert_keeps_previous_file':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
    'test_failed_remove_below_current_size_keeps_file':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
    'test_failed_table_update_keeps_file':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
    'test_failed_storage_write_with_encoding_and_kwargs':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
    'test_failure_at_various_offsets_keeps_file':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
    'test_failed_first_write_leaves_file_as_it_was':
        ['R-atomic', 'R-original-intact', 'R-no-temp-files'],
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

    def read_bytes(path):
        with open(path, 'rb') as handle:
            return handle.read()

    def parse(raw, encoding='utf-8'):
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

    def failure_report(directory, path, before, outcome, closable,
                       encoding='utf-8'):
        after = read_bytes(path)
        report = {
            'control': outcome['control'],
            'raised': outcome['raised'],
            'unchanged': after == before,
            'sizes': [len(before), len(after)],
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


def _check_report(report, expected_data, db_name):
    assert report['control'] == 'EFBIG', report
    assert report['parsed'] == {'valid': True, 'data': expected_data}, report
    assert report['unchanged'] is True, report
    assert report['listing'] == [db_name], report
    assert report['unchanged_after_close'] is True, report
    assert report['listing_after_close'] == [db_name], report


def test_failed_insert_keeps_previous_file():
    # The limit lies between the old and the new file size
    body = textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'db.json')
        db = TinyDB(path)
        db.insert({'name': 'alice', 'n': 1})
        db.insert({'name': 'bob', 'n': 2})
        before = read_bytes(path)
        outcome = with_fsize_limit(
            len(before) + 16,
            lambda: db.insert({'name': 'carol', 'blob': 'c' * 6000}))
        result = failure_report(d, path, before, outcome, db)
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = {'_default': {'1': {'name': 'alice', 'n': 1},
                             '2': {'name': 'bob', 'n': 2}}}
    _check_report(r.value, expected, 'db.json')


def test_failed_remove_below_current_size_keeps_file():
    # The new data is smaller than the old file, the limit smaller than both
    rows = [{'idx': i, 'text': 'row-%03d-' % i + '.' * 40} for i in range(40)]
    body = _embed('ROWS', rows) + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'db.json')
        db = TinyDB(path)
        db.insert_multiple(ROWS)
        before = read_bytes(path)
        outcome = with_fsize_limit(
            256, lambda: db.remove(doc_ids=[1, 2]))
        result = failure_report(d, path, before, outcome, db)
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = {'_default': {str(i + 1): row for i, row in enumerate(rows)}}
    _check_report(r.value, expected, 'db.json')
    assert r.value['sizes'][0] > 256


def test_failed_table_update_keeps_file():
    # Several tables, indented output, limit at half the old file size
    body = textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'store.json')
        db = TinyDB(path, indent=2)
        db.insert({'kind': 'meta', 'version': 1})
        items = db.table('items')
        items.insert_multiple(
            [{'sku': 'A%02d' % i, 'qty': i} for i in range(12)])
        before = read_bytes(path)
        outcome = with_fsize_limit(
            len(before) // 2,
            lambda: items.update({'note': 'n' * 300}, Query().qty >= 0))
        result = failure_report(d, path, before, outcome, db)
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    expected = {
        '_default': {'1': {'kind': 'meta', 'version': 1}},
        'items': {str(i + 1): {'sku': 'A%02d' % i, 'qty': i}
                  for i in range(12)},
    }
    _check_report(r.value, expected, 'store.json')


def test_failed_storage_write_with_encoding_and_kwargs():
    old = {'_default': {
        '1': {'greeting': 'こんにちは', 'city': 'Zürich'},
        '2': {'greeting': 'привет'},
    }}
    new = {'_default': dict(old['_default'],
                            **{'3': {'text': '世界' * 2000}})}
    body = _embed('OLD', old) + _embed('NEW', new) + textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'data.json')
        storage = JSONStorage(path, encoding='utf-16', indent=2,
                              ensure_ascii=False)
        storage.write(OLD)
        before = read_bytes(path)
        outcome = with_fsize_limit(len(before) + 8,
                                   lambda: storage.write(NEW))
        result = failure_report(d, path, before, outcome, storage,
                                encoding='utf-16')
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    _check_report(r.value, old, 'data.json')


def test_failure_at_various_offsets_keeps_file():
    # The write fails at the very first byte, right after it, in the middle
    # of the old size, in the middle of the new size and at the last byte
    old = {'_default': {str(i): {'v': 'old-%d' % i} for i in range(1, 15)}}
    new = {'_default': {str(i): {'v': 'new-%d' % i, 'pad': 'p' * 60}
                        for i in range(1, 40)}}
    body = _embed('OLD', old) + _embed('NEW', new) + textwrap.dedent('''
        new_size = len(json.dumps(NEW, indent=1).encode('utf-8'))
        cases = {'zero': 0, 'one': 1, 'forty': 40,
                 'half_new': new_size // 2, 'last_byte': new_size - 1}
        result = {}
        for name, limit in sorted(cases.items()):
            d = fresh_dir(name)
            path = os.path.join(d, 'db.json')
            storage = JSONStorage(path, indent=1)
            storage.write(OLD)
            before = read_bytes(path)
            outcome = with_fsize_limit(
                limit, lambda: storage.write(NEW))
            result[name] = failure_report(d, path, before, outcome, storage)
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    assert sorted(r.value) == ['forty', 'half_new', 'last_byte', 'one', 'zero']
    for name in sorted(r.value):
        _check_report(r.value[name], old, 'db.json')


def test_failed_first_write_leaves_file_as_it_was():
    # The very first write into a newly created (empty) database fails
    body = textwrap.dedent('''
        d = fresh_dir('db')
        path = os.path.join(d, 'fresh.json')
        db = TinyDB(path)

        def state():
            if not os.path.exists(path):
                return None
            return read_bytes(path).hex()

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
    ''')
    r = run_python(PRELUDE + body, timeout=60.0)
    assert r.ok, (r.error_type, r.error)
    res = r.value
    assert res['control'] == 'EFBIG', res
    expected_listing = [] if res['before'] is None else ['fresh.json']
    assert res['after'] == res['before'], res
    assert res['listing'] == expected_listing, res
    assert res['after_close'] == res['before'], res
    assert res['listing_after_close'] == expected_listing, res
