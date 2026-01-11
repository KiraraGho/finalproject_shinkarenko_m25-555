from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from valutatrade_hub.core.models import (
    InsufficientFundsError,
    User,
    ValidationError,
)
from valutatrade_hub.core.utils import (
    find_user_by_username,
    get_or_create_portfolio_record,
    load_portfolios,
    load_rates,
    load_users,
    next_user_id,
    now_iso,
    parse_iso,
    save_portfolios,
    save_rates,
    save_users,
)

# Заглушка курсов: сколько USD за 1 единицу валюты
EXCHANGE_RATES_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "RUB": 0.01016,
}


def _validate_username(username: str) -> str:
    if not isinstance(username, str) or not username.strip():
        raise ValidationError("Имя пользователя не может быть пустым")
    return username.strip()


def _validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 4:
        raise ValidationError("Пароль должен быть не короче 4 символов")
    return password


def _validate_currency(code: str) -> str:
    if not isinstance(code, str) or not code.strip():
        raise ValidationError("Код валюты должен быть непустой строкой")
    return code.strip().upper()


def _validate_amount(amount: Any) -> float:
    try:
        value = float(amount)
    except Exception as e:
        raise ValidationError("'amount' должен быть положительным числом") from e
    if value <= 0:
        raise ValidationError("'amount' должен быть положительным числом")
    return value


def register_user(username: str, password: str) -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)

    users = load_users()
    if find_user_by_username(users, username) is not None:
        raise ValidationError(f"Имя пользователя '{username}' уже занято")

    user_id = next_user_id(users)
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
    save_users(users)

    portfolios = load_portfolios()
    get_or_create_portfolio_record(portfolios, user_id=user_id)  # пустой портфель
    save_portfolios(portfolios)

    return {"user_id": user_id, "username": username}


def login_user(username: str, password: str) -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)

    users = load_users()
    record = find_user_by_username(users, username)
    if record is None:
        raise ValidationError(f"Пользователь '{username}' не найден")

    reg_dt = parse_iso(str(record.get("registration_date", ""))) or datetime.now()
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


def get_rate(from_currency: str, to_currency: str, max_age_seconds: int = 300) -> dict[str, Any]:
    """Возвращает курс from->to, используя rates.json как кеш (свежесть ~5 минут)."""
    from_c = _validate_currency(from_currency)
    to_c = _validate_currency(to_currency)
    pair = f"{from_c}_{to_c}"

    rates_cache = load_rates()

    # 1) Если есть свежий кеш — отдаём
    if pair in rates_cache and isinstance(rates_cache[pair], dict):
        updated_at = parse_iso(str(rates_cache[pair].get("updated_at", "")))
        if updated_at and datetime.now() - updated_at <= timedelta(seconds=max_age_seconds):
            rate_val = float(rates_cache[pair]["rate"])
            return {"pair": pair, "rate": rate_val, "updated_at": updated_at.isoformat()}

    # 2) Иначе — заглушка (как будто Parser Service)
    if from_c not in EXCHANGE_RATES_USD or to_c not in EXCHANGE_RATES_USD:
        raise ValidationError(f"Курс {from_c}→{to_c} недоступен. Повторите попытку позже.")

    # через USD: from->USD и to->USD
    # 1 FROM = (USD_per_FROM) USD
    # 1 TO   = (USD_per_TO) USD
    # FROM->TO = USD_per_FROM / USD_per_TO
    rate_val = EXCHANGE_RATES_USD[from_c] / EXCHANGE_RATES_USD[to_c]

    rates_cache[pair] = {"rate": rate_val, "updated_at": now_iso()}
    rates_cache["source"] = "StubRates"
    rates_cache["last_refresh"] = now_iso()
    save_rates(rates_cache)

    return {"pair": pair, "rate": rate_val, "updated_at": rates_cache[pair]["updated_at"]}


def show_portfolio(user_id: int, base_currency: str = "USD") -> dict[str, Any]:
    base = _validate_currency(base_currency)

    portfolios = load_portfolios()
    p = get_or_create_portfolio_record(portfolios, user_id=user_id)

    wallets: dict[str, dict[str, Any]] = p.get("wallets", {})
    if not wallets:
        return {"base": base, "wallets": [], "total": 0.0}

    items: list[dict[str, Any]] = []
    total = 0.0

    for code, w in wallets.items():
        code_u = _validate_currency(code)
        balance = float(w.get("balance", 0.0))

        rate_info = get_rate(code_u, base)
        value_in_base = balance * float(rate_info["rate"])
        total += value_in_base

        items.append(
            {
                "currency": code_u,
                "balance": balance,
                "rate": float(rate_info["rate"]),
                "value_in_base": value_in_base,
            }
        )

    return {"base": base, "wallets": items, "total": total}


def buy_currency(user_id: int, currency: str, amount: Any, base_currency: str = "USD") -> dict[str, Any]:
    cur = _validate_currency(currency)
    base = _validate_currency(base_currency)
    qty = _validate_amount(amount)

    portfolios = load_portfolios()
    p = get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p["wallets"]

    # авто-создание кошельков
    if cur not in wallets:
        wallets[cur] = {"balance": 0.0}
    if base not in wallets:
        wallets[base] = {"balance": 0.0}

    # стоимость покупки в base (USD)
    rate_info = get_rate(cur, base)
    cost = qty * float(rate_info["rate"])

    base_balance = float(wallets[base].get("balance", 0.0))
    if cost > base_balance:
        raise InsufficientFundsError(
            f"Недостаточно средств: доступно {base_balance:.2f} {base}, требуется {cost:.2f} {base}"
        )

    before_cur = float(wallets[cur].get("balance", 0.0))
    before_base = base_balance

    wallets[base]["balance"] = before_base - cost
    wallets[cur]["balance"] = before_cur + qty

    save_portfolios(portfolios)

    return {
        "currency": cur,
        "base": base,
        "amount": qty,
        "rate": float(rate_info["rate"]),
        "cost": cost,
        "before": {cur: before_cur, base: before_base},
        "after": {cur: float(wallets[cur]["balance"]), base: float(wallets[base]["balance"])},
    }


def sell_currency(user_id: int, currency: str, amount: Any, base_currency: str = "USD") -> dict[str, Any]:
    cur = _validate_currency(currency)
    base = _validate_currency(base_currency)
    qty = _validate_amount(amount)

    portfolios = load_portfolios()
    p = get_or_create_portfolio_record(portfolios, user_id=user_id)
    wallets: dict[str, dict[str, Any]] = p["wallets"]

    if cur not in wallets:
        raise ValidationError(
            f"У вас нет кошелька '{cur}'. Добавьте валюту: она создаётся автоматически при первой покупке."
        )
    if base not in wallets:
        wallets[base] = {"balance": 0.0}

    cur_balance = float(wallets[cur].get("balance", 0.0))
    if qty > cur_balance:
        raise InsufficientFundsError(
            f"Недостаточно средств: доступно {cur_balance:.4f} {cur}, требуется {qty:.4f} {cur}"
        )

    rate_info = get_rate(cur, base)
    proceeds = qty * float(rate_info["rate"])

    before_cur = cur_balance
    before_base = float(wallets[base].get("balance", 0.0))

    wallets[cur]["balance"] = before_cur - qty
    wallets[base]["balance"] = before_base + proceeds

    save_portfolios(portfolios)

    return {
        "currency": cur,
        "base": base,
        "amount": qty,
        "rate": float(rate_info["rate"]),
        "proceeds": proceeds,
        "before": {cur: before_cur, base: before_base},
        "after": {cur: float(wallets[cur]["balance"]), base: float(wallets[base]["balance"])},
    }
