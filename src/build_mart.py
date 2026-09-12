"""
Data mart — загрузка реальных и синтетических данных в SQLite по схеме sql/schema.sql.

Выход: data/processed/pmm.sqlite (pmm = Postupashki Marketing Measurement)
Каждая строка несёт data_origin: 'real' | 'synthetic' | 'real_post/synthetic_cost'.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from common import COLLECTED, COURSE_FAMILY, COURSE_LINE, LIST_PRICE, LIST_PRICE_DEFAULT, PROCESSED, ROOT, SYNTHETIC
from make_synthetic import user_hash

DB = PROCESSED / "pmm.sqlite"


def main() -> None:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))

    # --- измерения
    pd.read_csv(SYNTHETIC / "channels.csv").to_sql("dim_channel", con, if_exists="append", index=False)
    pd.read_csv(SYNTHETIC / "campaigns.csv").to_sql("dim_campaign", con, if_exists="append", index=False)
    creatives = pd.DataFrame([
        ("cr_sale", "sale", 35.0, None, "real_post/synthetic_cost"), ("cr_launch", "launch", 16.0, None, "real_post/synthetic_cost"),
        ("cr_native_promo", "native", 0.0, None, "real_post/synthetic_cost"), ("cr_lead_magnet", "lead_magnet", 0.0, None, "real_post/synthetic_cost"),
        ("cr_native", "native", 0.0, None, "synthetic"),
    ], columns=["creative_id", "offer_type", "discount_pct", "promo_code", "data_origin"])
    creatives.to_sql("dim_creative", con, if_exists="append", index=False)

    reg = pd.read_csv(SYNTHETIC / "ad_registry.csv")
    reg_db = reg.drop(columns=["opportunity_cost_rub"]).copy()
    reg_db.to_sql("dim_placement", con, if_exists="append", index=False)

    items = pd.read_csv(PROCESSED / "order_items.csv", parse_dates=["timestamp"])
    orders = pd.read_csv(PROCESSED / "orders.csv", parse_dates=["ts"])
    courses = pd.DataFrame({"course_name": sorted(items.course.unique())})
    courses["course_id"] = "crs_" + courses.index.astype(str).str.zfill(2)
    courses["family"] = courses.course_name.map(COURSE_FAMILY)
    courses["product_line"] = courses.course_name.map(COURSE_LINE)
    courses["list_price_rub"] = courses.course_name.map(LIST_PRICE).fillna(LIST_PRICE_DEFAULT)
    courses["margin_pct"] = 1.0
    courses[["course_id", "course_name", "family", "product_line", "list_price_rub", "margin_pct"]].to_sql("dim_course", con, if_exists="append", index=False)
    cid = dict(zip(courses.course_name, courses.course_id))

    # --- пользователи (реальные покупатели под хешем + синтетические непокупатели)
    touches = pd.read_csv(SYNTHETIC / "touches.csv", parse_dates=["ts"])
    users = pd.DataFrame({"user_hash": orders.student_id.map(user_hash), "first_seen_at": orders.ts}).groupby("user_hash").first_seen_at.min().reset_index()
    users["username_hash"] = users.user_hash  # в base.xlsx student_id уже = hash(username) → тот же ключ
    users["data_origin"] = "real"
    non = touches[~touches.user_hash.isin(users.user_hash)].groupby("user_hash").ts.min().reset_index().rename(columns={"ts": "first_seen_at"})
    non["username_hash"] = None; non["data_origin"] = "synthetic"
    first_touch = touches.sort_values("ts").groupby("user_hash").placement_id.first()
    all_users = pd.concat([users, non], ignore_index=True)
    all_users["first_placement_id"] = all_users.user_hash.map(first_touch)
    all_users["first_seen_at"] = pd.to_datetime(all_users.first_seen_at).dt.strftime("%Y-%m-%d %H:%M:%S")
    all_users.to_sql("dim_user", con, if_exists="append", index=False)

    # --- факты
    t = touches.drop(columns=["converted"]).copy()
    t["ts"] = t.ts.dt.strftime("%Y-%m-%d %H:%M:%S")
    t.to_sql("fact_touch", con, if_exists="append", index=False)

    leads = touches[touches.touch_type == "manager_chat_open"][["user_hash", "placement_id", "ts"]].rename(columns={"placement_id": "source_placement_id"})
    leads["ts"] = leads.ts.dt.strftime("%Y-%m-%d %H:%M:%S"); leads["status"] = "new"; leads["data_origin"] = "synthetic"
    leads.to_sql("fact_lead", con, if_exists="append", index=False)

    fo = pd.DataFrame({"order_id": orders.order_id, "user_hash": orders.student_id.map(user_hash),
                       "ts": orders.ts.dt.strftime("%Y-%m-%d %H:%M:%S"), "order_total_rub": orders.order_total,
                       "n_items": orders.n_items, "is_bundle": orders.is_bundle.astype(int), "order_seq": orders.order_seq,
                       "data_origin": "real"})
    fo.to_sql("fact_order", con, if_exists="append", index=False)
    fi = pd.DataFrame({"item_id": items.item_id, "order_id": items.order_id, "course_id": items.course.map(cid),
                       "amount_rub": items.amount, "list_price_rub": items.list_price, "discount_pct": items.discount_pct})
    fi.to_sql("fact_order_item", con, if_exists="append", index=False)

    posts = pd.read_csv(PROCESSED / "posts_classified.csv")
    fp = pd.DataFrame({"post_id": "postypashki_old/" + posts.message_id.astype(str), "channel_id": "own_tg_main",
                       "message_id": posts.message_id, "published_at": posts.published_msk, "post_class": posts.post_class,
                       "views_public": posts.views, "has_manager_cta": posts.has_manager_cta,
                       "placement_id": ("p_own_" + posts.message_id.astype(str)).where(("p_own_" + posts.message_id.astype(str)).isin(reg.placement_id)),
                       "text": posts.text, "data_origin": "real"})
    fp.to_sql("fact_post", con, if_exists="append", index=False)
    con.commit()

    for tbl in ["dim_channel", "dim_campaign", "dim_placement", "dim_course", "dim_user", "fact_touch", "fact_lead", "fact_order", "fact_order_item", "fact_post"]:
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"{tbl:16s} {n:6d}")
    con.close()
    print(f"saved -> {DB}")


if __name__ == "__main__":
    main()
