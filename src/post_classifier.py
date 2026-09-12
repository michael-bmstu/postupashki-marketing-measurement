"""
Post classifier — правило-ориентированная классификация публикаций собственного канала.

Вход:  data/collected/tg_posts_<channel>.csv (реальные посты, собранные tg_collector.py)
Выход: data/processed/posts_classified.csv
       data/processed/marketing_calendar.csv — восстановленный календарь маркетинговых событий

Классы (один пост — один основной класс, приоритет сверху вниз):
  external_ad   — реклама сторонних компаний в нашем канале («Реклама. ООО…», erid) → это ДОХОД канала, не расход
  sale          — распродажа / скидка / промокод / дедлайн скидки
  launch        — запуск новой линейки или продукта
  lead_magnet   — бесплатные интенсивы, «за подписку», открытая неделя (верх воронки)
  native_promo  — контент с продающим CTA («Записаться», ссылка на менеджера, «на наших курсах ПРО»)
  content       — гайды, сливы, дайджесты, интервью без явного CTA

Почему правила, а не ML: 72 поста, прозрачность важнее точности; правила легко править маркетологу.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

import pandas as pd

from common import COLLECTED, PROCESSED

MANAGER_LINK_RE = re.compile(r"t\.me/m/[A-Za-z0-9_-]+")
COURSE_LINK_RE = re.compile(r"old\.postypashki\.ru/карьерные-курсы/([^/\s|]+)/?")
DEADLINE_RE = re.compile(r"до (\d{1,2}) (август|сентябр)[а-я]*", re.I)

RULES = [
    ("external_ad", [r"\bреклама\.?\s", r"\berid\b", r"ИНН \d"]),
    ("sale", [r"распродаж", r"скидк[аиу]? ", r"скидки", r"промокод", r"финальн[а-я]+ \d+ час", r"последние \d+ час", r"продлеваем"]),
    ("launch", [r"запускаем", r"новое направление", r"выходим на новый уровень", r"новая линейка"]),
    ("lead_magnet", [r"за подписку", r"открыт[а-я]+ недел", r"мини-интенсив", r"проводим бесплатн", r"наш[а-я]* (первый )?(аналитическ[а-я]+ )?хакатон", r"вебинар"]),
    ("native_promo", [r"записаться", r"на наших (карьерных )?курсах", r"выложен[ыа]? на (наших )?курсах", r"курсах про", r"курсы про", r"наших курсах"]),
]
# Признаки партнёрской/платной интеграции в ссылках (erid — маркировка рекламы, utm_source=pr/tg_postypashki)
PARTNER_LINK_RE = re.compile(r"erid=|utm_source=(pr|tg_postypashki|telegram)\b", re.I)


def classify_text(text: str, links: str) -> tuple[str, str]:
    t = (text or "").lower()
    if PARTNER_LINK_RE.search(links or ""):
        return "external_ad", "partner_link"
    matched = []
    for label, pats in RULES:
        hits = [p for p in pats if re.search(p, t)]
        if hits:
            matched.append((label, hits[0]))
    if not matched:
        # ссылка на менеджера или на страницу курса без слов-триггеров — тоже мягкий CTA
        if MANAGER_LINK_RE.search(links or "") or COURSE_LINK_RE.search(unquote(links or "")):
            return "native_promo", "cta_link"
        return "content", ""
    return matched[0]


def main() -> None:
    src = COLLECTED / "tg_posts_postypashki_old.csv"
    p = pd.read_csv(src)
    p["published_at"] = pd.to_datetime(p.published_at, utc=True)
    p["published_msk"] = p.published_at.dt.tz_convert("Europe/Moscow").dt.tz_localize(None)
    p["date"] = p.published_msk.dt.date
    p["links_dec"] = p.links.fillna("").map(unquote)

    cls = p.apply(lambda r: classify_text(r.text if isinstance(r.text, str) else "", r.links_dec), axis=1)
    p["post_class"] = [c[0] for c in cls]
    p["matched_rule"] = [c[1] for c in cls]
    p["has_manager_cta"] = p.links_dec.str.contains(MANAGER_LINK_RE.pattern).astype(int)
    p["course_links"] = p.links_dec.map(lambda s: ";".join(sorted(set(COURSE_LINK_RE.findall(s)))))
    txt = p.text.fillna("")
    p["mentions_start"] = txt.str.contains(r"старт", case=False).astype(int)
    p["mentions_pro"] = txt.str.contains(r"\bпро\b|курсы про|курсах про|линейк", case=False).astype(int)
    p["deadline_mention"] = txt.map(lambda s: ";".join(f"{d} {m}" for d, m in DEADLINE_RE.findall(s)))
    p["title"] = txt.str.split("\n").str[0].str.slice(0, 80)

    # Пропуски message_id: удалённые посты ИЛИ элементы альбомов (файлы/фото в одной публикации).
    ids = p.message_id.sort_values().tolist()
    gaps = [j for i, k in zip(ids, ids[1:]) for j in range(i + 1, k)]
    p["prev_gap_ids"] = 0
    for i, k in zip(ids, ids[1:]):
        p.loc[p.message_id == k, "prev_gap_ids"] = k - i - 1

    cols = ["message_id", "published_msk", "date", "post_class", "matched_rule", "views", "title", "has_manager_cta",
            "course_links", "mentions_start", "mentions_pro", "deadline_mention", "has_media", "is_forward",
            "forward_from", "prev_gap_ids", "text_len", "text"]
    p[cols].to_csv(PROCESSED / "posts_classified.csv", index=False)

    # --- Календарь маркетинговых событий: наблюдаемые (из постов) + выведенные (из данных продаж)
    events = []
    for _, r in p[p.post_class.isin(["sale", "launch", "lead_magnet", "native_promo"])].iterrows():
        events.append({
            "event_id": f"post_{r.message_id}", "event_type": r.post_class,
            "start": r.published_msk.strftime("%Y-%m-%d %H:%M"), "end": "",
            "line": "СТАРТ" if r.mentions_start and not r.mentions_pro else "ПРО" if r.mentions_pro else "",
            "description": r.title, "evidence": "observed: public post", "source_post": int(r.message_id),
            "views": r.views, "cost_rub": "", "cost_note": "own channel: cost=0 (opportunity cost — see docs/romi.md)",
        })
    # Выведенные события: старт распродажи СТАРТ (пост-анонс не найден в превью — вероятно удалён), продление.
    events += [
        {"event_id": "inferred_sale_start_aug08", "event_type": "sale", "start": "2026-08-08 09:00", "end": "2026-08-10 23:59",
         "line": "СТАРТ", "description": "Финальная распродажа СТАРТ: «2 курса за 9 990», старт ~6 490 (−27…−45%)",
         "evidence": "inferred: цены 4 950/4 995/6 490 с 8 авг + пост 1837 «последние 6 часов» + 1838 «продлеваем до конца дня»",
         "source_post": "1835? (id отсутствует в превью)", "views": "", "cost_rub": "", "cost_note": ""},
        {"event_id": "inferred_pro_launch_price", "event_type": "launch", "start": "2026-08-22 13:19", "end": "2026-08-25 23:59",
         "line": "ПРО", "description": "Запуск линейки ПРО + AI агенты; launch-цена «2 курса за 14 950» (7 475 за курс, −16%)",
         "evidence": "observed post 1859 (35.7K views) + цены 7 475×2 с 22 авг", "source_post": 1859, "views": 35700, "cost_rub": "", "cost_note": ""},
        {"event_id": "external_tbank_deadline", "event_type": "external_demand", "start": "2026-08-31 00:00", "end": "2026-09-06 23:59",
         "line": "ПРО", "description": "Отбор на стажировку Т-Банк (дедлайн 6 сен) — серия постов «разбор экзамена на курсах ПРО»",
         "evidence": "observed posts 1875, 1877, 1878, 1880 + пик продаж 5–6 сен по полной цене", "source_post": "1875;1877;1878;1880", "views": "", "cost_rub": "", "cost_note": ""},
    ]
    cal = pd.DataFrame(events).sort_values("start")
    cal.to_csv(PROCESSED / "marketing_calendar.csv", index=False)

    print(p.post_class.value_counts().to_string())
    print(f"\nid gaps (deleted posts OR album items): {len(gaps)} missing ids in range {ids[0]}–{ids[-1]}")
    print(f"saved -> {PROCESSED / 'posts_classified.csv'}, {PROCESSED / 'marketing_calendar.csv'}")


if __name__ == "__main__":
    main()
