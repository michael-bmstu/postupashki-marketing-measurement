# Marketing data model (Задача 3)

DDL: `sql/schema.sql` (SQLite; переносится в Postgres/ClickHouse без изменений логики). Заполняется `src/build_mart.py`.

```
dim_channel ──┐
dim_campaign ─┼─► dim_placement ◄──── fact_touch ◄── dim_user ──► fact_lead
dim_creative ─┘        │                                 │
                       │                                 └──► fact_order ──► fact_order_item ──► dim_course
                       └──── fact_post (журнал публикаций своего канала)
attribution_result (order × placement × model × window)  ──►  v_romi_by_placement
```

| Таблица | Зерно (одна строка =) | Ключевые поля | Источник сегодня | Источник завтра |
|---|---|---|---|---|
| dim_channel | канал/площадка | channel_type, subscribers | вручную | реестр |
| dim_campaign | кампания (запуск, распродажа) | objective, product_line, даты, budget | выведено из постов | реестр |
| dim_creative | версия оффера/текста | offer_type, discount_pct, promo_code | классификатор постов | реестр |
| **dim_placement** | **одно размещение в одном канале** | **publication_time, cost_rub, deep_link**, views_public, status | посты канала (реальные) + синтетические внешние | реестр — заполняется ДО публикации |
| dim_course | продукт | family, product_line, list_price, margin_pct | base.xlsx | прайс/финансы |
| dim_user | человек (хеш) | user_hash, username_hash, first_placement_id | покупатели base.xlsx (хеш) | бот |
| fact_touch | касание | user_hash, placement_id, touch_type, ts, match_quality | **синтетика** | бот / промокод / менеджер |
| fact_lead | начало диалога / интерес | user_hash, source_placement_id, interest_course, status | синтетика | бот / кнопка у менеджера |
| fact_order | оплата | user_hash, ts, order_total, order_seq, promo_code | base.xlsx (реальные) | слой продаж + user_hash |
| fact_order_item | курс в заказе | course_id, amount, discount_pct | base.xlsx | слой продаж |
| fact_post | публикация своего канала | post_class, views_public, placement_id | tg_collector (реальные) | tg_collector по расписанию |
| attribution_result | доля заказа, приписанная размещению | model, window_days, weight | attribution.py | attribution.py |

Для каждого события отвечаем на «кто → что → когда → откуда → к какой активности»:
`fact_touch.user_hash → touch_type → ts → placement_id → dim_placement.campaign_id / creative_id`.

## Что в модели принципиально новое для бизнеса

1. `dim_placement.cost_rub` и `publication_time` обязательны (NOT NULL) — без них строка не принимается: это и есть «ROMI не считается».
2. `status = deleted` вместо удаления: продающие посты удаляются из канала после акции, но остаются в реестре.
3. `data_origin` в каждой таблице — реальные и синтетические строки не смешиваются в отчётах.
4. `match_quality` в касаниях — deterministic / probabilistic / self_reported; атрибуция может понижать вес.
5. `order_seq` — повторная покупка видна сразу; атрибуция учитывает только касания после предыдущего заказа.

## Операционный календарь

`templates/campaign_registry_template.xlsx` — три листа: «Размещения» (→ dim_placement), «Кампании» (→ dim_campaign),
«Календарь дедлайнов» (внешние события: стажировки, ШАД, олимпиады). Заполняется маркетологом в Google Sheets;
`build_mart.py` умеет читать тот же формат из CSV. Минимальная дисциплина: строка появляется **до** публикации.
