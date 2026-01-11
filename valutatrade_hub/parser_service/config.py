from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ParserConfig:
    # API key берём из окружения
    EXCHANGERATE_API_KEY: str | None = os.getenv("EXCHANGERATE_API_KEY")
    COINGECKO_API_KEY: str | None = os.getenv("COINGECKO_API_KEY")

    # Endpoints
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    # Валюты
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict[str, str] = None  # зададим в __post_init__

    # Файлы
    RATES_FILE_PATH: str = "data/rates.json"
    HISTORY_FILE_PATH: str = "data/exchange_rates.json"

    # Сеть
    REQUEST_TIMEOUT: int = 10

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "CRYPTO_ID_MAP",
            {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "SOL": "solana",
            },
        )
