from __future__ import annotations

from pathlib import Path
from typing import Any

from valutatrade_hub.core.utils import _load_json, _save_json
from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    _instance: "DatabaseManager | None" = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = SettingsLoader()
        return cls._instance

    def _path(self, filename: str) -> Path:
        data_dir = Path(str(self._settings.get("DATA_DIR", "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / filename

    def read_users(self) -> list[dict[str, Any]]:
        data = _load_json(self._path("users.json"), default=[])
        return data if isinstance(data, list) else []

    def write_users(self, users: list[dict[str, Any]]) -> None:
        _save_json(self._path("users.json"), users)

    def read_portfolios(self) -> list[dict[str, Any]]:
        data = _load_json(self._path("portfolios.json"), default=[])
        return data if isinstance(data, list) else []

    def write_portfolios(self, portfolios: list[dict[str, Any]]) -> None:
        _save_json(self._path("portfolios.json"), portfolios)

    def read_rates(self) -> dict[str, Any]:
        data = _load_json(self._path("rates.json"), default={})
        return data if isinstance(data, dict) else {}

    def write_rates(self, rates: dict[str, Any]) -> None:
        _save_json(self._path("rates.json"), rates)
