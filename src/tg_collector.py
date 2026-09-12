"""
Telegram collector — сбор истории ПУБЛИЧНОГО канала без админ-доступа и без API-ключей.

Источник: веб-превью t.me/s/<channel> (официальная публичная страница Telegram).
Пагинация назад через параметр ?before=<message_id>.

Что сохраняем по каждому посту:
    message_id, published_at (UTC), views, text, links, has_media, is_forward, forward_from

Использование:
    python src/tg_collector.py --channel postypashki_old --since 2026-07-25 \
        --out data/collected/tg_posts_postypashki_old.csv

Ограничения (честно):
  * превью показывает только не удалённые посты — удалённую рекламу так не восстановить;
  * views — публичный счётчик на момент сбора (не Telegram Insights);
  * нет данных о подписках/отписках, кликах по ссылкам, реакциях на уровне пользователя.
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import re
import sys
import time
from datetime import datetime, timezone

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

MSG_RE = re.compile(
    r'<div class="tgme_widget_message_wrap[^"]*">(.*?)(?=<div class="tgme_widget_message_wrap|</section>)',
    re.S,
)
ID_RE = re.compile(r'data-post="[^/]+/(\d+)"')
TIME_RE = re.compile(r'<time datetime="([^"]+)"')
VIEWS_RE = re.compile(r'tgme_widget_message_views">([^<]+)<')
TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
HREF_RE = re.compile(r'href="(https?://[^"]+)"')
FWD_RE = re.compile(r'tgme_widget_message_forwarded_from_name[^>]*>(.*?)</a>', re.S)
TAG_RE = re.compile(r'<[^>]+>')


def parse_views(s: str) -> int | None:
    s = s.strip().replace(",", ".")
    m = re.match(r"([\d.]+)\s*([KM]?)", s)
    if not m:
        return None
    val = float(m.group(1))
    mult = {"": 1, "K": 1_000, "M": 1_000_000}[m.group(2)]
    return int(val * mult)


def clean_text(fragment: str) -> str:
    fragment = fragment.replace("<br/>", "\n").replace("<br>", "\n")
    fragment = TAG_RE.sub("", fragment)
    return html_lib.unescape(fragment).strip()


def parse_page(page_html: str) -> list[dict]:
    posts = []
    for block in MSG_RE.findall(page_html):
        mid = ID_RE.search(block)
        ts = TIME_RE.search(block)
        if not mid or not ts:
            continue
        text_m = TEXT_RE.search(block)
        text = clean_text(text_m.group(1)) if text_m else ""
        links = sorted(set(h for h in HREF_RE.findall(block) if "t.me/postypashki_old" not in h))
        fwd = FWD_RE.search(block)
        posts.append(
            {
                "message_id": int(mid.group(1)),
                "published_at": datetime.fromisoformat(ts.group(1)).astimezone(timezone.utc).isoformat(),
                "views": parse_views(VIEWS_RE.search(block).group(1)) if VIEWS_RE.search(block) else None,
                "text": text,
                "links": " | ".join(links),
                "has_media": int("tgme_widget_message_photo" in block or "tgme_widget_message_video" in block),
                "is_forward": int(bool(fwd)),
                "forward_from": clean_text(fwd.group(1)) if fwd else "",
                "text_len": len(text),
            }
        )
    return posts


def collect(channel: str, since: datetime, max_pages: int = 60, pause: float = 1.0) -> list[dict]:
    url = f"https://t.me/s/{channel}"
    before: int | None = None
    all_posts: dict[int, dict] = {}
    for page in range(max_pages):
        params = {"before": before} if before else {}
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        posts = parse_page(r.text)
        if not posts:
            break
        for p in posts:
            all_posts[p["message_id"]] = p
        oldest = min(posts, key=lambda p: p["message_id"])
        oldest_dt = datetime.fromisoformat(oldest["published_at"])
        print(f"page {page + 1}: {len(posts)} posts, oldest id={oldest['message_id']} at {oldest_dt:%Y-%m-%d}", file=sys.stderr)
        if oldest_dt < since:
            break
        before = oldest["message_id"]
        time.sleep(pause)
    result = [p for p in all_posts.values() if datetime.fromisoformat(p["published_at"]) >= since]
    return sorted(result, key=lambda p: p["message_id"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="postypashki_old")
    ap.add_argument("--since", default="2026-07-25")
    ap.add_argument("--out", default="data/collected/tg_posts_postypashki_old.csv")
    args = ap.parse_args()

    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    posts = collect(args.channel, since)
    fields = ["message_id", "published_at", "views", "text_len", "has_media", "is_forward", "forward_from", "links", "text"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in posts:
            w.writerow({k: p[k] for k in fields})
    print(f"saved {len(posts)} posts -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
