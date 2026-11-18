
from tc_sandbox import run_python
CHECK_REQUIREMENTS = {"test_add": ["R1"], "test_negative": ["R1"]}
def test_add():
    r = run_python("from calc import add\nresult = add(2, 3)")
    assert r.ok, r
    assert r.value == 5
def test_negative():
    r = run_python("from calc import add\nresult = add(-2, 1)")
    assert r.ok, r
    assert r.value == -1
