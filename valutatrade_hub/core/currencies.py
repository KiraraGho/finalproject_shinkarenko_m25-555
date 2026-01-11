from __future__ import annotations

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError, ValidationError


def _validate_code(code: str) -> str:
    if not isinstance(code, str):
        raise ValidationError("Код валюты должен быть строкой")
    code = code.strip().upper()
    if not (2 <= len(code) <= 5) or " " in code:
        raise ValidationError("Код валюты должен быть в верхнем регистре, 2–5 символов, без пробелов")
    return code


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Название валюты не может быть пустым")
    return name.strip()


class Currency(ABC):
    name: str
    code: str

    def __init__(self, name: str, code: str) -> None:
        self.name = _validate_name(name)
        self.code = _validate_code(code)

    @abstractmethod
    def get_display_info(self) -> str:
        raise NotImplementedError


class FiatCurrency(Currency):
    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name=name, code=code)
        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValidationError("Issuing country не может быть пустым")
        self.issuing_country = issuing_country.strip()

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        super().__init__(name=name, code=code)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValidationError("Algorithm не может быть пустым")
        if not isinstance(market_cap, (int, float)) or float(market_cap) < 0:
            raise ValidationError("Market cap должен быть числом >= 0")
        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        return f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"


_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("British Pound", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 4.50e11),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof-of-History", 0.0),
}


def get_currency(code: str) -> Currency:
    normalized = _validate_code(code)
    cur = _REGISTRY.get(normalized)
    if cur is None:
        raise CurrencyNotFoundError(normalized)
    return cur


def supported_codes() -> list[str]:
    return sorted(_REGISTRY.keys())
