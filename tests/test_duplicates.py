"""Same-code duplicate detection (decision log D40): comments and docstrings are ignored."""

from __future__ import annotations

from tracecontract.duplicates import canonical, code_signatures
from tracecontract.patches import diff_dirs
from tracecontract.schemas import Candidate, CandidateOrigin, Split, sha256_text

BASE = 'def f(x):\n    """Return x."""\n    return x\n'


def _cand(tmp_path, name, src):
    new = tmp_path / ("new_" + name)
    new.mkdir()
    (new / "m.py").write_text(src)
    patch = diff_dirs(tmp_path / "base", new)
    return Candidate(candidate_id=name, task_id="t", origin=CandidateOrigin.constructed_near_miss, split=Split.eval,
                     patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture")


def test_canonical_ignores_comments_and_docstrings():
    a = canonical("m.py", b'def f(x):\n    """One."""\n    return x + 1  # c\n')
    b = canonical("m.py", b"def f(x):\n    '''Two, longer.'''\n    return x + 1\n")
    c = canonical("m.py", b"def f(x):\n    return x + 2\n")
    assert a == b != c
    assert canonical("README.md", b"x") == "x" and canonical("m.py", None) is None


def test_code_signatures_match_only_for_same_code(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "m.py").write_text(BASE)
    doc_only = _cand(tmp_path, "a", 'def f(x):\n    """Return x plus one."""\n    return x + 1\n')
    same_code = _cand(tmp_path, "b", 'def f(x):\n    """Return x + 1 (other words)."""\n    # comment\n    return x + 1\n')
    other = _cand(tmp_path, "c", 'def f(x):\n    """Return x plus one."""\n    return x - 1\n')
    sig = code_signatures(tmp_path / "base", [doc_only, same_code, other])
    assert sig["a"] == sig["b"] != sig["c"]
