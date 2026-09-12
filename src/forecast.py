"""
Задача 9. Прогноз продаж: baseline-модели + честный backtest на короткой истории (38 дней).

Целевая метрика: число заказов в день (стабильнее выручки; выручка = заказы × средний чек ≈ 9.4K ₽).
Гранулярность: день. Горизонт: 7 дней. Сегментация: без сегментации (мало данных), линейки — как расширение.

Модели (все простые, без обучения «весов»):
  naive          — последнее значение
  mean7          — среднее за 7 дней
  seasonal_naive — значение неделю назад
  dow_profile    — уровень (среднее за 14 дней) × индекс дня недели
  promo_aware    — dow_profile + средний эффект «дня волны», оценённый по ПРОШЛЫМ волнам,
                   применяется к будущим датам из маркетингового календаря (то самое «будущее маркетинговое признак»)

Backtest: скользящее начало (origin) по последним 14 дням, горизонт 1–7, метрики MAE / WAPE.
Прогноз на 7 дней вперёд с эмпирическим интервалом (квантили ошибок backtest).

Выход: data/processed/forecast_backtest.csv, forecast_next7.csv, figures/fig8_forecast.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import FIGURES, PROCESSED

HORIZON = 7
WAVE_DATES = {  # известный календарь: даты «дней волны» (из marketing_calendar.csv); в проде — из реестра размещений
    pd.Timestamp(d) for d in ["2026-08-08", "2026-08-09", "2026-08-10", "2026-08-22", "2026-08-23", "2026-08-24", "2026-09-04", "2026-09-05", "2026-09-06"]
}
FUTURE_WAVE_DATES: set = set()  # на 11–17 сентября запланированных акций в календаре нет


def dow_index(y: pd.Series) -> pd.Series:
    idx = y.groupby(y.index.dayofweek).mean() / y.mean()
    return idx.reindex(range(7)).fillna(1.0)


def forecast(y: pd.Series, origin: pd.Timestamp, horizon: int, model: str, wave_dates: set) -> pd.Series:
    hist = y.loc[:origin]
    future = pd.date_range(origin + pd.Timedelta(days=1), periods=horizon, freq="D")
    if model == "naive":
        vals = np.full(horizon, hist.iloc[-1])
    elif model == "mean7":
        vals = np.full(horizon, hist.iloc[-7:].mean())
    elif model == "seasonal_naive":
        vals = np.array([hist.get(dt - pd.Timedelta(days=7), hist.iloc[-7:].mean()) for dt in future])
    elif model in ("dow_profile", "promo_aware"):
        normal = hist[~hist.index.isin(wave_dates)]
        level = normal.iloc[-14:].mean()
        di = dow_index(normal)
        vals = np.array([level * di[dt.dayofweek] for dt in future])
        if model == "promo_aware":
            past_wave = hist[hist.index.isin(wave_dates)]
            if len(past_wave):
                wave_effect = past_wave.mean() - normal.mean()  # средний прирост в день волны по прошлым волнам
                vals = np.array([v + (wave_effect if dt in wave_dates else 0) for v, dt in zip(vals, future)])
    else:
        raise ValueError(model)
    return pd.Series(np.clip(vals, 0, None), index=future)


def main() -> None:
    d = pd.read_csv(PROCESSED / "daily.csv", parse_dates=["date"]).set_index("date")
    y = d.orders.astype(float)
    y = y.iloc[:-1]  # последний день (10.09) неполный — исключаем из обучения и оценки
    models = ["naive", "mean7", "seasonal_naive", "dow_profile", "promo_aware"]

    # --- backtest: origins — последние 14 дней, для каждого прогноз на 1..7 вперёд (в пределах данных)
    origins = y.index[-15:-1]
    rows = []
    for origin in origins:
        for model in models:
            fc = forecast(y, origin, HORIZON, model, WAVE_DATES)
            for h, (dt, pred) in enumerate(fc.items(), start=1):
                if dt in y.index:
                    rows.append({"origin": origin, "date": dt, "h": h, "model": model, "y": y[dt], "pred": pred, "abs_err": abs(y[dt] - pred)})
    bt = pd.DataFrame(rows)
    bt.to_csv(PROCESSED / "forecast_backtest.csv", index=False)
    metrics = bt.groupby("model").agg(MAE=("abs_err", "mean"), WAPE=("abs_err", lambda s: s.sum() / bt.loc[s.index, "y"].sum()),
                                     n=("abs_err", "size")).round(2).sort_values("MAE")
    metrics_h1 = bt[bt.h == 1].groupby("model").abs_err.mean().round(2).rename("MAE_h1")
    metrics = metrics.join(metrics_h1)
    metrics.to_csv(PROCESSED / "forecast_metrics.csv")

    # --- прогноз вперёд лучшей моделью + интервал из ошибок backtest
    best = metrics.index[0]
    origin = y.index[-1]
    fc = forecast(y, origin, HORIZON, best, WAVE_DATES | FUTURE_WAVE_DATES)
    errs = (bt[bt.model == best].y - bt[bt.model == best].pred)
    q10, q90 = np.percentile(errs, [10, 90])
    nxt = pd.DataFrame({"date": fc.index, "model": best, "orders_pred": fc.values.round(1),
                        "orders_p10": np.clip(fc.values + q10, 0, None).round(1), "orders_p90": (fc.values + q90).round(1)})
    avg_check = float(pd.read_csv(PROCESSED / "orders.csv").order_total.mean())
    nxt["revenue_pred_rub"] = (nxt.orders_pred * avg_check).round()
    nxt.to_csv(PROCESSED / "forecast_next7.csv", index=False)

    # --- figure: факт + прогнозы h=1 по backtest + будущее
    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.plot(y.index, y.values, color="#1f4e79", marker="o", ms=3, lw=1.5, label="факт, заказов/день")
    for model, c in [("mean7", "#8c8c8c"), ("dow_profile", "#e8a33d"), ("promo_aware", "#2a9d8f")]:
        b1 = bt[(bt.model == model) & (bt.h == 1)].sort_values("date")
        ax.plot(b1.date, b1.pred, color=c, ls="--", lw=1.3, label=f"{model} (backtest, h=1), MAE={metrics.loc[model, 'MAE']:.1f}")
    ax.plot(nxt.date, nxt.orders_pred, color="#d62828", lw=2, label=f"прогноз 7 дн. ({best})")
    ax.fill_between(nxt.date, nxt.orders_p10, nxt.orders_p90, color="#d62828", alpha=0.15, label="p10–p90 (ошибки backtest)")
    for dt in WAVE_DATES:
        ax.axvspan(dt - pd.Timedelta(hours=12), dt + pd.Timedelta(hours=12), color="#d62828", alpha=0.05)
    ax.set_ylabel("заказов в день"); ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.set_title(f"Прогноз заказов: baseline-модели и backtest на последних 14 днях (WAPE лучшей = {metrics.WAPE.iloc[0]:.0%})", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(FIGURES / "fig8_forecast.png", dpi=150); plt.close(fig)

    print(metrics.to_string()); print(); print(nxt.to_string(index=False))
    print(f"\nСредний чек для перевода в выручку: {avg_check:,.0f} ₽; сумма прогноза 7 дней: {nxt.orders_pred.sum():.0f} заказов ≈ {nxt.revenue_pred_rub.sum()/1e3:,.0f} тыс. ₽")


if __name__ == "__main__":
    main()
