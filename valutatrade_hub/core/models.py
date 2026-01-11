from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class ValidationError(ValueError):
    """Ошибка валидации входных данных."""


class InsufficientFundsError(ValueError):
    """Недостаточно средств для операции."""


def _hash_password(password: str, salt: str) -> str:
    raw = (password + salt).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_currency_code(code: str) -> str:
    if not isinstance(code, str) or not code.strip():
        raise ValidationError("Код валюты должен быть непустой строкой")
    code = code.strip().upper()
    return code


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        self._user_id = user_id
        self.username = username  # через сеттер
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> dict[str, Any]:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False
        return _hash_password(password, self._salt) == self._hashed_password

    def change_password(self, new_password: str) -> None:
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValidationError("Пароль должен быть не короче 4 символов")
        self._hashed_password = _hash_password(new_password, self._salt)

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @staticmethod
    def create_new(user_id: int, username: str, password: str) -> "User":
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError("Пароль должен быть не короче 4 символов")
        salt = secrets.token_hex(8)
        hashed = _hash_password(password, salt)
        return User(
            user_id=user_id,
            username=username,
            hashed_password=hashed,
            salt=salt,
            registration_date=datetime.now(),
        )


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        self.currency_code = _validate_currency_code(currency_code)
        self.balance = balance  # через сеттер

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if not isinstance(value, (int, float)):
            raise ValidationError("Баланс должен быть числом")
        value = float(value)
        if value < 0:
            raise ValidationError("Баланс не может быть отрицательным")
        self._balance = value

    def deposit(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or float(amount) <= 0:
            raise ValidationError("'amount' должен быть положительным числом")
        self._balance += float(amount)

    def withdraw(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or float(amount) <= 0:
            raise ValidationError("'amount' должен быть положительным числом")
        amount = float(amount)
        if amount > self._balance:
            raise InsufficientFundsError(
                f"Недостаточно средств: доступно {self._balance:.4f} {self.currency_code}, требуется {amount:.4f} {self.currency_code}"
            )
        self._balance -= amount

    def get_balance_info(self) -> str:
        return f"{self.currency_code}: {self._balance:.4f}"


class Portfolio:
    def __init__(self, user_id: int, wallets: dict[str, Wallet] | None = None) -> None:
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = wallets or {}

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        # вернуть копию, чтобы снаружи не могли подменить словарь
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        code = _validate_currency_code(currency_code)
        if code in self._wallets:
            raise ValidationError(f"Кошелёк '{code}' уже существует")
        wallet = Wallet(currency_code=code, balance=0.0)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        code = _validate_currency_code(currency_code)
        return self._wallets.get(code)

    def get_total_value(self, base_currency: str = "USD") -> float:
        base = _validate_currency_code(base_currency)

        # Заглушка курсов: сколько BASE за 1 единицу валюты
        # Например, BTC->USD = 59337.21 означает: 1 BTC = 59337.21 USD
        exchange_rates: dict[tuple[str, str], float] = {
            ("USD", "USD"): 1.0,
            ("EUR", "USD"): 1.0786,
            ("BTC", "USD"): 59337.21,
            ("ETH", "USD"): 3720.0,
            ("RUB", "USD"): 0.01016,
        }

        total = 0.0
        for code, wallet in self._wallets.items():
            if (code, base) not in exchange_rates:
                raise ValidationError(f"Неизвестная базовая валюта '{base}' или нет курса для '{code}→{base}'")
            rate = exchange_rates[(code, base)]
            total += wallet.balance * rate
        return total
