"""Environments and base tests of natural PR-review tasks (protocol v0.9 §17; stage S10 of §15.6).

The functions here are the S10 steps that need the network or Docker. Each can be dry-run: with
``dry_run=True`` (or a ``run``/``runner`` stub) it returns the commands or calls it would make and touches
neither. They are called by the S10 step after :func:`tracecontract.natural_pr.compile_pr_task` has built
the task directory.

* :func:`plan_closure` reads the dependency declarations at the base (``pyproject.toml``: project,
  optional-dependencies, dependency groups, Poetry and PDM; ``setup.cfg``; ``setup.py`` by static parsing,
  never executed; requirements files), keeps the runtime set and the test set (extras, groups or files named
  test, tests or testing; the dev ones only when no test set is declared), adds the packages that the PR
  declares and that the pre-review or reference state imports (§17.1), and the study's own test
  requirements (pytest runs the tests; generated verifiers may use hypothesis). Versions are bounded by the
  base commit's date (``--uploaded-prior-to``). Local path requirements of a monorepo are mapped to the
  project they name; URL requirements are recorded by name only.
* :func:`resolve_closure` runs pip's resolver wheels-only for Python 3.12 on manylinux x86_64 (a dry run
  with a report: no build code runs on the host), adds the wheels that :func:`build_sdist_wheel` built from
  pure-Python sdists in the sandbox with the network disabled (:func:`is_pure_python_sdist`), checks the
  wheelhouse against the 1.5 GB cap from the index's file sizes before downloading, and pins the closure;
  :func:`resolve_with_sdists` runs it in rounds, fetching the sdist of each wheel-less requirement
  (:func:`fetch_sdist`, the newest release before the base date, checked against the index's sha256).
* :func:`build_image` builds the image through ``docker_runner.build_env_image``: it pre-populates the
  wheelhouse that function would download (the same cache key), so locally built wheels are installed by
  the same offline ``docker build``.
* :func:`select_base_tests` fixes the base-test subset from the base tree (§17.2): the test files that
  import a module the PR changes, with the test files the PR changes that exist at the base; if that is
  empty, the test directory of the changed package.
* :func:`run_base_tests` runs the subset at the base in the sandbox, offline, within 10 minutes
  (``docker_runner.run_grader`` in repository-test mode) and records the counts; "collect and run" means
  collection succeeds and the subset runs to completion (skipped tests count as run).
* :func:`build_b1` selects B1: the subset's tests at the addressing commit that pass on the reference; none
  makes B1 unavailable for the family, which is not a rejection.

A rejection is returned as ``{"rejected": True, "stage": "S10", "reason": ...}``, never raised.
"""

from __future__ import annotations

import ast
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PYTHON = "3.12"
WHEELHOUSE_CAP = 1_500_000_000  # bytes (§17.1)
BASE_TEST_TIMEOUT_S = 600  # §15.6, §17.2
# manylinux tags the grading image (python:3.12-slim, glibc 2.36) accepts, and pure wheels.
PLATFORMS = ("manylinux2014_x86_64", *(f"manylinux_2_{k}_x86_64" for k in range(17, 37)), "any")
STUDY_TEST_REQUIREMENTS = ("pytest", "hypothesis")
TEST_SETS = ("test", "tests", "testing")
DEV_SETS = ("dev", "develop", "development", "devel")
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
# A source distribution with any of these is not pure Python (§17.1).
NATIVE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".pyx", ".pxd", ".pxi", ".rs", ".f", ".f90",
                   ".f95", ".for", ".cu", ".m", ".mm", ".s", ".asm", ".go", ".so", ".pyd", ".dll", ".dylib")
NATIVE_FILES = ("Cargo.toml", "CMakeLists.txt", "meson.build", "binding.gyp", "build.rs")
NATIVE_BACKENDS = ("maturin", "setuptools_rust", "setuptools-rust", "scikit_build", "scikit-build", "mesonpy", "meson-python",
                   "cmake", "pybind11", "cython", "cffi", "nanobind", "enscons")
# Distribution name -> import name, where the two differ (used only to see whether the PR's code imports a package it adds).
IMPORT_NAMES = {"pyyaml": "yaml", "pillow": "PIL", "scikit-learn": "sklearn", "scikit-image": "skimage", "opencv-python": "cv2",
                "opencv-python-headless": "cv2", "beautifulsoup4": "bs4", "python-dateutil": "dateutil", "protobuf": "google",
                "attrs": "attr", "pyjwt": "jwt", "python-dotenv": "dotenv", "msgpack-python": "msgpack", "pymupdf": "fitz",
                "typing-extensions": "typing_extensions", "importlib-metadata": "importlib_metadata", "faiss-cpu": "faiss",
                "pycryptodome": "Crypto", "pyzmq": "zmq", "google-cloud-storage": "google", "websocket-client": "websocket",
                "python-multipart": "multipart", "ruamel.yaml": "ruamel", "tensorflow-cpu": "tensorflow", "torchvision": "torchvision"}


def _rejected(reason: str, **details: Any) -> dict[str, Any]:
    return {"rejected": True, "stage": "S10", "reason": reason, **details}


def norm_name(name: str) -> str:
    """PEP 503 normalised distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def req_name(spec: str) -> str | None:
    m = _NAME.match(spec)
    return norm_name(m.group(1)) if m else None


# --------------------------------------------------------------------------- declarations


def _poetry_constraint(v: str) -> str:
    """A Poetry version constraint as a PEP 440 specifier (caret, tilde, wildcard, comma lists)."""
    out = []
    for part in [p.strip() for p in str(v).split(",") if p.strip()]:
        if part in ("*", ""):
            continue
        if part.startswith("^"):
            nums = part[1:].split(".")
            ints = [int(x) if x.isdigit() else 0 for x in nums]
            k = next((i for i, x in enumerate(ints) if x != 0), len(ints) - 1)
            upper = ints[:k] + [ints[k] + 1]
            out.append(f">={part[1:]},<{'.'.join(map(str, upper))}")
        elif part.startswith("~") and not part.startswith("~="):
            nums = part[1:].split(".")
            upper = [int(nums[0]) + 1] if len(nums) == 1 else [int(nums[0]), int(nums[1]) + 1] if nums[1].isdigit() else [int(nums[0]) + 1]
            out.append(f">={part[1:]},<{'.'.join(map(str, upper))}")
        elif re.match(r"^\d", part):
            out.append(part.replace(".*", ".*") if "*" in part else f"=={part}")
        else:
            out.append(part)
    return ",".join(out)


def _poetry_deps(table: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(requirements, optional names) of a Poetry dependency table (``python`` itself is left out)."""
    reqs, optional = [], []
    for name, v in (table or {}).items():
        if name.lower() == "python":
            continue
        specs = v if isinstance(v, list) else [v]
        for one in specs:
            if isinstance(one, str):
                reqs.append(f"{name}{_poetry_constraint(one)}")
            elif isinstance(one, dict):
                if one.get("optional"):
                    optional.append(name)
                    continue
                if "path" in one or "git" in one or "url" in one:
                    reqs.append(f"{name} @ <path or URL>")
                    continue
                extras = f"[{','.join(one['extras'])}]" if one.get("extras") else ""
                marker = one.get("markers")
                if one.get("python"):
                    marker = " and ".join(x for x in (marker, f"python_version {_python_marker(one['python'])}") if x)
                reqs.append(f"{name}{extras}{_poetry_constraint(one.get('version', '*'))}" + (f"; {marker}" if marker else ""))
    return reqs, optional


def _python_marker(constraint: str) -> str:
    c = _poetry_constraint(constraint).split(",")[0]
    return c if c[:1] in "<>=!~" else f"=={c}"


def _literal(node: ast.AST, names: dict[str, ast.AST]) -> Any:
    """The value of a literal expression in setup.py, following module-level names and list concatenation."""
    if isinstance(node, ast.Name) and node.id in names:
        return _literal(names[node.id], names)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _literal(node.left, names), _literal(node.right, names)
        return a + b if isinstance(a, list) and isinstance(b, list) else None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return None


def setup_py_requirements(text: str) -> dict[str, Any]:
    """``install_requires``, ``extras_require`` and ``tests_require`` of a ``setup()`` call, read statically (never executed)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"static": False}
    names: dict[str, ast.AST] = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            names[st.targets[0].id] = st.value
    out: dict[str, Any] = {"static": True, "name": None}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "setup":
            for kw in node.keywords:
                if kw.arg in ("install_requires", "extras_require", "tests_require", "name"):
                    val = _literal(kw.value, names)
                    if val is None:
                        out["static"] = False
                    out[kw.arg] = val
    return out


def _cfg_list(value: str) -> list[str]:
    return [ln.strip() for ln in value.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def requirement_lines(text: str) -> dict[str, list[str]]:
    """A requirements file: requirements, ``-r``/``-c`` includes, local paths and URL requirements (by name or path)."""
    out: dict[str, list[str]] = {"requirements": [], "includes": [], "paths": [], "urls": []}
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            out["includes"].append(line.split(None, 1)[1].strip())
        elif line.startswith(("-e ", "--editable ")) or line.startswith((".", "/")):
            target = line.split(None, 1)[1].strip() if line.startswith("-") else line
            if "://" in target or target.startswith("git+"):
                out["urls"].append(req_name(target.split("#egg=")[-1]) or "<url>")
            else:
                out["paths"].append(target.split("[", 1)[0])
        elif line.startswith("-"):
            continue  # an index or install option
        elif "://" in line or " @ " in line:
            out["urls"].append(req_name(line) or "<url>")
        else:
            out["requirements"].append(line)
    return out


def _requirements_kind(rel: str) -> str | None:
    """runtime, test, dev or None (docs, lint and other sets) for a requirements file name."""
    name = PurePosixPath(rel).name.lower()
    if "doc" in rel.lower() or "lint" in name or "deprecated" in name:
        return None
    if "test" in name:
        return "test"
    if "dev" in name:
        return "dev"
    if name in ("requirements.txt", "requirements.in") and "/" not in rel:
        return "runtime"
    in_dir = rel.lower().startswith("requirements/")
    return "runtime" if in_dir and PurePosixPath(name).stem in ("base", "main", "prod", "production", "runtime") else None


def declaration_files(names: Iterable[str]) -> list[str]:
    """The dependency declarations among the scope's file names: packaging files at its root, requirements files up to one level down."""
    keep = []
    for n in names:
        p = PurePosixPath(n)
        if len(p.parts) == 1 and p.name in ("pyproject.toml", "setup.py", "setup.cfg"):
            keep.append(n)
        elif len(p.parts) <= 2 and (re.search(r"requirements[^/]*\.(?:txt|in)$", p.name, re.I) or (
                len(p.parts) == 2 and p.parts[0].lower() == "requirements" and p.suffix in (".txt", ".in"))):
            keep.append(n)
    return sorted(keep)


def declared_dependencies(files: dict[str, str]) -> dict[str, Any]:
    """The runtime and test requirements that ``files`` (scope-relative path -> text) declare (see the module docstring)."""
    runtime: list[str] = []
    sets: dict[str, list[str]] = {}  # "extra:test", "group:dev", "file:requirements-dev.txt", ...
    paths: list[dict[str, str]] = []
    urls: list[str] = []
    notes: list[str] = []
    file_extra: dict[str, tuple[list[dict[str, str]], list[str]]] = {}  # a requirements file's local paths and URL requirements
    project_name = None
    for rel, text in sorted(files.items()):
        name = PurePosixPath(rel).name
        try:
            if name == "pyproject.toml":
                d = tomllib.loads(text)
                proj = d.get("project") or {}
                project_name = project_name or proj.get("name")
                runtime += [r for r in proj.get("dependencies") or [] if isinstance(r, str)]
                for k, v in (proj.get("optional-dependencies") or {}).items():
                    sets[f"extra:{k}"] = [r for r in v if isinstance(r, str)]
                groups = d.get("dependency-groups") or {}
                for k, v in groups.items():
                    flat: list[str] = []
                    for item in v:
                        if isinstance(item, str):
                            flat.append(item)
                        elif isinstance(item, dict) and "include-group" in item:
                            flat += [x for x in groups.get(item["include-group"], []) if isinstance(x, str)]
                    sets[f"group:{k}"] = flat
                poetry = (d.get("tool") or {}).get("poetry") or {}
                if poetry:
                    project_name = project_name or poetry.get("name")
                    reqs, optional = _poetry_deps(poetry.get("dependencies") or {})
                    runtime += reqs
                    for k, v in (poetry.get("extras") or {}).items():
                        sets[f"extra:{k}"] = [x for x in v if isinstance(x, str)]
                    if optional:
                        notes.append(f"{len(optional)} optional Poetry dependencies, installed only through an extra")
                    for k, g in (poetry.get("group") or {}).items():
                        sets[f"group:{k}"] = _poetry_deps((g or {}).get("dependencies") or {})[0]
                    if poetry.get("dev-dependencies"):
                        sets["group:dev"] = sets.get("group:dev", []) + _poetry_deps(poetry["dev-dependencies"])[0]
                for k, v in (((d.get("tool") or {}).get("pdm") or {}).get("dev-dependencies") or {}).items():
                    sets[f"group:{k}"] = [x for x in v if isinstance(x, str)]
            elif name == "setup.cfg":
                cp = configparser.ConfigParser(interpolation=None)
                cp.read_string(text)
                if cp.has_option("options", "install_requires"):
                    runtime += _cfg_list(cp.get("options", "install_requires"))
                if cp.has_section("options.extras_require"):
                    for k, v in cp.items("options.extras_require"):
                        sets[f"extra:{k}"] = _cfg_list(v)
                if cp.has_option("options", "tests_require"):
                    sets["extra:tests_require"] = _cfg_list(cp.get("options", "tests_require"))
                if cp.has_option("metadata", "name"):
                    project_name = project_name or cp.get("metadata", "name")
            elif name == "setup.py":
                s = setup_py_requirements(text)
                if not s.get("static"):
                    notes.append("setup.py: some requirements are not static literals (read as far as they are)")
                project_name = project_name or (s.get("name") if isinstance(s.get("name"), str) else None)
                runtime += [r for r in s.get("install_requires") or [] if isinstance(r, str)]
                for k, v in (s.get("extras_require") or {}).items() if isinstance(s.get("extras_require"), dict) else ():
                    sets[f"extra:{k}"] = [r for r in v if isinstance(r, str)] if isinstance(v, list) else []
                if isinstance(s.get("tests_require"), list):
                    sets["extra:tests_require"] = [r for r in s["tests_require"] if isinstance(r, str)]
            else:
                kind = _requirements_kind(rel)
                parsed = requirement_lines(text)
                if kind == "runtime":
                    runtime += parsed["requirements"]
                    paths += [{"from": rel, "path": p} for p in parsed["paths"]]
                    urls += parsed["urls"]
                elif kind:
                    sets[f"file:{rel}"] = parsed["requirements"]
                    file_extra[f"file:{rel}"] = ([{"from": rel, "path": p} for p in parsed["paths"]], parsed["urls"])
        except (tomllib.TOMLDecodeError, configparser.Error, UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
            notes.append(f"{rel}: not parsed ({type(exc).__name__})")
    # URL requirements and path requirements written in pyproject tables are kept by name only.
    for bucket in (runtime, *sets.values()):
        for r in list(bucket):
            if " @ " in r or "://" in r:
                bucket.remove(r)
                urls.append(req_name(r) or "<url>")
    test_keys = [k for k in sets if k.split(":", 1)[1].rsplit("/", 1)[-1].lower() in TEST_SETS or k == "extra:tests_require"
                 or (k.startswith("file:") and _requirements_kind(k[5:]) == "test")]
    dev_keys = [k for k in sets if k.split(":", 1)[1].lower() in DEV_SETS or (k.startswith("file:") and _requirements_kind(k[5:]) == "dev")]
    chosen = test_keys or dev_keys
    test = [r for k in chosen for r in sets[k]]
    for k in chosen:  # only the chosen files' local paths and URL requirements count
        paths += file_extra.get(k, ([], []))[0]
        urls += file_extra.get(k, ([], []))[1]
    return {"project": project_name, "runtime": sorted(dict.fromkeys(runtime)), "test": sorted(dict.fromkeys(test)),
            "test_sets": chosen, "test_sets_rule": "test" if test_keys else "dev" if dev_keys else "none declared",
            "other_sets": sorted(set(sets) - set(chosen)), "path_requirements": paths, "url_requirements": sorted(set(urls)),
            "notes": notes, "files": sorted(files)}


def _imports(text: str) -> set[str]:
    """Top-level module names a Python file imports (statically)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    got: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            got |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            got.add(node.module.split(".")[0])
    return got


def imports_distribution(dist: str, imported: set[str]) -> bool:
    n = norm_name(dist)
    want = {n.replace("-", "_"), IMPORT_NAMES.get(n, "").split(".")[0]} - {""}
    if n.startswith(("python-", "py-")):
        want.add(n.split("-", 1)[1].replace("-", "_"))
    return bool({m.lower() for m in want} & {m.lower() for m in imported})


def plan_closure(*, declared_base: dict[str, Any], declared_later: Iterable[dict[str, Any]], changed_code: dict[str, str],
                 base_date: str, path_names: dict[str, str | None] | None = None) -> dict[str, Any]:
    """The planned closure (§17.1): the base's runtime and test requirements, the PR-added packages its code imports,
    the study's test requirements, the date bound and the resolver commands. Nothing is resolved or downloaded here.

    ``declared_later``: the declarations at the reviewed and the addressing commit; ``changed_code``: the text of
    the Python files the PR changes, at those commits; ``path_names``: local path requirement -> the project it names.
    """
    base_names = {req_name(r) for r in declared_base["runtime"] + declared_base["test"]} - {None}
    imported = set().union(*(_imports(t) for t in changed_code.values())) if changed_code else set()
    added, not_imported = [], []
    for later in declared_later:
        for r in later["runtime"] + later["test"]:
            n = req_name(r)
            if n is None or n in base_names or n in {req_name(x) for x in added}:
                continue
            (added if imports_distribution(n, imported) else not_imported).append(r)
    mapped = {p: n for p, n in (path_names or {}).items() if n}
    declared_names = {req_name(r) for r in declared_base["runtime"] + declared_base["test"] + added}
    path_only = sorted({n for n in mapped.values() if norm_name(n) not in declared_names})
    reqs = list(dict.fromkeys(declared_base["runtime"] + declared_base["test"] + added + path_only))
    have = {req_name(r) for r in reqs}
    study = [r for r in STUDY_TEST_REQUIREMENTS if norm_name(r) not in have]
    reqs += study
    bound = to_utc(base_date)
    return {"python": PYTHON, "platforms": list(PLATFORMS), "uploaded_prior_to": bound, "requirements": reqs,
            "declared": {k: declared_base[k] for k in ("project", "runtime", "test", "test_sets", "test_sets_rule", "other_sets",
                                                       "url_requirements", "notes", "files")},
            "pr_added": added, "pr_added_not_imported": sorted(set(not_imported)), "study_test_requirements": study,
            "path_requirements": [{"path": p, "maps_to": mapped.get(p)} for p in sorted(path_names or {})],
            "path_only": path_only,
            "commands": [resolver_command(reqs, report="<workdir>/report.json", uploaded_prior_to=bound)],
            "rule": "wheels only for CPython 3.12 on manylinux x86_64, versions uploaded before the base commit's date; "
                    "pure-Python sdists may be built into wheels in the sandbox without network (§17.1)"}


def to_utc(stamp: str) -> str:
    t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- resolution


def _platform_flags() -> list[str]:
    out = []
    for p in PLATFORMS:
        out += ["--platform", p]
    return out


def resolver_command(reqs: list[str], *, report: str, uploaded_prior_to: str | None, find_links: str | None = None,
                     python: str = sys.executable) -> list[str]:
    """pip's resolver, dry run, wheels only, for the grading image's interpreter and platform (no build code runs)."""
    cmd = [python, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet", "--disable-pip-version-check",
           "--report", report, "--only-binary=:all:", "--python-version", PYTHON, "--implementation", "cp", *_platform_flags()]
    if uploaded_prior_to:
        cmd += ["--uploaded-prior-to", uploaded_prior_to]
    if find_links:
        cmd += ["--find-links", find_links]
    return cmd + list(reqs)


def download_command(pins: list[str], dest: str, *, find_links: str | None = None, python: str = sys.executable) -> list[str]:
    cmd = [python, "-m", "pip", "download", "--quiet", "--disable-pip-version-check", "--no-deps", "--only-binary=:all:",
           "--python-version", PYTHON, "--implementation", "cp", *_platform_flags(), "-d", dest]
    return cmd + (["--find-links", find_links] if find_links else []) + list(pins)


_NO_MATCH = re.compile(r"No matching distribution found for ([A-Za-z0-9][A-Za-z0-9._-]*)")


def wheel_less(stderr: str) -> list[str]:
    """The requirements pip found no wheel for (from its error output)."""
    return sorted({norm_name(m) for m in _NO_MATCH.findall(stderr)})


def pins_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """name, version, file name and sha256 of every item a pip install report selects."""
    out = []
    for item in report.get("install", []):
        meta, info = item.get("metadata") or {}, item.get("download_info") or {}
        url = info.get("url", "")
        out.append({"name": norm_name(meta.get("name", "")), "version": meta.get("version"), "file": url.rsplit("/", 1)[-1],
                    "url": url, "sha256": ((info.get("archive_info") or {}).get("hashes") or {}).get("sha256")})
    return sorted(out, key=lambda x: x["name"])


def pypi_json(name: str, version: str | None = None, *, timeout: float = 60) -> dict[str, Any]:
    """PyPI's JSON API (network; the S10 environment step only)."""
    import urllib.request

    url = f"https://pypi.org/pypi/{name}/{version}/json" if version else f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - a fixed https host
        return json.loads(resp.read().decode("utf-8"))


def wheelhouse_size(pins: list[dict[str, Any]], *, fetch_json: Callable[..., dict[str, Any]] = pypi_json,
                    local: dict[str, int] | None = None) -> tuple[int, list[str]]:
    """The bytes of the selected files, from the index's metadata (nothing is downloaded); and the files whose size is unknown."""
    total, unknown = 0, []
    for p in pins:
        if local and p["file"] in local:
            total += local[p["file"]]
            continue
        try:
            urls = fetch_json(p["name"], p["version"]).get("urls", [])
        except Exception:  # noqa: BLE001 - a lookup failure leaves the size unknown, recorded
            urls = []
        size = next((u.get("size") for u in urls if u.get("filename") == p["file"]), None)
        if size is None:
            unknown.append(p["file"])
        else:
            total += int(size)
    return total, unknown


def is_pure_python_sdist(path: str | Path) -> tuple[bool, list[str]]:
    """Whether an sdist holds no C, C++, Cython, Rust or Fortran sources and declares no extension modules (§17.1).

    The archive is listed and its build files are read as text; nothing is extracted or run.
    """
    reasons: list[str] = []
    path = Path(path)
    try:
        if path.name.endswith(".zip"):
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                read = lambda n: zf.read(n)  # noqa: E731
        else:
            tf = tarfile.open(path)
            names = [m.name for m in tf.getmembers() if m.isfile()]
            read = lambda n: tf.extractfile(n).read()  # noqa: E731
        for n in names:
            low = n.lower()
            if low.endswith(NATIVE_SUFFIXES) or PurePosixPath(n).name in NATIVE_FILES:
                reasons.append(f"native source or build file: {PurePosixPath(n).name}")
        for n in names:
            base = PurePosixPath(n).name
            if base in ("setup.py", "pyproject.toml", "setup.cfg") and len(PurePosixPath(n).parts) <= 2:
                text = read(n).decode("utf-8", "replace")
                if re.search(r"\bext_modules\b|\bExtension\s*\(|\bcythonize\b|\bext-modules\b", text):
                    reasons.append(f"{base} declares extension modules")
                for b in NATIVE_BACKENDS:
                    if re.search(rf"(?i)['\"]{re.escape(b)}\b", text) or (base == "pyproject.toml" and re.search(
                            rf"(?im)^\s*build-backend\s*=\s*['\"]{re.escape(b)}", text)):
                        reasons.append(f"{base} names the native build tool {b}")
    except (tarfile.TarError, zipfile.BadZipFile, OSError, KeyError, AttributeError) as exc:
        return False, [f"unreadable archive: {type(exc).__name__}"]
    reasons = sorted(set(reasons))
    return not reasons, reasons


def build_sdist_wheel(sdist: Path, build_wheels: Path, out: Path, *, image: str | None = None,
                      run: Callable[..., Any] = subprocess.run, dry_run: bool = False) -> dict[str, Any]:
    """Build a pure-Python sdist into a wheel inside the sandbox, with the network disabled (§17.1).

    ``build_wheels`` holds the wheels of the sdist's build backend (pip installs them into its isolated build
    environment from there, offline). Returns the command and, after a real build, the wheel's sha256.
    """
    from .sandbox.docker_runner import BASE_IMAGE
    from .schemas import sha256_bytes

    ok, why = is_pure_python_sdist(sdist)
    if not ok:
        return _rejected("no resolvable closure: an sdist-only requirement is not pure Python", sdist=sdist.name, why=why)
    cmd = ["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--read-only", "--tmpfs", "/tmp:rw,size=512m", "--memory", "2g", "--pids-limit", "256", "--user", "1001:1001",
           "-e", "HOME=/tmp", "-e", "PIP_NO_INDEX=1", "-e", "PIP_CONFIG_FILE=/dev/null",
           "-v", f"{sdist.parent.resolve()}:/in:ro", "-v", f"{build_wheels.resolve()}:/wheels:ro", "-v", f"{out.resolve()}:/out:rw",
           image or BASE_IMAGE, "python", "-m", "pip", "wheel", "--no-deps", "--no-index", "--find-links", "/wheels",
           "--disable-pip-version-check", "-w", "/out", f"/in/{sdist.name}"]
    rec: dict[str, Any] = {"sdist": sdist.name, "sdist_sha256": sha256_bytes(sdist.read_bytes()), "command": cmd}
    if dry_run:
        return {**rec, "planned": True}
    out.mkdir(parents=True, exist_ok=True)
    proc = run(cmd, capture_output=True, text=True, timeout=1800)
    wheels = sorted(out.glob("*.whl"))
    if proc.returncode != 0 or not wheels:
        return _rejected("no resolvable closure: an sdist did not build into a wheel in the sandbox", sdist=sdist.name,
                         stderr_tail=(proc.stderr or "")[-500:])
    return {**rec, "wheel": wheels[-1].name, "wheel_sha256": sha256_bytes(wheels[-1].read_bytes())}


def resolve_closure(plan: dict[str, Any], workdir: Path, *, run: Callable[..., Any] = subprocess.run,
                    fetch_json: Callable[..., dict[str, Any]] = pypi_json, local_wheels: Path | None = None,
                    dry_run: bool = False, cap: int = WHEELHOUSE_CAP) -> dict[str, Any]:
    """Resolve and pin the planned closure (network-enabled step on the host; wheels only, a dry run with a report).

    ``local_wheels``: wheels built from pure-Python sdists (:func:`build_sdist_wheel`), offered to the resolver
    as ``--find-links``. Returns the pins with each file's sha256, the wheelhouse size and the commands; or a
    rejection (``environment too large`` above the cap, ``no resolvable closure`` with the wheel-less
    requirements, which the caller may build from sdists and resolve again).
    """
    workdir.mkdir(parents=True, exist_ok=True)
    report = workdir / "report.json"
    cmd = resolver_command(plan["requirements"], report=str(report), uploaded_prior_to=plan.get("uploaded_prior_to"),
                           find_links=str(local_wheels) if local_wheels else None)
    env_note = {"PIP_CONFIG_FILE": "/dev/null", "PIP_CACHE_DIR": str(workdir / "cache")}
    if dry_run:
        return {"planned": True, "commands": [cmd], "env": env_note}
    report.unlink(missing_ok=True)  # pip writes the report only when it resolves: never read an earlier run's
    proc = run(cmd, capture_output=True, text=True, timeout=1800, env={**os.environ, **env_note})
    dropped: list[str] = []
    if (proc.returncode != 0 or not report.is_file()) and plan.get("path_only"):
        # A local path requirement maps to a project; where the index has no release of it, it is dropped once (recorded).
        missing = set(wheel_less(proc.stderr or ""))
        dropped = sorted(n for n in plan["path_only"] if norm_name(n) in missing)
        if dropped:
            keep = [r for r in plan["requirements"] if req_name(r) not in {norm_name(n) for n in dropped}]
            cmd2 = resolver_command(keep, report=str(report), uploaded_prior_to=plan.get("uploaded_prior_to"),
                                    find_links=str(local_wheels) if local_wheels else None)
            report.unlink(missing_ok=True)
            proc = run(cmd2, capture_output=True, text=True, timeout=1800, env={**os.environ, **env_note})
            cmd = cmd2
    if proc.returncode != 0 or not report.is_file():
        missing = wheel_less(proc.stderr or "")
        return _rejected("no resolvable closure: no wheels-only resolution" + (f" ({len(missing)} wheel-less requirement(s))"
                                                                              if missing else ""),
                         wheel_less=missing, stderr_tail=(proc.stderr or "")[-1500:], commands=[cmd])
    pins = pins_from_report(json.loads(report.read_text(encoding="utf-8")))
    local = {w.name: w.stat().st_size for w in local_wheels.glob("*.whl")} if local_wheels else {}
    size, unknown = wheelhouse_size(pins, fetch_json=fetch_json, local=local)
    rec = {"pins": [f"{p['name']}=={p['version']}" for p in pins], "files": pins, "wheelhouse_bytes": size,
           "unknown_sizes": unknown, "commands": [cmd], "uploaded_prior_to": plan.get("uploaded_prior_to"),
           "dropped_path_requirements": dropped}
    if size > cap:
        return _rejected(f"environment too large: the wheelhouse would hold {size / 1e9:.2f} GB, over the 1.5 GB cap (§17.1)",
                         **rec)
    return rec


def _download(url: str, dest: Path, *, timeout: float = 300) -> None:
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as resp, dest.open("wb") as fh:  # noqa: S310 - the index's https URL
        shutil.copyfileobj(resp, fh)


def fetch_sdist(requirement: str, before: str | None, dest: Path, *, fetch_json: Callable[..., dict[str, Any]] = pypi_json,
                download: Callable[[str, Path], None] = _download) -> dict[str, Any] | None:
    """The newest release satisfying ``requirement`` whose sdist was uploaded before ``before``: downloaded to ``dest`` and
    checked against the index's sha256. None when there is none. Only the archive is fetched; nothing in it runs."""
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.version import InvalidVersion, Version

    try:
        req = Requirement(requirement)
    except InvalidRequirement:
        return None
    meta = fetch_json(norm_name(req.name))
    limit = datetime.fromisoformat(before.replace("Z", "+00:00")) if before else None
    best = None
    for ver, files in (meta.get("releases") or {}).items():
        try:
            v = Version(ver)
        except InvalidVersion:
            continue
        if v.is_prerelease or not req.specifier.contains(v, prereleases=False):
            continue
        for f in files:
            up = f.get("upload_time_iso_8601") or f.get("upload_time")
            when = datetime.fromisoformat(str(up).replace("Z", "+00:00")) if up else None
            if when is not None and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if f.get("packagetype") == "sdist" and not f.get("yanked") and (limit is None or (when and when < limit)):
                if best is None or v > best[0]:
                    best = (v, f)
    if best is None:
        return None
    v, f = best
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f["filename"]
    download(f["url"], path)
    from .schemas import sha256_bytes

    got, want = sha256_bytes(path.read_bytes()), (f.get("digests") or {}).get("sha256")
    if want and got != want:
        path.unlink(missing_ok=True)
        return None
    return {"name": norm_name(req.name), "version": str(v), "file": path.name, "path": str(path), "sha256": got}


def _sdist_build_requires(path: Path) -> list[str]:
    """``[build-system] requires`` of an sdist, read from the archive (setuptools and wheel when it declares none)."""
    try:
        with tarfile.open(path) as tf:
            for m in tf.getmembers():
                if m.isfile() and PurePosixPath(m.name).name == "pyproject.toml" and len(PurePosixPath(m.name).parts) == 2:
                    d = tomllib.loads(tf.extractfile(m).read().decode("utf-8", "replace"))
                    return list((d.get("build-system") or {}).get("requires") or ["setuptools", "wheel"])
    except (tarfile.TarError, OSError, tomllib.TOMLDecodeError, AttributeError):
        pass
    return ["setuptools", "wheel"]


def resolve_with_sdists(plan: dict[str, Any], workdir: Path, *, run: Callable[..., Any] = subprocess.run,
                        fetch_json: Callable[..., dict[str, Any]] = pypi_json, download: Callable[[str, Path], None] = _download,
                        max_rounds: int = 3, cap: int = WHEELHOUSE_CAP) -> dict[str, Any]:
    """Wheels only; for requirements with no wheel, their pure-Python sdist built into a wheel in the sandbox (§17.1).

    Each round resolves with the wheels built so far (``--find-links``). A wheel-less requirement is fetched as the
    newest sdist uploaded before the base date; it must be pure Python; its build backend is downloaded as wheels for
    the image's platform; the build runs in a container without network. Every build is recorded with both sha256s.
    """
    built: list[dict[str, Any]] = []
    local, backends = workdir / "built-wheels", workdir / "build-backend-wheels"
    specs = {req_name(r): r for r in plan["requirements"]}
    res: dict[str, Any] = {}
    for k in range(max_rounds):
        res = resolve_closure(plan, workdir / f"round-{k}", run=run, fetch_json=fetch_json,
                              local_wheels=local if built else None, cap=cap)
        if not res.get("rejected") or not res.get("wheel_less"):
            return {**res, "sdist_builds": built}
        for name in res["wheel_less"]:
            if any(b["name"] == name for b in built):
                return _rejected("no resolvable closure: a wheel built from an sdist was not accepted by the resolver",
                                 sdist_builds=built, wheel_less=res["wheel_less"])
            sd = fetch_sdist(specs.get(name) or name, plan.get("uploaded_prior_to"), workdir / "sdists", fetch_json=fetch_json,
                             download=download)
            if sd is None:
                return _rejected(f"no resolvable closure: {name} has no wheel and no sdist released before the base date",
                                 sdist_builds=built, wheel_less=res["wheel_less"])
            reqs = _sdist_build_requires(Path(sd["path"]))
            backends.mkdir(parents=True, exist_ok=True)
            dl = [sys.executable, "-m", "pip", "download", "--quiet", "--disable-pip-version-check", "--only-binary=:all:",
                  "--python-version", PYTHON, "--implementation", "cp", *_platform_flags(), "-d", str(backends), *reqs]
            proc = run(dl, capture_output=True, text=True, timeout=900)
            if proc.returncode != 0:
                return _rejected(f"no resolvable closure: the build backend of {name}'s sdist has no wheels", sdist_builds=built)
            rec = build_sdist_wheel(Path(sd["path"]), backends, local, run=run)
            if rec.get("rejected"):
                return {**rec, "sdist_builds": built}
            built.append({"name": sd["name"], "version": sd["version"], "sdist": sd["file"], "sdist_sha256": sd["sha256"],
                          "wheel": rec.get("wheel"), "wheel_sha256": rec.get("wheel_sha256"), "build_requires": reqs,
                          "command": rec.get("command")})
    return {**res, "sdist_builds": built} if not res.get("rejected") else _rejected(
        f"no resolvable closure after {max_rounds} rounds of sdist builds", sdist_builds=built, wheel_less=res.get("wheel_less"))


def build_image(pins: list[str], cache_dir: Path, *, local_wheels: Path | None = None, run: Callable[..., Any] = subprocess.run,
                build: Callable[..., tuple[str, str]] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Build the task's image through ``docker_runner.build_env_image`` (offline ``docker build``, ``--no-deps`` install).

    The wheelhouse that ``build_env_image`` would download is filled first, under its own cache key, with the
    PyPI wheels (downloaded for every manylinux tag the image accepts) and the locally built wheels; that is
    the thin extension, so nothing else of the mechanism changes.
    """
    from .sandbox.docker_runner import _req_hash, build_env_image

    reqs = sorted(set(pins))
    wh = cache_dir / f"wheelhouse-{_req_hash(reqs)}"
    cmd = download_command(reqs, str(wh), find_links=str(local_wheels) if local_wheels else None)
    if dry_run:
        return {"planned": True, "wheelhouse": str(wh), "commands": [cmd], "build": "docker_runner.build_env_image(pins)"}
    if not (wh / ".complete").exists():
        wh.mkdir(parents=True, exist_ok=True)
        proc = run(cmd, capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            return _rejected("no resolvable closure: the pinned wheels could not be downloaded", stderr_tail=(proc.stderr or "")[-800:])
        size = sum(f.stat().st_size for f in wh.glob("*.whl"))
        if size > WHEELHOUSE_CAP:
            shutil.rmtree(wh, ignore_errors=True)
            return _rejected(f"environment too large: the wheelhouse holds {size / 1e9:.2f} GB, over the 1.5 GB cap (§17.1)")
        (wh / ".complete").write_text("\n".join(reqs) + "\n")
    tag, image_id = (build or build_env_image)(reqs, cache_dir)
    return {"image": tag, "image_id": image_id, "wheelhouse": str(wh),
            "wheelhouse_bytes": sum(f.stat().st_size for f in wh.glob("*.whl"))}


# --------------------------------------------------------------------------- base tests (§17.2)


def is_test_file(rel: str) -> bool:
    name = PurePosixPath(rel).name
    return rel.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")) and name != "conftest.py"


def import_roots(snapshot: Path) -> list[str]:
    """The directories that are import roots in the sandbox: ``src`` when it holds a package, and the snapshot root."""
    src = snapshot / "src"
    if src.is_dir() and any(True for _ in src.rglob("*.py")):  # also a namespace package (src/<ns>/<pkg>/)
        return ["src", ""]
    return [""]


def candidate_pythonpath(snapshot: Path) -> str:
    return ":".join(f"/work/{r}" if r else "/work" for r in import_roots(snapshot))


def module_names(rel: str, roots: list[str]) -> set[str]:
    """Dotted module names of a scope-relative Python file under each import root (``pkg/__init__.py`` -> ``pkg``)."""
    out = set()
    for root in roots:
        if root and not rel.startswith(root + "/"):
            continue
        sub = rel[len(root) + 1:] if root else rel
        parts = list(PurePosixPath(sub).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts and all(p.isidentifier() for p in parts):
            out.add(".".join(parts))
    return out


def file_imports(text: str, own: set[str]) -> set[str]:
    """Dotted names a test file imports, with ``from p import x`` also as ``p.x``; relative imports resolved from ``own``."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    got: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            got |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            bases = {node.module or ""} if not node.level else {
                ".".join([*o.split(".")[:-node.level], *([node.module] if node.module else [])]) for o in own
                if len(o.split(".")) > node.level}
            for b in bases:
                if b:
                    got.add(b)
                    got |= {f"{b}.{a.name}" for a in node.names if a.name != "*"}
    return got


def select_base_tests(snapshot: Path, *, changed: list[tuple[str, str]], commented_path: str) -> dict[str, Any]:
    """The base-test subset of §17.2, fixed from the base tree (``changed``: (status, scope-relative path), base to addressing)."""
    roots = import_roots(snapshot)
    files = sorted(p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*.py") if p.is_file() and not p.is_symlink())
    tests = [f for f in files if is_test_file(f)]
    changed_modules: dict[str, set[str]] = {}
    for status, rel in changed:
        if rel.endswith(".py") and status[:1] in ("M", "D", "T") and not is_test_file(rel) and (snapshot / rel).is_file():
            changed_modules[rel] = module_names(rel, roots)
    packages = {n for rel, names in changed_modules.items() if rel.endswith("__init__.py") for n in names}
    modules = {n for names in changed_modules.values() for n in names}
    by_import: dict[str, list[str]] = {}
    for t in tests:
        try:
            text = (snapshot / t).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        got = file_imports(text, module_names(t, roots))
        hit = sorted(m for m in modules if m in got or (m in packages and any(g.startswith(m + ".") for g in got)))
        if hit:
            by_import[t] = hit
    changed_tests = sorted(rel for status, rel in changed if is_test_file(rel) and status[:1] in ("M", "D", "T")
                           and (snapshot / rel).is_file())
    subset = sorted(set(by_import) | set(changed_tests))
    rule = "test files importing a changed module, and changed test files present at the base"
    fallback = None
    if not subset:
        parents = [str(p) for p in PurePosixPath(commented_path).parents if str(p) != "."]  # the deepest package first
        for d in ["tests", "test", "testing", *(f"{p}/{t}" for p in parents for t in ("tests", "test"))]:
            if (snapshot / d).is_dir() and any(is_test_file(f) and f.startswith(d + "/") for f in tests):
                fallback = d
                break
        if fallback:
            subset, rule = [fallback], "the test directory of the changed package (no test file imports a changed module)"
    return {"subset": subset, "rule": rule, "by_import": by_import, "changed_test_files": changed_tests,
            "changed_modules": sorted(modules), "n_test_files_at_base": len(tests), "import_roots": roots,
            "empty": not subset}


def repo_test_args(subset: list[str]) -> list[str]:
    """pytest arguments of the base run and of B1: the repository's addopts are switched off, as in the pilot tasks."""
    return ["-o", "addopts=", *subset]


def _counts(results: dict[str, Any]) -> dict[str, int]:
    c = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for t in results.get("tests", []):
        c[t.get("outcome", "error") if t.get("outcome") in c else "error"] += 1
    return c


def collection_failed(results: dict[str, Any]) -> list[str]:
    """Collection errors in a repository-test run: junit errors named as collection failures, or pytest exit codes 2-4."""
    errs = [t["nodeid"] for t in results.get("tests", []) if t.get("outcome") == "error"
            and "collection failure" in (t.get("longrepr") or "").lower()]
    errs += [c.get("nodeid", "?") for c in results.get("collect_errors", [])]
    if results.get("pytest_exit_code") in (2, 3, 4) and not errs:
        errs.append(f"pytest exit code {results.get('pytest_exit_code')}")
    return errs


def run_base_tests(base_dir: Path, image: str | None, *, args: list[str], pythonpath: str,
                   runner: Callable[..., Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Run the subset at the base offline in the sandbox, within 10 minutes, and record the counts (§17.2)."""
    from .sandbox.docker_runner import Limits, prepare_workspace, run_grader
    from .schemas import Isolation

    limits = Limits(wall_s=BASE_TEST_TIMEOUT_S + 120)
    call = {"call": "docker_runner.run_grader", "image": image or "<the task image>", "mode": "repo_tests (in_process)",
            "network": "none", "repo_test_args": args, "candidate_pythonpath": pythonpath,
            "repo_test_timeout_s": BASE_TEST_TIMEOUT_S, "container_wall_s": limits.wall_s}
    if dry_run:
        return {"planned": True, **call}
    ws, diags, err = prepare_workspace(base_dir, "")
    if ws is None:
        return _rejected("base tests: the base could not be staged", diagnostics=diags)
    try:
        raw, nonce = (runner or run_grader)(image, workspace=ws, mode=Isolation.in_process, overlay_dir=None, repo_test_args=args,
                                            candidate_pythonpath=pythonpath, limits=limits)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    r = raw.results or {}
    rec = {**call, "counts": _counts(r), "pytest_exit_code": r.get("pytest_exit_code"), "elapsed_s": r.get("elapsed_s"),
           "timed_out": bool(raw.timed_out or r.get("timed_out")), "harness_version": r.get("harness_version")}
    if r.get("nonce") != nonce or r.get("status") != "completed":
        return _rejected("base tests: the grader did not complete", **rec, status=r.get("status"))
    if rec["timed_out"]:
        return _rejected("base tests do not run to completion within 10 minutes", **rec)
    errs = collection_failed(r)
    if errs:
        return _rejected("base tests fail to collect", **rec, collection_errors=errs[:20])
    if sum(rec["counts"].values()) == 0:
        return _rejected("base tests: the subset collects no test", **rec)
    return {**rec, "passed": True}


def build_b1(task_dir: Path, base_dir: Path, image: str | None, *, subset: list[str], pythonpath: str,
             runner: Callable[..., Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """B1's selection (§17.2): the subset's tests at the addressing commit that pass on the reference.

    The overlay is the subset's files as the reference state has them (the base with the reference patch,
    protected paths included); files the PR deletes drop out. No passing test: B1 is unavailable (not a rejection).
    """
    from .patches import apply_patch
    from .sandbox.docker_runner import prepare_workspace, run_grader
    from .schemas import Candidate, Isolation, TaskManifest, VerifierCondition
    from .store import dump, load, write_json
    from .verifier import build_spec

    m = load(task_dir / "task.json", TaskManifest)
    ref = next(c for c in (load(task_dir / p, Candidate) for p in m.candidates) if c.origin.value == "reference")
    vdir = task_dir / "verifiers" / "repo_tests"
    with tempfile.TemporaryDirectory(prefix="tc_b1_") as tmp:
        state, _ = apply_patch(base_dir, ref.patch, Path(tmp) / "ref")
        present = [p for p in subset if (state / p).exists()]
        args = repo_test_args(present)
        call = {"call": "docker_runner.run_grader", "image": image or "<the task image>", "mode": "repo_tests (in_process)",
                "overlay": present, "repo_test_args": args, "candidate_pythonpath": pythonpath, "network": "none"}
        if dry_run:
            return {"planned": True, **call}
        overlay = vdir / "overlay"
        if overlay.exists():
            shutil.rmtree(overlay)
        for p in present:
            src, dst = state / p, overlay / p
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
    ws, diags, err = prepare_workspace(base_dir, ref.patch)
    if ws is None:
        return {"available": False, "reason": "the reference patch could not be staged", "diagnostics": diags}
    try:
        raw, nonce = (runner or run_grader)(image, workspace=ws, mode=Isolation.in_process, overlay_dir=overlay, repo_test_args=args,
                                            candidate_pythonpath=pythonpath)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    r = raw.results or {}
    if r.get("nonce") != nonce or r.get("status") != "completed" or r.get("timed_out"):
        return {"available": False, "reason": "the reference run did not complete", "status": r.get("status"), **call}
    passing = sorted(t["nodeid"] for t in r.get("tests", []) if t["outcome"] == "passed")
    failing = sorted(t["nodeid"] for t in r.get("tests", []) if t["outcome"] != "passed")
    write_json({"passing_on_reference": passing, "excluded_not_passing_on_reference": failing,
                "collect_errors": r.get("collect_errors", []), "harness_version": r.get("harness_version")}, vdir / "selection.json")
    if not passing:
        return {"available": False, "reason": "no test of the subset passes on the reference (B1 unavailable, §17.2)",
                "excluded": len(failing), **call}
    (vdir / "check_ids.json").write_text(json.dumps(passing))
    spec = build_spec(verifier_id="repo_tests", task_id=m.task_id, condition=VerifierCondition.repo_tests, test_dir=overlay,
                      task_dir=task_dir, isolation=Isolation.in_process, check_ids=passing)
    dump(spec, vdir / "spec.json")
    rel = "verifiers/repo_tests/spec.json"
    upd = {"repo_test_args": args, **({"verifiers": m.verifiers + [rel]} if rel not in m.verifiers else {})}
    dump(m.model_copy(update=upd), task_dir / "task.json")
    return {"available": True, "n_checks": len(passing), "excluded": len(failing), **call}


__all__ = ["BASE_TEST_TIMEOUT_S", "PLATFORMS", "WHEELHOUSE_CAP", "build_b1", "build_image", "build_sdist_wheel", "candidate_pythonpath",
           "declaration_files", "declared_dependencies", "download_command", "fetch_sdist", "is_pure_python_sdist", "plan_closure",
           "repo_test_args", "resolve_closure", "resolve_with_sdists", "resolver_command", "run_base_tests", "select_base_tests",
           "wheel_less", "wheelhouse_size"]
