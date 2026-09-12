-- Marketing data model «Поступашки» (Задача 3). SQLite-совместимый DDL.
-- Принцип: для каждого события понятно  КТО (user_hash) → ЧТО (event type) → КОГДА (ts)
--          → ОТКУДА (placement_id → channel, campaign, creative) → СКОЛЬКО (amount / cost).
-- Персональные данные не хранятся: только sha256(telegram_user_id + salt) и sha256(username + salt).

PRAGMA foreign_keys = ON;

-- ---------- измерения (dimensions)
CREATE TABLE IF NOT EXISTS dim_channel (
    channel_id      TEXT PRIMARY KEY,           -- own_tg_main, ext_tg_<slug>, youtube, instagram
    channel_name    TEXT NOT NULL,
    channel_type    TEXT NOT NULL CHECK (channel_type IN ('own_tg','external_tg','youtube','instagram','other')),
    subscribers     INTEGER,                    -- публичный счётчик на момент размещения
    contact         TEXT,                       -- контакт админа (для внешних)
    data_origin     TEXT NOT NULL DEFAULT 'real' CHECK (data_origin IN ('real','synthetic'))
);

CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_id     TEXT PRIMARY KEY,           -- 2026-09_pro_launch
    campaign_name   TEXT NOT NULL,
    objective       TEXT,                       -- sale | launch | lead_gen | brand
    product_line    TEXT,                       -- СТАРТ | ПРО | all
    start_date      TEXT, end_date TEXT,
    budget_rub      REAL,
    data_origin     TEXT NOT NULL DEFAULT 'real'
);

CREATE TABLE IF NOT EXISTS dim_creative (
    creative_id     TEXT PRIMARY KEY,           -- cr_sale_2for9990_v1
    offer_type      TEXT CHECK (offer_type IN ('sale','launch','native','content','lead_magnet')),
    discount_pct    REAL,                       -- глубина скидки в оффере
    promo_code      TEXT,                       -- уникальный промокод креатива (второй механизм стичинга)
    text_hash       TEXT,                       -- sha256 текста — чтобы отличать версии
    data_origin     TEXT NOT NULL DEFAULT 'real'
);

-- Размещение = единица, для которой считается ROMI: один пост в одном канале в одно время с одной стоимостью.
CREATE TABLE IF NOT EXISTS dim_placement (
    placement_id     TEXT PRIMARY KEY,          -- p_<channel>_<yyyymmdd>_<n>
    campaign_id      TEXT REFERENCES dim_campaign(campaign_id),
    channel_id       TEXT NOT NULL REFERENCES dim_channel(channel_id),
    creative_id      TEXT REFERENCES dim_creative(creative_id),
    publication_time TEXT NOT NULL,             -- ОБЯЗАТЕЛЬНО (иначе окно атрибуции не построить)
    cost_rub         REAL NOT NULL DEFAULT 0,   -- ОБЯЗАТЕЛЬНО (иначе ROMI не считается); для своего канала — opportunity cost
    cost_type        TEXT CHECK (cost_type IN ('fixed','cpm','barter','opportunity','zero')),
    post_url         TEXT,                      -- t.me/<channel>/<id>
    message_id       INTEGER,
    deep_link        TEXT,                      -- t.me/<bot>?start=<placement_id>
    views_public     INTEGER,                   -- публичный счётчик просмотров (снимок через 48/72 ч)
    status           TEXT DEFAULT 'published',  -- planned | published | deleted
    data_origin      TEXT NOT NULL DEFAULT 'real'
);

CREATE TABLE IF NOT EXISTS dim_course (
    course_id       TEXT PRIMARY KEY,
    course_name     TEXT NOT NULL UNIQUE,
    family          TEXT, product_line TEXT,
    list_price_rub  REAL,
    margin_pct      REAL DEFAULT 1.0            -- contribution margin (по умолчанию = выручка; заполняется финансами)
);

CREATE TABLE IF NOT EXISTS dim_user (
    user_hash        TEXT PRIMARY KEY,          -- sha256(telegram_user_id || salt)
    username_hash    TEXT,                      -- sha256(lower(username) || salt) — мост к student_id в base.xlsx
    first_seen_at    TEXT,
    first_placement_id TEXT REFERENCES dim_placement(placement_id),
    data_origin      TEXT NOT NULL DEFAULT 'real'
);

-- ---------- события (facts)
-- Касание: пользователь пришёл по трекинговой ссылке / нажал /start / вступил в канал по инвайт-ссылке
CREATE TABLE IF NOT EXISTS fact_touch (
    touch_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash       TEXT NOT NULL,
    placement_id    TEXT REFERENCES dim_placement(placement_id),
    touch_type      TEXT NOT NULL CHECK (touch_type IN ('bot_start','invite_join','manager_chat_open','promo_code_used','utm_click')),
    ts              TEXT NOT NULL,
    raw_payload     TEXT,                       -- то, что реально пришло: start-параметр, текст pre-filled сообщения, промокод
    match_quality   TEXT DEFAULT 'deterministic' CHECK (match_quality IN ('deterministic','probabilistic','self_reported')),
    data_origin     TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS ix_touch_user_ts ON fact_touch(user_hash, ts);

-- Лид: начало диалога с менеджером (логируется ботом/менеджером одной кнопкой)
CREATE TABLE IF NOT EXISTS fact_lead (
    lead_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash       TEXT NOT NULL,
    ts              TEXT NOT NULL,
    source_placement_id TEXT REFERENCES dim_placement(placement_id),
    source_self_reported TEXT,                  -- ответ на «откуда узнали?» (кнопки), если детерминированного источника нет
    interest_course TEXT,
    manager_id      TEXT,
    status          TEXT DEFAULT 'new',         -- new | qualified | paid | lost
    data_origin     TEXT NOT NULL DEFAULT 'real'
);

-- Заказ = одна оплата (все строки base.xlsx с одинаковыми student_id + timestamp)
CREATE TABLE IF NOT EXISTS fact_order (
    order_id        INTEGER PRIMARY KEY,
    user_hash       TEXT NOT NULL,
    ts              TEXT NOT NULL,
    order_total_rub REAL NOT NULL,
    n_items         INTEGER NOT NULL,
    is_bundle       INTEGER NOT NULL DEFAULT 0,
    order_seq       INTEGER NOT NULL DEFAULT 1, -- 1 = первая покупка, >1 = повторная
    promo_code      TEXT,
    data_origin     TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS ix_order_user_ts ON fact_order(user_hash, ts);

CREATE TABLE IF NOT EXISTS fact_order_item (
    item_id         INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES fact_order(order_id),
    course_id       TEXT NOT NULL REFERENCES dim_course(course_id),
    amount_rub      REAL NOT NULL,              -- доля суммы заказа, приходящаяся на курс (равные доли в пакете)
    list_price_rub  REAL,
    discount_pct    REAL
);

-- Публикации собственного канала (собранные tg_collector.py) — журнал контента/акций
CREATE TABLE IF NOT EXISTS fact_post (
    post_id         TEXT PRIMARY KEY,           -- <channel>/<message_id>
    channel_id      TEXT NOT NULL REFERENCES dim_channel(channel_id),
    message_id      INTEGER NOT NULL,
    published_at    TEXT NOT NULL,
    post_class      TEXT,                       -- sale | launch | native_promo | lead_magnet | external_ad | content
    views_public    INTEGER,
    has_manager_cta INTEGER,
    placement_id    TEXT REFERENCES dim_placement(placement_id),
    text            TEXT,
    data_origin     TEXT NOT NULL DEFAULT 'real'
);

-- Результат атрибуции (заполняется attribution.py)
CREATE TABLE IF NOT EXISTS attribution_result (
    order_id        INTEGER NOT NULL REFERENCES fact_order(order_id),
    placement_id    TEXT,                       -- NULL = organic / unknown
    model           TEXT NOT NULL,              -- first | last | linear | time_decay | position
    window_days     INTEGER NOT NULL,
    weight          REAL NOT NULL,
    attributed_revenue_rub REAL NOT NULL,
    PRIMARY KEY (order_id, placement_id, model, window_days)
);

-- ---------- витрины
CREATE VIEW IF NOT EXISTS v_user_journey AS
SELECT t.user_hash, t.ts AS event_ts, 'touch:' || t.touch_type AS event, t.placement_id, p.channel_id, p.campaign_id, NULL AS amount
FROM fact_touch t LEFT JOIN dim_placement p USING (placement_id)
UNION ALL
SELECT l.user_hash, l.ts, 'lead', l.source_placement_id, p.channel_id, p.campaign_id, NULL
FROM fact_lead l LEFT JOIN dim_placement p ON p.placement_id = l.source_placement_id
UNION ALL
SELECT o.user_hash, o.ts, 'order', NULL, NULL, NULL, o.order_total_rub FROM fact_order o
ORDER BY 1, 2;

CREATE VIEW IF NOT EXISTS v_romi_by_placement AS
SELECT a.model, a.window_days, p.placement_id, p.channel_id, p.campaign_id, p.publication_time, p.cost_rub,
       SUM(a.attributed_revenue_rub)              AS attributed_revenue_rub,
       SUM(a.weight)                              AS attributed_orders,
       CASE WHEN p.cost_rub > 0 THEN (SUM(a.attributed_revenue_rub) - p.cost_rub) / p.cost_rub END AS romi_attr,
       CASE WHEN SUM(a.weight) > 0 THEN p.cost_rub / SUM(a.weight) END AS cac_rub
FROM attribution_result a JOIN dim_placement p USING (placement_id)
GROUP BY 1, 2, 3, 4, 5, 6, 7;
