"""Candidate patches that ship a module named like a standard-library module the grader relies on.

The trusted wrapper that runs inside a candidate's sandboxed process imports and uses
modules such as ``json``, ``hmac``, ``traceback`` and ``ast`` while it formats, serialises
and signs a call's result. A candidate module of the same name that loads instead of the
standard one can forge that result: ``json.py`` (decision log D36), an ``encodings``
package read while the interpreter starts (D40), and ``ast.py`` while an exception is
formatted (D44). The harness keeps candidate directories off the import path at those
points, and probes cover each known path. This check is a guard on top, for the
pre-flight before a final run: a candidate whose patch adds or modifies a top-level module
or package with one of these names is rejected before it is graded.

"Top level" means directly in an import root of the candidate's code: the working tree
itself (the working directory of every sandboxed call) and every entry of the task's
``candidate_pythonpath`` inside it (for example ``src``). A module file counts with any
importable suffix (``json.py``, ``json.pyc``, ``json.cpython-312-x86_64-linux-gnu.so``),
and a package counts by any file inside its directory (``json/__init__.py``, or
``encodings/utf_8.py`` in a namespace package). A module deeper in a package
(``src/humanize/json.py`` is ``humanize.json``) does not shadow the standard library and
is not rejected.
"""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from .patches import split_sections

GUARDED_MODULES = ("ast", "unicodedata", "linecache", "tokenize", "traceback", "encodings", "json", "hmac", "hashlib",
                   "os", "sys")
_MODULE_SUFFIXES = ("py", "pyc", "pyo", "pyw", "so", "pyd")  # the last dot-separated part of an importable file name


def import_roots(candidate_pythonpath: str, workdir: str = "/work") -> list[str]:
    """Import roots of the candidate's code, relative to its working tree (``""`` is the tree itself).

    Relative entries of ``candidate_pythonpath`` are resolved against ``workdir``, as the harness does;
    entries outside the working tree are not the candidate's and are left out.
    """
    roots = [""]
    for entry in filter(None, candidate_pythonpath.split(":")):
        p = PurePosixPath(posixpath.normpath(posixpath.join(workdir, entry)))
        if p != PurePosixPath(workdir) and p.is_relative_to(workdir):
            rel = p.relative_to(workdir).as_posix()
            if rel not in roots:
                roots.append(rel)
    return roots


def top_level_module(path: str, root: str) -> str | None:
    """The top-level module or package that ``path`` (relative to the working tree) belongs to under ``root``."""
    parts = PurePosixPath(path).parts
    if root:
        n = len(PurePosixPath(root).parts)
        if parts[:n] != PurePosixPath(root).parts:
            return None
        parts = parts[n:]
    if len(parts) > 1:
        return parts[0]  # a file inside a package directory (regular or namespace)
    if len(parts) == 1 and "." in parts[0]:
        name, ext = parts[0].split(".", 1)
        if ext.rsplit(".", 1)[-1] in _MODULE_SUFFIXES:
            return name
    return None


def shadowing_files(patch: str, candidate_pythonpath: str = "/work", names: tuple[str, ...] = GUARDED_MODULES,
                    workdir: str = "/work") -> list[tuple[str, str]]:
    """``(path, module)`` for each file the patch adds or modifies that is a guarded top-level module or package.

    A renamed file counts under its new name; a deleted file does not count. Every section of the
    patch is checked, including those the patch policy would remove before grading.
    """
    roots = import_roots(candidate_pythonpath, workdir)
    out: list[tuple[str, str]] = []
    for sec in split_sections(patch or ""):
        if sec.new_path is None:
            continue
        for root in roots:
            mod = top_level_module(sec.new_path, root)
            if mod in names:
                out.append((sec.new_path, mod))
                break
    return out
