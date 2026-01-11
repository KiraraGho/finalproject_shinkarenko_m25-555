from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency  # валидируем коды
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import BaseApiClient
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import append_history, read_json, write_rates_snapshot


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class RatesUpdater:
    config: ParserConfig
    clients: list[BaseApiClient]

    def run_update(self, source: str | None = None) -> dict:
        logger = logging.getLogger(__name__)
        logger.info("Starting rates update...")

        combined: dict[str, dict] = {}
        errors: list[str] = []

        for client in self.clients:
            name = client.__class__.__name__.lower()
            if source:
                s = source.lower()
                if s == "coingecko" and "coingecko" not in name:
                    continue
                if s in {"exchangerate", "exchangerate-api", "exchangerateapi"} and "exchange" not in name:
                    continue

            try:
                logger.info("Fetching from %s...", client.__class__.__name__)
                data = client.fetch_rates()
                logger.info("OK (%d rates)", len(data))
                combined.update(data)
            except ApiRequestError as e:
                msg = f"{client.__class__.__name__}: {e}"
                logger.error("Failed: %s", msg)
                errors.append(msg)

        if not combined and errors:
            raise ApiRequestError("Ни один источник не вернул данные. " + "; ".join(errors))

        # Валидируем валютные коды и собираем историю + snapshot
        now_z = _utc_now_iso_z()

        history_records: list[dict] = []
        pairs_snapshot: dict[str, dict] = {}

        # загрузим текущий snapshot, чтобы обновлять только если свежее
        current_snapshot = read_json(self.config.RATES_FILE_PATH, default={})
        current_pairs = current_snapshot.get("pairs", {}) if isinstance(current_snapshot, dict) else {}
        if not isinstance(current_pairs, dict):
            current_pairs = {}

        for pair, info in combined.items():
            try:
                from_code, to_code = pair.split("_", 1)
                from_code = get_currency(from_code).code
                to_code = get_currency(to_code).code
                rate = float(info["rate"])
                ts = str(info["timestamp"])
                src = str(info["source"])
                meta = dict(info.get("meta", {}))

                rec_id = f"{from_code}_{to_code}_{ts}"
                record = {
                    "id": rec_id,
                    "from_currency": from_code,
                    "to_currency": to_code,
                    "rate": rate,
                    "timestamp": ts,
                    "source": src,
                    "meta": meta,
                }
                history_records.append(record)

                # snapshot: обновляем, если timestamp "свежее" текущего
                prev = current_pairs.get(f"{from_code}_{to_code}")
                if isinstance(prev, dict):
                    prev_ts = str(prev.get("updated_at", ""))
                    if prev_ts and prev_ts >= ts:
                        # старее/равно — не перетираем
                        continue

                pairs_snapshot[f"{from_code}_{to_code}"] = {"rate": rate, "updated_at": ts, "source": src}

            except Exception as e:
                logger.error("Skip invalid rate %s: %s", pair, e)

        append_history(self.config.HISTORY_FILE_PATH, history_records)

        # Объединяем snapshot с тем, что было
        merged_pairs = dict(current_pairs)
        merged_pairs.update(pairs_snapshot)

        write_rates_snapshot(self.config.RATES_FILE_PATH, merged_pairs, last_refresh=now_z)

        logger.info("Update finished. Total updated pairs: %d", len(pairs_snapshot))
        return {
            "updated": len(pairs_snapshot),
            "last_refresh": now_z,
            "errors": errors,
        }
