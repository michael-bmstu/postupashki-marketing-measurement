"""
Генератор СИНТЕТИЧЕСКИХ данных для демонстрации measurement-пайплайна.

ЧТО РЕАЛЬНО, А ЧТО НЕТ (важно для интерпретации результатов):
  РЕАЛЬНО:      заказы и покупатели (base.xlsx); посты собственного канала, их время и просмотры (tg_collector).
  СИНТЕТИЧНО:   (1) стоимость размещений — бизнес её не логировал, а для своего канала это opportunity cost;
                (2) внешние размещения в 5 вымышленных каналах — у нас нет журнала реальных закупок;
                (3) касания (bot_start / открытие чата с менеджером / промокод) — их никто не логировал.
  Касания генерируются ДЛЯ РЕАЛЬНЫХ заказов по описанному ниже процессу, чтобы показать, как заказ
  стыкуется с размещением. Числа ROMI по размещениям — ИЛЛЮСТРАЦИЯ работы движка, а не оценка бизнеса.

Генеративный процесс касаний (упрощённая, но правдоподобная модель поведения):
  * для каждого реального заказа: с p=0.20 — органика (касаний нет);
    иначе последнее касание — за Exp(mean=1.2 дня) до заказа, источник выбирается среди размещений,
    опубликованных в окне 14 дней до заказа, с весом ~ views × exp(-возраст/5 дней);
  * с p=0.45 добавляется 1–2 более ранних касания (multi-touch);
  * ~1 400 касаний от пользователей, которые НЕ купили (реалистичная конверсия касание→заказ ≈ 25–30%).

Все синтетические строки помечены data_origin='synthetic'. Seed фиксирован — генерация воспроизводима.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from common import PROCESSED, SYNTHETIC

SEED = 42
SALT = "postupashki-hackathon-demo-salt"      # в проде — секрет из переменной окружения
OWN_POST_OPPORTUNITY_COST = 20_000            # ASSUMPTION: цена рекламного поста в канале ~45K подписчиков / ~20K просмотров
ATTRIBUTION_WINDOW_DAYS = 14


def user_hash(student_id: int) -> str:
    return hashlib.sha256(f"student:{student_id}:{SALT}".encode()).hexdigest()[:16]


def synthetic_user_hash(i: int) -> str:
    return hashlib.sha256(f"synthetic-nonbuyer:{i}:{SALT}".encode()).hexdigest()[:16]


def build_registry(posts: pd.DataFrame) -> pd.DataFrame:
    """Реестр размещений: реальные CTA-посты своего канала + синтетические внешние закупки."""
    own = posts[posts.post_class.isin(["sale", "launch", "native_promo", "lead_magnet"])].copy()
    own["published_msk"] = pd.to_datetime(own.published_msk)
    reg_own = pd.DataFrame({
        "placement_id": "p_own_" + own.message_id.astype(str),
        "campaign_id": own.published_msk.map(_campaign_for_date),
        "channel_id": "own_tg_main",
        "creative_id": "cr_" + own.post_class,
        "publication_time": own.published_msk.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "cost_rub": 0.0,                                  # прямых затрат нет
        "cost_type": "opportunity",
        "opportunity_cost_rub": OWN_POST_OPPORTUNITY_COST,  # ASSUMPTION
        "post_url": "https://t.me/postypashki_old/" + own.message_id.astype(str),
        "message_id": own.message_id,
        "deep_link": "https://t.me/PostupashkiTrackBot?start=p_own_" + own.message_id.astype(str),
        "views_public": own.views,
        "status": "published",
        "data_origin": "real_post/synthetic_cost",
    })

    ext = pd.DataFrame([
        # placement_id, channel, publication_time, cost, views  — ВЫМЫШЛЕННЫЕ каналы и цены
        ("p_ext_it_jobs_0807", "ext_tg_it_jobs", "2026-08-07 12:00:00", 25_000, 18_000),
        ("p_ext_ds_memes_0808", "ext_tg_ds_memes", "2026-08-08 11:00:00", 15_000, 30_000),
        ("p_ext_stud_life_0821", "ext_tg_student_life", "2026-08-21 18:00:00", 12_000, 9_000),
        ("p_ext_it_jobs_0822", "ext_tg_it_jobs", "2026-08-22 10:00:00", 25_000, 17_000),
        ("p_ext_ml_digest_0823", "ext_tg_ml_digest", "2026-08-23 09:00:00", 40_000, 45_000),
        ("p_ext_yt_review_0830", "ext_youtube_review", "2026-08-30 15:00:00", 35_000, 12_000),
        ("p_ext_stud_life_0903", "ext_tg_student_life", "2026-09-03 19:00:00", 12_000, 8_500),
        ("p_ext_ds_memes_0904", "ext_tg_ds_memes", "2026-09-04 12:00:00", 18_000, 28_000),
    ], columns=["placement_id", "channel_id", "publication_time", "cost_rub", "views_public"])
    ext["campaign_id"] = pd.to_datetime(ext.publication_time).map(_campaign_for_date)
    ext["creative_id"] = "cr_native"
    ext["cost_type"] = "fixed"; ext["opportunity_cost_rub"] = 0.0
    ext["post_url"] = ""; ext["message_id"] = np.nan
    ext["deep_link"] = "https://t.me/PostupashkiTrackBot?start=" + ext.placement_id
    ext["status"] = "published"; ext["data_origin"] = "synthetic"
    reg = pd.concat([reg_own, ext[reg_own.columns]], ignore_index=True)
    reg["publication_time"] = pd.to_datetime(reg.publication_time)
    return reg.sort_values("publication_time").reset_index(drop=True)


def _campaign_for_date(ts: pd.Timestamp) -> str:
    ts = pd.Timestamp(ts)
    if ts < pd.Timestamp("2026-08-12"):
        return "cmp_2026-08_start_sale"
    if ts < pd.Timestamp("2026-08-28"):
        return "cmp_2026-08_pro_launch"
    return "cmp_2026-09_tbank_season"


def generate_touches(orders: pd.DataFrame, reg: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    touches = []
    reg = reg.copy()
    reg["w_base"] = reg.views_public.fillna(10_000).astype(float)
    touch_types = np.array(["bot_start", "manager_chat_open", "promo_code_used"])
    type_p = np.array([0.55, 0.35, 0.10])

    for o in orders.itertuples(index=False):
        if rng.random() < 0.20:
            continue  # органика: касаний нет
        # кандидаты — размещения за 21 день до заказа (шире окна атрибуции, чтобы было что «отрезать» окном)
        window_start = o.ts - pd.Timedelta(days=21)
        cand = reg[(reg.publication_time <= o.ts) & (reg.publication_time >= window_start)]
        if cand.empty:
            continue
        age_days = (o.ts - cand.publication_time).dt.total_seconds() / 86400
        w = cand.w_base.values * np.exp(-age_days.values / 5.0)
        w = w / w.sum()
        n_touch = 1 + (rng.random() < 0.45) * rng.integers(1, 3)
        chosen = rng.choice(len(cand), size=min(n_touch, len(cand)), replace=False, p=w)
        # последнее касание близко к покупке (Exp, mean 1.2 дня); более ранние — на 1–12 дней раньше
        lags = [float(rng.exponential(1.2))]
        for _ in range(len(chosen) - 1):
            lags.append(lags[-1] + float(rng.uniform(1, 12)))
        for idx, lag in zip(chosen, lags):
            p = cand.iloc[idx]
            ts = max(o.ts - pd.Timedelta(days=lag), p.publication_time + pd.Timedelta(minutes=5))
            touches.append({"user_hash": user_hash(o.student_id), "placement_id": p.placement_id,
                            "touch_type": rng.choice(touch_types, p=type_p), "ts": ts,
                            "raw_payload": f"start={p.placement_id}", "converted": 1})

    # касания без покупки
    n_non = 1400
    w = reg.w_base.values / reg.w_base.sum()
    for i in range(n_non):
        p = reg.iloc[rng.choice(len(reg), p=w)]
        ts = p.publication_time + pd.Timedelta(hours=float(rng.exponential(30)))
        touches.append({"user_hash": synthetic_user_hash(i), "placement_id": p.placement_id,
                        "touch_type": rng.choice(touch_types, p=type_p), "ts": ts,
                        "raw_payload": f"start={p.placement_id}", "converted": 0})
    t = pd.DataFrame(touches).sort_values("ts").reset_index(drop=True)
    t["touch_id"] = range(1, len(t) + 1)
    t["match_quality"] = "deterministic"
    t["data_origin"] = "synthetic"
    return t[["touch_id", "user_hash", "placement_id", "touch_type", "ts", "raw_payload", "match_quality", "converted", "data_origin"]]


def main() -> None:
    rng = np.random.default_rng(SEED)
    posts = pd.read_csv(PROCESSED / "posts_classified.csv")
    orders = pd.read_csv(PROCESSED / "orders.csv", parse_dates=["ts"])

    reg = build_registry(posts)
    reg.to_csv(SYNTHETIC / "ad_registry.csv", index=False)

    channels = pd.DataFrame([
        ("own_tg_main", "Поступашки — ШАД, Стажировки и Магистратура (@postypashki_old)", "own_tg", 45_000, "real"),
        ("ext_tg_it_jobs", "[SYNTHETIC] IT Jobs Digest", "external_tg", 60_000, "synthetic"),
        ("ext_tg_ds_memes", "[SYNTHETIC] DS Memes", "external_tg", 120_000, "synthetic"),
        ("ext_tg_student_life", "[SYNTHETIC] Student Life", "external_tg", 25_000, "synthetic"),
        ("ext_tg_ml_digest", "[SYNTHETIC] ML Digest", "external_tg", 150_000, "synthetic"),
        ("ext_youtube_review", "[SYNTHETIC] YouTube интеграция", "youtube", 80_000, "synthetic"),
    ], columns=["channel_id", "channel_name", "channel_type", "subscribers", "data_origin"])
    channels.to_csv(SYNTHETIC / "channels.csv", index=False)

    campaigns = pd.DataFrame([
        ("cmp_2026-08_start_sale", "Финальная распродажа СТАРТ", "sale", "СТАРТ", "2026-08-07", "2026-08-11", "real (inferred from posts)"),
        ("cmp_2026-08_pro_launch", "Запуск линейки ПРО + AI агенты", "launch", "ПРО", "2026-08-22", "2026-08-27", "real (inferred from posts)"),
        ("cmp_2026-09_tbank_season", "Сезон стажировок: разборы Т-Банк/Яндекс на курсах ПРО", "native", "ПРО", "2026-08-28", "2026-09-10", "real (inferred from posts)"),
    ], columns=["campaign_id", "campaign_name", "objective", "product_line", "start_date", "end_date", "data_origin"])
    campaigns.to_csv(SYNTHETIC / "campaigns.csv", index=False)

    touches = generate_touches(orders, reg, rng)
    touches.to_csv(SYNTHETIC / "touches.csv", index=False)

    conv_users = touches[touches.converted == 1].user_hash.nunique()
    print(f"registry: {len(reg)} placements ({(reg.data_origin != 'synthetic').sum()} real own posts + {(reg.data_origin == 'synthetic').sum()} synthetic external)")
    print(f"touches: {len(touches)} (converted users: {conv_users} of {orders.student_id.nunique()} buyers; non-buyers: {touches[touches.converted == 0].user_hash.nunique()})")
    print(touches.touch_type.value_counts().to_string())


if __name__ == "__main__":
    main()
