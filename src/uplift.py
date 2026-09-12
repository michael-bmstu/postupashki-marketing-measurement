"""
Задача 7. Attribution ≠ Incrementality.

Что здесь считается (на РЕАЛЬНЫХ дневных продажах):
  «наивный uplift» волны = факт заказов в окне волны − ожидание по baseline (медиана обычных дней, с поправкой
  на день недели) × длина окна; доверительный интервал — бутстрап обычных дней.

ЧТО ЭТО НЕ ЕСТЬ: это НЕ каузальная оценка. Нет контрольной группы; ожидание «без акции» — экстраполяция обычных дней.
Конфаундеры: сезон (начало учебного года), внешний дедлайн стажировки Т-Банка (6 сен), pull-forward
(покупатели, которые купили бы позже по полной цене, купили сейчас со скидкой — см. «провал» 15–21 авг).

Дизайны, которые дадут ROMI_inc в будущем, описаны в docs/experiments.md; здесь — калькулятор размера выборки
для holdout-теста промокода (сколько дней/пользователей нужно, чтобы увидеть эффект заданного размера).

Выход: data/processed/uplift_waves.csv, figures/fig7_uplift.png, data/processed/experiment_power.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import FIGURES, PROCESSED

WAVES = [
    ("W1: распродажа СТАРТ (−35%)", "2026-08-08", "2026-08-10"),
    ("W2: запуск ПРО + AI агенты", "2026-08-22", "2026-08-24"),
    ("W3: дедлайн Т-Банк (полная цена)", "2026-09-04", "2026-09-06"),
]
POST_WAVE_DAYS = 7  # окно после волны для оценки pull-forward («провала»)


def main() -> None:
    d = pd.read_csv(PROCESSED / "daily.csv", parse_dates=["date"]).set_index("date")
    in_wave = pd.Series(False, index=d.index)
    for _, a, b in WAVES:
        in_wave.loc[a:b] = True
    base = d[~in_wave]
    # поправка на день недели: ожидание = медиана обычных дней × индекс дня недели
    dow_idx = (base.groupby(base.index.dayofweek).orders.mean() / base.orders.mean()).reindex(range(7)).fillna(1.0)
    rng = np.random.default_rng(7)

    rows = []
    for name, a, b in WAVES:
        seg = d.loc[a:b]
        expected = sum(base.orders.median() * dow_idx[dt.dayofweek] for dt in seg.index)
        observed = seg.orders.sum()
        # бутстрап: пересэмплируем обычные дни того же дня недели
        boots = []
        for _ in range(4000):
            tot = 0.0
            for dt in seg.index:
                pool = base[base.index.dayofweek == dt.dayofweek].orders.values
                if len(pool) == 0:
                    pool = base.orders.values
                tot += rng.choice(pool)
            boots.append(tot)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        # pull-forward: неделя после волны vs baseline
        post = d.loc[pd.Timestamp(b) + pd.Timedelta(days=1): pd.Timestamp(b) + pd.Timedelta(days=POST_WAVE_DAYS)]
        post_expected = sum(base.orders.median() * dow_idx[dt.dayofweek] for dt in post.index)
        rows.append({
            "wave": name, "start": a, "end": b, "observed_orders": int(observed), "expected_orders_baseline": round(expected, 1),
            "naive_uplift_orders": round(observed - expected, 1), "uplift_ci95_low": round(observed - hi, 1), "uplift_ci95_high": round(observed - lo, 1),
            "observed_revenue": round(seg.revenue.sum()), "avg_order_rub": round(seg.revenue.sum() / observed),
            "post_week_orders": int(post.orders.sum()), "post_week_expected": round(post_expected, 1),
            "post_week_delta": round(post.orders.sum() - post_expected, 1),
            "note": "NOT causal: no control group; baseline = median of non-wave days × weekday index",
        })
    up = pd.DataFrame(rows)
    up.to_csv(PROCESSED / "uplift_waves.csv", index=False)

    # --- калькулятор мощности для holdout промокода (пропорции: конверсия касание→покупка)
    # p0 — конверсия без стимула, эффект — относительный прирост; alpha=0.05, power=0.8, двусторонний
    power_rows = []
    for p0 in [0.05, 0.10, 0.20]:
        for rel in [0.2, 0.3, 0.5]:
            p1 = p0 * (1 + rel)
            h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p0))  # Cohen's h
            n = ((stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) / h) ** 2
            power_rows.append({"baseline_cr": p0, "relative_effect": rel, "n_per_group": int(np.ceil(n)),
                               "days_at_60_leads_per_day": round(2 * n / 60, 1)})
    pw = pd.DataFrame(power_rows)
    pw.to_csv(PROCESSED / "experiment_power.csv", index=False)

    # --- figure
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(up))
    ax.bar(x - 0.2, up.expected_orders_baseline, width=0.4, color="#8c8c8c", label="ожидание по baseline (обычные дни)")
    ax.bar(x + 0.2, up.observed_orders, width=0.4, color="#1f4e79", label="факт заказов в волне")
    ax.errorbar(x + 0.2, up.observed_orders, yerr=[up.observed_orders - (up.expected_orders_baseline + up.uplift_ci95_low),
                                                    (up.expected_orders_baseline + up.uplift_ci95_high) - up.observed_orders],
                fmt="none", ecolor="#d62828", capsize=4, lw=1.2, label="95% интервал ожидания (бутстрап)")
    for i, r in up.iterrows():
        ax.text(i + 0.2, r.observed_orders + 3, f"+{r.naive_uplift_orders:.0f} зак.\nср. чек {r.avg_order_rub/1000:.1f}K\nнеделя после: {r.post_week_delta:+.0f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(up.wave, fontsize=9); ax.set_ylabel("заказов за 3 дня")
    ax.set_ylim(0, up.observed_orders.max() * 1.35)
    ax.set_title("Наивный uplift волн относительно обычных дней — оценка, НЕ каузальный эффект (нет контрольной группы)", fontsize=10, loc="left")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(FIGURES / "fig7_uplift.png", dpi=150); plt.close(fig)

    print(up.drop(columns=["note"]).to_string(index=False))
    print("\nPower calculator (holdout промокода):"); print(pw.to_string(index=False))


if __name__ == "__main__":
    main()
