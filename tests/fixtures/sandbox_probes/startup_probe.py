"""Probe (decision log D36, D40): startup hooks and packages written at runtime never load in later sandbox calls.

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
    "os.makedirs('/work/encodings', exist_ok=True)\n"
    "open('/work/encodings/__init__.py', 'w').write(ENC)\n"
    "result = True"
)
# A runtime-written encodings package that marks sys when it loads, then hands over to
# the real package (D40). Under harness 0.3.1 it loaded at the start of every later call.
ENC = (
    "import sys\n"
    "sys._tc_planted_encodings = __file__\n"
    "_here = __file__.rsplit('/', 2)[0]\n"
    "del sys.modules['encodings']\n"
    "_saved = sys.path[:]\n"
    "sys.path[:] = [p for p in sys.path if p != _here]\n"
    "import encodings as _real\n"
    "sys.path[:] = _saved\n"
    "sys.modules['encodings'] = _real\n"
)
PLANT = "ENC = " + repr(ENC) + "\n" + PLANT
CHECK = (
    "import os, sys, json\n"
    "sc = sys.modules.get('sitecustomize')\n"
    "result = [os.path.exists('/tmp/hook_ran'), json.__file__.startswith(('/work', '/tmp')),\n"
    "          bool(sc) and getattr(sc, '__file__', '').startswith(('/work', '/tmp')),\n"
    "          hasattr(sys, '_tc_planted_encodings')]"
)


def test_runtime_startup_hooks_are_never_loaded():
    r1 = run_python(PLANT, timeout=10)
    assert r1.ok, r1
    r2 = run_python(CHECK, timeout=10)
    assert r2.ok and r2.value == [False, False, False, False], r2
