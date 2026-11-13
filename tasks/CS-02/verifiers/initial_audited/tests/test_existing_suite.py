"""
Hidden behavioural test for task CS-02 (condition initial_plain), R4:
the repository's existing tests still pass.

The storage-related test modules of the base commit (``tests/conftest.py``,
``test_storages.py``, ``test_middlewares.py``, ``test_tinydb.py``,
``test_tables.py`` and ``test_operations.py``; their JSON variants all use
``JSONStorage``) are copied below verbatim. Inside the sandbox they are
written to a temporary directory and run with pytest against the candidate's
``tinydb`` package, so a candidate that edited or removed these tests in its
own repository is still checked against the original ones.
"""

import textwrap

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_existing_test_suite_still_passes": ["R4"],
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


# Number of these tests that pass on the base commit (the only other one,
# test_yaml, is skipped because PyYAML is not installed).
_BASE_PASSED = 181

_BASE_TEST_FILES = {}

_BASE_TEST_FILES['conftest.py'] = r'''import os.path
import tempfile
from pathlib import Path

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


@pytest.fixture(params=['memory', 'json'])
def db(request, tmp_path: Path):
    if request.param == 'json':
        db_ = TinyDB(tmp_path / 'test.db', storage=JSONStorage)
    else:
        db_ = TinyDB(storage=MemoryStorage)

    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    yield db_


@pytest.fixture
def storage():
    return CachingMiddleware(MemoryStorage)()
'''

_BASE_TEST_FILES['test_storages.py'] = (
    'import json\n'
    'import os\n'
    'import random\n'
    'import tempfile\n'
    '\n'
    'import pytest\n'
    '\n'
    'from tinydb import TinyDB, where\n'
    'from tinydb.storages import JSONStorage, MemoryStorage, Storage, touch\n'
    'from tinydb.table import Document\n'
    '\n'
    'random.seed()\n'
    '\n'
    "doc = {'none': [None, None], 'int': 42, 'float': 3.1415899999999999,\n"
    "       'list': ['LITE', 'RES_ACID', 'SUS_DEXT'],\n"
    "       'dict': {'hp': 13, 'sp': 5},\n"
    "       'bool': [True, False, True, False]}\n"
    '\n'
    '\n'
    'def test_json(tmpdir):\n'
    '    # Write contents\n'
    "    path = str(tmpdir.join('test.db'))\n"
    '    storage = JSONStorage(path)\n'
    '    storage.write(doc)\n'
    '\n'
    '    # Verify contents\n'
    '    assert doc == storage.read()\n'
    '    storage.close()\n'
    '\n'
    '\n'
    'def test_json_kwargs(tmpdir):\n'
    "    db_file = tmpdir.join('test.db')\n"
    "    db = TinyDB(str(db_file), sort_keys=True, indent=4, separators=(',', ': '))\n"
    '\n'
    '    # Write contents\n'
    "    db.insert({'b': 1})\n"
    "    db.insert({'a': 1})\n"
    '\n'
    "    assert db_file.read() == '''{\n"
    '    "_default": {\n'
    '        "1": {\n'
    '            "b": 1\n'
    '        },\n'
    '        "2": {\n'
    '            "a": 1\n'
    '        }\n'
    '    }\n'
    "}'''\n"
    '    db.close()\n'
    '\n'
    '\n'
    'def test_json_readwrite(tmpdir):\n'
    '    """\n'
    '    Regression test for issue #1\n'
    '    """\n'
    "    path = str(tmpdir.join('test.db'))\n"
    '\n'
    '    # Create TinyDB instance\n'
    '    db = TinyDB(path, storage=JSONStorage)\n'
    '\n'
    "    item = {'name': 'A very long entry'}\n"
    "    item2 = {'name': 'A short one'}\n"
    '\n'
    '    def get(s):\n'
    "        return db.get(where('name') == s)\n"
    '\n'
    '    db.insert(item)\n'
    "    assert get('A very long entry') == item\n"
    '\n'
    "    db.remove(where('name') == 'A very long entry')\n"
    "    assert get('A very long entry') is None\n"
    '\n'
    '    db.insert(item2)\n'
    "    assert get('A short one') == item2\n"
    '\n'
    "    db.remove(where('name') == 'A short one')\n"
    "    assert get('A short one') is None\n"
    '\n'
    '    db.close()\n'
    '\n'
    '\n'
    'def test_json_read(tmpdir):\n'
    '    r"""Open a database only for reading"""\n'
    "    path = str(tmpdir.join('test.db'))\n"
    '    with pytest.raises(FileNotFoundError):\n'
    "        db = TinyDB(path, storage=JSONStorage, access_mode='r')\n"
    '    # Create small database\n'
    '    db = TinyDB(path, storage=JSONStorage)\n'
    "    db.insert({'b': 1})\n"
    "    db.insert({'a': 1})\n"
    '    db.close()\n'
    '    # Access in read mode\n'
    "    db = TinyDB(path, storage=JSONStorage, access_mode='r')\n"
    "    assert db.get(where('a') == 1) == {'a': 1}  # reading is fine\n"
    '    with pytest.raises(IOError):\n'
    "        db.insert({'c': 1})  # writing is not\n"
    '    db.close()\n'
    '\n'
    '\n'
    'def test_create_dirs():\n'
    '    temp_dir = tempfile.gettempdir()\n'
    '\n'
    '    while True:\n'
    '        dname = os.path.join(temp_dir, str(random.getrandbits(20)))\n'
    '        if not os.path.exists(dname):\n'
    '            db_dir = dname\n'
    "            db_file = os.path.join(db_dir, 'db.json')\n"
    '            break\n'
    '\n'
    '    with pytest.raises(IOError):\n'
    '        JSONStorage(db_file)\n'
    '\n'
    '    JSONStorage(db_file, create_dirs=True).close()\n'
    '    assert os.path.exists(db_file)\n'
    '\n'
    '    # Use create_dirs with already existing directory\n'
    '    JSONStorage(db_file, create_dirs=True).close()\n'
    '    assert os.path.exists(db_file)\n'
    '\n'
    '    os.remove(db_file)\n'
    '    os.rmdir(db_dir)\n'
    '\n'
    '\n'
    'def test_json_invalid_directory():\n'
    '    with pytest.raises(IOError):\n'
    "        with TinyDB('/this/is/an/invalid/path/db.json', storage=JSONStorage):\n"
    '            pass\n'
    '\n'
    '\n'
    'def test_in_memory():\n'
    '    # Write contents\n'
    '    storage = MemoryStorage()\n'
    '    storage.write(doc)\n'
    '\n'
    '    # Verify contents\n'
    '    assert doc == storage.read()\n'
    '\n'
    '    # Test case for #21\n'
    '    other = MemoryStorage()\n'
    '    other.write({})\n'
    '    assert other.read() != storage.read()\n'
    '\n'
    '\n'
    'def test_in_memory_close():\n'
    '    with TinyDB(storage=MemoryStorage) as db:\n'
    '        db.insert({})\n'
    '\n'
    '\n'
    'def test_custom():\n'
    '    # noinspection PyAbstractClass\n'
    '    class MyStorage(Storage):\n'
    '        pass\n'
    '\n'
    '    with pytest.raises(TypeError):\n'
    '        MyStorage()\n'
    '\n'
    '\n'
    'def test_read_once():\n'
    '    count = 0\n'
    '\n'
    '    # noinspection PyAbstractClass\n'
    '    class MyStorage(Storage):\n'
    '        def __init__(self):\n'
    '            self.memory = None\n'
    '\n'
    '        def read(self):\n'
    '            nonlocal count\n'
    '            count += 1\n'
    '\n'
    '            return self.memory\n'
    '\n'
    '        def write(self, data):\n'
    '            self.memory = data\n'
    '\n'
    '    with TinyDB(storage=MyStorage) as db:\n'
    '        assert count == 0\n'
    '\n'
    '        db.table(db.default_table_name)\n'
    '\n'
    '        assert count == 0\n'
    '\n'
    '        db.all()\n'
    '\n'
    '        assert count == 1\n'
    '\n'
    "        db.insert({'foo': 'bar'})\n"
    '\n'
    '        assert count == 3  # One for getting the next ID, one for the insert\n'
    '\n'
    '        db.all()\n'
    '\n'
    '        assert count == 4\n'
    '\n'
    '\n'
    'def test_custom_with_exception():\n'
    '    class MyStorage(Storage):\n'
    '        def read(self):\n'
    '            pass\n'
    '\n'
    '        def write(self, data):\n'
    '            pass\n'
    '\n'
    '        def __init__(self):\n'
    '            raise ValueError()\n'
    '\n'
    '        def close(self):\n'
    '            raise RuntimeError()\n'
    '\n'
    '    with pytest.raises(ValueError):\n'
    '        with TinyDB(storage=MyStorage) as db:\n'
    '            pass\n'
    '\n'
    '\n'
    'def test_yaml(tmpdir):\n'
    '    """\n'
    '    :type tmpdir: py._path.local.LocalPath\n'
    '    """\n'
    '\n'
    '    try:\n'
    '        import yaml\n'
    '    except ImportError:\n'
    "        return pytest.skip('PyYAML not installed')\n"
    '\n'
    '    def represent_doc(dumper, data):\n'
    "        # Represent `Document` objects as their dict's string representation\n"
    '        # which PyYAML understands\n'
    '        return dumper.represent_data(dict(data))\n'
    '\n'
    '    yaml.add_representer(Document, represent_doc)\n'
    '\n'
    '    class YAMLStorage(Storage):\n'
    '        def __init__(self, filename):\n'
    '            self.filename = filename\n'
    '            touch(filename, False)\n'
    '\n'
    '        def read(self):\n'
    '            with open(self.filename) as handle:\n'
    '                data = yaml.safe_load(handle.read())\n'
    '                return data\n'
    '\n'
    '        def write(self, data):\n'
    "            with open(self.filename, 'w') as handle:\n"
    '                yaml.dump(data, handle)\n'
    '\n'
    '        def close(self):\n'
    '            pass\n'
    '\n'
    '    # Write contents\n'
    "    path = str(tmpdir.join('test.db'))\n"
    '    db = TinyDB(path, storage=YAMLStorage)\n'
    '    db.insert(doc)\n'
    '    assert db.all() == [doc]\n'
    '\n'
    "    db.update({'name': 'foo'})\n"
    '\n'
    "    assert '!' not in tmpdir.join('test.db').read()\n"
    '\n'
    "    assert db.contains(where('name') == 'foo')\n"
    '    assert len(db) == 1\n'
    '\n'
    '\n'
    'def test_encoding(tmpdir):\n'
    '    japanese_doc = {"Test": u"こんにちは世界"}\n'
    '\n'
    "    path = str(tmpdir.join('test.db'))\n"
    '    # cp936 is used for japanese encodings\n'
    '    jap_storage = JSONStorage(path, encoding="cp936")\n'
    '    jap_storage.write(japanese_doc)\n'
    '\n'
    '    try:\n'
    '        exception = json.decoder.JSONDecodeError\n'
    '    except AttributeError:\n'
    '        exception = ValueError\n'
    '\n'
    '    with pytest.raises(exception):\n'
    '        # cp037 is used for english encodings\n'
    '        eng_storage = JSONStorage(path, encoding="cp037")\n'
    '        eng_storage.read()\n'
    '\n'
    '    jap_storage = JSONStorage(path, encoding="cp936")\n'
    '    assert japanese_doc == jap_storage.read()\n'
    '\n'
    '\n'
    'def test_json_invalid_mode_warning(tmpdir):\n'
    "    path = str(tmpdir.join('test.db'))\n"
    "    with pytest.warns(UserWarning, match='Using an `access_mode` other than'):\n"
    "        JSONStorage(path, access_mode='w')\n"
)

_BASE_TEST_FILES['test_middlewares.py'] = r'''import os

import pytest

from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage, JSONStorage

doc = {'none': [None, None], 'int': 42, 'float': 3.1415899999999999,
       'list': ['LITE', 'RES_ACID', 'SUS_DEXT'],
       'dict': {'hp': 13, 'sp': 5},
       'bool': [True, False, True, False]}


def test_caching(storage):
    # Write contents
    storage.write(doc)

    # Verify contents
    assert doc == storage.read()


def test_caching_read():
    db = TinyDB(storage=CachingMiddleware(MemoryStorage))
    assert db.all() == []


def test_caching_write_many(storage):
    storage.WRITE_CACHE_SIZE = 3

    # Storage should be still empty
    assert storage.memory is None

    # Write contents
    for x in range(2):
        storage.write(doc)
        assert storage.memory is None  # Still cached

    storage.write(doc)

    # Verify contents: Cache should be emptied and written to storage
    assert storage.memory


def test_caching_flush(storage):
    # Write contents
    for _ in range(CachingMiddleware.WRITE_CACHE_SIZE - 1):
        storage.write(doc)

    # Not yet flushed...
    assert storage.memory is None

    storage.write(doc)

    # Verify contents: Cache should be emptied and written to storage
    assert storage.memory


def test_caching_flush_manually(storage):
    # Write contents
    storage.write(doc)

    storage.flush()

    # Verify contents: Cache should be emptied and written to storage
    assert storage.memory


def test_caching_write(storage):
    # Write contents
    storage.write(doc)

    storage.close()

    # Verify contents: Cache should be emptied and written to storage
    assert storage.storage.memory


def test_nested():
    storage = CachingMiddleware(MemoryStorage)
    storage()  # Initialization

    # Write contents
    storage.write(doc)

    # Verify contents
    assert doc == storage.read()


def test_caching_json_write(tmpdir):
    path = str(tmpdir.join('test.db'))

    with TinyDB(path, storage=CachingMiddleware(JSONStorage)) as db:
        db.insert({'key': 'value'})

    # Verify database filesize
    statinfo = os.stat(path)
    assert statinfo.st_size != 0

    # Assert JSON file has been closed
    assert db._storage._handle.closed

    del db

    # Reopen database
    with TinyDB(path, storage=CachingMiddleware(JSONStorage)) as db:
        assert db.all() == [{'key': 'value'}]


def test_caching_rejects_use_after_close(tmpdir):
    path = str(tmpdir.join('closed.db'))
    db = TinyDB(path, storage=CachingMiddleware(JSONStorage))
    db.insert({'key': 'value'})
    db.close()

    with pytest.raises(ValueError, match='closed'):
        db.insert({'key': 'again'})

    with pytest.raises(ValueError, match='closed'):
        db.all()

    with TinyDB(path, storage=CachingMiddleware(JSONStorage)) as reopened:
        assert reopened.all() == [{'key': 'value'}]
'''

_BASE_TEST_FILES['test_tinydb.py'] = r'''import re
from collections.abc import Mapping

import pytest

from tinydb import TinyDB, where, Query
from tinydb.middlewares import Middleware, CachingMiddleware
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.table import Document


def test_drop_tables(db: TinyDB):
    db.drop_tables()

    db.insert({})
    db.drop_tables()

    assert len(db) == 0


def test_all(db: TinyDB):
    db.drop_tables()

    for i in range(10):
        db.insert({})

    assert len(db.all()) == 10


def test_insert(db: TinyDB):
    db.drop_tables()
    db.insert({'int': 1, 'char': 'a'})

    assert db.count(where('int') == 1) == 1

    db.drop_tables()

    db.insert({'int': 1, 'char': 'a'})
    db.insert({'int': 1, 'char': 'b'})
    db.insert({'int': 1, 'char': 'c'})

    assert db.count(where('int') == 1) == 3
    assert db.count(where('char') == 'a') == 1


def test_insert_ids(db: TinyDB):
    db.drop_tables()
    assert db.insert({'int': 1, 'char': 'a'}) == 1
    assert db.insert({'int': 1, 'char': 'a'}) == 2


def test_insert_with_doc_id(db: TinyDB):
    db.drop_tables()
    assert db.insert({'int': 1, 'char': 'a'}) == 1
    assert db.insert(Document({'int': 1, 'char': 'a'}, 12)) == 12
    assert db.insert(Document({'int': 1, 'char': 'a'}, 77)) == 77
    assert db.insert({'int': 1, 'char': 'a'}) == 78


def test_insert_with_duplicate_doc_id(db: TinyDB):
    db.drop_tables()
    assert db.insert({'int': 1, 'char': 'a'}) == 1

    with pytest.raises(ValueError):
        db.insert(Document({'int': 1, 'char': 'a'}, 1))


def test_insert_multiple(db: TinyDB):
    db.drop_tables()
    assert not db.contains(where('int') == 1)

    # Insert multiple from list
    db.insert_multiple([{'int': 1, 'char': 'a'},
                        {'int': 1, 'char': 'b'},
                        {'int': 1, 'char': 'c'}])

    assert db.count(where('int') == 1) == 3
    assert db.count(where('char') == 'a') == 1

    # Insert multiple from generator function
    def generator():
        for j in range(10):
            yield {'int': j}

    db.drop_tables()

    db.insert_multiple(generator())

    for i in range(10):
        assert db.count(where('int') == i) == 1
    assert db.count(where('int').exists()) == 10

    # Insert multiple from inline generator
    db.drop_tables()

    db.insert_multiple({'int': i} for i in range(10))

    for i in range(10):
        assert db.count(where('int') == i) == 1


def test_insert_multiple_with_ids(db: TinyDB):
    db.drop_tables()

    # Insert multiple from list
    assert db.insert_multiple([{'int': 1, 'char': 'a'},
                               {'int': 1, 'char': 'b'},
                               {'int': 1, 'char': 'c'}]) == [1, 2, 3]


def test_insert_multiple_with_doc_ids(db: TinyDB):
    db.drop_tables()

    assert db.insert_multiple([
        Document({'int': 1, 'char': 'a'}, 12),
        Document({'int': 1, 'char': 'b'}, 77)
    ]) == [12, 77]
    assert db.get(doc_id=12) == {'int': 1, 'char': 'a'}
    assert db.get(doc_id=77) == {'int': 1, 'char': 'b'}

    with pytest.raises(ValueError):
        db.insert_multiple([Document({'int': 1, 'char': 'a'}, 12)])


def test_insert_multiple_mixed_document_and_dict(db: TinyDB):
    db.drop_tables()

    ids = db.insert_multiple([
        Document({'int': 1, 'char': 'explicit'}, 1),
        {'int': 2, 'char': 'auto'},
    ])
    assert ids == [1, 2]
    assert db.get(doc_id=1) == {'int': 1, 'char': 'explicit'}
    assert db.get(doc_id=2) == {'int': 2, 'char': 'auto'}


def test_insert_invalid_type_raises_error(db: TinyDB):
    with pytest.raises(ValueError, match='Document is not a Mapping'):
        # object() as an example of a non-mapping-type
        db.insert(object())  # type: ignore


def test_insert_valid_mapping_type(db: TinyDB):
    class CustomDocument(Mapping):
        def __init__(self, data):
            self.data = data

        def __getitem__(self, key):
            return self.data[key]

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

    db.drop_tables()
    db.insert(CustomDocument({'int': 1, 'char': 'a'}))
    assert db.count(where('int') == 1) == 1


def test_custom_mapping_type_with_json(tmpdir):
    class CustomDocument(Mapping):
        def __init__(self, data):
            self.data = data

        def __getitem__(self, key):
            return self.data[key]

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

    # Insert
    db = TinyDB(str(tmpdir.join('test.db')))
    db.drop_tables()
    db.insert(CustomDocument({'int': 1, 'char': 'a'}))
    assert db.count(where('int') == 1) == 1

    # Insert multiple
    db.insert_multiple([
        CustomDocument({'int': 2, 'char': 'a'}),
        CustomDocument({'int': 3, 'char': 'a'})
    ])
    assert db.count(where('int') == 1) == 1
    assert db.count(where('int') == 2) == 1
    assert db.count(where('int') == 3) == 1

    # Write back
    doc_id = db.get(where('int') == 3).doc_id
    db.update(CustomDocument({'int': 4, 'char': 'a'}), doc_ids=[doc_id])
    assert db.count(where('int') == 3) == 0
    assert db.count(where('int') == 4) == 1


def test_remove(db: TinyDB):
    db.remove(where('char') == 'b')

    assert len(db) == 2
    assert db.count(where('int') == 1) == 2


def test_remove_all_fails(db: TinyDB):
    with pytest.raises(RuntimeError):
        db.remove()


def test_remove_multiple(db: TinyDB):
    db.remove(where('int') == 1)

    assert len(db) == 0


def test_remove_ids(db: TinyDB):
    db.remove(doc_ids=[1, 2])

    assert len(db) == 1


def test_remove_returns_ids(db: TinyDB):
    assert db.remove(where('char') == 'b') == [2]


def test_remove_ids_missing(db: TinyDB):
    # Removing by a non-existent doc_id should not raise; the returned list
    # only contains IDs that were actually removed. This mirrors the silent
    # behaviour of ``get(doc_id=N)`` / ``get(doc_ids=[N])``.
    assert db.remove(doc_ids=[99]) == []
    assert len(db) == 3


def test_remove_ids_mixed(db: TinyDB):
    # When a mix of existing and missing IDs is passed, only the existing
    # documents should be removed and the missing IDs ignored. The removal
    # must be atomic - either every existing target is removed or none is
    # (no partial state on failure).
    assert sorted(db.remove(doc_ids=[1, 99])) == [1]
    assert len(db) == 2
    assert db.get(doc_id=1) is None
    assert db.get(doc_id=2) is not None


def test_update(db: TinyDB):
    assert len(db) == 3

    db.update({'int': 2}, where('char') == 'a')

    assert db.count(where('int') == 2) == 1
    assert db.count(where('int') == 1) == 2


def test_update_all(db: TinyDB):
    assert db.count(where('int') == 1) == 3

    db.update({'newField': True})

    assert db.count(where('newField') == True) == 3  # noqa


def test_update_returns_ids(db: TinyDB):
    db.drop_tables()
    assert db.insert({'int': 1, 'char': 'a'}) == 1
    assert db.insert({'int': 1, 'char': 'a'}) == 2

    assert db.update({'char': 'b'}, where('int') == 1) == [1, 2]


def test_update_transform(db: TinyDB):
    def increment(field):
        def transform(el):
            el[field] += 1

        return transform

    def delete(field):
        def transform(el):
            del el[field]

        return transform

    assert db.count(where('int') == 1) == 3

    db.update(increment('int'), where('char') == 'a')
    db.update(delete('char'), where('char') == 'a')

    assert db.count(where('int') == 2) == 1
    assert db.count(where('char') == 'a') == 0
    assert db.count(where('int') == 1) == 2


def test_update_custom_transform_callable(db: TinyDB):
    from collections.abc import MutableMapping

    from tinydb.operations import delete as delete_field

    doc_id = db.insert({'name': 'John', 'temp': True})

    def remove_temp(doc: MutableMapping) -> None:
        del doc['temp']

    db.update(remove_temp, where('name') == 'John')

    assert db.get(doc_id=doc_id) == {'name': 'John'}

    db.update({'temp': True}, where('name') == 'John')
    db.update(delete_field('temp'), where('name') == 'John')

    assert db.get(doc_id=doc_id) == {'name': 'John'}


def test_move_document_between_tables(db: TinyDB):
    source = db.table('source')
    target = db.table('target')

    doc_id = source.insert({'type': 'apple', 'count': 7})
    target.insert({'placeholder': True})
    document = source.get(doc_id=doc_id)
    assert document is not None

    with pytest.raises(ValueError, match='already exists'):
        target.insert(document)

    new_id = target.insert(dict(document))
    source.remove(doc_ids=[doc_id])

    assert source.all() == []
    assert target.get(doc_id=new_id) == {'type': 'apple', 'count': 7}
    assert new_id == 2


def test_update_ids(db: TinyDB):
    db.update({'int': 2}, doc_ids=[1, 2])

    assert db.count(where('int') == 2) == 2


def test_update_ids_missing(db: TinyDB):
    # Updating by a non-existent doc_id should not raise; the returned list
    # only contains IDs that were actually updated. This mirrors the silent
    # behaviour of ``get(doc_id=N)`` / ``get(doc_ids=[N])``.
    assert db.update({'int': 9}, doc_ids=[99]) == []
    assert db.count(where('int') == 9) == 0
    assert db.count(where('int') == 1) == 3


def test_update_ids_mixed(db: TinyDB):
    # When a mix of existing and missing IDs is passed, only the existing
    # documents should be updated and the missing IDs ignored. The update
    # must be atomic - either every existing target is updated or none is
    # (no partial state on failure).
    assert sorted(db.update({'int': 9}, doc_ids=[1, 99])) == [1]
    assert db.count(where('int') == 9) == 1
    assert db.count(where('int') == 1) == 2


def test_doc_id_missing_consistency(db: TinyDB):
    # ``get``, ``update`` and ``remove`` must all behave consistently when
    # given an ID that does not exist (see #591). None of them should raise.
    assert db.get(doc_id=99) is None
    assert db.get(doc_ids=[99]) == []
    assert db.update({'int': 9}, doc_ids=[99]) == []
    assert db.remove(doc_ids=[99]) == []


def test_update_multiple(db: TinyDB):
    assert len(db) == 3

    db.update_multiple([
        ({'int': 2}, where('char') == 'a'),
        ({'int': 4}, where('char') == 'b'),
    ])

    assert db.count(where('int') == 1) == 1
    assert db.count(where('int') == 2) == 1
    assert db.count(where('int') == 4) == 1


def test_update_multiple_operation(db: TinyDB):
    def increment(field):
        def transform(el):
            el[field] += 1

        return transform

    assert db.count(where('int') == 1) == 3

    db.update_multiple([
        (increment('int'), where('char') == 'a'),
        (increment('int'), where('char') == 'b')
    ])

    assert db.count(where('int') == 2) == 2


def test_upsert(db: TinyDB):
    assert len(db) == 3

    # Document existing
    db.upsert({'int': 5}, where('char') == 'a')
    assert db.count(where('int') == 5) == 1

    # Document missing
    assert db.upsert({'int': 9, 'char': 'x'}, where('char') == 'x') == [4]
    assert db.count(where('int') == 9) == 1


def test_upsert_by_id(db: TinyDB):
    assert len(db) == 3

    # Single document existing
    extant_doc = Document({'char': 'v'}, doc_id=1)
    assert db.upsert(extant_doc) == [1]
    doc = db.get(where('char') == 'v')
    assert isinstance(doc, Document)
    assert doc is not None
    assert doc.doc_id == 1
    assert len(db) == 3

    # Single document missing
    missing_doc = Document({'int': 5, 'char': 'w'}, doc_id=5)
    assert db.upsert(missing_doc) == [5]
    doc = db.get(where('char') == 'w')
    assert isinstance(doc, Document)
    assert doc is not None
    assert doc.doc_id == 5
    assert len(db) == 4

    # Missing doc_id and condition
    with pytest.raises(ValueError, match=r"(?=.*\bdoc_id\b)(?=.*\bquery\b)"):
        db.upsert({'no_Document': 'no_query'})

    # Make sure we didn't break anything
    assert db.insert({'check': '_next_id'}) == 6


def test_search(db: TinyDB):
    assert not db._query_cache
    assert len(db.search(where('int') == 1)) == 3

    assert len(db._query_cache) == 1
    assert len(db.search(where('int') == 1)) == 3  # Query result from cache


def test_search_path(db: TinyDB):
    assert not db._query_cache
    assert len(db.search(where('int').exists())) == 3
    assert len(db._query_cache) == 1

    assert len(db.search(where('asd').exists())) == 0
    assert len(db.search(where('int').exists())) == 3  # Query result from cache


def test_search_no_results_cache(db: TinyDB):
    assert len(db.search(where('missing').exists())) == 0
    assert len(db.search(where('missing').exists())) == 0


def test_get(db: TinyDB):
    item = db.get(where('char') == 'b')
    assert isinstance(item, Document)
    assert item is not None
    assert item['char'] == 'b'


def test_get_ids(db: TinyDB):
    el = db.all()[0]
    assert db.get(doc_id=el.doc_id) == el
    assert db.get(doc_id=float('NaN')) is None  # type: ignore


def test_get_multiple_ids(db: TinyDB):
    el = db.all()
    assert db.get(doc_ids=[x.doc_id for x in el]) == el


def test_get_invalid(db: TinyDB):
    with pytest.raises(RuntimeError):
        db.get()


def test_count(db: TinyDB):
    assert db.count(where('int') == 1) == 3
    assert db.count(where('char') == 'd') == 0


def test_contains(db: TinyDB):
    assert db.contains(where('int') == 1)
    assert not db.contains(where('int') == 0)


def test_contains_ids(db: TinyDB):
    assert db.contains(doc_id=1)
    assert db.contains(doc_id=2)
    assert not db.contains(doc_id=88)


def test_contains_invalid(db: TinyDB):
    with pytest.raises(RuntimeError):
        db.contains()


def test_get_idempotent(db: TinyDB):
    u = db.get(where('int') == 1)
    z = db.get(where('int') == 1)
    assert u == z


def test_multiple_dbs():
    """
    Regression test for issue #3
    """
    db1 = TinyDB(storage=MemoryStorage)
    db2 = TinyDB(storage=MemoryStorage)

    db1.insert({'int': 1, 'char': 'a'})
    db1.insert({'int': 1, 'char': 'b'})
    db1.insert({'int': 1, 'value': 5.0})

    db2.insert({'color': 'blue', 'animal': 'turtle'})

    assert len(db1) == 3
    assert len(db2) == 1


def test_storage_closed_once():
    class Storage:
        def __init__(self):
            self.closed = False

        def read(self):
            return {}

        def write(self, data):
            pass

        def close(self):
            assert not self.closed
            self.closed = True

    with TinyDB(storage=Storage) as db:
        db.close()

    del db
    # If db.close() is called during cleanup, the assertion will fail and throw
    # and exception


def test_unique_ids(tmpdir):
    """
    :type tmpdir: py._path.local.LocalPath
    """
    path = str(tmpdir.join('db.json'))

    # Verify ids are unique when reopening the DB and inserting
    with TinyDB(path) as _db:
        _db.insert({'x': 1})

    with TinyDB(path) as _db:
        _db.insert({'x': 1})

    with TinyDB(path) as _db:
        data = _db.all()

        assert data[0].doc_id != data[1].doc_id

    # Verify ids stay unique when inserting/removing
    with TinyDB(path) as _db:
        _db.drop_tables()
        _db.insert_multiple({'x': i} for i in range(5))
        _db.remove(where('x') == 2)

        assert len(_db) == 4

        ids = [e.doc_id for e in _db.all()]
        assert len(ids) == len(set(ids))


def test_lastid_after_open(tmpdir):
    """
    Regression test for issue #34

    :type tmpdir: py._path.local.LocalPath
    """

    NUM = 100
    path = str(tmpdir.join('db.json'))

    with TinyDB(path) as _db:
        _db.insert_multiple({'i': i} for i in range(NUM))

    with TinyDB(path) as _db:
        assert _db._get_next_id() - 1 == NUM


def test_doc_ids_json(tmpdir):
    """
    Regression test for issue #45
    """

    path = str(tmpdir.join('db.json'))

    with TinyDB(path) as _db:
        _db.drop_tables()
        assert _db.insert({'int': 1, 'char': 'a'}) == 1
        assert _db.insert({'int': 1, 'char': 'a'}) == 2

        _db.drop_tables()
        assert _db.insert_multiple([{'int': 1, 'char': 'a'},
                                    {'int': 1, 'char': 'b'},
                                    {'int': 1, 'char': 'c'}]) == [1, 2, 3]

        assert _db.contains(doc_id=1)
        assert _db.contains(doc_id=2)
        assert not _db.contains(doc_id=88)

        _db.update({'int': 2}, doc_ids=[1, 2])
        assert _db.count(where('int') == 2) == 2

        el = _db.all()[0]
        assert _db.get(doc_id=el.doc_id) == el
        assert _db.get(doc_id=float('NaN')) is None

        _db.remove(doc_ids=[1, 2])
        assert len(_db) == 1


def test_insert_string(tmpdir):
    path = str(tmpdir.join('db.json'))

    with TinyDB(path) as _db:
        data = [{'int': 1}, {'int': 2}]
        _db.insert_multiple(data)

        with pytest.raises(ValueError):
            _db.insert([1, 2, 3])  # Fails

        with pytest.raises(ValueError):
            _db.insert({'bark'})  # Fails

        assert data == _db.all()

        _db.insert({'int': 3})  # Does not fail


def test_insert_invalid_dict(tmpdir):
    path = str(tmpdir.join('db.json'))

    with TinyDB(path) as _db:
        data = [{'int': 1}, {'int': 2}]
        _db.insert_multiple(data)

        with pytest.raises(TypeError):
            _db.insert({'int': _db})  # Fails

        assert data == _db.all()

        _db.insert({'int': 3})  # Does not fail


def test_gc(tmpdir):
    # See https://github.com/msiemens/tinydb/issues/92
    path = str(tmpdir.join('db.json'))
    db = TinyDB(path)
    table = db.table('foo')
    table.insert({'something': 'else'})
    table.insert({'int': 13})
    assert len(table.search(where('int') == 13)) == 1
    assert table.all() == [{'something': 'else'}, {'int': 13}]
    db.close()


def test_drop_table():
    db = TinyDB(storage=MemoryStorage)
    default_table_name = db.table(db.default_table_name).name

    assert [] == list(db.tables())
    db.drop_table(default_table_name)

    db.insert({'a': 1})
    assert [default_table_name] == list(db.tables())

    db.drop_table(default_table_name)
    assert [] == list(db.tables())

    table_name = 'some-other-table'
    db = TinyDB(storage=MemoryStorage)
    db.table(table_name).insert({'a': 1})
    assert {table_name} == db.tables()

    db.drop_table(table_name)
    assert set() == db.tables()
    assert table_name not in db._tables

    db.drop_table('non-existent-table-name')
    assert set() == db.tables()


def test_empty_write(tmpdir):
    path = str(tmpdir.join('db.json'))

    class ReadOnlyMiddleware(Middleware):
        def write(self, data):
            raise AssertionError('No write for unchanged db')

    TinyDB(path).close()
    TinyDB(path, storage=ReadOnlyMiddleware(JSONStorage)).close()


def test_query_cache():
    db = TinyDB(storage=MemoryStorage)
    db.insert_multiple([
        {'name': 'foo', 'value': 42},
        {'name': 'bar', 'value': -1337}
    ])

    query = where('value') > 0

    results = db.search(query)
    assert len(results) == 1

    # Modify the db instance to not return any results when
    # bypassing the query cache
    db._tables[db.table(db.default_table_name).name]._read_table = lambda: {}

    # Make sure we got an independent copy of the result list
    results.extend([1])
    assert db.search(query) == [{'name': 'foo', 'value': 42}]


def test_query_cache_documents_are_shared_with_cache():
    """search() returns a fresh list each call, but its documents are the
    same objects the cache holds (see the docstring): the list itself can
    be mutated freely, the documents inside it cannot."""
    db = TinyDB(storage=MemoryStorage)
    db.insert({'name': 'Alice', 'tags': ['a', 'b']})

    query = where('name') == 'Alice'

    results1 = db.search(query)
    assert results1 == [{'name': 'Alice', 'tags': ['a', 'b']}]

    # Mutating the returned list itself doesn't touch the cache.
    results1.append({'name': 'fake'})
    results2 = db.search(query)
    assert results2 == [{'name': 'Alice', 'tags': ['a', 'b']}]

    # But a document inside it is the cached object, so mutating a
    # top-level key or a nested value both reach the cache.
    results2[0]['tags'].append('c')
    results3 = db.search(query)
    assert results3[0]['tags'] == ['a', 'b', 'c']


def test_tinydb_is_iterable(db: TinyDB):
    assert [r for r in db] == db.all()


def test_repr(tmpdir):
    path = str(tmpdir.join('db.json'))

    db = TinyDB(path)
    db.insert({'a': 1})

    assert re.match(
        r"<TinyDB "
        r"tables=\[u?\'_default\'\], "
        r"tables_count=1, "
        r"default_table_documents_count=1, "
        r"all_tables_documents_count=\[\'_default=1\'\]>",
        repr(db))


def test_delete(tmpdir):
    path = str(tmpdir.join('db.json'))

    db = TinyDB(path, ensure_ascii=False)
    q = Query()
    db.insert({'network': {'id': '114', 'name': 'ok', 'rpc': 'dac',
                           'ticker': 'mkay'}})
    assert db.search(q.network.id == '114') == [
        {'network': {'id': '114', 'name': 'ok', 'rpc': 'dac',
                     'ticker': 'mkay'}}
    ]
    db.remove(q.network.id == '114')
    assert db.search(q.network.id == '114') == []


def test_insert_multiple_with_single_dict(db: TinyDB):
    with pytest.raises(ValueError):
        d = {'first': 'John', 'last': 'smith'}
        db.insert_multiple(d)  # type: ignore
        db.close()


def test_access_storage():
    assert isinstance(TinyDB(storage=MemoryStorage).storage,
                      MemoryStorage)
    assert isinstance(TinyDB(storage=CachingMiddleware(MemoryStorage)).storage,
                      CachingMiddleware)


def test_empty_db_len():
    db = TinyDB(storage=MemoryStorage)
    assert len(db) == 0


def test_insert_on_existing_db(tmpdir):
    path = str(tmpdir.join('db.json'))

    db = TinyDB(path, ensure_ascii=False)
    db.insert({'foo': 'bar'})

    assert len(db) == 1

    db.close()

    db = TinyDB(path, ensure_ascii=False)
    db.insert({'foo': 'bar'})
    db.insert({'foo': 'bar'})

    assert len(db) == 3


def test_storage_access():
    db = TinyDB(storage=MemoryStorage)

    assert isinstance(db.storage, MemoryStorage)


def test_lambda_query():
    db = TinyDB(storage=MemoryStorage)
    db.insert({'foo': 'bar'})

    query = lambda doc: doc.get('foo') == 'bar'
    query.is_cacheable = lambda: False
    assert db.search(query) == [{'foo': 'bar'}]
    assert not db._query_cache
'''

_BASE_TEST_FILES['test_tables.py'] = r'''import re

import pytest

from tinydb import where


def test_next_id(db):
    db.truncate()

    assert db._get_next_id() == 1
    assert db._get_next_id() == 2
    assert db._get_next_id() == 3


def test_tables_list(db):
    db.table('table1').insert({'a': 1})
    db.table('table2').insert({'a': 1})

    assert db.tables() == {'_default', 'table1', 'table2'}


def test_one_table(db):
    table1 = db.table('table1')

    table1.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    assert table1.get(where('int') == 1)['char'] == 'a'
    assert table1.get(where('char') == 'b')['char'] == 'b'


def test_multiple_tables(db):
    table1 = db.table('table1')
    table2 = db.table('table2')
    table3 = db.table('table3')

    table1.insert({'int': 1, 'char': 'a'})
    table2.insert({'int': 1, 'char': 'b'})
    table3.insert({'int': 1, 'char': 'c'})

    assert table1.count(where('char') == 'a') == 1
    assert table2.count(where('char') == 'b') == 1
    assert table3.count(where('char') == 'c') == 1

    db.drop_tables()

    assert len(table1) == 0
    assert len(table2) == 0
    assert len(table3) == 0


def test_caching(db):
    table1 = db.table('table1')
    table2 = db.table('table1')

    assert table1 is table2


def test_query_cache(db):
    query1 = where('int') == 1

    assert db.count(query1) == 3
    assert query1 in db._query_cache

    assert db.count(query1) == 3
    assert query1 in db._query_cache

    query2 = where('int') == 0

    assert db.count(query2) == 0
    assert query2 in db._query_cache

    assert db.count(query2) == 0
    assert query2 in db._query_cache


def test_query_cache_with_mutable_callable(db):
    table = db.table('table')
    table.insert({'val': 5})

    mutable = 5
    increase = lambda x: x + mutable

    assert where('val').is_cacheable()
    assert not where('val').map(increase).is_cacheable()
    assert not (where('val').map(increase) == 10).is_cacheable()

    search = where('val').map(increase) == 10
    assert table.count(search) == 1

    # now `increase` would yield 15, not 10
    mutable = 10

    assert table.count(search) == 0
    assert len(table._query_cache) == 0


def test_zero_cache_size(db):
    table = db.table('table3', cache_size=0)
    query = where('int') == 1

    table.insert({'int': 1})
    table.insert({'int': 1})

    assert table.count(query) == 2
    assert table.count(where('int') == 2) == 0
    assert len(table._query_cache) == 0


def test_query_cache_size(db):
    table = db.table('table3', cache_size=1)
    query = where('int') == 1

    table.insert({'int': 1})
    table.insert({'int': 1})

    assert table.count(query) == 2
    assert table.count(where('int') == 2) == 0
    assert len(table._query_cache) == 1


def test_lru_cache(db):
    # Test integration into TinyDB
    table = db.table('table3', cache_size=2)
    query = where('int') == 1

    table.search(query)
    table.search(where('int') == 2)
    table.search(where('int') == 3)
    assert query not in table._query_cache

    table.remove(where('int') == 1)
    assert not table._query_cache.lru

    table.search(query)

    assert len(table._query_cache) == 1
    table.clear_cache()
    assert len(table._query_cache) == 0


def test_table_is_iterable(db):
    table = db.table('table1')

    table.insert_multiple({'int': i} for i in range(3))

    assert [r for r in table] == table.all()


def test_table_name(db):
    name = 'table3'
    table = db.table(name)
    assert name == table.name

    with pytest.raises(AttributeError):
        table.name = 'foo'


def test_table_repr(db):
    name = 'table4'
    table = db.table(name)

    assert re.match(
        r"<Table name=\'table4\', total=0, "
        r"storage=<tinydb\.storages\.(MemoryStorage|JSONStorage) object at [a-zA-Z0-9]+>>",
        repr(table))


def test_truncate_table(db):
    db.truncate()
    assert db._get_next_id() == 1


def test_persist_table(db):
    db.table("persisted", persist_empty=True)
    assert "persisted" in db.tables()

    db.table("nonpersisted", persist_empty=False)
    assert "nonpersisted" not in db.tables()


def test_persist_empty_does_not_wipe_existing_data(tmpdir):
    """persist_empty must not clear documents already stored for the table.

    See https://github.com/msiemens/tinydb/issues/636
    """
    from tinydb import TinyDB

    path = str(tmpdir.join('db.json'))
    db = TinyDB(path)
    db.table('t').insert({'a': 1})
    db.close()

    db = TinyDB(path)
    assert 't' not in db._tables
    table = db.table('t', persist_empty=True)
    assert len(table) == 1
    assert table.all() == [{'a': 1}]
    db.close()
'''

_BASE_TEST_FILES['test_operations.py'] = r'''from tinydb import where
from tinydb.operations import delete, increment, decrement, add, subtract, set


def test_delete(db):
    db.update(delete('int'), where('char') == 'a')
    assert 'int' not in db.get(where('char') == 'a')


def test_add_int(db):
    db.update(add('int', 5), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 6


def test_add_str(db):
    db.update(add('char', 'xyz'), where('char') == 'a')
    assert db.get(where('char') == 'axyz')['int'] == 1


def test_subtract(db):
    db.update(subtract('int', 5), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == -4


def test_set(db):
    db.update(set('char', 'xyz'), where('char') == 'a')
    assert db.get(where('char') == 'xyz')['int'] == 1


def test_increment(db):
    db.update(increment('int'), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 2


def test_decrement(db):
    db.update(decrement('int'), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 0
'''

_EXISTING_SUITE = _program(r'''
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

files = @FILES@
root = tempfile.mkdtemp()
tests_dir = os.path.join(root, 'tinydb_base_tests')
os.mkdir(tests_dir)
for name, content in files.items():
    with open(os.path.join(tests_dir, name), 'w', encoding='utf-8') as fh:
        fh.write(content)
# Pins pytest's rootdir/config to the temporary directory (the candidate's
# pytest.ini adds coverage options that need pytest-cov).
with open(os.path.join(root, 'pytest.ini'), 'w', encoding='utf-8') as fh:
    fh.write('[pytest]\n')
env = dict(os.environ)
env['PYTHONPATH'] = os.pathsep.join(
    [os.getcwd()] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
env['PYTHONDONTWRITEBYTECODE'] = '1'
junit = os.path.join(root, 'junit.xml')
proc = subprocess.run(
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
     '--junitxml=' + junit, tests_dir],
    cwd=root, env=env, capture_output=True, text=True, timeout=600)
cases = {}
if os.path.exists(junit):
    for case in ET.parse(junit).getroot().iter('testcase'):
        status = 'passed'
        for child in case:
            if child.tag in ('failure', 'error'):
                status = child.tag
                break
            if child.tag == 'skipped':
                status = 'skipped'
        cases[case.get('classname', '') + '::' + case.get('name', '')] = status
return {'returncode': proc.returncode, 'cases': cases,
        'output': proc.stdout[-4000:], 'stderr': proc.stderr[-2000:]}
''', FILES=_BASE_TEST_FILES)


def test_existing_test_suite_still_passes():
    v = _value(run_python(_EXISTING_SUITE, timeout=600.0))
    failed = sorted(name for name, status in v["cases"].items()
                    if status in ("failure", "error"))
    assert failed == [], "existing tests fail: %r\n%s" % (
        failed[:20], v["output"])
    passed = [name for name, status in v["cases"].items()
              if status == "passed"]
    assert len(passed) == _BASE_PASSED, (
        "expected %d passing existing tests, got %d\n%s\n%s"
        % (_BASE_PASSED, len(passed), v["output"], v["stderr"]))
    assert v["returncode"] == 0, v["output"]
