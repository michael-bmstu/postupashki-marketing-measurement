"""
Общие функции: загрузка base.xlsx, сборка заказов, константы проекта.

Ключевые определения (см. README, раздел «Assumptions»):
  * строка base.xlsx = order item — доступ к одному курсу;
  * заказ (order) = все строки одного student_id с ОДИНАКОВЫМ timestamp (до секунды);
    в многострочных заказах amount — равная доля общей суммы заказа
    (доказательство: 5463.33 + 5463.33 + 5463.34 = 16 390; 2237.5 × 4 = 8 950; 4995 × 2 = 9 990);
  * order_total = сумма amount по строкам заказа;
  * уникальный покупатель = student_id;
  * повторная покупка = ещё один заказ того же student_id с другим timestamp.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "base.xlsx"
PROCESSED = ROOT / "data" / "processed"
SYNTHETIC = ROOT / "data" / "synthetic"
COLLECTED = ROOT / "data" / "collected"
FIGURES = ROOT / "figures"
REPORTS = ROOT / "reports"

for _d in (PROCESSED, SYNTHETIC, COLLECTED, FIGURES, REPORTS):
    _d.mkdir(parents=True, exist_ok=True)

# Линейки продуктов: нужны для группировки и для сопоставления с постами.
COURSE_FAMILY = {
    "Аналитика старт": "Аналитика", "Аналитика про": "Аналитика", "АВ тестам": "Аналитика",
    "ML старт": "ML", "ML про": "ML", "AI агенты": "AI агенты",
    "Backend старт": "Backend", "Backend про": "Backend",
    "Алгоритмы старт": "Алгоритмы", "Алгоритмы про": "Алгоритмы", "Алгоритмы": "Алгоритмы",
    "Data Science": "Data", "Data Engenering": "Data",
    "Мат анализ": "Математика", "Линейная алгебра": "Математика", "Теория вероятностей": "Математика",
    "Дискретка": "Математика", "К ВУЗу": "К ВУЗу",
}
COURSE_LINE = {  # СТАРТ / ПРО / прочее — линейки, которыми оперирует маркетинг канала
    c: ("СТАРТ" if "старт" in c.lower() else "ПРО" if ("про" in c.lower() or c == "AI агенты") else "Другое")
    for c in COURSE_FAMILY
}

# Полная цена (mode цен в одиночных заказах вне акций) — используется для расчёта глубины скидки.
LIST_PRICE_DEFAULT = 8950.0
LIST_PRICE = {
    "Мат анализ": 9950.0, "Линейная алгебра": 9950.0, "Теория вероятностей": 9950.0,
    "К ВУЗу": 6950.0, "Data Science": 6950.0, "Data Engenering": 6950.0,
}


def load_raw() -> pd.DataFrame:
    df = pd.read_excel(RAW)
    df.columns = ["student_id", "amount", "course", "timestamp"]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "student_id", "course"]).reset_index(drop=True)
    df["item_id"] = range(1, len(df) + 1)
    return df


def build_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Возвращает (order_items, orders)."""
    items = df.copy()
    items["order_id"] = items.groupby(["student_id", "timestamp"], sort=False).ngroup() + 1
    items["family"] = items.course.map(COURSE_FAMILY).fillna("Другое")
    items["line"] = items.course.map(COURSE_LINE).fillna("Другое")
    items["list_price"] = items.course.map(LIST_PRICE).fillna(LIST_PRICE_DEFAULT)
    items["discount_pct"] = (1 - items.amount / items.list_price).clip(lower=-1).round(3)

    orders = (
        items.groupby("order_id")
        .agg(
            student_id=("student_id", "first"),
            ts=("timestamp", "first"),
            n_items=("course", "size"),
            order_total=("amount", "sum"),
            courses=("course", lambda s: " + ".join(sorted(s))),
            lines=("line", lambda s: "/".join(sorted(set(s)))),
        )
        .reset_index()
    )
    orders["date"] = orders.ts.dt.date
    orders["is_bundle"] = orders.n_items > 1
    # порядковый номер заказа у покупателя → повторные покупки
    orders = orders.sort_values(["student_id", "ts"])
    orders["order_seq"] = orders.groupby("student_id").cumcount() + 1
    orders["is_repeat"] = orders.order_seq > 1
    orders = orders.sort_values("ts").reset_index(drop=True)

    # флаги аномалий — не удаляем, только помечаем
    items["flag_low_amount"] = items.amount <= 1000
    items["flag_high_amount"] = (items.amount >= 15000)
    dup = items.duplicated(["student_id", "course"], keep=False)
    items["flag_same_course_twice"] = dup
    return items, orders


def daily_frame(orders: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    idx = pd.date_range(orders.ts.min().normalize(), orders.ts.max().normalize(), freq="D")
    d = orders.groupby(orders.ts.dt.normalize()).agg(orders=("order_id", "size"), revenue=("order_total", "sum"),
                                                    buyers=("student_id", "nunique"))
    it = items.groupby(items.timestamp.dt.normalize()).agg(items=("course", "size"),
                                                          avg_discount=("discount_pct", "mean"))
    d = d.join(it, how="outer").reindex(idx).fillna({"orders": 0, "revenue": 0, "buyers": 0, "items": 0})
    d.index.name = "date"
    d["dow"] = d.index.day_name().str[:3]
    d["is_weekend"] = d.index.dayofweek >= 5
    return d.reset_index()
