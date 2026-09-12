# Postupashki Marketing Measurement

Репозиторий содержит локальный исследовательский batch-пайплайн и прототип Telegram-бота для сбора касаний и лидов с источником размещения.

Презентационные выводы исходного кейса находятся в [результатах исследования](docs/research-results.md), все исследования и методические материалы собраны в [оглавлении `docs/`](docs/README.md).

Целевой [продуктовый MVP](agents_docs/PRODUCT.md) ещё не реализован полностью. Текущее поведение кода описано в [архитектуре](agents_docs/ARCHITECTURE.md), разрыв и следующие этапы — в [плане](PLANS.md), принятые границы — в [журнале решений](agents_docs/DECISIONS.md).

## Постановка задачи

Исходные продажи содержат факт оплаты, но не полный путь пользователя. Реализованный исследовательский контур демонстрирует связывание размещения, касания, лида и заказа для расчёта атрибуции и ROMI. Фактические границы приведены в [разделе 1 архитектуры](agents_docs/ARCHITECTURE.md#1-назначение-и-границы), целевой пользовательский сценарий — в [разделе 3 продуктового документа](agents_docs/PRODUCT.md#3-сквозной-сценарий-mvp).

## Реализованный функционал

### Batch-пайплайн

`src/run_all.py` собирает или использует сохранённые Telegram-посты, подготавливает продажи, строит SQLite-витрину и запускает атрибуцию, ROMI, uplift и прогноз. Полная последовательность этапов, их входы и результаты приведены в [разделе 3.1 архитектуры](agents_docs/ARCHITECTURE.md#31-batch-пайплайн).

### Telegram-бот

`src/tracking_bot.py` принимает `placement_id` из deep-link, хеширует Telegram user id, записывает касания и интерес к курсу, уведомляет менеджера и формирует ссылку на диалог с кодом источника. Режимы работы и жизненный цикл события описаны в [разделе 3.2 архитектуры](agents_docs/ARCHITECTURE.md#32-telegram-бот).

Текущий бот не позволяет менеджеру отметить оплату или отказ и не связывает лид с реальной продажей. Эти функции относятся к целевому MVP и перечислены в [текущем этапе плана](PLANS.md#1-продуктовый-mvp-current).

## Архитектура

Проект состоит из последовательного batch-контура и отдельного polling-бота. Общей точкой интеграции служит `data/processed/pmm.sqlite`. Контекст системы показан в [разделе 2](agents_docs/ARCHITECTURE.md#2-контекст-системы), ответственность модулей — в [разделе 4](agents_docs/ARCHITECTURE.md#4-компоненты-и-ответственность), модель SQLite — в [разделе 5.3](agents_docs/ARCHITECTURE.md#53-реляционная-модель).

## Данные и assumptions

Входные продажи находятся в `data/raw/base.xlsx`, сохранённые Telegram-посты — в `data/collected/`. Пересобираемые результаты пишутся в `data/processed/`, `figures/` и `reports/`; демонстрационные расходы и касания — в `data/synthetic/`. Исследовательские выводы собраны в [результатах исследования](docs/research-results.md), структура витрины — в [описании модели данных](docs/marketing-data-model.md), численные результаты последнего запуска — в [сводке пайплайна](reports/summary.md).

Подробное назначение слоёв описано в [разделе 5.1](agents_docs/ARCHITECTURE.md#51-файловые-слои), зерно таблиц — в [разделе 5.2](agents_docs/ARCHITECTURE.md#52-основные-зерна). Правила атрибуции, ROMI, uplift и прогноза находятся в [разделе 6](agents_docs/ARCHITECTURE.md#6-алгоритмические-правила).

Ключевые assumptions:

- заказ объединяет строки одного `student_id` с одинаковым timestamp;
- `order_total` равен сумме `amount` его позиций;
- даты маркетинговых волн заданы в коде;
- исторические касания, внешние размещения и их стоимость синтетические, поэтому текущий ROMI является демонстрационным.

Полный список допущений исходного анализа сохранён в [результатах исследования](docs/research-results.md#8-assumptions-и-как-их-проверить).

## Установка окружения

Проект требует Python 3.14+, согласно `pyproject.toml`. Установите `uv` [официальным standalone installer](https://docs.astral.sh/uv/getting-started/installation/).

macOS/Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Перезапустите shell, перейдите в каталог проекта и установите окружение из lock-файла:

```bash
uv --version
uv sync
```

Для команд `uv run` активировать `.venv` вручную не требуется. Зависимости и ограничения окружения описаны в [разделе 7 архитектуры](agents_docs/ARCHITECTURE.md#7-конфигурация-и-внешние-зависимости).

## Запуск batch-пайплайна

На сохранённом снимке Telegram:

```bash
uv run python src/run_all.py
```

С повторным сбором публичных постов:

```bash
uv run python src/run_all.py --collect
```

Для `--collect` в `run_all.py` сейчас зафиксированы канал `postypashki_old` и начальная дата `2026-07-20`. Сбор требует доступа к `https://t.me`.

Другой канал или начальную дату можно передать напрямую сборщику:

```bash
uv run python src/tg_collector.py \
  --channel channel_username \
  --since 2026-08-01 \
  --out data/collected/tg_posts_postypashki_old.csv

uv run python src/run_all.py
```

Username передаётся без `@`, дата — в формате `YYYY-MM-DD`. Стандартное имя выходного файла нужно сохранить: `post_classifier.py` читает этот путь напрямую.

Период продаж определяется минимальным и максимальным timestamp в `base.xlsx`. Даты маркетинговых событий пока меняются в константах:

- `WAVES` и `EVENTS` в `src/eda.py`;
- `WAVES` в `src/uplift.py`;
- `WAVE_DATES` и `FUTURE_WAVE_DATES` в `src/forecast.py`;
- выведенные события в `src/post_classifier.py`.

Пересчёт атрибуции и ROMI с отдельными параметрами:

```bash
uv run python src/attribution.py --window 7 14 30
uv run python src/romi.py --model position --window 14 --margin 0.7
```

Допустимые модели и фактическое поведение приведены в разделах [6.1 «Атрибуция»](agents_docs/ARCHITECTURE.md#61-атрибуция) и [6.2 «ROMI»](agents_docs/ARCHITECTURE.md#62-romi); обоснование методики — в [исследовании атрибуции и ROMI](docs/attribution-and-romi.md).

## Запуск Telegram-бота

### 1. Подготовить витрину и ссылки

Боту нужна существующая `data/processed/pmm.sqlite` с зарегистрированными размещениями:

```bash
uv run python src/run_all.py
BOT_USERNAME='bot_name' uv run python src/tracking_bot.py --make-links
```

`BOT_USERNAME` указывается без `@`. Payload должен совпадать с `placement_id` в `dim_placement`.

### 2. Создать бота

1. Откройте `@BotFather` в Telegram.
2. Выполните `/newbot` и задайте имя и username.
3. Сохраните выданный токен как `BOT_TOKEN`. Не добавляйте его в Git или файлы проекта.

### 3. Получить `MANAGER_CHAT_ID` по username

Менеджер должен открыть созданного бота и отправить ему `/start`. Бот в этот момент не должен работать в polling-режиме: `getUpdates` использует ту же очередь обновлений.

```bash
export BOT_TOKEN='token'
export MANAGER_USERNAME='manager_username'

curl --silent \
  "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" |
jq --arg username "${MANAGER_USERNAME}" '
  .result[]
  | select(.message.from.username == $username)
  | {
      username: .message.from.username,
      user_id: .message.from.id,
      chat_id: .message.chat.id,
      text: .message.text
    }
'
```

Пример результата:

```json
{
  "username": "manager_username",
  "user_id": 878623702,
  "chat_id": 878623702,
  "text": "/start"
}
```

Значение `chat_id` используется как `MANAGER_CHAT_ID`. Если результат пуст, отправьте боту новое сообщение и повторите запрос. Для команды требуется `jq`.

После проверки удалите временные переменные:

```bash
unset BOT_TOKEN MANAGER_USERNAME
```

### 4. Запустить бота

```bash
BOT_USERNAME='bot_name' \
BOT_TOKEN='token' \
PMM_SALT='long-random-production-secret' \
MANAGER_LINK='https://t.me/manager_username' \
MANAGER_CHAT_ID='878623702' \
uv run python src/tracking_bot.py
```

Назначение переменных и поведение при их отсутствии описаны в [разделе 7 архитектуры](agents_docs/ARCHITECTURE.md#7-конфигурация-и-внешние-зависимости). Для production обязательно задайте уникальную `PMM_SALT`, совпадающую с солью слоя продаж.

Остановить polling можно сочетанием `Ctrl+C`.

### 5. Проверить без Telegram

```bash
uv run python src/tracking_bot.py --simulate
```

Симуляция добавляет demo-события в текущую SQLite-базу. Повторный запуск создаёт новые строки; полный `run_all.py` пересоздаёт базу. Другие ограничения и способы восстановления перечислены в [разделе 8 архитектуры](agents_docs/ARCHITECTURE.md#8-ошибки-ограничения-и-восстановление).

## Документация

- [Целевой продуктовый MVP](agents_docs/PRODUCT.md)
- [Оглавление исследований и результатов](docs/README.md)
- [Архитектура текущей реализации](agents_docs/ARCHITECTURE.md)
- [План проекта](PLANS.md)
- [Журнал решений](agents_docs/DECISIONS.md)
- [Модель маркетинговых данных](docs/marketing-data-model.md)
- [Telegram-трекинг](docs/telegram-tracking.md)
- [Атрибуция и ROMI](docs/attribution-and-romi.md)
- [Эксперименты по инкрементальности](docs/incrementality-experiments.md)
- [Результаты исследования](docs/research-results.md)
