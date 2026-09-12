"""
Attribution engine (Задача 6) — распределение выручки заказа по касаниям.

Модели: first · last · linear · time_decay (half-life 7 дней) · position (40/20/40).
Окно атрибуции: по умолчанию 14 дней (обоснование — docs/attribution.md), параметр --window.
Правила:
  * учитываются касания в окне [ts_order − window; ts_order];
  * для повторных покупок — только касания ПОСЛЕ предыдущего заказа того же пользователя
    (иначе одно касание «продавало» бы дважды);
  * заказ без касаний → organic/unknown (placement_id = NULL) — не «размазываем» по каналам;
  * выручка = order_total (можно заменить на contribution margin через dim_course.margin_pct).

Вход: SQLite pmm.sqlite (fact_touch — СИНТЕТИЧЕСКИЕ касания, fact_order — РЕАЛЬНЫЕ заказы).
Выход: таблица attribution_result в SQLite + data/processed/attribution_by_placement.csv
"""
from __future__ import annotations

import argparse
import sqlite3

import numpy as np
import pandas as pd

from common import PROCESSED

DB = PROCESSED / "pmm.sqlite"
MODELS = ["first", "last", "linear", "time_decay", "position"]


def weights(ages_days: np.ndarray, model: str, half_life: float = 7.0) -> np.ndarray:
    """ages_days — возраст касаний относительно заказа, отсортирован по времени касания (от раннего к позднему)."""
    n = len(ages_days)
    if n == 1:
        return np.array([1.0])
    if model == "first":
        w = np.zeros(n); w[0] = 1
    elif model == "last":
        w = np.zeros(n); w[-1] = 1
    elif model == "linear":
        w = np.full(n, 1 / n)
    elif model == "time_decay":
        w = 2.0 ** (-ages_days / half_life); w = w / w.sum()
    elif model == "position":
        if n == 2:
            w = np.array([0.5, 0.5])
        else:  # 40% первому, 40% последнему, 20% поровну между средними
            w = np.full(n, 0.2 / (n - 2)); w[0] = 0.4; w[-1] = 0.4
    else:
        raise ValueError(model)
    return w


def attribute(orders: pd.DataFrame, touches: pd.DataFrame, window_days: int, model: str) -> pd.DataFrame:
    """Возвращает long-таблицу: order_id, placement_id, weight, attributed_revenue."""
    touches = touches.sort_values("ts")
    by_user = {u: g for u, g in touches.groupby("user_hash")}
    prev_order_ts = orders.sort_values("ts").groupby("user_hash").ts.shift()
    rows = []
    for o, prev_ts in zip(orders.itertuples(index=False), prev_order_ts.loc[orders.index]):
        g = by_user.get(o.user_hash)
        lo = o.ts - pd.Timedelta(days=window_days)
        if prev_ts is not None and not pd.isna(prev_ts):
            lo = max(lo, prev_ts)
        if g is not None:
            g = g[(g.ts > lo) & (g.ts <= o.ts)]
        if g is None or g.empty:
            rows.append((o.order_id, None, 1.0, o.order_total_rub))
            continue
        ages = ((o.ts - g.ts).dt.total_seconds() / 86400).values
        w = weights(ages, model)
        # одно и то же размещение может встретиться несколько раз — суммируем веса
        tmp = pd.DataFrame({"placement_id": g.placement_id.values, "weight": w}).groupby("placement_id").weight.sum()
        for pid, wt in tmp.items():
            rows.append((o.order_id, pid, float(wt), float(wt) * o.order_total_rub))
    return pd.DataFrame(rows, columns=["order_id", "placement_id", "weight", "attributed_revenue_rub"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, nargs="+", default=[7, 14, 30])
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    orders = pd.read_sql("SELECT order_id, user_hash, ts, order_total_rub FROM fact_order", con, parse_dates=["ts"])
    touches = pd.read_sql("SELECT user_hash, placement_id, ts FROM fact_touch", con, parse_dates=["ts"])
    con.execute("DELETE FROM attribution_result")

    summary = []
    for window in args.window:
        for model in MODELS:
            res = attribute(orders, touches, window, model)
            res["model"] = model; res["window_days"] = window
            res.to_sql("attribution_result", con, if_exists="append", index=False)
            organic = res[res.placement_id.isna()].attributed_revenue_rub.sum()
            summary.append({"window_days": window, "model": model,
                            "attributed_revenue_rub": round(res[res.placement_id.notna()].attributed_revenue_rub.sum()),
                            "organic_revenue_rub": round(organic),
                            "organic_share_pct": round(organic / res.attributed_revenue_rub.sum() * 100, 1)})
    con.commit()

    piv = pd.read_sql("""
        SELECT a.window_days, a.model, p.placement_id, p.channel_id, p.campaign_id, p.publication_time, p.cost_rub, p.data_origin,
               SUM(a.attributed_revenue_rub) AS attributed_revenue_rub, SUM(a.weight) AS attributed_orders
        FROM attribution_result a JOIN dim_placement p USING (placement_id)
        GROUP BY 1,2,3,4,5,6,7,8""", con)
    piv.to_csv(PROCESSED / "attribution_by_placement.csv", index=False)
    pd.DataFrame(summary).to_csv(PROCESSED / "attribution_summary.csv", index=False)
    con.close()

    print(pd.DataFrame(summary).to_string(index=False))
    w14 = piv[piv.window_days == 14].pivot_table(index=["channel_id", "placement_id"], columns="model", values="attributed_revenue_rub", aggfunc="sum").fillna(0).round()
    print("\nwindow=14d, attributed revenue by placement (DEMO on synthetic touches):")
    print(w14.sort_values("position", ascending=False).head(15).to_string())


if __name__ == "__main__":
    main()
