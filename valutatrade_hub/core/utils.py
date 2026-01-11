from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"


def ensure_storage() -> None:
    """Создаёт папку data/ и пустые JSON-файлы с валидным содержимым."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]\n", encoding="utf-8")
    if not PORTFOLIOS_FILE.exists():
        PORTFOLIOS_FILE.write_text("[]\n", encoding="utf-8")
    if not RATES_FILE.exists():
        RATES_FILE.write_text("{}\n", encoding="utf-8")


def _load_json(path: Path, default: Any) -> Any:
    ensure_storage()
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return default
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _save_json(path: Path, data: Any) -> None:
    ensure_storage()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_users() -> list[dict[str, Any]]:
    users = _load_json(USERS_FILE, default=[])
    return users if isinstance(users, list) else []


def save_users(users: list[dict[str, Any]]) -> None:
    _save_json(USERS_FILE, users)


def load_portfolios() -> list[dict[str, Any]]:
    portfolios = _load_json(PORTFOLIOS_FILE, default=[])
    return portfolios if isinstance(portfolios, list) else []


def save_portfolios(portfolios: list[dict[str, Any]]) -> None:
    _save_json(PORTFOLIOS_FILE, portfolios)


def load_rates() -> dict[str, Any]:
    rates = _load_json(RATES_FILE, default={})
    return rates if isinstance(rates, dict) else {}


def save_rates(rates: dict[str, Any]) -> None:
    _save_json(RATES_FILE, rates)


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def parse_iso(dt: str) -> datetime | None:
    try:
        return datetime.fromisoformat(dt)
    except Exception:
        return None


def next_user_id(users: list[dict[str, Any]]) -> int:
    max_id = 0
    for u in users:
        try:
            max_id = max(max_id, int(u.get("user_id", 0)))
        except Exception:
            continue
    return max_id + 1


def find_user_by_username(users: list[dict[str, Any]], username: str) -> dict[str, Any] | None:
    for u in users:
        if u.get("username") == username:
            return u
    return None


def get_or_create_portfolio_record(portfolios: list[dict[str, Any]], user_id: int) -> dict[str, Any]:
    for p in portfolios:
        if int(p.get("user_id", -1)) == int(user_id):
            if "wallets" not in p or not isinstance(p["wallets"], dict):
                p["wallets"] = {}
            return p
    new_p = {"user_id": int(user_id), "wallets": {}}
    portfolios.append(new_p)
    return new_p
