"""Probe (decision log D36): startup hooks written at runtime never run in later sandbox calls.

Copied into a fixture task's hidden tests by tests/test_sandbox_isolation.py.
"""
from tc_sandbox import run_python

PLANT = (
    "import os, site\n"
    "hook = \"import pathlib; pathlib.Path('/tmp/hook_ran').write_text(__file__)\\n\"\n"
    "user_site = site.getusersitepackages()\n"
    "os.makedirs(user_site, exist_ok=True)\n"
    "for p in ['/work/sitecustomize.py', '/work/usercustomize.py', '/tmp/json.py', user_site + '/usercustomize.py']:\n"
    "    open(p, 'w').write(hook)\n"
    "result = True"
)
CHECK = (
    "import os, sys, json\n"
    "sc = sys.modules.get('sitecustomize')\n"
    "result = [os.path.exists('/tmp/hook_ran'), json.__file__.startswith(('/work', '/tmp')),\n"
    "          bool(sc) and getattr(sc, '__file__', '').startswith(('/work', '/tmp'))]"
)


def test_runtime_startup_hooks_are_never_loaded():
    r1 = run_python(PLANT, timeout=10)
    assert r1.ok, r1
    r2 = run_python(CHECK, timeout=10)
    assert r2.ok and r2.value == [False, False, False], r2
