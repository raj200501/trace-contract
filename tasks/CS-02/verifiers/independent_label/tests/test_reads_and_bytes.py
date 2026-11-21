"""Checks for reads after writes and for the bytes written, compared with the base (CS-02).

Candidate code runs only through tc_sandbox.run_python.
"""

import base64
import json

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_read_after_write_same_instance": ["R-read-after-write"],
    "test_read_after_write_storage_object": ["R-read-after-write"],
    "test_new_instance_sees_writes": ["R-read-after-write"],
    "test_bytes_default_kwargs_utf8": ["R-bytes-unchanged"],
    "test_bytes_indent_sort_keys_utf8": ["R-bytes-unchanged"],
    "test_bytes_ensure_ascii_false_utf8": ["R-bytes-unchanged"],
    "test_bytes_latin1_and_utf16": ["R-bytes-unchanged"],
    "test_bytes_overwrite_shorter": ["R-bytes-unchanged"],
}


def base_write_bytes(data, encoding, kwargs):
    # Oracle copied from the base commit (snapshots/CS-02/tinydb/storages.py, JSONStorage.write):
    #     serialized = json.dumps(data, **self.kwargs)
    #     self._handle.write(serialized)    # text handle opened with the given encoding
    serialized = json.dumps(data, **kwargs)
    return serialized.encode(encoding)


def storage_snippet(writes, encoding, kwargs):
    lines = [
        "import base64, os, tempfile",
        "from tinydb import JSONStorage",
        "d = tempfile.mkdtemp()",
        "p = os.path.join(d, 'db.json')",
        "s = JSONStorage(p, encoding=%r, **%r)" % (encoding, kwargs),
    ]
    for data in writes:
        lines.append("s.write(%r)" % (data,))
    lines += [
        "s.close()",
        "with open(p, 'rb') as fh:",
        "    raw = fh.read()",
        "result = base64.b64encode(raw).decode('ascii')",
    ]
    return "\n".join(lines) + "\n"


def test_read_after_write_same_instance():
    snippet = """
import os, tempfile
from tinydb import TinyDB, Query
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
seen = []
for i in range(4):
    db.insert({"n": i})
    seen.append(sorted(doc["n"] for doc in db.all()))
db.update({"n": 100}, Query().n == 0)
seen.append(sorted(doc["n"] for doc in db.all()))
db.remove(Query().n == 1)
seen.append(sorted(doc["n"] for doc in db.all()))
found = [doc["n"] for doc in db.search(Query().n == 100)]
result = {"seen": seen, "found": found}
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == {
        "seen": [[0], [0, 1], [0, 1, 2], [0, 1, 2, 3], [1, 2, 3, 100], [2, 3, 100]],
        "found": [100],
    }


def test_read_after_write_storage_object():
    snippet = """
import os, tempfile
from tinydb import JSONStorage
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
s = JSONStorage(p, encoding="utf-8")
d1 = {"_default": {"1": {"a": 1}}}
d2 = {"_default": {"1": {"a": 2, "b": "x" * 300}}, "t": {"2": {"z": []}}}
d3 = {"_default": {"1": {"a": 3}}}
s.write(d1)
r1 = s.read()
s.write(d2)
r2 = s.read()
s.write(d3)
r3 = s.read()
s.close()
result = {"r1": r1 == d1, "r2": r2 == d2, "r3": r3 == d3}
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == {"r1": True, "r2": True, "r3": True}


def test_new_instance_sees_writes():
    snippet = """
import os, tempfile
from tinydb import TinyDB
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
db.insert({"a": 1})
db.insert({"a": 2})
other = TinyDB(p)
before = sorted(dict(x)["a"] for x in other.all())
db.insert({"a": 3})
after = sorted(dict(x)["a"] for x in TinyDB(p).all())
result = {"before": before, "after": after}
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == {"before": [1, 2], "after": [1, 2, 3]}


def test_bytes_default_kwargs_utf8():
    data = {"_default": {"1": {"name": "Ann", "n": 1.5, "tags": ["a", None, True]}}}
    r = run_python(storage_snippet([data], "utf-8", {}))
    assert r.ok, r
    assert base64.b64decode(r.value) == base_write_bytes(data, "utf-8", {})


def test_bytes_indent_sort_keys_utf8():
    data = {"b": 1, "a": {"d": 2, "c": [1, 2]}, "_default": {"2": {"z": "y", "m": 0.25}}}
    kwargs = {"indent": 4, "sort_keys": True}
    r = run_python(storage_snippet([data], "utf-8", kwargs))
    assert r.ok, r
    assert base64.b64decode(r.value) == base_write_bytes(data, "utf-8", kwargs)


def test_bytes_ensure_ascii_false_utf8():
    data = {"_default": {"1": {"city": "Zoë", "word": "日本", "n": 3}}}
    kwargs = {"ensure_ascii": False, "indent": 4, "sort_keys": True}
    r = run_python(storage_snippet([data], "utf-8", kwargs))
    assert r.ok, r
    assert base64.b64decode(r.value) == base_write_bytes(data, "utf-8", kwargs)


def test_bytes_latin1_and_utf16():
    data = {"_default": {"1": {"name": "Zoë", "n": 2}}}
    r1 = run_python(storage_snippet([data], "latin-1", {"ensure_ascii": False}))
    assert r1.ok, r1
    assert base64.b64decode(r1.value) == base_write_bytes(data, "latin-1", {"ensure_ascii": False})
    r2 = run_python(storage_snippet([data], "utf-16", {"sort_keys": True}))
    assert r2.ok, r2
    assert base64.b64decode(r2.value) == base_write_bytes(data, "utf-16", {"sort_keys": True})


def test_bytes_overwrite_shorter():
    long_data = {"_default": {"1": {"a": "x" * 300}}}
    short = {"_default": {"1": {"a": "s"}}}
    kwargs = {"sort_keys": True}
    r = run_python(storage_snippet([long_data, short], "utf-8", kwargs))
    assert r.ok, r
    assert base64.b64decode(r.value) == base_write_bytes(short, "utf-8", kwargs)
