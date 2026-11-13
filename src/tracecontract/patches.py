"""Candidate patch handling: parsing, path policy, filtering, and application.

Candidates are unified diffs against the base snapshot. Before any candidate is
graded, the trusted host process:

1. parses every file section of the diff;
2. rejects unsafe paths (absolute paths, ``..`` components, ``.git/``, NUL bytes),
   symlink or gitlink modes, and binary patches;
3. removes sections that touch protected paths (by default: test files and test
   configuration), recording what was removed - SWE-bench-style graders do the same
   so that a candidate cannot rewrite the tests that grade it;
4. applies the remaining sections to a fresh copy of the base snapshot with
   ``git apply`` (no ``.git`` history is present in the snapshot).
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DEFAULT_PROTECTED = (
    "tests/*", "test/*", "testing/*", "*/tests/*", "*/test/*", "test_*.py", "*/test_*.py", "*_test.py",
    "conftest.py", "*/conftest.py", "pytest.ini", "tox.ini", "noxfile.py", "setup.cfg",
    "sitecustomize.py", "*/sitecustomize.py", "usercustomize.py", "*.pth",
)

_DIFF_GIT = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass
class FileSection:
    old_path: str | None
    new_path: str | None
    text: str
    is_binary: bool = False
    new_mode: str | None = None

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""


@dataclass
class PatchReport:
    accepted_paths: list[str] = field(default_factory=list)
    removed_protected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _strip_prefix(p: str) -> str | None:
    p = p.strip()
    if p == "/dev/null":
        return None
    if "\t" in p:
        p = p.split("\t", 1)[0]
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p


def split_sections(patch: str) -> list[FileSection]:
    """Split a unified diff (git or plain) into per-file sections."""
    lines = patch.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if ln.startswith("diff --git ")]
    if not starts:
        # Plain unified diff: sections start at '--- ' lines followed by '+++ '.
        starts = [i for i, ln in enumerate(lines) if ln.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ ")]
    sections = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        chunk = lines[s:e]
        old = new = None
        mode = None
        binary = False
        m = _DIFF_GIT.match(chunk[0].rstrip("\n"))
        if m:
            old, new = m.group(1), m.group(2)
        for ln in chunk:
            if ln.startswith("--- "):
                old = _strip_prefix(ln[4:])
            elif ln.startswith("+++ "):
                new = _strip_prefix(ln[4:])
            elif ln.startswith(("new file mode ", "new mode ")):
                mode = ln.split()[-1]
            elif ln.startswith("deleted file mode "):
                new = None
            elif ln.startswith(("GIT binary patch", "Binary files ")):
                binary = True
            elif ln.startswith("@@"):
                break
        sections.append(FileSection(old, new, "".join(chunk), binary, mode))
    return sections


def unsafe_path_reason(p: str) -> str | None:
    if not p:
        return "empty path"
    if "\x00" in p:
        return "NUL byte in path"
    pp = PurePosixPath(p)
    if pp.is_absolute() or p.startswith("~"):
        return "absolute path"
    if any(part == ".." for part in pp.parts):
        return "parent-directory component"
    if pp.parts and pp.parts[0] == ".git" or "/.git/" in f"/{p}":
        return "path inside .git"
    return None


def is_protected(p: str, protected: tuple[str, ...]) -> bool:
    name = PurePosixPath(p).name
    return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(name, pat) for pat in protected)


def filter_patch(patch: str, protected: tuple[str, ...] = DEFAULT_PROTECTED) -> tuple[str, PatchReport]:
    """Return (approved_patch, report). Unsafe sections make the report not ok."""
    rep = PatchReport()
    keep = []
    for sec in split_sections(patch):
        for p in {sec.old_path, sec.new_path} - {None}:
            why = unsafe_path_reason(p)  # type: ignore[arg-type]
            if why:
                rep.errors.append(f"{p}: {why}")
        if sec.is_binary:
            rep.errors.append(f"{sec.path}: binary patches are not accepted")
        if sec.new_mode in ("120000", "160000"):
            rep.errors.append(f"{sec.path}: symlink/gitlink modes are not accepted")
        if is_protected(sec.path, protected) or (sec.old_path and is_protected(sec.old_path, protected)):
            rep.removed_protected.append(sec.path)
            continue
        rep.accepted_paths.append(sec.path)
        keep.append(sec.text)
    if patch.strip() and not split_sections(patch):
        rep.errors.append("patch has no recognisable file sections")
    approved = "".join(keep)
    if approved and not approved.endswith("\n"):
        approved += "\n"
    return approved, rep


def apply_patch(base_dir: Path, patch: str, dest: Path | None = None) -> tuple[Path, str]:
    """Copy ``base_dir`` and apply ``patch`` with ``git apply``. Returns (dir, log)."""
    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix="tc_ws_"))
        shutil.rmtree(dest)
    shutil.copytree(base_dir, dest, symlinks=True)
    if not patch.strip():
        return dest, "empty patch (no-op)"
    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8") as fh:
        fh.write(patch)
        pfile = fh.name
    cmd = ["git", "apply", "--whitespace=nowarn", "--verbose", pfile]
    proc = subprocess.run(cmd, cwd=dest, capture_output=True, text=True)
    Path(pfile).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise PatchApplyError(proc.stderr.strip() or proc.stdout.strip())
    # Defence in depth: no symlinks may point outside the workspace.
    for p in dest.rglob("*"):
        if p.is_symlink():
            target = (p.parent / p.readlink()).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise PatchApplyError(f"symlink escapes workspace: {p.relative_to(dest)}")
    return dest, (proc.stdout + proc.stderr).strip()


class PatchApplyError(RuntimeError):
    pass


def diff_dirs(base: Path, new: Path, *, exclude: tuple[str, ...] = (".git",)) -> str:
    """Unified diff (``a/`` ``b/`` paths) turning tree ``base`` into tree ``new``.

    Computed in a throwaway git repository so that paths are clean and relative,
    renames are not inferred, and binary changes are marked as such.
    """
    def _copy(src: Path, dst: Path) -> None:
        for item in src.iterdir():
            if item.name in exclude:
                continue
            t = dst / item.name
            if item.is_dir() and not item.is_symlink():
                shutil.copytree(item, t, symlinks=True, ignore=shutil.ignore_patterns(*exclude))
            else:
                shutil.copy2(item, t, follow_symlinks=False)

    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "HOME": "/tmp", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    with tempfile.TemporaryDirectory(prefix="tc_diff_") as tmp:
        repo = Path(tmp) / "r"
        repo.mkdir()
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, env=env, capture_output=True, text=True, check=True)  # noqa: E731
        run("init", "-q")
        _copy(base, repo)
        run("add", "-A", "-f")
        run("-c", "user.name=tc", "-c", "user.email=tc@localhost", "commit", "-q", "--allow-empty", "-m", "base")
        for item in repo.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        _copy(new, repo)
        run("add", "-A", "-f")
        out = run("diff", "--cached", "--binary", "--no-renames", "--no-color", "--full-index").stdout
    return out
