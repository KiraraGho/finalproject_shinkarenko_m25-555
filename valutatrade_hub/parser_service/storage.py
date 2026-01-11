from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # атомарно на POSIX


def read_json(path: str, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def append_history(history_path: str, records: list[dict]) -> None:
    p = Path(history_path)
    data = read_json(history_path, default=[])
    if not isinstance(data, list):
        data = []

    # дедуп по id
    existing = {r.get("id") for r in data if isinstance(r, dict)}
    for r in records:
        if r.get("id") not in existing:
            data.append(r)

    _atomic_write_json(p, data)


def write_rates_snapshot(rates_path: str, pairs: dict[str, dict], last_refresh: str) -> None:
    p = Path(rates_path)
    snapshot = {"pairs": pairs, "last_refresh": last_refresh}
    _atomic_write_json(p, snapshot)
