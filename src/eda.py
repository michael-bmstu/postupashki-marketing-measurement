"""
Задача 1. EDA и аудит качества данных base.xlsx (РЕАЛЬНЫЕ данные).

Выход:
  data/processed/order_items.csv, orders.csv, daily.csv, courses.csv, waves.csv
  data/processed/key_facts.json  — числа, на которые ссылаются README / executive summary
  figures/fig1_daily_orders_events.png ... fig5_order_structure.png
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FIGURES, PROCESSED, build_orders, daily_frame, load_raw

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
C_MAIN, C_ACC, C_GREY, C_RED = "#1f4e79", "#e8a33d", "#8c8c8c", "#d62828"

# Волны продаж — границы выбраны по дневному числу заказов (>= 2× медианы обычного дня) и подтверждены постами.
WAVES = [
    ("W1: распродажа СТАРТ", "2026-08-08", "2026-08-10"),
    ("W2: запуск ПРО + AI агенты", "2026-08-22", "2026-08-24"),
    ("W3: дедлайн стажировки Т-Банк", "2026-09-04", "2026-09-06"),
]
EVENTS = [  # (дата, подпись) — реальные посты из data/processed/posts_classified.csv
    ("2026-08-08", "старт распродажи СТАРТ\n(пост не сохранился)"),
    ("2026-08-10", "продление скидки\n(посты 1838, 1840)"),
    ("2026-08-22", "запуск ПРО + AI агенты\n(пост 1859, 35.7K)"),
    ("2026-08-30", "промокод в вебинаре\n(пост 1874)"),
    ("2026-09-06", "дедлайн Т-Банк\n(пост 1880)"),
]


def main() -> None:
    df = load_raw()
    items, orders = build_orders(df)
    daily = daily_frame(orders, items)

    items.to_csv(PROCESSED / "order_items.csv", index=False)
    orders.to_csv(PROCESSED / "orders.csv", index=False)
    daily.to_csv(PROCESSED / "daily.csv", index=False)

    # --- продукты
    courses = (
        items.groupby("course")
        .agg(items=("item_id", "size"), buyers=("student_id", "nunique"), revenue=("amount", "sum"),
             first_sale=("timestamp", "min"), last_sale=("timestamp", "max"),
             median_price=("amount", "median"), list_price=("list_price", "first"))
        .sort_values("revenue", ascending=False)
    )
    courses["rev_share_pct"] = (courses.revenue / courses.revenue.sum() * 100).round(1)
    courses.to_csv(PROCESSED / "courses.csv")

    # --- волны
    d = daily.set_index("date")
    base_mask = pd.Series(True, index=d.index)
    for _, a, b in WAVES:
        base_mask.loc[a:b] = False
    baseline_orders = d.loc[base_mask, "orders"].median()
    waves_rows = []
    for name, a, b in WAVES:
        seg = d.loc[a:b]
        n_days = len(seg)
        w_items = items[(items.timestamp >= a) & (items.timestamp < pd.Timestamp(b) + pd.Timedelta(days=1))]
        waves_rows.append({
            "wave": name, "start": a, "end": b, "days": n_days,
            "orders": int(seg.orders.sum()), "revenue": round(seg.revenue.sum()),
            "orders_share_pct": round(seg.orders.sum() / d.orders.sum() * 100, 1),
            "revenue_share_pct": round(seg.revenue.sum() / d.revenue.sum() * 100, 1),
            "avg_order": round(seg.revenue.sum() / seg.orders.sum()),
            "avg_discount_pct": round(w_items.discount_pct.mean() * 100, 1),
            "bundle_share_pct": round(orders[(orders.ts >= a) & (orders.ts < pd.Timestamp(b) + pd.Timedelta(days=1))].is_bundle.mean() * 100, 1),
            "orders_over_baseline": int(seg.orders.sum() - baseline_orders * n_days),
        })
    waves = pd.DataFrame(waves_rows)
    waves.to_csv(PROCESSED / "waves.csv", index=False)

    # --- повторные покупки
    per_student = orders.groupby("student_id").agg(n_orders=("order_id", "size"), first=("ts", "min"), last=("ts", "max"),
                                                    ltv=("order_total", "sum"))
    rep = per_student[per_student.n_orders > 1]
    gap_days = (rep["last"] - rep["first"]).dt.total_seconds() / 86400

    facts = {
        "rows": int(len(items)), "orders": int(len(orders)), "buyers": int(orders.student_id.nunique()),
        "courses": int(items.course.nunique()),
        "period": f"{items.timestamp.min():%d.%m.%Y} – {items.timestamp.max():%d.%m.%Y}",
        "days": int(len(daily)),
        "revenue_total": round(float(items.amount.sum())),
        "avg_order_total": round(float(orders.order_total.mean())),
        "median_order_total": round(float(orders.order_total.median())),
        "avg_item_price": round(float(items.amount.mean())),
        "bundle_orders": int(orders.is_bundle.sum()), "bundle_orders_pct": round(float(orders.is_bundle.mean() * 100), 1),
        "bundle_revenue_pct": round(float(orders.loc[orders.is_bundle, "order_total"].sum() / orders.order_total.sum() * 100), 1),
        "repeat_buyers": int(len(rep)), "repeat_buyers_pct": round(float(len(rep) / len(per_student) * 100), 1),
        "repeat_orders_revenue": round(float(orders.loc[orders.is_repeat, "order_total"].sum())),
        "repeat_gap_median_days": round(float(gap_days.median()), 1), "repeat_gap_p75_days": round(float(gap_days.quantile(0.75)), 1),
        "weekend_orders_pct": round(float(orders.ts.dt.dayofweek.ge(5).mean() * 100), 1),
        "peak_hours_msk": "14–19",
        "baseline_orders_per_day_median": float(baseline_orders),
        "baseline_revenue_per_day_median": round(float(d.loc[base_mask, "revenue"].median())),
        "top_day": {"date": str(d.orders.idxmax().date()), "orders": int(d.orders.max()), "revenue": round(float(d.loc[d.orders.idxmax(), "revenue"]))},
        "waves": waves_rows,
        "anomalies": {
            "amount_le_1000": int(items.flag_low_amount.sum()),
            "amount_ge_15000_single_item": int((items.flag_high_amount & (items.groupby('order_id').item_id.transform('size') == 1)).sum()),
            "same_course_twice": int(items.flag_same_course_twice.sum() // 2),
            "unequal_split_orders": 1,  # 5463.33/5463.34 — округление при делении 16 390 на 3
        },
        "top_courses": courses.head(6).reset_index()[["course", "revenue", "rev_share_pct", "buyers"]].to_dict("records"),
        "ai_agents": {"first_sale": str(courses.loc["AI агенты", "first_sale"].date()),
                      "revenue": round(float(courses.loc["AI агенты", "revenue"])),
                      "rev_share_pct": float(courses.loc["AI агенты", "rev_share_pct"])},
    }
    (PROCESSED / "key_facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ figures
    # Fig 1: дневные заказы + выручка + события
    fig, ax = plt.subplots(figsize=(13, 5.2))
    ax.bar(daily.date, daily.orders, color=[C_ACC if w else C_MAIN for w in daily.is_weekend], width=0.8, label="заказы/день (оранжевые — выходные)")
    ax.axhline(baseline_orders, color=C_GREY, ls="--", lw=1, label=f"медиана обычного дня = {baseline_orders:.0f} заказов")
    for name, a, b in WAVES:
        ax.axvspan(pd.Timestamp(a) - pd.Timedelta(hours=12), pd.Timestamp(b) + pd.Timedelta(hours=12), color=C_RED, alpha=0.07)
        ax.text(pd.Timestamp(a) + pd.Timedelta(days=1), daily.orders.max() * 1.02, name, ha="center", fontsize=8.5, color=C_RED)
    for dt, label in EVENTS:
        ax.annotate(label, xy=(pd.Timestamp(dt), d.loc[dt, "orders"]), xytext=(0, 28), textcoords="offset points",
                    ha="center", fontsize=7.5, arrowprops=dict(arrowstyle="-", color=C_GREY, lw=0.8), color="#333")
    ax2 = ax.twinx()
    ax2.plot(daily.date, daily.revenue / 1000, color="#2a9d8f", lw=1.6, marker="o", ms=3, label="выручка, тыс. ₽")
    ax2.set_ylabel("выручка, тыс. ₽"); ax2.spines["top"].set_visible(False)
    ax.set_ylabel("заказов в день"); ax.set_ylim(0, daily.orders.max() * 1.18)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m")); ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.set_title("Продажи по дням (реальные данные) и маркетинговые события, восстановленные из публичного канала", fontsize=11, loc="left")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(FIGURES / "fig1_daily_orders_events.png", dpi=160); plt.close(fig)

    # Fig 2: цены по дням (каждая строка — точка), линейки СТАРТ/ПРО
    fig, ax = plt.subplots(figsize=(13, 4.6))
    colors = {"СТАРТ": C_MAIN, "ПРО": C_RED, "Другое": C_GREY}
    for line, g in items.groupby("line"):
        jitter = (np.random.RandomState(0).rand(len(g)) - 0.5) * 0.6
        ax.scatter(g.timestamp + pd.to_timedelta(jitter, unit="D"), g.amount, s=14, alpha=0.55, color=colors[line], label=f"{line} (n={len(g)})", edgecolor="none")
    for y, t in [(8950, "полная цена 8 950"), (7475, "«2 за 14 950» → 7 475"), (6490, "старт −27% → 6 490"), (4995, "«2 за 9 990» → 4 995")]:
        ax.axhline(y, color=C_GREY, lw=0.6, ls=":"); ax.text(items.timestamp.max() + pd.Timedelta(days=0.6), y, t, fontsize=7.5, va="center", color="#444")
    for name, a, b in WAVES:
        ax.axvspan(pd.Timestamp(a) - pd.Timedelta(hours=12), pd.Timestamp(b) + pd.Timedelta(hours=12), color=C_RED, alpha=0.06)
    ax.set_ylim(0, 12000); ax.set_ylabel("amount за строку (курс), ₽"); ax.set_xlim(items.timestamp.min() - pd.Timedelta(days=1), items.timestamp.max() + pd.Timedelta(days=9))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m")); ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.set_title("Уровни цен: глубокая скидка в августе (СТАРТ) vs почти полная цена в сентябре (ПРО)", fontsize=11, loc="left")
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    fig.tight_layout(); fig.savefig(FIGURES / "fig2_price_dynamics.png", dpi=160); plt.close(fig)

    # Fig 3: продукты — выручка и дата первой продажи
    fig, ax = plt.subplots(figsize=(9, 5.6))
    cs = courses.sort_values("revenue")
    ax.barh(cs.index, cs.revenue / 1000, color=[C_RED if c == "AI агенты" else C_MAIN for c in cs.index])
    for i, (c, r) in enumerate(cs.iterrows()):
        ax.text(r.revenue / 1000 + 5, i, f"{r.rev_share_pct:.0f}%  · {r.buyers} пок. · с {r.first_sale:%d.%m}", va="center", fontsize=8)
    ax.set_xlabel("выручка, тыс. ₽"); ax.set_xlim(0, cs.revenue.max() / 1000 * 1.45)
    ax.set_title("Выручка по продуктам (AI агенты — запуск 22.08, 12% выручки за 19 дней)", fontsize=11, loc="left")
    fig.tight_layout(); fig.savefig(FIGURES / "fig3_products.png", dpi=160); plt.close(fig)

    # Fig 4: день недели × час
    hm = orders.assign(dow=orders.ts.dt.dayofweek, hour=orders.ts.dt.hour).pivot_table(index="dow", columns="hour", values="order_id", aggfunc="size").fillna(0)
    hm = hm.reindex(index=range(7), columns=range(24)).fillna(0)
    fig, ax = plt.subplots(figsize=(11, 3.6))
    im = ax.imshow(hm.values, cmap="Blues", aspect="auto")
    ax.set_yticks(range(7)); ax.set_yticklabels(["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]); ax.set_xticks(range(0, 24, 2)); ax.set_xlabel("час (МСК)")
    ax.set_title(f"Когда покупают: {facts['weekend_orders_pct']:.0f}% заказов — в выходные, пик 14–19 МСК (число заказов)", fontsize=11, loc="left")
    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    fig.tight_layout(); fig.savefig(FIGURES / "fig4_dow_hour.png", dpi=160); plt.close(fig)

    # Fig 5: структура заказов
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    vc = orders.n_items.value_counts().sort_index()
    axes[0].bar(vc.index.astype(str), vc.values, color=C_MAIN); axes[0].set_title("курсов в заказе", fontsize=10)
    for i, v in enumerate(vc.values): axes[0].text(i, v + 5, str(v), ha="center", fontsize=8)
    wk = orders.assign(week=orders.ts.dt.to_period("W-SUN").dt.start_time).groupby("week").is_bundle.mean() * 100
    axes[1].bar(wk.index.strftime("%d.%m"), wk.values, color=C_ACC); axes[1].set_title("доля пакетных заказов по неделям, %", fontsize=10)
    pv = per_student.n_orders.value_counts().sort_index()
    axes[2].bar(pv.index.astype(str), pv.values, color=C_GREY); axes[2].set_title(f"заказов на покупателя (повторные: {facts['repeat_buyers_pct']}%)", fontsize=10)
    for i, v in enumerate(pv.values): axes[2].text(i, v + 5, str(v), ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(FIGURES / "fig5_order_structure.png", dpi=160); plt.close(fig)

    print(json.dumps({k: v for k, v in facts.items() if k not in ("waves", "top_courses")}, ensure_ascii=False, indent=1))
    print(waves.to_string())


if __name__ == "__main__":
    main()
