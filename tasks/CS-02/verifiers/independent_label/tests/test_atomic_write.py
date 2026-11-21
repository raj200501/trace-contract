"""Checks for failed and successful writes of the database file (CS-02).

Candidate code runs only through tc_sandbox.run_python.
"""

import json

from tc_sandbox import run_python

CHECK_REQUIREMENTS = {
    "test_failed_insert_keeps_bytes_identical": ["R-original-intact", "R-atomic"],
    "test_failed_insert_file_parses_to_old_data": ["R-atomic"],
    "test_failed_update_keeps_old_bytes": ["R-original-intact"],
    "test_no_temp_files_after_failed_insert": ["R-no-temp-files"],
    "test_no_temp_files_after_successful_writes": ["R-no-temp-files"],
    "test_successful_insert_file_holds_exact_data": ["R-new-content"],
    "test_successful_shorter_write_file_holds_exact_data": ["R-new-content"],
}

OLD_DATA = {
    "_default": {
        "1": {"k": 0, "text": "old-0"},
        "2": {"k": 1, "text": "old-1"},
        "3": {"k": 2, "text": "old-2"},
    }
}

# Builds a database with three documents, then lowers the file-size limit so that
# the next write of a large document fails partway (RLIMIT_FSIZE, EFBIG).
_SETUP = """
import json, os, resource, tempfile
from tinydb import TinyDB, Query
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
for i in range(3):
    db.insert({"k": i, "text": "old-%d" % i})
db.close()
with open(p, "rb") as fh:
    before = fh.read()
db = TinyDB(p)
limit = os.path.getsize(p) + 2048
resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
"""

_FAILED_INSERT = """
try:
    db.insert({"k": 99, "text": "x" * 100000})
except Exception:
    pass
with open(p, "rb") as fh:
    after = fh.read()
"""

_FAILED_UPDATE = """
try:
    db.update({"text": "x" * 100000}, Query().k == 1)
except Exception:
    pass
with open(p, "rb") as fh:
    after = fh.read()
"""


def test_failed_insert_keeps_bytes_identical():
    r = run_python(_SETUP + _FAILED_INSERT + "\nresult = after == before\n")
    assert r.ok, r
    assert r.value is True


def test_failed_insert_file_parses_to_old_data():
    r = run_python(_SETUP + _FAILED_INSERT + "\nresult = json.loads(after)\n")
    assert r.ok, r
    assert r.value == OLD_DATA


def test_failed_update_keeps_old_bytes():
    r = run_python(_SETUP + _FAILED_UPDATE + "\nresult = after == before\n")
    assert r.ok, r
    assert r.value is True


def test_no_temp_files_after_failed_insert():
    r = run_python(_SETUP + _FAILED_INSERT + "\nresult = sorted(os.listdir(d))\n")
    assert r.ok, r
    assert r.value == ["db.json"]


def test_no_temp_files_after_successful_writes():
    snippet = """
import os, tempfile
from tinydb import TinyDB, Query
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
db.insert({"k": 0, "text": "a"})
db.insert({"k": 1, "text": "b"})
db.update({"text": "c"}, Query().k == 0)
db.remove(Query().k == 1)
result = sorted(os.listdir(d))
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == ["db.json"]


def test_successful_insert_file_holds_exact_data():
    snippet = """
import json, os, tempfile
from tinydb import TinyDB
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
db.insert({"name": "ann", "n": 1})
with open(p, "r", encoding="utf-8") as fh:
    result = json.load(fh)
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == {"_default": {"1": {"name": "ann", "n": 1}}}


def test_successful_shorter_write_file_holds_exact_data():
    snippet = """
import json, os, tempfile
from tinydb import TinyDB, Query
d = tempfile.mkdtemp()
p = os.path.join(d, "db.json")
db = TinyDB(p)
db.insert({"v": "x" * 500})
db.update({"v": "s"}, Query().v == "x" * 500)
with open(p, "r", encoding="utf-8") as fh:
    result = json.load(fh)
"""
    r = run_python(snippet)
    assert r.ok, r
    assert r.value == {"_default": {"1": {"v": "s"}}}
