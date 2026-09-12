# Postupashki Marketing Measurement

Локальный проект измерения рекламы в публичных Telegram-каналах. В репозитории уже есть сбор и классификация постов, исследовательский batch-пайплайн и прототип tracking-бота. Полный продуктовый MVP пока не реализован.

## Статус проекта

| Контур | Статус | Что входит |
|---|---|---|
| Текущая реализация | Работает как прототип и исследовательский кейс | Сбор публичных постов, rule-based классификация, SQLite-витрина, Telegram deep-link, касания и новые лиды. |
| Целевой MVP | В разработке | Локальный веб-интерфейс, операционный реестр, статусы `paid`/`lost`, сумма оплаты, постаналитика и linear-атрибуция. |
| Следующий этап | Не входит в MVP | Атрибутированный ROMI и сравнительный пилот рекламных каналов. |
| Исследования и demo | Не являются функциями продукта | EDA, uplift, forecast, альтернативные модели атрибуции, synthetic-генератор и презентационные материалы. |

Фактическое устройство кода описано в [архитектуре](agents_docs/ARCHITECTURE.md#1-назначение-и-границы), целевой сценарий — в [PRODUCT.md](agents_docs/PRODUCT.md#3-сквозной-сценарий-mvp), следующие этапы — в [PLANS.md](PLANS.md), роль каждого экспериментального модуля — в [каталоге экспериментов](docs/experiment-catalog.md).

## Постановка задачи и целевой MVP

Продажи содержат факт оплаты, но не полный путь пользователя от рекламного поста. Целевой продукт связывает зарегистрированное размещение, переход по deep-link, лид и подтверждённую менеджером оплату, после чего показывает результат по кампании и посту.

MVP рассчитан на маркетолога и менеджера без участия аналитика:

- маркетолог регистрирует размещение, задаёт канал, даты и стоимость и получает deep-link;
- система собирает пост и публичные просмотры через 48 часов и 7 дней;
- пост автоматически получает класс `promo`, `content` или `external_ad`, который маркетолог может исправить;
- бот фиксирует касание и лид, а менеджер отмечает оплату или отказ и вводит сумму;
- отчёт показывает просмотры, переходы, лиды, оплаты и linear-атрибутированную выручку.

Это целевое, а не полностью реализованное поведение. Подробные границы MVP и список исключений находятся в [разделах 4–5 PRODUCT.md](agents_docs/PRODUCT.md#4-результат-mvp).

## Что реализовано сейчас

### Сбор и классификация постов

`src/tg_collector.py` читает публичное web preview `t.me/s/<channel>` без Telegram API-ключей и сохраняет id, время, текущий счётчик просмотров, текст, ссылки и признаки медиа/репоста. Он не видит удалённые публикации, private/admin analytics, реакции и user-level действия.

`src/post_classifier.py` классифицирует собранные посты прозрачными правилами. Текущая версия привязана к файлу канала кейса, использует шесть внутренних классов и добавляет три вручную выведенных события. В продуктовую постаналитику переходят только rule-based основа, три целевых класса и события из наблюдаемых постов или реестра.

Фактическая ответственность компонентов и продуктовая классификация приведены в [разделах 4–4.1 архитектуры](agents_docs/ARCHITECTURE.md#4-компоненты-и-ответственность).

### Telegram-бот

`src/tracking_bot.py`:

- принимает `placement_id` из `/start <placement_id>`;
- хеширует Telegram user id;
- записывает касание и выбранный пользователем курс в SQLite;
- создаёт новый лид и уведомляет менеджера;
- формирует ссылку на диалог с кодом источника.

Текущий бот не даёт менеджеру отметить оплату или отказ, не записывает сумму, не сохраняет `username_hash` и не связывает реальный лид с заказом из `base.xlsx`. Источник между `/start` и выбором курса хранится только в памяти процесса. Полный жизненный цикл описан в [разделе 3.2 архитектуры](agents_docs/ARCHITECTURE.md#32-telegram-бот), ограничения — в [разделе 8](agents_docs/ARCHITECTURE.md#8-ошибки-ограничения-и-восстановление).

### Исследовательский batch

`src/run_all.py` последовательно обрабатывает продажи и посты, генерирует synthetic-размещения и касания, пересоздаёт SQLite, считает attribution, ROMI, uplift и прогноз, запускает симуляцию бота и формирует сводку.

Batch смешивает реальные продажи и публичные посты с синтетическими расходами и касаниями. Его attribution и ROMI демонстрируют механику, но не измеряют фактическую эффективность рекламы. Uplift не является causal-оценкой, forecast построен на короткой истории. Порядок этапов указан в [разделе 3.1 архитектуры](agents_docs/ARCHITECTURE.md#31-batch-пайплайн), доказательность — в [каталоге экспериментов](docs/experiment-catalog.md).

## Архитектура

Текущая система состоит из последовательного batch-контура и отдельного aiogram polling-бота. Общая точка интеграции — `data/processed/pmm.sqlite`.

```text
публичный Telegram ─► collector ─► classifier ─┐
base.xlsx ──────────► EDA ─────────────────────┼─► CSV ─► SQLite ─► demo-отчёты
synthetic generator ─► placements / touches ──┘

Telegram deep-link ─► tracking bot ─► fact_touch / fact_lead
```

Подробный поток данных находится в [разделе 2 архитектуры](agents_docs/ARCHITECTURE.md#2-контекст-системы), модель SQLite — в [разделе 5.3](agents_docs/ARCHITECTURE.md#53-реляционная-модель).

## Данные и assumptions

| Слой | Содержание | Интерпретация |
|---|---|---|
| `data/raw/base.xlsx` | Реальные строки продаж | Входной файл, не изменяется пайплайном. |
| `data/collected/` | Реальные публичные посты | Снимок доступного web preview и просмотров на момент сбора. |
| `data/synthetic/` | Вымышленные каналы, расходы и касания | Только демонстрация measurement-механики. |
| `data/processed/` | CSV, JSON и `pmm.sqlite` | Пересобираемые результаты со смешанным real/synthetic происхождением. |
| `figures/`, `reports/` | Графики и Markdown-сводка | Результаты исследовательского запуска. |

Ключевые assumptions текущего кейса:

- заказ объединяет строки одного `student_id` с одинаковым timestamp;
- `order_total` равен сумме `amount` всех позиций заказа;
- маркетинговые волны и часть событий заданы в коде;
- исторические касания, внешние размещения и их стоимость синтетические;
- одинаковой `PMM_SALT` недостаточно для связи бота с `base.xlsx`: в текущих источниках нет общего реализованного идентификатора.

Назначение слоёв и зерно таблиц подробно описаны в [разделах 5.1–5.2 архитектуры](agents_docs/ARCHITECTURE.md#51-файловые-слои), полный список допущений исходного анализа — в [результатах исследования](docs/research-results.md#8-assumptions-и-как-их-проверить).

## Установка окружения

Проект требует Python 3.14+ согласно `pyproject.toml`. Установите `uv` [официальным standalone installer](https://docs.astral.sh/uv/getting-started/installation/).

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

Для `uv run` активировать `.venv` вручную не требуется. Зависимости и переменные окружения перечислены в [разделе 7 архитектуры](agents_docs/ARCHITECTURE.md#7-конфигурация-и-внешние-зависимости).

## Запуск исследовательского контура

На сохранённом снимке Telegram:

```bash
uv run python src/run_all.py
```

С повторным сбором публичных постов:

```bash
uv run python src/run_all.py --collect
```

`run_all.py --collect` использует захардкоженные канал `postypashki_old`, начальную дату `2026-07-20` и стандартное имя выходного файла. Сбор требует доступа к `https://t.me`.

Другой публичный канал или начальную дату можно передать напрямую сборщику:

```bash
uv run python src/tg_collector.py \
  --channel channel_username \
  --since 2026-08-01 \
  --out data/collected/tg_posts_postypashki_old.csv

uv run python src/run_all.py
```

Username передаётся без `@`, дата — в формате `YYYY-MM-DD`. Путь `data/collected/tg_posts_postypashki_old.csv` нужно сохранить: текущий `post_classifier.py` читает его напрямую.

Даты маркетинговых событий пока меняются в константах:

- `WAVES` и `EVENTS` в `src/eda.py`;
- `WAVES` в `src/uplift.py`;
- `WAVE_DATES` и `FUTURE_WAVE_DATES` в `src/forecast.py`;
- inferred-события в `src/post_classifier.py`.

Отдельный пересчёт исследовательской attribution и demo-ROMI:

```bash
uv run python src/attribution.py --window 7 14 30
uv run python src/romi.py --model position --window 14 --margin 0.7
```

Эти команды работают на текущей mixed real/synthetic витрине. Они не являются расчётом продуктовой linear-атрибуции или фактической окупаемости. Модели и формулы описаны в [разделе 6 архитектуры](agents_docs/ARCHITECTURE.md#6-алгоритмические-правила).

### Основные результаты batch

| Результат | Назначение |
|---|---|
| `data/processed/pmm.sqlite` | Пересоздаваемая SQLite-витрина. |
| `reports/summary.md` | Сводка последнего исследовательского запуска. |
| `data/processed/*.csv`, `*.json` | Нормализованные данные и результаты отдельных этапов. |
| `figures/` | Графики EDA, ROMI, uplift и forecast. |

`run_all.py` удаляет и пересоздаёт `pmm.sqlite`, а затем запускает `tracking_bot.py --simulate`. Симуляция добавляет demo-события, которые текущий код помечает как `data_origin='real'`; не используйте эту базу как операционный источник.

## Запуск прототипа Telegram-бота

Бот требует уже созданную SQLite-витрину и зарегистрированные в ней `placement_id`. Подготовка через `run_all.py` создаёт именно demo-витрину; рабочий операционный реестр пока не подключён.

### 1. Подготовить demo-витрину и ссылки

```bash
uv run python src/run_all.py
BOT_USERNAME='bot_name' uv run python src/tracking_bot.py --make-links
```

`BOT_USERNAME` указывается без `@`. Режим `--make-links` читает synthetic-реестр и печатает только deep-link для каждого `placement_id`.

### 2. Создать бота

1. Откройте `@BotFather` в Telegram.
2. Выполните `/newbot` и задайте имя и username.
3. Сохраните выданный токен как `BOT_TOKEN`. Не добавляйте его в Git, исходный код или файлы проекта.

Если реальный токен когда-либо попадал в Git, отзовите его через BotFather и выпустите новый. Удаление строки из файла не делает опубликованный токен недействительным.

### 3. Получить `MANAGER_CHAT_ID` по username

Менеджер должен открыть созданного бота и отправить ему `/start`. В этот момент бот не должен работать в polling-режиме: `getUpdates` использует ту же очередь обновлений.

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

`PMM_SALT` должна быть уникальным секретом для реального запуска. Она стабилизирует хеши Telegram user id внутри бота, но сама по себе не создаёт связь с текущей выгрузкой продаж.

Остановить polling можно сочетанием `Ctrl+C`.

### 5. Проверить без Telegram

```bash
uv run python src/tracking_bot.py --simulate
```

Симуляция добавляет demo-события в текущую SQLite-базу. Повторный запуск создаёт новые строки; полный `run_all.py` сначала пересоздаёт базу.

## Документация

Нормативные документы:

- [Целевой продуктовый MVP](agents_docs/PRODUCT.md)
- [Архитектура текущей реализации](agents_docs/ARCHITECTURE.md)
- [План проекта](PLANS.md)
- [Журнал решений](agents_docs/DECISIONS.md)
- [Каталог экспериментальных модулей](docs/experiment-catalog.md)

Исследования и результаты:

- [Оглавление исследований](docs/README.md)
- [Результаты исходного исследования](docs/research-results.md)
- [Сводка последнего запуска](reports/summary.md)
- [Модель маркетинговых данных](docs/marketing-data-model.md)
- [Telegram-трекинг](docs/telegram-tracking.md)
- [Атрибуция и ROMI](docs/attribution-and-romi.md)
- [Эксперименты по инкрементальности](docs/incrementality-experiments.md)
