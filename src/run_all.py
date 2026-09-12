"""
End-to-end запуск measurement-пайплайна:

  [1] tg_collector   (опционально, --collect; нужен интернет)  → data/collected/tg_posts_*.csv      [REAL]
  [2] post_classifier                                          → posts_classified, marketing_calendar [REAL]
  [3] eda                                                      → orders, daily, key_facts, fig1–5     [REAL]
  [4] make_synthetic                                           → ad_registry, touches                [SYNTHETIC]
  [5] build_mart                                               → pmm.sqlite (schema.sql)              [REAL + SYNTHETIC]
  [6] attribution                                              → attribution_result                   [DEMO]
  [7] romi                                                     → romi_by_*, fig6                      [DEMO]
  [8] uplift                                                   → uplift_waves, fig7                   [REAL, not causal]
  [9] forecast                                                 → backtest, next7, fig8                [REAL]
  [10] tracking_bot --simulate                                 → 3 «реальных» события в fact_touch     [DEMO]
  [11] reports/summary.md

python src/run_all.py            # использует уже собранные посты из data/collected
python src/run_all.py --collect  # заново собирает посты канала из t.me/s/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent


def run(script: str, *args: str) -> None:
    print(f"\n=== {script} {' '.join(args)}")
    subprocess.run([sys.executable, str(SRC / script), *args], check=True, cwd=ROOT)


def md_table(df: pd.DataFrame) -> str:
    """Markdown-таблица без зависимости от tabulate."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(f"{v:,.1f}" if isinstance(v, float) else str(v) for v in row) + " |")
    return "\n".join(lines)


def summary() -> None:
    P = ROOT / "data" / "processed"
    facts = json.loads((P / "key_facts.json").read_text(encoding="utf-8"))
    waves = pd.read_csv(P / "waves.csv")
    up = pd.read_csv(P / "uplift_waves.csv")
    romi_ch = pd.read_csv(P / "romi_by_channel.csv")
    metrics = pd.read_csv(P / "forecast_metrics.csv")
    nxt = pd.read_csv(P / "forecast_next7.csv")
    att = pd.read_csv(P / "attribution_summary.csv")
    posts = pd.read_csv(P / "posts_classified.csv")

    md = [f"# Сводка пайплайна\n",
          "## Что мы знаем (реальные данные)\n",
          f"- {facts['rows']} строк · {facts['orders']} заказов · {facts['buyers']} покупателей · {facts['courses']} продуктов · {facts['period']} ({facts['days']} дней)",
          f"- Выручка {facts['revenue_total']:,} ₽; средний чек заказа {facts['avg_order_total']:,} ₽ (медиана {facts['median_order_total']:,}); пакетных заказов {facts['bundle_orders_pct']}% ({facts['bundle_revenue_pct']}% выручки)",
          f"- Повторные покупатели: {facts['repeat_buyers']} ({facts['repeat_buyers_pct']}%), медианный интервал {facts['repeat_gap_median_days']} дн., p75 = {facts['repeat_gap_p75_days']} дн.",
          f"- {facts['weekend_orders_pct']}% заказов — в выходные; пик {facts['peak_hours_msk']} МСК; обычный день = {facts['baseline_orders_per_day_median']:.0f} заказов / {facts['baseline_revenue_per_day_median']:,} ₽",
          f"- Лучший день: {facts['top_day']['date']} — {facts['top_day']['orders']} заказов, {facts['top_day']['revenue']:,} ₽\n",
          "### Волны продаж\n", waves.pipe(md_table), "",
          "### Посты собственного канала (собрано из публичного превью)\n", posts.post_class.value_counts().rename_axis("class").reset_index(name="posts").pipe(md_table), "",
          "## Что мы оцениваем\n",
          "### Наивный uplift волн (НЕ каузальный)\n", up.drop(columns=["note"]).pipe(md_table), "",
          "### Атрибуция (ДЕМО на синтетических касаниях)\n", att.pipe(md_table), "",
          "### ROMI по каналам (ДЕМО: синтетические касания и стоимость)\n", romi_ch.pipe(md_table), "",
          "### Прогноз: backtest\n", metrics.pipe(md_table), "",
          "### Прогноз на 7 дней\n", nxt.pipe(md_table), ""]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nsaved -> {ROOT / 'reports' / 'summary.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true", help="заново собрать посты канала (нужен интернет)")
    args = ap.parse_args()
    if args.collect:
        run("tg_collector.py", "--channel", "postypashki_old", "--since", "2026-07-20", "--out", "data/collected/tg_posts_postypashki_old.csv")
    run("post_classifier.py")
    run("eda.py")
    run("make_synthetic.py")
    run("build_mart.py")
    run("attribution.py")
    run("romi.py")
    run("uplift.py")
    run("forecast.py")
    run("tracking_bot.py", "--simulate")
    summary()


if __name__ == "__main__":
    main()
