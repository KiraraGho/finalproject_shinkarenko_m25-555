from __future__ import annotations

import shlex
from typing import Any

from prettytable import PrettyTable

from valutatrade_hub.core.models import InsufficientFundsError, ValidationError
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
                    table.add_row(
                        [
                            w["currency"],
                            f"{float(w['balance']):.4f}",
                            f"{float(w['value_in_base']):.2f}",
                        ]
                    )

                print(f"Портфель пользователя '{session['username']}' (база: {res['base']}):")
                if res["wallets"]:
                    print(table)
                    print(f"ИТОГО: {float(res['total']):,.2f} {res['base']}")
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
                res = buy_currency(user_id=int(session["user_id"]), currency=currency, amount=amount, base_currency="USD")
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
                res = sell_currency(user_id=int(session["user_id"]), currency=currency, amount=amount, base_currency="USD")
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
                inv = get_rate(from_currency=to_c, to_currency=from_c)
                print(f"Курс {from_c.upper()}→{to_c.upper()}: {float(r['rate']):.8f} (обновлено: {r['updated_at']})")
                print(f"Обратный курс {to_c.upper()}→{from_c.upper()}: {float(inv['rate']):.8f}")
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

