from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib  
except Exception:  
    tomllib = None  


class SettingsLoader:
    _instance: "SettingsLoader | None" = None

    def __new__(cls) -> "SettingsLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance.reload()
        return cls._instance

    def reload(self) -> None:
        self._cache = {
            "DATA_DIR": "data",
            "RATES_TTL_SECONDS": 300,
            "DEFAULT_BASE": "USD",
            "LOG_PATH": "logs/actions.log",
            "LOG_LEVEL": "INFO",
        }

        pyproject = Path("pyproject.toml")
        if not pyproject.exists() or tomllib is None:
            return

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        section = (((data.get("tool") or {}).get("valutatrade")) or {})
        for k, v in section.items():
            self._cache[str(k)] = v

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)
