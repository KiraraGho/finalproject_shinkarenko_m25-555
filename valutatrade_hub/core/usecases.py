from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    InsufficientFundsError,
    ValidationError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


def _validate_username(username: str) -> str:
    if not isinstance(username, str) or not username.strip():
        raise ValidationError("Имя пользователя не может быть пустым")
    return username.strip()


def _validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 4:
        raise ValidationError("Пароль должен быть не короче 4 символов")
    return password


def _validate_amount(amount: Any) -> float:
    try:
        value = float(amount)
    except Exception as e:
        raise ValidationError("'amount' должен быть положительным числом") from e
    if value <= 0:
        raise ValidationError("'amount' должен быть положительным числом")
    return value


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parse_iso(dt: str) -> datetime | None:
    try:
        return datetime.fromisoformat(dt)
    except Exception:
        return None


def _next_user_id(users: list[dict[str, Any]]) -> int:
    max_id = 0
    for u in users:
        try:
            max_id = max(max_id, int(u.get("user_id", 0)))
        except Exception:
            continue
    return max_id + 1


def _find_user_by_username(users: list[dict[str, Any]], username: str) -> dict[str, Any] | None:
    for u in users:
        if u.get("username") == username:
            return u
    return None


def _get_or_create_portfolio_record(portfolios: list[dict[str, Any]], user_id: int) -> dict[str, Any]:
    for p in portfolios:
        if int(p.get("user_id", -1)) == int(user_id):
            if "wallets" not in p or not isinstance(p["wallets"], dict):
                p["wallets"] = {}
            return p
    new_p = {"user_id": int(user_id), "wallets": {}}
    portfolios.append(new_p)
    return new_p


def _ensure_wallet(wallets: dict[str, dict[str, Any]], code: str) -> None:
    if code not in wallets:
        wallets[code] = {"balance": 0.0}
    if "balance" not in wallets[code]:
        wallets[code]["balance"] = 0.0


def _get_balance(wallets: dict[str, dict[str, Any]], code: str) -> float:
    _ensure_wallet(wallets, code)
    try:
        return float(wallets[code].get("balance", 0.0))
    except Exception:
        return 0.0


def _set_balance(wallets: dict[str, dict[str, Any]], code: str, value: float) -> None:
    if value < 0:
        value = 0.0
    _ensure_wallet(wallets, code)
    wallets[code]["balance"] = float(value)


@log_action("REGISTER", verbose=False)
def register_user(username: str, password: str) -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)

    db = DatabaseManager()
    users = db.read_users()

    if _find_user_by_username(users, username) is not None:
        raise ValidationError(f"Имя пользователя '{username}' уже занято")

    user_id = _next_user_id(users)
    user = User.create_new(user_id=user_id, username=username, password=password)

    users.append(
        {
            "user_id": user.user_id,
            "username": user.username,
            "hashed_password": user.hashed_password,
            "salt": user.salt,
            "registration_date": user.registration_date.isoformat(),
        }
    )
    db.write_users(users)

    portfolios = db.read_portfolios()
    _get_or_create_portfolio_record(portfolios, user_id=user_id)
    db.write_portfolios(portfolios)

    return {"user_id": user_id, "username": username}


@log_action("LOGIN", verbose=False)
def login_user(username: str, password: str) -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)

    db = DatabaseManager()
    users = db.read_users()

    record = _find_user_by_username(users, username)
    if record is None:
        raise ValidationError(f"Пользователь '{username}' не найден")

    reg_dt = _parse_iso(str(record.get("registration_date", ""))) or datetime.now()
    user = User(
        user_id=int(record["user_id"]),
        username=str(record["username"]),
        hashed_password=str(record["hashed_password"]),
        salt=str(record["salt"]),
        registration_date=reg_dt,
    )

    if not user.verify_password(password):
        raise ValidationError("Неверный пароль")

    return {"user_id": user.user_id, "username": user.username}


@log_action("GET_RATE", verbose=False)
def get_rate(from_currency: str, to_currency: str) -> dict[str, Any]:
    """
    Валидируем валюты через get_currency()
    Читаем rates.json в формате {"pairs": {...}, "last_refresh": "..."}
    Проверяем TTL из SettingsLoader
    Если данных нет/устарели -> ApiRequestError с подсказкой выполнить update-rates
    """
    from_cur = get_currency(from_currency)
    to_cur = get_currency(to_currency)

    from_code = from_cur.code
    to_code = to_cur.code
    pair = f"{from_code}_{to_code}"

    settings = SettingsLoader()
    ttl = int(settings.get("RATES_TTL_SECONDS", 300))

    db = DatabaseManager()
    cache = db.read_rates()

    pairs = cache.get("pairs") if isinstance(cache, dict) else None
    if not isinstance(pairs, dict) or not pairs:
        raise ApiRequestError("Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные.")

    info = pairs.get(pair)
    if not isinstance(info, dict):
        raise ApiRequestError(f"Курс {pair} не найден в кеше. Выполните 'update-rates'.")

    updated_at = _parse_iso(str(info.get("updated_at", "")))
    if not updated_at:
        raise ApiRequestError(f"Курс {pair} в кеше повреждён. Выполните 'update-rates'.")

    from datetime import timezone
    
    now = datetime.now(timezone.utc) if updated_at.tzinfo is not None else datetime.now()
    age = now - updated_at

    if age > timedelta(seconds=ttl):
        raise ApiRequestError(
            f"Данные для {pair} устарели (обновлено: {updated_at.isoformat()}). Выполните 'update-rates'."
        )

    try:
        rate_val = float(info["rate"])
    except Exception as e:
        raise ApiRequestError(f"Курс {pair} в кеше имеет некорректный формат. Выполните 'update-rates'.") from e

    source = str(info.get("source", "unknown"))
    return {"pair": pair, "rate": rate_val, "updated_at": updated_at.isoformat(), "source": source}


def show_portfolio(user_id: int, base_currency: str | None = None) -> dict[str, Any]:
    """
    Устойчивый вывод портфеля:
    - если курс недоступен/устарел -> value_in_base=None и отмечаем, что есть проблемы с курсами
    - в ответ добавляем flags: rates_ok (bool) и rates_note (str|None)
    """
    settings = SettingsLoader()
    base = (base_currency or str(settings.get("DEFAULT_BASE", "USD"))).strip().upper()

    # валидируем базовую валюту через реестр
    get_currency(base)

    db = DatabaseManager()
    portfolios = db.read_portfolios()
    p = _get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p.get("wallets", {})

    if not wallets:
        return {"base": base, "wallets": [], "total": 0.0, "rates_ok": True, "rates_note": None}

    items: list[dict[str, Any]] = []
    total = 0.0

    rates_ok = True
    rates_note: str | None = None

    for code in sorted(wallets.keys()):
        # валидируем код через реестр валют
        cur = get_currency(code)
        balance = _get_balance(wallets, cur.code)

        # базовая валюта: курс 1.0, не обращаемся к кешу
        if cur.code == base:
            value_in_base = balance
            rate_val = 1.0
            updated_at = None
            source = "local"
            total += value_in_base

            items.append(
                {
                    "currency": cur.code,
                    "balance": balance,
                    "rate": rate_val,
                    "value_in_base": value_in_base,
                    "updated_at": updated_at,
                    "source": source,
                }
            )
            continue

        value_in_base: float | None = None
        rate_val: float | None = None
        updated_at: str | None = None
        source: str | None = None

        try:
            rate_info = get_rate(cur.code, base)
            rate_val = float(rate_info["rate"])
            updated_at = str(rate_info.get("updated_at"))
            source = str(rate_info.get("source", "unknown"))
            value_in_base = balance * rate_val
            total += value_in_base
        except ApiRequestError:
            # курс недоступен/устарел — не падаем
            rates_ok = False
            rates_note = "Курсы устарели/недоступны, выполните update-rates."
            value_in_base = None

        items.append(
            {
                "currency": cur.code,
                "balance": balance,
                "rate": rate_val,
                "value_in_base": value_in_base,
                "updated_at": updated_at,
                "source": source,
            }
        )

    # если портфель только что создавался — сохраняем
    db.write_portfolios(portfolios)

    return {
        "base": base,
        "wallets": items,
        "total": total,
        "rates_ok": rates_ok,
        "rates_note": rates_note,
    }


def deposit_funds(user_id: int, currency: str, amount: Any) -> dict[str, Any]:
    """
    Пополнение баланса. Валюта валидируется через get_currency()
    """
    cur = get_currency(currency)
    qty = _validate_amount(amount)

    db = DatabaseManager()
    portfolios = db.read_portfolios()
    p = _get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p["wallets"]

    before = _get_balance(wallets, cur.code)
    after = before + qty
    _set_balance(wallets, cur.code, after)

    db.write_portfolios(portfolios)

    return {"currency": cur.code, "amount": qty, "before": before, "after": after}


@log_action("BUY", verbose=True)
def buy_currency(user_id: int, currency: str, amount: Any) -> dict[str, Any]:
    """
    Покупка валюты за базовую валюту (по умолчанию DEFAULT_BASE).
    Списываем base, начисляем currency.
    """
    cur = get_currency(currency)
    qty = _validate_amount(amount)

    settings = SettingsLoader()
    base = str(settings.get("DEFAULT_BASE", "USD")).strip().upper()
    base_cur = get_currency(base)  # валидируем

    db = DatabaseManager()
    portfolios = db.read_portfolios()
    p = _get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p["wallets"]

    rate_info = get_rate(cur.code, base_cur.code)
    rate = float(rate_info["rate"])
    cost = qty * rate

    base_before = _get_balance(wallets, base_cur.code)
    if cost > base_before:
        raise InsufficientFundsError(available=base_before, required=cost, code=base_cur.code)

    cur_before = _get_balance(wallets, cur.code)

    _set_balance(wallets, base_cur.code, base_before - cost)
    _set_balance(wallets, cur.code, cur_before + qty)

    db.write_portfolios(portfolios)

    return {
        "currency": cur.code,
        "base": base_cur.code,
        "amount": qty,
        "rate": rate,
        "cost": cost,
        "updated_at": rate_info["updated_at"],
        "before": {cur.code: cur_before, base_cur.code: base_before},
        "after": {cur.code: _get_balance(wallets, cur.code), base_cur.code: _get_balance(wallets, base_cur.code)},
    }


@log_action("SELL", verbose=True)
def sell_currency(user_id: int, currency: str, amount: Any) -> dict[str, Any]:
    """
    Продажа валюты за базовую валюту DEFAULT_BASE.
    Списываем currency, начисляем base.
    """
    cur = get_currency(currency)
    qty = _validate_amount(amount)

    settings = SettingsLoader()
    base = str(settings.get("DEFAULT_BASE", "USD")).strip().upper()
    base_cur = get_currency(base)

    db = DatabaseManager()
    portfolios = db.read_portfolios()
    p = _get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p["wallets"]

    cur_before = _get_balance(wallets, cur.code)
    if qty > cur_before:
        raise InsufficientFundsError(available=cur_before, required=qty, code=cur.code)

    rate_info = get_rate(cur.code, base_cur.code)
    rate = float(rate_info["rate"])
    proceeds = qty * rate

    base_before = _get_balance(wallets, base_cur.code)

    _set_balance(wallets, cur.code, cur_before - qty)
    _set_balance(wallets, base_cur.code, base_before + proceeds)

    db.write_portfolios(portfolios)

    return {
        "currency": cur.code,
        "base": base_cur.code,
        "amount": qty,
        "rate": rate,
        "proceeds": proceeds,
        "updated_at": rate_info["updated_at"],
        "before": {cur.code: cur_before, base_cur.code: base_before},
        "after": {cur.code: _get_balance(wallets, cur.code), base_cur.code: _get_balance(wallets, base_cur.code)},
    }
