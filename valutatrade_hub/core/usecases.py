from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValidationError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


# Заглушка "внешнего API" (Parser Service) — сколько USD за 1 единицу валюты.
USD_PER_UNIT: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.00,
}


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


def _stub_fetch_rate(from_code: str, to_code: str) -> float:
    """
    Заглушка внешнего API/Parser Service
    Если валюты нет в USD_PER_UNIT — считаем это проблемой источника
    """
    if from_code not in USD_PER_UNIT or to_code not in USD_PER_UNIT:
        raise ApiRequestError(f"нет данных у источника для пары {from_code}→{to_code}")
    return USD_PER_UNIT[from_code] / USD_PER_UNIT[to_code]


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
    Валидируем коды через get_currency() -> CurrencyNotFoundError
    Берём TTL из SettingsLoader
    Пытаемся взять из rates.json если свежее TTL
    Иначе обновляем через заглушку API, иначе ApiRequestError
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

    # свежий кеш
    if pair in cache and isinstance(cache[pair], dict):
        updated_at = _parse_iso(str(cache[pair].get("updated_at", "")))
        if updated_at and datetime.now() - updated_at <= timedelta(seconds=ttl):
            try:
                rate_val = float(cache[pair]["rate"])
                return {"pair": pair, "rate": rate_val, "updated_at": updated_at.isoformat()}
            except Exception:
                pass

    # запрос к API
    rate_val = _stub_fetch_rate(from_code, to_code)

    cache[pair] = {"rate": rate_val, "updated_at": _now_iso()}
    cache["source"] = "StubRates"
    cache["last_refresh"] = _now_iso()
    db.write_rates(cache)

    return {"pair": pair, "rate": rate_val, "updated_at": cache[pair]["updated_at"]}


def show_portfolio(user_id: int, base_currency: str | None = None) -> dict[str, Any]:
    """
    Показываем портфель + оценку в base валюте.
    base по умолчанию берём из SettingsLoader.DEFAULT_BASE
    """
    settings = SettingsLoader()
    base = (base_currency or str(settings.get("DEFAULT_BASE", "USD"))).strip().upper()

    # валидируем base через реестр валют
    get_currency(base)

    db = DatabaseManager()
    portfolios = db.read_portfolios()
    p = _get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p.get("wallets", {})

    if not wallets:
        return {"base": base, "wallets": [], "total": 0.0}

    items: list[dict[str, Any]] = []
    total = 0.0

    for code in sorted(wallets.keys()):
        # валидируем код через реестр
        cur = get_currency(code)
        balance = _get_balance(wallets, cur.code)

        rate_info = get_rate(cur.code, base)
        value_in_base = balance * float(rate_info["rate"])
        total += value_in_base

        items.append(
            {
                "currency": cur.code,
                "balance": balance,
                "rate": float(rate_info["rate"]),
                "value_in_base": value_in_base,
            }
        )

    # портфели не меняли — но на всякий случай (если создали запись)
    db.write_portfolios(portfolios)

    return {"base": base, "wallets": items, "total": total}


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
