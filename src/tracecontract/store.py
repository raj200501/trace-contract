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


def read_jsonl(path: str | Path, cls: type[M]) -> list[M]:
    p = Path(path)
    if not p.exists():
        return []
    return [cls.model_validate_json(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_json(obj, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return p
