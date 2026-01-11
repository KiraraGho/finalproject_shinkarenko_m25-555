# ValutaTrade Hub

**ValutaTrade Hub** — консольное (CLI) приложение на Python для симуляции торговли фиатными и криптовалютами.  
Проект состоит из двух логических частей:

- **Core Service** — управление пользователями, кошельками, портфелями и торговыми операциями.
- **Parser Service** — отдельный сервис для получения актуальных курсов валют из внешних API и сохранения их в локальный кеш.

Проект реализован как полноценный Python-пакет с использованием Poetry.

---

## Автор

Проект выполнен студенткой группы **М25-555**  
**Шинкаренко Викторией**


---

## Возможности

- регистрация и авторизация пользователей;
- управление виртуальным портфелем валют;
- покупка и продажа валют (buy / sell);
- просмотр портфеля с пересчётом в базовую валюту;
- получение текущего курса валют;
- обновление курсов через Parser Service;
- локальный кеш курсов с TTL;
- история курсов в `exchange_rates.json`.

---

## Стек технологий

- **Python 3.12**
- **Poetry** — управление зависимостями и сборка пакета
- **Git** — контроль версий
- **Ruff** — статический анализ и форматирование
- **PrettyTable** — табличный вывод в CLI
- **Requests** — HTTP-запросы к внешним API

---

## Установка

### 1. Клонировать репозиторий
```bash
git clone https://github.com/KiraraGho/finalproject_shinkarenko_m25-555.git
cd finalproject_shinkarenko_m25-555
```
Установить зависимости
```bash
make install
```
или
```bash
poetry install
```

---

## Переменные окружения

Для работы Parser Service требуется ключ **ExchangeRate-API.**

**Получение ключа**
- Зарегистрироваться на https://www.exchangerate-api.com/
- Получить персональный API-ключ

**Установка ключа (Linux / WSL)**
```bash
export EXCHANGERATE_API_KEY="ВАШ_КЛЮЧ"
```

---

## Запуск приложения
```bash
make project
```
или
```bash
poetry run project
```

После запуска откроется интерактивный CLI.

---

## Команды CLI
**Пользователи**
```text
register --username <str> --password <str>
    Регистрация нового пользователя.
login --username <str> --password <str>
    Вход в систему под существующим пользователем.
```

**Портфель и операции**
```text
deposit --currency <CODE> --amount <float>
    Пополнение кошелька указанной валюты.
buy --currency <CODE> --amount <float>
    Покупка валюты по текущему курсу.
sell --currency <CODE> --amount <float>
    Продажа валюты по текущему курсу.
show-portfolio [--base <CODE>]
    Просмотр портфеля и общей стоимости (по умолчанию в USD).
```

**Курсы валют**
```text
update-rates [--source coingecko|exchangerate]
    Обновить курсы валют через Parser Service.
show-rates [--currency <CODE>] [--top <N>] [--base <CODE>]
    Показать курсы валют из локального кеша.
get-rate --from <CODE> --to <CODE>
    Получить курс одной валюты к другой.
```

**Служебные**
```text
help
    Показать это сообщение.
exit
    Выход из приложения.
```

---

## Кеш курсов и TTL
- Актуальные курсы хранятся в data/rates.json
- История обновлений — в data/exchange_rates.json
- Срок актуальности курсов (TTL) задаётся в pyproject.toml:
```toml
[tool.valutatrade]
RATES_TTL_SECONDS = 300
```
Если курсы устарели, Core Service сообщает пользователю и предлагает выполнить:
update-rates

---

## Логирование
- Логи операций пишутся в logs/actions.log
- Используется декоратор @log_action
- Логируются операции buy / sell (и другие ключевые действия)

---

## Демонстраниция Asciinema
**Запись работы приложения:**
https://asciinema.org/a/AcJdYiYlUzJZyszU