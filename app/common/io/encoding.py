from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TEXT_ENCODING = "utf-8"
CSV_ENCODING = "utf-8-sig"


def decode_text(payload: bytes) -> str:
    return payload.decode(TEXT_ENCODING)


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding=TEXT_ENCODING)


def write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(str(text), encoding=TEXT_ENCODING)


def load_json_file(path: str | Path) -> Any:
    with Path(path).open("r", encoding=TEXT_ENCODING) as file:
        return json.load(file)


def dump_json_file(
    path: str | Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    with Path(path).open("w", encoding=TEXT_ENCODING) as file:
        json.dump(payload, file, ensure_ascii=ensure_ascii, indent=indent)
