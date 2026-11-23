"""Small helpers to read/write pydantic models as JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def load(path: str | Path, cls: type[M]) -> M:
    return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def dump(model: BaseModel, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return p


def append_jsonl(model: BaseModel, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(model.model_dump_json() + "\n")


def jsonl_lines(text: str) -> list[str]:
    """The lines of a JSON Lines text, split at line feeds only. ``str.splitlines`` also splits at U+0085, U+2028 and
    U+2029, which a JSON string may hold unescaped, so it can cut a record in two. A carriage return before a line feed is
    dropped, and so is the empty string after a final line feed: for records joined by line feeds that hold none of those
    three characters, the result is ``text.splitlines()``."""
    out = text.split("\n")
    if out and out[-1] == "":
        out.pop()
    return [x.removesuffix("\r") for x in out]


def read_jsonl(path: str | Path, cls: type[M]) -> list[M]:
    p = Path(path)
    if not p.exists():
        return []
    return [cls.model_validate_json(ln) for ln in jsonl_lines(p.read_text(encoding="utf-8")) if ln.strip()]


def write_json(obj, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return p
