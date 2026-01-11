from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError, ValidationError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    @abstractmethod
    def fetch_rates(self) -> dict[str, dict]:
        """
        Возвращает стандартизированный формат
        """
        raise NotImplementedError


class CoinGeckoClient(BaseApiClient):
    def __init__(self, config: ParserConfig) -> None:
        self.config = config

    def fetch_rates(self) -> dict[str, dict]:
        ids = [self.config.CRYPTO_ID_MAP[c] for c in self.config.CRYPTO_CURRENCIES]
        params = {
            "ids": ",".join(ids),
            "vs_currencies": self.config.BASE_CURRENCY.lower(),
        }

        headers = {}
        if self.config.COINGECKO_API_KEY:
            headers["x-cg-pro-api-key"] = self.config.COINGECKO_API_KEY

        start = time.perf_counter()
        try:
            resp = requests.get(
                self.config.COINGECKO_URL,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise ApiRequestError(f"CoinGecko: ошибка сети ({e})") from e

        ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            raise ApiRequestError(f"CoinGecko: HTTP {resp.status_code}")

        data = resp.json()
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        out: dict[str, dict] = {}
        for code, cg_id in self.config.CRYPTO_ID_MAP.items():
            if code not in self.config.CRYPTO_CURRENCIES:
                continue

            try:
                rate = float(data[cg_id][self.config.BASE_CURRENCY.lower()])
            except Exception as e:
                raise ApiRequestError(f"CoinGecko: неожиданный формат ответа для {cg_id}") from e

            pair = f"{code}_{self.config.BASE_CURRENCY}"
            out[pair] = {
                "rate": rate,
                "timestamp": ts,
                "source": "CoinGecko",
                "meta": {
                    "raw_id": cg_id,
                    "request_ms": ms,
                    "status_code": resp.status_code,
                    "etag": resp.headers.get("ETag"),
                },
            }
        return out


class ExchangeRateApiClient(BaseApiClient):
    def __init__(self, config: ParserConfig) -> None:
        self.config = config

    def fetch_rates(self) -> dict[str, dict]:
        if not self.config.EXCHANGERATE_API_KEY:
            raise ApiRequestError("ExchangeRate-API: не задан EXCHANGERATE_API_KEY в окружении")

        url = f"{self.config.EXCHANGERATE_API_URL}/{self.config.EXCHANGERATE_API_KEY}/latest/{self.config.BASE_CURRENCY}"

        start = time.perf_counter()
        try:
            resp = requests.get(url, timeout=self.config.REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise ApiRequestError(f"ExchangeRate-API: ошибка сети ({e})") from e

        ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            raise ApiRequestError(f"ExchangeRate-API: HTTP {resp.status_code}")

        payload = resp.json()
        if payload.get("result") != "success":
            raise ApiRequestError(f"ExchangeRate-API: ответ не success ({payload.get('result')})")

        rates = payload.get("conversion_rates") or payload.get("rates")
        if not isinstance(rates, dict):
            raise ApiRequestError("ExchangeRate-API: отсутствует словарь rates")

        # Время обновления. 
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        out: dict[str, dict] = {}
        for code in self.config.FIAT_CURRENCIES:
            if code == self.config.BASE_CURRENCY:
                continue
            if code not in rates:
                continue

            try:
                usd_to_x = float(rates[code])
                if usd_to_x <= 0:
                    raise ValidationError("некорректный курс")
                x_to_usd = 1.0 / usd_to_x
            except Exception as e:
                raise ApiRequestError(f"ExchangeRate-API: некорректный курс для {code}") from e

            pair = f"{code}_{self.config.BASE_CURRENCY}"
            out[pair] = {
                "rate": x_to_usd,
                "timestamp": ts,
                "source": "ExchangeRate-API",
                "meta": {
                    "request_ms": ms,
                    "status_code": resp.status_code,
                },
            }
        return out
