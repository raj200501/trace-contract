"""Initial-state reconstruction from pinned public git revisions.

``build_snapshot`` exports exactly the tree of ``commit`` (``git archive``), so no
``.git`` directory - and therefore no later history that could contain the
solution - is present in the workspace. ``leakage_check`` verifies that no file of
the snapshot already equals the reference solution's post-image of a changed file.

Replaying a task *from its start* is what is validated here; replaying the
identical stochastic agent trajectory is a different (and not attempted) claim.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .patches import split_sections
from .schemas import Fidelity, LeakageCheck, Snapshot, SnapshotSource


def _git(args: list[str], cwd: Path | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=True,
                          env={"GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp"})


def fetch_commit(repo_url: str, commit: str, cache_dir: Path) -> Path:
    """Fetch exactly one commit (depth 1) into a bare cache repository."""
    key = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
    bare = cache_dir / f"{key}.git"
    if not bare.exists():
        bare.mkdir(parents=True)
        _git(["init", "-q", "--bare", str(bare)])
        _git(["remote", "add", "origin", repo_url], cwd=bare)
    have = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=bare, capture_output=True)
    if have.returncode != 0:
        _git(["fetch", "-q", "--depth", "1", "origin", commit], cwd=bare)
    return bare


def export_tree(bare: Path, commit: str, dest: Path, subdir: str = "") -> None:
    data = subprocess.run(["git", "archive", "--format=tar", commit, *([subdir] if subdir else [])],
                          cwd=bare, capture_output=True, check=True).stdout
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError(f"unsafe archive member {m.name}")
            if m.issym() or m.islnk():
                # Keep the tree but drop links; record them as approximations upstream.
                continue
        safe = [m for m in tf.getmembers() if not (m.issym() or m.islnk())]
        tf.extractall(dest, members=safe, filter="data")
    if subdir:
        inner = dest / subdir
        tmp = Path(tempfile.mkdtemp(prefix="tc_sub_"))
        shutil.move(str(inner), tmp / "x")
        for child in list(dest.iterdir()):
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for child in (tmp / "x").iterdir():
            shutil.move(str(child), dest / child.name)
        shutil.rmtree(tmp)


def manifest(root: Path) -> list[tuple[str, str]]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out.append((p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def manifest_sha256(entries: list[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for path, digest in entries:
        h.update(f"{path}\0{digest}\n".encode())
    return h.hexdigest()


def post_images(reference_patch: str, base: Path) -> dict[str, bytes | None]:
    """Contents of every file changed by the reference patch after applying it."""
    from .patches import apply_patch

    with tempfile.TemporaryDirectory(prefix="tc_ref_") as tmp:
        ws, _ = apply_patch(base, reference_patch, Path(tmp) / "ws")
        out: dict[str, bytes | None] = {}
        for sec in split_sections(reference_patch):
            p = sec.path
            f = ws / p
            out[p] = f.read_bytes() if f.is_file() else None
    return out


def leakage_check(snapshot_dir: Path, reference_patch: str, reference_base: Path | None = None) -> LeakageCheck:
    """Detect accidental inclusion of the final solution in the initial state.

    A changed file *leaks* if the snapshot already contains its post-image while the
    reference patch actually changes it (i.e. post-image differs from the base).
    Also flags any ``.git`` directory in the snapshot.
    """
    base = reference_base or snapshot_dir
    images = post_images(reference_patch, base)
    checked, leaked = [], []
    for path, post in images.items():
        checked.append(path)
        pre = (base / path).read_bytes() if (base / path).is_file() else None
        cur = (snapshot_dir / path).read_bytes() if (snapshot_dir / path).is_file() else None
        if post is not None and post != pre and cur == post:
            leaked.append(path)
    if (snapshot_dir / ".git").exists():
        leaked.append(".git")
    return LeakageCheck(checked_paths=sorted(checked), leaked_paths=sorted(leaked), passed=not leaked)


def build_snapshot(task_id: str, source: SnapshotSource, dest: Path, cache_dir: Path) -> Snapshot:
    bare = fetch_commit(source.repo_url, source.commit, cache_dir)
    if dest.exists():
        shutil.rmtree(dest)
    export_tree(bare, source.commit, dest, source.subdir)
    entries = manifest(dest)
    approximations = []
    links = subprocess.run(["git", "ls-tree", "-r", source.commit], cwd=bare, capture_output=True, text=True, check=True).stdout
    n_links = sum(1 for ln in links.splitlines() if ln.startswith("120000 "))
    if n_links:
        approximations.append(f"{n_links} symlink(s) in the source tree were not materialised")
    return Snapshot(
        snapshot_id=f"{task_id}@{source.commit[:12]}",
        task_id=task_id,
        repo_url=source.repo_url,
        base_commit=source.commit,
        fidelity=Fidelity.approximate if approximations else Fidelity.exact,
        approximations=approximations,
        file_manifest_sha256=manifest_sha256(entries),
        n_files=len(entries),
    )
