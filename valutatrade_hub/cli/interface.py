from __future__ import annotations

import shlex
from typing import Any

from prettytable import PrettyTable

from valutatrade_hub.core.usecases import (
    buy_currency,
    deposit_funds,
    get_rate,
    login_user,
    register_user,
    sell_currency,
    show_portfolio,
)
from valutatrade_hub.core.utils import ensure_storage
from valutatrade_hub.core.exceptions import (
    InsufficientFundsError,
    CurrencyNotFoundError,
    ApiRequestError,
    ValidationError,
)
from valutatrade_hub.core.currencies import supported_codes
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.api_clients import CoinGeckoClient, ExchangeRateApiClient
from valutatrade_hub.parser_service.updater import RatesUpdater
from valutatrade_hub.parser_service.storage import read_json


def _parse_flags(tokens: list[str]) -> dict[str, str]:
    """
    Простой парсер флагов формата:
    --username alice --password 1234
    """
    args: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:]
            if i + 1 >= len(tokens):
                raise ValidationError(f"Для аргумента --{key} требуется значение")
            args[key] = tokens[i + 1]
            i += 2
        else:
            i += 1
    return args


def _print_help() -> None:
    print(
        "\nКоманды:\n"
        "  register --username <str> --password <str>\n"
        "  login --username <str> --password <str>\n"
        "  show-portfolio [--base <str>]\n"
        "  buy --currency <str> --amount <float>\n"
        "  sell --currency <str> --amount <float>\n"
        "  get-rate --from <str> --to <str>\n"
        "  deposit --currency <str> --amount <float>\n"
        "  update-rates [--source coingecko|exchangerate]\n"
        "  show-rates [--currency <CODE>] [--top <N>] [--base <CODE>]\n"
        "  help\n"
        "  exit\n"
    )


def main() -> None:
    ensure_storage()
    print("Приложение «Валютный кошелёк» запущено.")
    print("Введите help для списка команд.\n")

    session: dict[str, Any] = {"user_id": None, "username": None}

    while True:
        try:
            line = input("wallet> ").strip()
            if not line:
                continue

            tokens = shlex.split(line)
            cmd = tokens[0]
            args = _parse_flags(tokens[1:])

            if cmd in {"exit", "quit"}:
                print("Выход.")
                return

            if cmd == "help":
                _print_help()
                continue

            if cmd == "register":
                username = args.get("username", "")
                password = args.get("password", "")
                res = register_user(username=username, password=password)
                print(
                    f"Пользователь '{res['username']}' зарегистрирован (id={res['user_id']}). "
                    f"Войдите: login --username {res['username']} --password ****"
                )
                continue

            if cmd == "login":
                username = args.get("username", "")
                password = args.get("password", "")
                res = login_user(username=username, password=password)
                session["user_id"] = res["user_id"]
                session["username"] = res["username"]
                print(f"Вы вошли как '{res['username']}'")
                continue

            # команды ниже — только для залогиненного
            if cmd in {"show-portfolio", "deposit", "buy", "sell"}:
                if session["user_id"] is None:
                    raise ValidationError("Сначала выполните login")

            if cmd == "show-portfolio":
                base = args.get("base", "USD")
                res = show_portfolio(user_id=int(session["user_id"]), base_currency=base)

                table = PrettyTable()
                table.field_names = ["Валюта", "Баланс", f"Стоимость в {res['base']}"]

                for w in res["wallets"]:
                    value = w.get("value_in_base")
                    value_str = f"{float(value):.2f}" if value is not None else "н/д"
                    table.add_row(
                        [
                            w["currency"],
                            f"{float(w['balance']):.4f}",
                            value_str,
                        ]
                    )

                print(f"Портфель пользователя '{session['username']}' (база: {res['base']}):")
                if res["wallets"]:
                    print(table)
                    print(f"ИТОГО: {float(res['total']):,.2f} {res['base']}")
                    if not res.get("rates_ok", True) and res.get("rates_note"):
                        print(res["rates_note"])
                else:
                    print("Портфель пуст.")
                continue


            if cmd == "deposit":
                currency = args.get("currency", "")
                amount = args.get("amount", "")
                res = deposit_funds(user_id=int(session["user_id"]), currency=currency, amount=amount)
                print(
                    f"Пополнение выполнено: +{res['amount']:.2f} {res['currency']}\n"
                    f"- {res['currency']}: было {res['before']:.2f} → стало {res['after']:.2f}"
                )
                continue

            if cmd == "buy":
                currency = args.get("currency", "")
                amount = args.get("amount", "")
                res = buy_currency(user_id=int(session["user_id"]), currency=currency, amount=amount)
                print(
                    f"Покупка выполнена: {res['amount']:.4f} {res['currency']} "
                    f"по курсу {res['rate']:.2f} {res['base']}/{res['currency']}"
                )
                print("Изменения в портфеле:")
                print(
                    f"- {res['currency']}: было {res['before'][res['currency']]:.4f} → стало {res['after'][res['currency']]:.4f}"
                )
                print(
                    f"- {res['base']}: было {res['before'][res['base']]:.2f} → стало {res['after'][res['base']]:.2f}"
                )
                print(f"Стоимость покупки: {res['cost']:.2f} {res['base']}")
                continue

            if cmd == "sell":
                currency = args.get("currency", "")
                amount = args.get("amount", "")
                res = sell_currency(user_id=int(session["user_id"]), currency=currency, amount=amount)
                print(
                    f"Продажа выполнена: {res['amount']:.4f} {res['currency']} "
                    f"по курсу {res['rate']:.2f} {res['base']}/{res['currency']}"
                )
                print("Изменения в портфеле:")
                print(
                    f"- {res['currency']}: было {res['before'][res['currency']]:.4f} → стало {res['after'][res['currency']]:.4f}"
                )
                print(
                    f"- {res['base']}: было {res['before'][res['base']]:.2f} → стало {res['after'][res['base']]:.2f}"
                )
                print(f"Выручка: {res['proceeds']:.2f} {res['base']}")
                continue

            if cmd == "get-rate":
                from_c = args.get("from", "")
                to_c = args.get("to", "")

                r = get_rate(from_currency=from_c, to_currency=to_c)
                print(
                    f"Курс {from_c.upper()}→{to_c.upper()}: {float(r['rate']):.8f} "
                    f"(обновлено: {r['updated_at']}, источник: {r.get('source', '-')})"
                )

                # Обратный курс:
                # Пытаемся взять из кеша напрямую, а если пары нет — считаем как 1 / прямой курс
                try:
                    inv = get_rate(from_currency=to_c, to_currency=from_c)
                    inv_rate = float(inv["rate"])
                except ApiRequestError:
                    inv_rate = 1.0 / float(r["rate"]) if float(r["rate"]) != 0 else 0.0

                print(f"Обратный курс {to_c.upper()}→{from_c.upper()}: {inv_rate:.8f}")
                continue


            if cmd == "update-rates":
                src = args.get("source")  # coingecko / exchangerate
                cfg = ParserConfig()
                updater = RatesUpdater(
                    config=cfg,
                    clients=[
                        CoinGeckoClient(cfg),
                        ExchangeRateApiClient(cfg),
                    ],
                )
                res = updater.run_update(source=src)
                if res["errors"]:
                    print("Обновление завершено с ошибками. Проверьте логи.")
                    for e in res["errors"]:
                        print("-", e)
                print(f"Update successful. Total rates updated: {res['updated']}. Last refresh: {res['last_refresh']}")
                continue

            if cmd == "show-rates":
                currency = args.get("currency")
                top = args.get("top")
                base = args.get("base")  # опционально, сейчас просто фильтр по *_BASE

                cache = read_json("data/rates.json", default={})
                pairs = cache.get("pairs") if isinstance(cache, dict) else None
                if not isinstance(pairs, dict) or not pairs:
                    print("Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные.")
                    continue

                items = []
                for pair, info in pairs.items():
                    if not isinstance(info, dict):
                        continue
                    if base and not pair.endswith(f"_{base.strip().upper()}"):
                        continue
                    if currency:
                        c = currency.strip().upper()
                        if not (pair.startswith(f"{c}_") or pair.endswith(f"_{c}")):
                            continue
                    items.append((pair, float(info.get("rate", 0.0)), str(info.get("updated_at", "")), str(info.get("source", ""))))

                if not items:
                    if currency:
                        print(f"Курс для '{currency.strip().upper()}' не найден в кеше.")
                    else:
                        print("Нет данных по выбранному фильтру.")
                    continue

                if top:
                    try:
                        n = int(top)
                        items.sort(key=lambda x: x[1], reverse=True)
                        items = items[:n]
                    except Exception:
                        print("--top должен быть целым числом")
                        continue
                else:
                    items.sort(key=lambda x: x[0])

                print(f"Rates from cache (updated at {cache.get('last_refresh', '-')})")
                for pair, rate, updated_at, source in items:
                    print(f"- {pair}: {rate} (updated_at={updated_at}, source={source})")
                continue

            print("Неизвестная команда. Введите help.")

        except InsufficientFundsError as e:
            print(str(e))

        except CurrencyNotFoundError as e:
            print(str(e))
            print("Подсказка: используйте команду get-rate --from <CUR> --to <CUR>")
            print("Поддерживаемые валюты:", ", ".join(supported_codes()))

        except ApiRequestError as e:
            print(str(e))
            print("Попробуйте повторить позже или проверьте подключение к сети.")

        except ValidationError as e:
            print(str(e))

        except KeyboardInterrupt:
            print("\nВыход.")
            return

        except Exception as e:
            print(f"Непредвиденная ошибка: {e}")

