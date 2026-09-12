"""
ROMI calculator (Задача 8) — ROMI_attr на уровне размещения / канала / кампании.

ROMI_attr = (attributed_value − cost) / cost,  attributed_value = attributed_revenue × margin.
  * margin по умолчанию 1.0 (выручка). Параметр --margin 0.7 даёт contribution-margin вариант.
  * cost для внешних размещений — из реестра (здесь СИНТЕТИЧЕСКИЙ);
    для постов собственного канала прямых затрат нет → считаем два варианта:
      - direct: cost = 0 → ROMI не определён, показываем revenue per 1K views (RPM);
      - opportunity: cost = упущенная выручка от продажи рекламного слота (ASSUMPTION 20 000 ₽/пост).
  * CAC = cost / attributed_orders;  payback = cost / attributed_revenue.

ROMI_inc (инкрементальный) здесь НЕ считается: для него нужен эксперимент (см. docs/experiments.md, uplift.py).

Выход: data/processed/romi_by_placement.csv, romi_by_channel.csv, romi_by_campaign.csv, romi_sensitivity.csv
       figures/fig6_romi_by_placement.png
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from common import FIGURES, PROCESSED, SYNTHETIC

DEFAULT_MODEL, DEFAULT_WINDOW = "position", 14


def romi_table(att: pd.DataFrame, reg: pd.DataFrame, model: str, window: int, margin: float, cost_mode: str) -> pd.DataFrame:
    a = att[(att.model == model) & (att.window_days == window)]
    a = a.groupby("placement_id").agg(attributed_revenue_rub=("attributed_revenue_rub", "sum"), attributed_orders=("attributed_orders", "sum")).reset_index()
    t = reg.merge(a, on="placement_id", how="left").fillna({"attributed_revenue_rub": 0, "attributed_orders": 0})
    t["cost_used_rub"] = t.cost_rub if cost_mode == "direct" else t.cost_rub + t.opportunity_cost_rub
    t["attributed_value_rub"] = t.attributed_revenue_rub * margin
    t["romi_attr"] = ((t.attributed_value_rub - t.cost_used_rub) / t.cost_used_rub).where(t.cost_used_rub > 0)
    t["cac_rub"] = (t.cost_used_rub / t.attributed_orders).where(t.attributed_orders > 0)
    t["rpm_rub"] = (t.attributed_revenue_rub / t.views_public * 1000).where(t.views_public > 0)  # выручка на 1000 просмотров
    t["model"] = model; t["window_days"] = window; t["margin"] = margin; t["cost_mode"] = cost_mode
    return t


def aggregate(t: pd.DataFrame, key: str) -> pd.DataFrame:
    g = t.groupby(key).agg(placements=("placement_id", "size"), cost_used_rub=("cost_used_rub", "sum"),
                           attributed_revenue_rub=("attributed_revenue_rub", "sum"), attributed_value_rub=("attributed_value_rub", "sum"),
                           attributed_orders=("attributed_orders", "sum"), views=("views_public", "sum"))
    g["romi_attr"] = ((g.attributed_value_rub - g.cost_used_rub) / g.cost_used_rub).where(g.cost_used_rub > 0)
    g["cac_rub"] = (g.cost_used_rub / g.attributed_orders).where(g.attributed_orders > 0)
    g["rpm_rub"] = (g.attributed_revenue_rub / g.views * 1000).where(g.views > 0)
    return g.round(1).reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL); ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument("--margin", type=float, default=1.0)
    args = ap.parse_args()

    att = pd.read_csv(PROCESSED / "attribution_by_placement.csv")
    reg = pd.read_csv(SYNTHETIC / "ad_registry.csv")

    base = romi_table(att, reg, args.model, args.window, args.margin, "opportunity")
    base.sort_values("romi_attr", ascending=False).round(1).to_csv(PROCESSED / "romi_by_placement.csv", index=False)
    aggregate(base, "channel_id").to_csv(PROCESSED / "romi_by_channel.csv", index=False)
    aggregate(base, "campaign_id").to_csv(PROCESSED / "romi_by_campaign.csv", index=False)

    # чувствительность: модель × окно × cost_mode — насколько «прыгает» ROMI канала от методологии
    rows = []
    for model in ["first", "last", "linear", "time_decay", "position"]:
        for window in [7, 14, 30]:
            for cost_mode in ["direct", "opportunity"]:
                t = romi_table(att, reg, model, window, args.margin, cost_mode)
                g = aggregate(t, "channel_id")
                for r in g.itertuples(index=False):
                    rows.append({"model": model, "window_days": window, "cost_mode": cost_mode, "channel_id": r.channel_id,
                                 "romi_attr": r.romi_attr, "attributed_revenue_rub": r.attributed_revenue_rub, "cac_rub": r.cac_rub})
    sens = pd.DataFrame(rows)
    sens.to_csv(PROCESSED / "romi_sensitivity.csv", index=False)

    # --- figure
    t = base.sort_values("romi_attr", ascending=True)
    t = t[t.cost_used_rub > 0]
    fig, ax = plt.subplots(figsize=(11, 9))
    colors = ["#d62828" if o == "synthetic" else "#1f4e79" for o in t.data_origin]
    ax.barh(t.placement_id, t.romi_attr, color=colors)
    for i, r in enumerate(t.itertuples(index=False)):
        ax.text(max(r.romi_attr, 0) + 0.2, i, f"{r.attributed_revenue_rub/1000:.0f}K ₽ / {r.attributed_orders:.0f} зак. / cost {r.cost_used_rub/1000:.0f}K", va="center", fontsize=7)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel(f"ROMI_attr, модель {args.model}, окно {args.window} д, margin={args.margin}")
    ax.set_title("ROMI по размещениям — ДЕМО на синтетических касаниях и синтетической стоимости\n"
                 "синие = реальные посты своего канала (cost = opportunity 20K ₽, ASSUMPTION); красные = вымышленные внешние закупки", fontsize=10, loc="left")
    ax.set_xlim(left=min(-1.5, t.romi_attr.min() - 0.5), right=t.romi_attr.max() * 1.6)
    fig.tight_layout(); fig.savefig(FIGURES / "fig6_romi_by_placement.png", dpi=150); plt.close(fig)

    print("ROMI by channel (DEMO):"); print(aggregate(base, "channel_id").to_string(index=False))
    print("\nROMI by campaign (DEMO):"); print(aggregate(base, "campaign_id").to_string(index=False))
    piv = sens[(sens.cost_mode == "opportunity")].pivot_table(index="channel_id", columns=["window_days", "model"], values="romi_attr")
    print("\nSensitivity of channel ROMI to model × window (opportunity cost):"); print(piv.round(1).to_string())


if __name__ == "__main__":
    main()
