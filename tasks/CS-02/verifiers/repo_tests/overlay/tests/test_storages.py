import errno
import json
import os
import random
import stat
import subprocess
import sys
import tempfile
import textwrap

import pytest

import tinydb
from tinydb import TinyDB, where
from tinydb.storages import JSONStorage, MemoryStorage, Storage, touch
from tinydb.table import Document

random.seed()

doc = {'none': [None, None], 'int': 42, 'float': 3.1415899999999999,
       'list': ['LITE', 'RES_ACID', 'SUS_DEXT'],
       'dict': {'hp': 13, 'sp': 5},
       'bool': [True, False, True, False]}


def test_json(tmpdir):
    # Write contents
    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path)
    storage.write(doc)

    # Verify contents
    assert doc == storage.read()
    storage.close()


def test_json_kwargs(tmpdir):
    db_file = tmpdir.join('test.db')
    db = TinyDB(str(db_file), sort_keys=True, indent=4, separators=(',', ': '))

    # Write contents
    db.insert({'b': 1})
    db.insert({'a': 1})

    assert db_file.read() == '''{
    "_default": {
        "1": {
            "b": 1
        },
        "2": {
            "a": 1
        }
    }
}'''
    db.close()


def test_json_readwrite(tmpdir):
    """
    Regression test for issue #1
    """
    path = str(tmpdir.join('test.db'))

    # Create TinyDB instance
    db = TinyDB(path, storage=JSONStorage)

    item = {'name': 'A very long entry'}
    item2 = {'name': 'A short one'}

    def get(s):
        return db.get(where('name') == s)

    db.insert(item)
    assert get('A very long entry') == item

    db.remove(where('name') == 'A very long entry')
    assert get('A very long entry') is None

    db.insert(item2)
    assert get('A short one') == item2

    db.remove(where('name') == 'A short one')
    assert get('A short one') is None

    db.close()


@pytest.mark.parametrize('failing_function', ['fsync', 'replace'])
def test_json_failed_write_keeps_old_data(tmpdir, monkeypatch,
                                          failing_function):
    """
    If a write fails midway (e.g. because the disk is full), the database
    file has to keep its previous contents
    """
    path = str(tmpdir.join('test.db'))
    old_data = {'_default': {str(i): {'value': 'x' * 50} for i in range(20)}}
    new_data = {'_default': {}}

    storage = JSONStorage(path)
    storage.write(old_data)

    with open(path, 'rb') as handle:
        old_contents = handle.read()
    old_stat = os.stat(path)

    def fail(*args):
        raise OSError(errno.ENOSPC, 'No space left on device')

    with monkeypatch.context() as m:
        m.setattr(os, failing_function, fail)

        with pytest.raises(OSError, match='No space left on device'):
            storage.write(new_data)

    # The database file is exactly as it was...
    with open(path, 'rb') as handle:
        assert handle.read() == old_contents
    assert os.path.samestat(os.stat(path), old_stat)
    assert os.stat(path).st_mtime_ns == old_stat.st_mtime_ns
    assert storage.read() == old_data

    # ...no temporary file has been left behind...
    assert os.listdir(str(tmpdir)) == ['test.db']

    # ...and the storage can still be used
    storage.write(new_data)
    assert storage.read() == new_data
    assert os.listdir(str(tmpdir)) == ['test.db']
    storage.close()


@pytest.mark.parametrize('encoding, kwargs', [
    ('utf-8', {'indent': 4, 'sort_keys': True}),
    ('utf-16', {'ensure_ascii': False}),
    ('cp936', {'ensure_ascii': False, 'indent': 2, 'separators': (',', ': ')}),
])
def test_json_read_after_write(tmpdir, encoding, kwargs):
    """
    Reads see what has just been written, the file contains exactly what
    ``json.dumps`` returns for the given options (in the given encoding) and
    no temporary files are left behind
    """
    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path, encoding=encoding, **kwargs)

    for i in [3, 10, 0, 7, 1]:
        data = {'_default': {str(n): {'text': u'こんにちは世界', 'n': n}
                             for n in range(i)}}
        storage.write(data)

        assert storage.read() == data

        with open(path, 'rb') as handle:
            serialized = json.dumps(data, **kwargs)
            expected = serialized.replace('\n', os.linesep).encode(encoding)
            assert handle.read() == expected

        assert os.listdir(str(tmpdir)) == ['test.db']

    storage.close()


def test_json_read_after_failed_reopen(tmpdir, monkeypatch):
    """
    If re-opening the file after replacing it fails, the write has still
    succeeded and the next read re-opens the file
    """
    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path)
    open_for_reading = storage._open_for_reading
    calls = []

    def fail_once():
        calls.append(None)
        if len(calls) == 1:
            raise OSError(errno.EMFILE, 'Too many open files')
        return open_for_reading()

    monkeypatch.setattr(storage, '_open_for_reading', fail_once)

    storage.write(doc)
    assert storage.read() == doc
    assert len(calls) == 2
    storage.close()


def test_json_crash_during_write_keeps_old_data(tmpdir):
    """
    If the process dies in the middle of a write, the database file has to
    keep its previous contents
    """
    path = str(tmpdir.join('test.db'))
    script = textwrap.dedent('''
        import os, sys
        from tinydb.storages import JSONStorage

        storage = JSONStorage(sys.argv[1])
        storage.write({'_default': {'1': {'value': 'old' * 100}}})

        # Kill the process after the new data has been written, but before
        # the write has finished
        os.fsync = lambda fd: os._exit(23)
        storage.write({'_default': {}})
    ''')

    # Make sure the subprocess imports the same TinyDB as this test
    env = dict(os.environ)
    tinydb_root = os.path.dirname(os.path.dirname(tinydb.__file__))
    env['PYTHONPATH'] = os.pathsep.join(
        filter(None, [tinydb_root, env.get('PYTHONPATH')])
    )

    process = subprocess.run([sys.executable, '-c', script, path], env=env,
                             timeout=60)
    assert process.returncode == 23

    with open(path) as handle:
        assert json.load(handle) == {'_default': {'1': {'value': 'old' * 100}}}

    # The killed process couldn't remove its temporary file, so it's removed
    # when the database is opened for writing again
    assert len(os.listdir(str(tmpdir))) == 2
    JSONStorage(path).close()
    assert os.listdir(str(tmpdir)) == ['test.db']


def test_json_removes_temp_files_of_interrupted_writes(tmpdir):
    path = str(tmpdir.join('test.db'))
    touch(path, create_dirs=False)

    leftover = tmpdir.join('.test.db.k3j2_9ab.tinydb.tmp')
    leftover.write('{"_default": {"1": ')

    # Files that only look similar are kept, like the temporary files of the
    # database "test.db.v2"
    unrelated = ['.test.db.backup', '.test.db.v2.k3j2_9ab.tinydb.tmp',
                 'test.db.k3j2_9ab.tinydb.tmp', 'other.json']
    for name in unrelated:
        tmpdir.join(name).write('')

    # Opening the database read-only doesn't remove anything
    JSONStorage(path, access_mode='r').close()
    assert leftover.exists()

    JSONStorage(path).close()
    assert not leftover.exists()
    assert sorted(os.listdir(str(tmpdir))) == sorted(unrelated + ['test.db'])


@pytest.mark.skipif(os.name != 'posix', reason='Needs POSIX permissions')
def test_json_write_keeps_permissions(tmpdir):
    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path)
    os.chmod(path, 0o640)

    storage.write(doc)
    storage.close()

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640


def test_json_write_through_symlink(tmpdir):
    target = str(tmpdir.join('target.db'))
    link = str(tmpdir.join('link.db'))
    touch(target, create_dirs=False)

    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip('Symlinks are not supported')

    storage = JSONStorage(link)
    storage.write(doc)
    storage.close()

    # The symlink is kept and the file it points to is updated
    assert os.path.islink(link)
    with open(target) as handle:
        assert json.load(handle) == doc


def test_json_relative_path_after_chdir(tmpdir, monkeypatch):
    monkeypatch.chdir(tmpdir)
    storage = JSONStorage('test.db')

    # Writes go to the file that was opened, not to a file relative to the
    # new working directory
    monkeypatch.chdir(tmpdir.mkdir('other'))
    storage.write(doc)
    storage.close()

    assert json.loads(tmpdir.join('test.db').read()) == doc
    assert tmpdir.join('other').listdir() == []


@pytest.mark.skipif(os.name == 'nt',
                    reason="Windows can't replace files that are open")
def test_json_storages_sharing_a_file(tmpdir):
    path = str(tmpdir.join('test.db'))
    first = JSONStorage(path)
    second = JSONStorage(path)

    # Each storage sees what the other one has written
    first.write({'_default': {'1': {'a': 1}}})
    assert second.read() == {'_default': {'1': {'a': 1}}}

    second.write({'_default': {'2': {'b': 2}}})
    assert first.read() == {'_default': {'2': {'b': 2}}}

    first.close()
    second.close()


def test_json_read(tmpdir):
    r"""Open a database only for reading"""
    path = str(tmpdir.join('test.db'))
    with pytest.raises(FileNotFoundError):
        db = TinyDB(path, storage=JSONStorage, access_mode='r')
    # Create small database
    db = TinyDB(path, storage=JSONStorage)
    db.insert({'b': 1})
    db.insert({'a': 1})
    db.close()
    # Access in read mode
    db = TinyDB(path, storage=JSONStorage, access_mode='r')
    assert db.get(where('a') == 1) == {'a': 1}  # reading is fine
    with pytest.raises(IOError):
        db.insert({'c': 1})  # writing is not
    db.close()


def test_create_dirs():
    temp_dir = tempfile.gettempdir()

    while True:
        dname = os.path.join(temp_dir, str(random.getrandbits(20)))
        if not os.path.exists(dname):
            db_dir = dname
            db_file = os.path.join(db_dir, 'db.json')
            break

    with pytest.raises(IOError):
        JSONStorage(db_file)

    JSONStorage(db_file, create_dirs=True).close()
    assert os.path.exists(db_file)

    # Use create_dirs with already existing directory
    JSONStorage(db_file, create_dirs=True).close()
    assert os.path.exists(db_file)

    os.remove(db_file)
    os.rmdir(db_dir)


def test_json_invalid_directory():
    with pytest.raises(IOError):
        with TinyDB('/this/is/an/invalid/path/db.json', storage=JSONStorage):
            pass


def test_in_memory():
    # Write contents
    storage = MemoryStorage()
    storage.write(doc)

    # Verify contents
    assert doc == storage.read()

    # Test case for #21
    other = MemoryStorage()
    other.write({})
    assert other.read() != storage.read()


def test_in_memory_close():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert({})


def test_custom():
    # noinspection PyAbstractClass
    class MyStorage(Storage):
        pass

    with pytest.raises(TypeError):
        MyStorage()


def test_read_once():
    count = 0

    # noinspection PyAbstractClass
    class MyStorage(Storage):
        def __init__(self):
            self.memory = None

        def read(self):
            nonlocal count
            count += 1

            return self.memory

        def write(self, data):
            self.memory = data

    with TinyDB(storage=MyStorage) as db:
        assert count == 0

        db.table(db.default_table_name)

        assert count == 0

        db.all()

        assert count == 1

        db.insert({'foo': 'bar'})

        assert count == 3  # One for getting the next ID, one for the insert

        db.all()

        assert count == 4


def test_custom_with_exception():
    class MyStorage(Storage):
        def read(self):
            pass

        def write(self, data):
            pass

        def __init__(self):
            raise ValueError()

        def close(self):
            raise RuntimeError()

    with pytest.raises(ValueError):
        with TinyDB(storage=MyStorage) as db:
            pass


def test_yaml(tmpdir):
    """
    :type tmpdir: py._path.local.LocalPath
    """

    try:
        import yaml
    except ImportError:
        return pytest.skip('PyYAML not installed')

    def represent_doc(dumper, data):
        # Represent `Document` objects as their dict's string representation
        # which PyYAML understands
        return dumper.represent_data(dict(data))

    yaml.add_representer(Document, represent_doc)

    class YAMLStorage(Storage):
        def __init__(self, filename):
            self.filename = filename
            touch(filename, False)

        def read(self):
            with open(self.filename) as handle:
                data = yaml.safe_load(handle.read())
                return data

        def write(self, data):
            with open(self.filename, 'w') as handle:
                yaml.dump(data, handle)

        def close(self):
            pass

    # Write contents
    path = str(tmpdir.join('test.db'))
    db = TinyDB(path, storage=YAMLStorage)
    db.insert(doc)
    assert db.all() == [doc]

    db.update({'name': 'foo'})

    assert '!' not in tmpdir.join('test.db').read()

    assert db.contains(where('name') == 'foo')
    assert len(db) == 1


def test_encoding(tmpdir):
    japanese_doc = {"Test": u"こんにちは世界"}

    path = str(tmpdir.join('test.db'))
    # cp936 is used for japanese encodings
    jap_storage = JSONStorage(path, encoding="cp936")
    jap_storage.write(japanese_doc)

    try:
        exception = json.decoder.JSONDecodeError
    except AttributeError:
        exception = ValueError

    with pytest.raises(exception):
        # cp037 is used for english encodings
        eng_storage = JSONStorage(path, encoding="cp037")
        eng_storage.read()

    jap_storage = JSONStorage(path, encoding="cp936")
    assert japanese_doc == jap_storage.read()


def test_json_invalid_mode_warning(tmpdir):
    path = str(tmpdir.join('test.db'))
    with pytest.warns(UserWarning, match='Using an `access_mode` other than'):
        JSONStorage(path, access_mode='w')
