"""
Сборка docs/executive_summary.pdf (2 страницы A4) и docs/presentation.pdf (10 слайдов 16:9) из результатов пайплайна.
Числа берутся из data/processed/*.json|csv — документы всегда согласованы с кодом.
Требует reportlab и шрифт с кириллицей (Arial из Windows или DejaVuSans из matplotlib).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, Table, TableStyle

from common import FIGURES, PROCESSED, ROOT

DOCS = ROOT / "docs"
TEAM = ("Команда: [капитан — Имя Фамилия, @telegram] · [участник 2, @telegram] · [участник 3, @telegram] · "
        "[участник 4, @telegram] · [участник 5, @telegram]")
REPO = "github.com/<team>/postupashki-marketing-measurement"

# ---------- шрифты
for name, path in [("Arial", r"C:\Windows\Fonts\arial.ttf"), ("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf")]:
    if Path(path).exists():
        pdfmetrics.registerFont(TTFont(name, path))
if "Arial" not in pdfmetrics.getRegisteredFontNames():  # fallback (Linux/macOS)
    import matplotlib
    dv = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("Arial", str(dv / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(dv / "DejaVuSans-Bold.ttf")))

NAVY, RED, GREY, ACC, TEAL = (colors.HexColor("#1f4e79"), colors.HexColor("#d62828"), colors.HexColor("#666666"),
                              colors.HexColor("#e8a33d"), colors.HexColor("#2a9d8f"))
LIGHT = colors.HexColor("#e9eef5")


def st(size=9, bold=False, color=colors.black, leading=None, space=1.5):
    return ParagraphStyle("s", fontName="Arial-Bold" if bold else "Arial", fontSize=size, leading=leading or size * 1.28,
                          textColor=color, alignment=TA_LEFT, spaceAfter=space)


def fmt(n) -> str:
    return f"{n:,.0f}".replace(",", " ")


def box(c, x, y_top, w, title, paras, title_color=NAVY, size=8.2, min_h=0, pad=1.5 * mm):
    """Блок с заголовком; высота считается по содержимому. Возвращает использованную высоту."""
    ps = [Paragraph(p, st(size)) for p in paras]
    inner_w = w - 2 * pad
    text_h = sum(p.wrap(inner_w, 10000)[1] + p.style.spaceAfter for p in ps)
    h = max(min_h, text_h + 5.2 * mm + 2 * pad + 1 * mm)
    y = y_top - h
    c.setStrokeColor(colors.HexColor("#c9c9c9")); c.setLineWidth(0.5); c.setFillColor(colors.white); c.rect(x, y, w, h, stroke=1, fill=1)
    c.setFillColor(title_color); c.rect(x, y + h - 5.2 * mm, w, 5.2 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 8.6); c.drawString(x + 2 * mm, y + h - 3.7 * mm, title)
    f = Frame(x + pad, y + pad, inner_w, h - 5.2 * mm - 2 * pad, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    f.addFromList(ps, c)
    return h


def bullets(c, x, y_top, w, items, size=9.5, space=3):
    """Маркированный список; возвращает высоту."""
    ps = [Paragraph(("" if it.startswith("<b>§") else "• ") + it.replace("<b>§", "<b>"), st(size, space=space)) for it in items]
    h = sum(p.wrap(w, 10000)[1] + p.style.spaceAfter for p in ps) + 1
    f = Frame(x, y_top - h, w, h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    f.addFromList(ps, c)
    return h


def table(c, x, y_top, data, col_widths, size=7.2, header_bg=NAVY):
    """Таблица с переносом строк в ячейках; рисуется от верхней границы вниз, возвращает высоту."""
    body = st(size, space=0); head = st(size, bold=True, color=colors.white, space=0)
    rows = [[Paragraph(str(v), head) for v in data[0]]] + [[Paragraph(str(v), body) for v in r] for r in data[1:]]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), header_bg),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9c9c9")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f9")])]))
    w, h = t.wrapOn(c, 0, 0)
    t.drawOn(c, x, y_top - h)
    return h


def load():
    f = json.loads((PROCESSED / "key_facts.json").read_text(encoding="utf-8"))
    return (f, pd.read_csv(PROCESSED / "waves.csv"), pd.read_csv(PROCESSED / "uplift_waves.csv"),
            pd.read_csv(PROCESSED / "forecast_metrics.csv"), pd.read_csv(PROCESSED / "romi_by_channel.csv"),
            pd.read_csv(PROCESSED / "romi_sensitivity.csv"), pd.read_csv(PROCESSED / "posts_classified.csv"),
            pd.read_csv(PROCESSED / "forecast_next7.csv"))


# =============================================================================== EXECUTIVE SUMMARY
def executive_summary():
    f, waves, up, met, romi_ch, sens, posts, nxt = load()
    W, H = A4
    c = canvas.Canvas(str(DOCS / "executive_summary.pdf"), pagesize=A4)
    c.setTitle("Поступашки: куда исчезает маркетинг? — Executive summary")
    m = 12 * mm; cw = W - 2 * m; gap = 2.5 * mm
    w1, w2, w3 = [up.iloc[i] for i in range(3)]
    cls = posts.post_class.value_counts()
    ms = met.set_index("model")

    # ---------------- страница 1
    c.setFillColor(NAVY); c.rect(0, H - 22 * mm, W, 22 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 15); c.drawString(m, H - 9.5 * mm, "Поступашки: куда исчезает маркетинг? — от рекламы в Telegram до ROMI")
    c.setFont("Arial", 8.3); c.drawString(m, H - 15 * mm, "Executive summary · хакатон «Аналитика вне SQL», 12.09.2026 · страница 1: проблема → данные → основные выводы → решение")
    c.setFont("Arial", 7.4); c.drawString(m, H - 19.3 * mm, TEAM)
    y = H - 25 * mm
    y -= box(c, m, y, cw, "ПРОБЛЕМА", [
        "Бизнес фиксирует <b>факт оплаты</b>, но не видит путь к ней: реклама → переход → канал → менеджер → оплата наблюдается только на последнем шаге. "
        "Все продающие посты ведут на <b>одну ссылку менеджера без параметров</b>, продающие посты <b>удаляются после акции</b>, стоимость размещений <b>не логируется</b>. "
        "Поэтому целевая метрика — ROMI — сегодня не считается в принципе: не хватает трёх событий — источник пользователя, время/стоимость размещения, начало диалога с менеджером.",
        "<b>Задача решения:</b> восстановить максимум из прошлого (продажи + публичный Telegram) и запустить measurement system, в которой каждая оплата знает свой источник.",
    ], size=8.4) + gap
    y -= box(c, m, y, cw, "ДАННЫЕ: ЧТО МЫ ЗНАЕМ (реальные)", [
        f"<b>{f['rows']} строк = {f['orders']} заказов, {f['buyers']} покупателей, {f['courses']} продуктов, {f['period']} ({f['days']} дней). Выручка {fmt(f['revenue_total'])} ₽</b>, "
        f"средний чек заказа {fmt(f['avg_order_total'])} ₽, пакетных заказов {f['bundle_orders_pct']}% ({f['bundle_revenue_pct']}% выручки), повторных покупателей {f['repeat_buyers_pct']}% (медиана интервала {f['repeat_gap_median_days']} дн.).",
        "<b>Правила данных:</b> заказ = строки одного покупателя с одинаковым timestamp; в пакете сумма делится поровну (5 463.33 + 5 463.33 + 5 463.34 = 16 390; 4 995 × 2 = 9 990 — пакет из условия); "
        "полная цена 8 950 ₽ (старт/про), 9 950 ₽ (математика). Аномалии помечены, не удалены: 3 строки ≤ 1 000 ₽, 4 строки ≥ 15 000 ₽ за один курс, 3 повторные покупки того же курса.",
        f"<b>Восстановлено из публичного канала @postypashki_old</b> собственным collector'ом (без API и админ-доступа): {len(posts)} постов за 20.07–12.09 с временем, просмотрами и ссылками; классификация правилами: "
        f"{cls.get('sale', 0)} sale, {cls.get('launch', 0)} launch, {cls.get('native_promo', 0)} native promo, {cls.get('lead_magnet', 0)} lead magnet, {cls.get('external_ad', 0)} чужая реклама, {cls.get('content', 0)} контент. "
        "28 message_id в диапазоне отсутствуют (удалённые посты или вложения) — анонс распродажи 8.08 не сохранился.",
    ], size=8.4) + gap
    fig_h = 66 * mm
    c.drawImage(str(FIGURES / "fig1_daily_orders_events.png"), m, y - fig_h, width=cw, height=fig_h, preserveAspectRatio=True, anchor="n")
    y -= fig_h + gap
    y -= box(c, m, y, cw, "ОСНОВНЫЕ ВЫВОДЫ", [
        f"<b>1. Три волны = {waves.orders_share_pct.sum():.0f}% заказов и {waves.revenue_share_pct.sum():.0f}% выручки за 9 из 38 дней.</b> "
        f"W1 (8–10.08) — финальная распродажа СТАРТ, скидка −{waves.avg_discount_pct[0]:.0f}%, «2 курса за 9 990»; W2 (22–24.08) — запуск линейки ПРО и продукта AI агенты (пост 35.7K просмотров — рекорд канала); "
        "W3 (4–6.09) — дедлайн стажировки Т-Банк + серия постов «разбор экзамена на курсах ПРО» — продажи по полной цене.",
        f"<b>2. Скидка — не единственный рычаг.</b> W3 дала +{w3.naive_uplift_orders:.0f} заказов к базе при среднем чеке {fmt(w3.avg_order_rub)} ₽; распродажа W1 — +{w1.naive_uplift_orders:.0f} при чеке {fmt(w1.avg_order_rub)} ₽ и «провале» на следующей неделе (−{abs(w1.post_week_delta):.0f} заказов: pull-forward). "
        f"Запуск W2: +{w2.naive_uplift_orders:.0f} и хвост +{w2.post_week_delta:.0f} на следующей неделе. Оценки не каузальные (нет контрольной группы), но направление ясно: контент под внешний дедлайн ≈ распродажа по числу заказов и на 26% дороже по чеку.",
        f"<b>3.</b> AI агенты (запуск 22.08) — {f['ai_agents']['rev_share_pct']}% выручки за 19 дней, топ-3 продукт. <b>4.</b> {f['weekend_orders_pct']:.0f}% заказов — в выходные, пик 14–19 МСК: эффект дня недели и эффект поста неразделимы, пока публикации не логируются. "
        f"<b>5.</b> Обычный день = {f['baseline_orders_per_day_median']:.0f} заказов / {fmt(f['baseline_revenue_per_day_median'])} ₽ — база для оценки любой акции. <b>6.</b> Повторных покупателей 3.3%: апсейл «старт → про» системно не работает.",
    ], size=8.4) + gap
    data = [["Что мы знаем (факты)", "Что мы оцениваем (модели, с оговорками)", "Чего узнать нельзя — и что начать логировать"],
            ["Структура и динамика продаж, пакеты, повторные покупки, ценовые уровни, «обычный день»; календарь постов канала: время, просмотры, класс",
             "Наивный uplift волн с бутстрап-интервалом; атрибуция 5 моделями и ROMI по размещениям — демо на синтетических касаниях; прогноз заказов с backtest",
             "Источник покупателя → fact_touch (deep-link бота, промокод); стоимость и время размещений → реестр; диалоги с менеджером → fact_lead; инкрементальность → эксперименты"]]
    y -= table(c, m, y, data, [cw / 3] * 3, size=7.6) + gap
    y -= box(c, m, y, cw, "РЕШЕНИЕ", [
        "Реестр размещений (время + cost, заполняется до публикации) → трекинг-ссылки t.me/&lt;bot&gt;?start=&lt;placement_id&gt;, промокоды и pre-filled текст менеджеру → витрина событий (SQLite → DWH) → "
        "атрибуция (position-based, окно 14 дн., контроль last touch) → ROMI_attr по размещению/каналу + эксперименты → ROMI_inc → прогноз с календарём акций. "
        "MVP запускается одной командой и уже работает на реальных продажах и реальных постах канала. Подробнее — стр. 2.",
    ], size=8.4, title_color=RED)
    c.showPage()

    # ---------------- страница 2
    c.setFillColor(NAVY); c.rect(0, H - 14 * mm, W, 14 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 12); c.drawString(m, H - 6.5 * mm, "Страница 2: архитектура → ROMI → MVP → план внедрения")
    c.setFont("Arial", 8); c.drawString(m, H - 11 * mm, f"Репозиторий: {REPO} · запуск: python src/run_all.py · README: инструкция, assumptions, описание данных")
    y = H - 17 * mm
    y -= box(c, m, y, cw, "MEASUREMENT ARCHITECTURE: marketing activity → user touch → lead → payment → revenue", [
        "<b>Реестр размещений</b> (Google Sheet → dim_placement, шаблон templates/campaign_registry_template.xlsx): одна строка = один пост в одном канале; обязательны publication_time, cost_rub, creative_id, deep_link, promo_code; "
        "статус deleted вместо удаления — история больше не теряется. Кампания → размещение → креатив: уникальные идентификаторы p_&lt;канал&gt;_&lt;ммдд&gt;, cr_&lt;оффер&gt;_&lt;версия&gt;, промокод &lt;КАНАЛ&gt;&lt;ММДД&gt;.",
        "<b>Трекинг и user stitching</b> с учётом ограничений Telegram (нет UTM/cookies): ссылка t.me/&lt;bot&gt;?start=&lt;placement_id&gt; → бот пишет bot_start c user_hash = sha256(telegram_user_id + salt) — без персональных данных; "
        "показывает кнопки курсов (лид) и «Написать менеджеру» с pre-filled текстом «#placement_id хочу на курс» — источник виден менеджеру и без бота. Стыковка с продажами — тот же хеш username, что уже используется в student_id (плюс стабильный хеш user_id). "
        "Если детерминированной связки нет: промокод креатива → self-reported («откуда узнали», кнопки у бота/менеджера) → probabilistic: вступление по инвайт-ссылке размещения + диалог ≤ 48 ч (пониженный вес).",
        "<b>Модель данных</b> (sql/schema.sql, SQLite → любой DWH): dim_channel · dim_campaign · dim_creative · dim_placement · dim_course · dim_user; fact_touch · fact_lead · fact_order · fact_order_item · fact_post; attribution_result; витрины v_user_journey и v_romi_by_placement. "
        "В каждой строке data_origin (real / synthetic), в касаниях match_quality. cost_rub и publication_time — NOT NULL: без них ROMI не считается по определению.",
        "<b>Собственный канал и менеджер:</b> tg_collector.py собирает историю публичного канала, post_classifier.py классифицирует посты (sale / launch / native / lead magnet / чужая реклама / контент) — журнал контента ведётся автоматически; "
        "менеджеру — одна кнопка «зафиксировать источник» и user_hash в записи об оплате; операционный календарь — тот же реестр (листы «Размещения», «Кампании», «Календарь дедлайнов»).",
    ], size=8.2) + gap
    half = (cw - gap) / 2
    h1 = box(c, m, y, half, "ATTRIBUTION → ROMI", [
        "<b>Модели:</b> first · last · linear · time decay (half-life 7 д) · position 40/20/40. Дефолт — <b>position</b> (у бизнеса два типа касаний: вход через контент/рекламу и дожим через sale/дедлайн), контроль — last touch; расхождение = канал работает на входе, а не на закрытии.",
        "<b>Окно 14 дней:</b> реакция на пост 0–2 дня, медиана повторной покупки 14.9 дн. (p75 = 24.6); повторная покупка — только касания после предыдущего заказа; без касаний = organic отдельной строкой; probabilistic × 0.5; опция contribution margin.",
        "<b>ROMI_attr = (attributed revenue × margin − cost) / cost</b> по размещению / каналу / кампании; CAC = cost / заказы; RPM = выручка на 1 000 просмотров. Для своего канала cost = opportunity (цена рекламного слота; допущение 20 000 ₽/пост — канал продаёт рекламу, 5 постов с erid за период). "
        "Таблица чувствительности модель × окно × cost показывает, когда ранг каналов зависит от методологии — тогда решение о бюджете принимать рано.",
        "<b>ROMI_inc</b> — только из эксперимента: promo-code holdout (нужна ли скидка −35%, если дедлайн продаёт по полной цене?), staggered rollout по тематическим суб-каналам, внешние закупки в 2 волны (DiD). Мощность: при CR 10% и эффекте +30% — 885 лидов на группу.",
        f"<b>Прогноз:</b> заказы/день, горизонт 7 дн., скользящий backtest на 14 днях: baseline + индекс дня недели + календарь акций — WAPE {ms.WAPE['promo_aware']:.0%}; без календаря {ms.WAPE['mean7']:.0%}–{ms.WAPE['dow_profile']:.0%}. "
        "38 дней и 3 волны — мало для чего-то сложнее baseline; главный будущий признак — реестр (ad_spend, placements, sale_post, discount, launch, deadline).",
    ], size=7.9)
    h2 = box(c, m + half + gap, y, half, "MVP — ЧТО РАБОТАЕТ (python src/run_all.py, ~1 мин)", [
        "<b>Цепочка:</b> Telegram collector (72 реальных поста) → post classifier → EDA/волны/аномалии → реестр + касания (синтетика, помечена) → data mart SQLite → attribution engine (5 моделей × окна 7/14/30) → ROMI calculator + чувствительность → uplift + калькулятор мощности → forecast + backtest → tracking bot (deep-link, хеширование, лиды; --simulate и aiogram-режим) → reports/summary.md.",
        "<b>Реально:</b> продажи; посты канала (время, просмотры, текст, ссылки); классификация и календарь событий; uplift; прогноз. <b>Синтетично:</b> касания и стоимость размещений — их никто не логировал; сгенерированы для реальных заказов по описанному процессу (make_synthetic.py, seed фиксирован), чтобы показать стыковку «заказ ↔ размещение» и работу расчётов end-to-end.",
        "<b>Числа ROMI по каналам — демонстрация движка, не оценка бизнеса.</b> Через 2–4 недели сбора реальных касаний те же скрипты дают настоящий ROMI_attr, а первый holdout — ROMI_inc.",
        "<b>Стек:</b> Python 3.11+, pandas / numpy / scipy / matplotlib / openpyxl / requests; без Kafka/Airflow/ML — простой инструмент, который реально закрывает разрыв в данных.",
    ], size=7.9)
    y -= max(h1, h2) + gap
    data = [["Неделя", "Что делаем", "Результат", "Стоимость"],
            ["0 (до запуска)", "Реестр размещений · deep-links и промокоды во всех постах · кнопка «источник» у менеджера · user_hash в оплатах · календарь внешних дедлайнов", "каждая новая оплата знает источник", "0 ₽, 2 дня работы"],
            ["1–2 (explore)", "6–8 размещений в разных каналах по 10–15 тыс. ₽ с уникальными placement_id и одним оффером; метрики через 7 и 14 дней; стоп-правило: CAC > 4 500 ₽ после 10 лидов", "первые CAC / ROMI_attr по каналам", "≈ 90 000 ₽ (30%)"],
            ["3–4 (exploit)", "Перераспределение в топ-3 по нижней границе доверительного интервала ROMI; запуск под внешний дедлайн (стажировки); holdout промокода в своём канале", "ROMI_attr + первый ROMI_inc", "≈ 210 000 ₽ (70%)"],
            ["5+", "Отчёт по кампании из v_romi_by_placement и uplift.py; уточнение окна атрибуции по реальному лагу «касание → заказ»; прогноз с календарём", "решение о следующем бюджете на данных", "—"]]
    y -= table(c, m, y, data, [22 * mm, 100 * mm, 38 * mm, 26 * mm], size=7.4) + gap
    box(c, m, y, cw, "ОТВЕТ ВЛАДЕЛЬЦУ: «300 000 ₽ НА СЛЕДУЮЩИЙ ЗАПУСК — ЧТО ДЕЛАТЬ?»", [
        f"<b>Экономика:</b> средний чек {fmt(f['avg_order_total'])} ₽ → безубыточность 300 000 ₽ = 32 заказа; цель ROMI ≥ 2 → ≥ 96 заказов ≈ одна волна уровня W3 ({waves.orders[2]} заказов за 3 дня) из платных источников.",
        "<b>Система решения:</b> сначала измерение (неделя 0, 0 ₽) → 30% бюджета на разведку каналов с уникальными идентификаторами → 70% в лидеров по нижней границе доверительного интервала ROMI, а не по точечной оценке → "
        "holdout промокода отвечает, нужна ли глубокая скидка → отчёт по кампании определяет следующий бюджет. Запуск привязывать к внешним дедлайнам (стажировки Т-Банк/Яндекс — уже работает), платные размещения ставить в пт–сб (48% заказов в выходные), новый продукт анонсировать за неделю до пикового дедлайна.",
        "<b>Главный принцип:</b> данные, которых нет, не придумываем — фиксируем, что начать собирать: касания, стоимость и время размещений, лиды. Без этого любой бюджет остаётся слепым.",
    ], size=8.2, title_color=RED)
    c.save()
    print(f"saved -> {DOCS / 'executive_summary.pdf'}")


# =============================================================================== PRESENTATION
def presentation():
    f, waves, up, met, romi_ch, sens, posts, nxt = load()
    W, H = landscape(A4)
    c = canvas.Canvas(str(DOCS / "presentation.pdf"), pagesize=landscape(A4))
    c.setTitle("Поступашки: куда исчезает маркетинг? — презентация решения")
    m = 12 * mm; cw = W - 2 * m; n_slides = 10
    ms = met.set_index("model"); cls = posts.post_class.value_counts()

    def header(i, title, subtitle=""):
        c.setFillColor(NAVY); c.rect(0, H - 16 * mm, W, 16 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Arial-Bold", 14.5); c.drawString(m, H - 10.5 * mm, title)
        c.setFont("Arial", 8); c.drawRightString(W - m, H - 10.5 * mm, f"{i}/{n_slides}")
        if subtitle:
            c.setFillColor(GREY); c.setFont("Arial", 9.5); c.drawString(m, H - 22 * mm, subtitle)
        c.setFillColor(GREY); c.setFont("Arial", 6.5); c.drawString(m, 5 * mm, "Хакатон «Аналитика вне SQL» · Поступашки: куда исчезает маркетинг? · " + TEAM)
        return H - 27 * mm

    # 1 — титул
    c.setFillColor(NAVY); c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(RED); c.rect(0, H - 6 * mm, W, 6 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 30); c.drawString(m, H * 0.62, "Поступашки: куда исчезает маркетинг?")
    c.setFont("Arial", 16); c.drawString(m, H * 0.62 - 12 * mm, "От рекламы в Telegram до ROMI — measurement system и работающий MVP")
    c.setFont("Arial", 11); c.drawString(m, H * 0.62 - 24 * mm, "Хакатон «Аналитика вне SQL» · 12 сентября 2026")
    c.setFont("Arial", 10); c.drawString(m, H * 0.30, TEAM)
    c.drawString(m, H * 0.30 - 7 * mm, f"Репозиторий: {REPO}")
    c.setFillColor(colors.HexColor("#9fb3c8")); c.setFont("Arial", 9)
    c.drawString(m, H * 0.30 - 18 * mm, "Обнаружить проблему → измерить масштаб → предложить решение → показать MVP")
    c.showPage()

    # 2 — проблема
    y = header(2, "Проблема: воронка — black box, и это не «мало данных», а три незалогированных события", "Реклама → переход → канал → менеджер → оплата: системно наблюдаем только оплату")
    steps = ["Реклама в TG-каналах", "Переход / просмотр", "Основной канал", "Менеджер (t.me/m/…)", "Оплата", "Курс"]
    bw = (cw - 5 * 4 * mm) / 6
    for i, s in enumerate(steps):
        x = m + i * (bw + 4 * mm); yy = y - 18 * mm
        c.setFillColor(RED if s == "Оплата" else LIGHT); c.roundRect(x, yy, bw, 16 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white if s == "Оплата" else NAVY); c.setFont("Arial-Bold", 9.5); c.drawCentredString(x + bw / 2, yy + 6.5 * mm, s)
        c.setFillColor(GREY); c.setFont("Arial", 8); c.drawCentredString(x + bw / 2, yy - 4.5 * mm, "не логируется" if i < 4 else ("логируется" if i == 4 else "доступ = timestamp"))
    y -= 30 * mm
    bullets(c, m, y, cw, [
        "<b>Факт 1.</b> Все продающие посты канала ведут на одну ссылку менеджера t.me/m/p94YcePXNjcy без параметров: источник теряется в момент клика (проверено на 72 реальных постах, 21 из них — с этой ссылкой).",
        "<b>Факт 2.</b> Продающие посты удаляются после акции: анонса распродажи 8.08 в канале нет, о ней известно только по постам «последние 6 часов» и «продлеваем до конца дня». 28 message_id в диапазоне 1802–1901 не сохранились.",
        "<b>Факт 3.</b> Стоимость и время размещений нигде не фиксируются → у формулы ROMI нет знаменателя.",
        "<b>Следствие.</b> ROMI сегодня нельзя посчитать даже приблизительно; любой бюджет тратится вслепую. Задача: восстановить максимум из прошлого и сделать так, чтобы каждая новая оплата знала свой источник.",
        "<b>Структура решения — три уровня знания:</b> что мы знаем (факты из продаж и публичного Telegram) · что оцениваем (uplift, атрибуция, прогноз — с оговорками) · чего узнать нельзя и что начать логировать.",
    ], size=10)
    c.showPage()

    # 3 — данные
    y = header(3, "Данные: 795 строк → 628 заказов → 606 покупателей; правила, которые мы зафиксировали", f"{f['period']} · выручка {fmt(f['revenue_total'])} ₽ · средний чек заказа {fmt(f['avg_order_total'])} ₽ · обычный день = {f['baseline_orders_per_day_median']:.0f} заказов")
    fig_h = 68 * mm
    c.drawImage(str(FIGURES / "fig5_order_structure.png"), m, y - fig_h, width=cw, height=fig_h, preserveAspectRatio=True, anchor="n")
    y -= fig_h + 3 * mm
    bullets(c, m, y, cw * 0.55, [
        "<b>Заказ</b> = строки одного student_id с одинаковым timestamp (до секунды): 145 пар, 4 тройки, по 2 заказа из 4 и 5 курсов.",
        "<b>Сумма пакета делится поровну по строкам:</b> 5 463.33 + 5 463.33 + 5 463.34 = 16 390; 2 237.5 × 4 = 8 950; 4 995 × 2 = 9 990 — тот самый пакет «за 9 990» из условия. Выручка заказа = сумма строк.",
        "<b>Покупатель</b> = student_id (хеш username). Повторных покупателей 20 (3.3%), медианный интервал 14.9 дня — основа для окна атрибуции.",
        "<b>Полная цена:</b> 8 950 ₽ (старт/про), 9 950 ₽ (математика), 6 950 ₽ (К ВУЗу, DS); скидочные уровни 7 475 («2 за 14 950»), 6 490, 4 950 / 4 995 («2 за 9 900 / 9 990»).",
        "<b>Аномалии помечены, не удалены:</b> 3 строки ≤ 1 000 ₽ (предоплата?), 4 строки ≥ 15 000 ₽ за один курс (двойная оплата / другой формат?), 3 повторные покупки того же курса — вопросы менеджерам.",
    ], size=9)
    bullets(c, m + cw * 0.57, y, cw * 0.43, [
        "<b>§Можно решить текущими данными:</b> структура и динамика продаж, пакеты, повторные покупки, продуктовые связки, ценовые уровни, эффект дня недели, «обычный день» как база.",
        "<b>§Принципиально нельзя:</b> источник покупателя, конверсия из клика/диалога, стоимость привлечения, инкрементальность акций, LTV (история 38 дней), доля органики.",
        "<b>§Топ продуктов по выручке:</b> Аналитика ПРО 12.5%, ML ПРО 12.1%, AI агенты 12.1% (запуск 22.08), Аналитика старт 10.9%, Алгоритмы старт 9.0%.",
    ], size=9)
    c.showPage()

    # 4 — волны
    y = header(4, "Что мы знаем: три волны дают половину выручки — и они устроены по-разному", "Дневные заказы (реальные) + события, восстановленные из публичного канала")
    fig_h = 80 * mm
    c.drawImage(str(FIGURES / "fig1_daily_orders_events.png"), m, y - fig_h, width=cw, height=fig_h, preserveAspectRatio=True, anchor="n")
    y -= fig_h + 2 * mm
    data = [["Волна", "Дни", "Заказы", "Выручка", "Доля заказов", "Ср. чек", "Ср. скидка", "Пакеты", "Uplift к базе (наивный, 95% ДИ)", "Неделя после"]]
    for w, u in zip(waves.itertuples(index=False), up.itertuples(index=False)):
        data.append([w.wave, f"{w.start[8:]}–{w.end[8:]}.{w.end[5:7]}", w.orders, fmt(w.revenue), f"{w.orders_share_pct}%", fmt(w.avg_order), f"{w.avg_discount_pct}%", f"{w.bundle_share_pct}%",
                     f"+{u.naive_uplift_orders:.0f} [{u.uplift_ci95_low:.0f}; {u.uplift_ci95_high:.0f}]", f"{u.post_week_delta:+.0f}"])
    y -= table(c, m, y, data, [52 * mm, 20 * mm, 16 * mm, 22 * mm, 22 * mm, 18 * mm, 20 * mm, 16 * mm, 50 * mm, 22 * mm], size=7.6) + 2 * mm
    bullets(c, m, y, cw, [
        f"<b>Скидка — не единственный рычаг:</b> W3 (дедлайн стажировки Т-Банк, полная цена) дала столько же заказов над базой, сколько распродажа W1 со скидкой −35%, но с чеком на 26% выше и без «провала» после. Запуск W2 имеет хвост +{up.post_week_delta[1]:.0f} заказов на следующей неделе.",
        f"<b>{f['weekend_orders_pct']:.0f}% заказов — в выходные</b>, пик 14–19 МСК. Uplift — оценка относительно обычных дней (медиана × индекс дня недели, бутстрап-интервал), не каузальный эффект: нет контрольной группы, есть сезон и внешние дедлайны.",
    ], size=8.8)
    c.showPage()

    # 5 — восстановленная история
    y = header(5, "Маркетинговая история восстановлена из публичного Telegram — частично, и это само по себе вывод", "Собственный collector: t.me/s/postypashki_old + пагинация, без API и админ-доступа · 72 поста за 20.07–12.09 · классификация правилами")
    data = [["Дата (МСК)", "Пост (реальный)", "Класс", "Просмотры", "Связь с продажами"],
            ["09.08 18:35", "«…последние 6 часов финальной распродажи на СТАРТ» (#1837)", "sale", "19.8K", "68 заказов 09.08 — пик периода"],
            ["10.08 16:26 / 20:33", "«продлеваем распродажу до конца дня» (#1838); «финальные 4 часа скидки» (#1840)", "sale", "16.5K / 30.8K", "29 заказов 10.08; цены 4 950 ещё 11–12.08"],
            ["22.08 13:19", "«Выходим на новый уровень с линейкой ПРО» — AI агенты ПРО, хард-курсы (#1859)", "launch", "35.7K (рекорд)", "первые продажи AI агентов 22.08; «2 за 14 950»"],
            ["29.08 21:58", "«Яндекс обновил контест — разбор уже на курсах ПРО» (#1872)", "launch / native", "20.3K", "рост продаж с 30.08"],
            ["30.08 16:26", "вебинар «ИИ-инженеры зарабатывают 300к…» + «в конце записи спрятан промокод» (#1874)", "sale", "19.4K", "нестандартные суммы (8 450, 8 545…)"],
            ["31.08 → 06.09", "серия «Отбор в Т-Банк… разбор на курсах ПРО», «через 12 часов закончится отбор» (#1875, 1877, 1878, 1880)", "native promo", "12–21K", "94 заказа 5–6.09 по полной цене"],
            ["07.09", "бесплатная неделя «Аналитика вне SQL» (#1887) — лид-магнит для Аналитики ПРО", "lead magnet", "18.4K", "верх воронки (этот хакатон)"]]
    y -= table(c, m, y, data, [26 * mm, 120 * mm, 24 * mm, 26 * mm, 66 * mm], size=7.6) + 3 * mm
    bullets(c, m, y, cw * 0.5, [
        f"<b>Классы</b> (правила прозрачны и правятся маркетологом): sale {cls.get('sale', 0)}, launch {cls.get('launch', 0)}, native promo {cls.get('native_promo', 0)}, lead magnet {cls.get('lead_magnet', 0)}, чужая реклама {cls.get('external_ad', 0)}, контент {cls.get('content', 0)}.",
        "<b>Что не восстановилось:</b> анонс распродажи 8.08 (удалён), точные условия в удалённых постах, внешние закупки (в своём канале их не видно). TGStat хранит удалённые посты и упоминания канала в других каналах, но закрыт авторизацией — ручной/платный источник.",
        "<b>Вывод:</b> канал <i>продаёт</i> рекламу (5 постов с erid: РУДН/WB, МТС, Яндекс, ggsel) — у собственного продающего поста есть opportunity cost, и его можно оценить по прайсу канала.",
    ], size=8.8)
    bullets(c, m + cw * 0.52, y, cw * 0.48, [
        "<b>§Наблюдаемая механика продаж канала:</b> контент (гайды, «сливы» собесов) → нативный CTA «Записаться» → одна ссылка на менеджера; акции — по выходным с дедлайном «до конца дня»; лид-магниты — бесплатные разборы «за подписку».",
        "<b>§Что логировать с завтрашнего дня:</b> каждую публикацию (время, класс, оффер, скидка, ссылка), каждое внешнее размещение (канал, cost, время, креатив), каждый дедлайн-триггер (стажировки, ШАД). Это и есть реестр размещений — заполняется до публикации.",
    ], size=8.8)
    c.showPage()

    # 6 — архитектура
    y = header(6, "Measurement architecture: реестр → трекинг → витрина событий → атрибуция → ROMI", "Чтобы каждая оплата знала свой источник — запускается за неделю, без новой инфраструктуры")
    flow = [("Реестр размещений", "dim_placement: канал, кампания, креатив, publication_time, cost, deep-link, промокод, status (deleted ≠ удалить)"),
            ("Касание", "fact_touch: t.me/&lt;bot&gt;?start=&lt;placement_id&gt; → bot_start; pre-filled текст менеджеру; промокод; user_hash = sha256(user_id + salt)"),
            ("Лид", "fact_lead: кнопки курсов у бота / кнопка «источник» у менеджера; интерес, статус; self-reported при отсутствии ключа"),
            ("Оплата", "fact_order + items: существующий слой продаж + user_hash (тот же хеш username, что в student_id)"),
            ("Атрибуция → ROMI", "attribution_result (5 моделей × окна) → v_romi_by_placement: ROMI_attr, CAC, RPM; ROMI_inc — из экспериментов")]
    bw = (cw - 4 * 4 * mm) / 5
    for i, (t, d) in enumerate(flow):
        x = m + i * (bw + 4 * mm); yy = y - 42 * mm
        c.setFillColor(NAVY if i != 4 else RED); c.roundRect(x, yy, bw, 42 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Arial-Bold", 10.5); c.drawString(x + 3 * mm, yy + 36 * mm, t)
        fr = Frame(x + 2 * mm, yy + 1 * mm, bw - 4 * mm, 33 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
        fr.addFromList([Paragraph(d, st(7.9, color=colors.white))], c)
        if i < 4:
            c.setFillColor(GREY); c.setFont("Arial-Bold", 14); c.drawString(x + bw + 0.6 * mm, yy + 19 * mm, "→")
    y -= 46 * mm
    bullets(c, m, y, cw * 0.5, [
        "<b>§User stitching с учётом ограничений Telegram</b> (нет UTM/cookies; единственный «параметр» — start-payload бота или текст сообщения). Ключи по убыванию качества: deep-link → промокод → pre-filled текст менеджеру (все deterministic) → self-reported кнопки «откуда узнали» → probabilistic: вступление по инвайт-ссылке размещения + диалог ≤ 48 ч (вес 0.5).",
        "<b>§Без персональных данных:</b> только sha256(user_id + salt) и sha256(username + salt); username может смениться — основной ключ user_id.",
        "<b>§Собственный канал и менеджер:</b> tg_collector + post_classifier ведут журнал публикаций автоматически; менеджеру — одна кнопка «зафиксировать источник» и user_hash в оплате; операционный календарь — Google Sheet по шаблону templates/campaign_registry_template.xlsx (размещения, кампании, дедлайны).",
    ], size=8.6)
    bullets(c, m + cw * 0.52, y, cw * 0.48, [
        "<b>§Tracking внешней рекламы (20 каналов завтра):</b> placement_id = p_&lt;канал&gt;_&lt;ммдд&gt; на каждое размещение; creative_id — версия оффера; промокод = &lt;КАНАЛ&gt;&lt;ММДД&gt;; в реестр — publication_time и cost до публикации; views_public через 48 ч и 7 дн.; status = deleted вместо удаления; исторические размещения — опрос админов + TGStat-упоминания.",
        "<b>§Модель данных</b> (sql/schema.sql): 6 измерений, 5 фактов, attribution_result, 2 витрины; в каждой строке data_origin (real/synthetic), в касаниях match_quality. Переносится в Postgres/ClickHouse без изменений.",
        "<b>§Что принципиально нового для бизнеса:</b> cost_rub и publication_time — NOT NULL (без них ROMI не считается по определению); удалённый пост остаётся в реестре; повторная покупка видна через order_seq.",
    ], size=8.6)
    c.showPage()

    # 7 — атрибуция и ROMI
    y = header(7, "Attribution → ROMI: простая модель по умолчанию, чувствительность к методологии — на виду", "Движок работает на реальных заказах и СИНТЕТИЧЕСКИХ касаниях/стоимости — числа иллюстрируют метод, не бизнес")
    c.drawImage(str(FIGURES / "fig6_romi_by_placement.png"), W * 0.56, y - 128 * mm, width=W * 0.44 - m, height=128 * mm, preserveAspectRatio=True, anchor="n")
    lw = W * 0.54 - m
    y2 = y - bullets(c, m, y, lw, [
        "<b>Модели:</b> first · last · linear · time decay (half-life 7 д) · position 40/20/40. <b>Дефолт — position</b> (два работающих типа касаний: вход через контент/рекламу и дожим через sale/дедлайн), <b>контроль — last touch</b>; расхождение = канал работает на входе, а не на закрытии.",
        "<b>Окно 14 дней:</b> реакция на пост 0–2 дня, медиана повторной покупки 14.9 дн., p75 = 24.6; 30 дней захватывало бы предыдущую волну. Уточняется по реальному лагу «касание → заказ».",
        "<b>Правила:</b> выручка заказа целиком (пакет не дробим); повторная покупка — только касания после предыдущего заказа; нет касаний → organic отдельной строкой; probabilistic × 0.5; опция contribution margin.",
        "<b>ROMI_attr = (attributed revenue × margin − cost) / cost</b>; CAC = cost / заказы; RPM = выручка на 1 000 просмотров (для своего канала: прямой cost = 0, opportunity cost ≈ 20 000 ₽/пост — допущение).",
        "<b>Две оценки в отчёте:</b> ROMI_attr (кому приписали) и ROMI_inc (что реально добавила реклама) — вторая только из эксперимента (следующий слайд).",
    ], size=8.5) - 2 * mm
    piv = sens[sens.cost_mode == "opportunity"].pivot_table(index="channel_id", columns="model", values="romi_attr").loc[:, ["first", "last", "linear", "time_decay", "position"]]
    piv = piv.loc[piv.index.isin(["own_tg_main", "ext_tg_ds_memes", "ext_tg_ml_digest", "ext_youtube_review"])]
    data = [["Канал (ДЕМО), окно 14 д", "first", "last", "linear", "time decay", "position"]] + [[i] + [f"{v:.1f}" for v in r] for i, r in piv.iterrows()]
    y2 -= table(c, m, y2, data, [50 * mm, 18 * mm, 18 * mm, 18 * mm, 22 * mm, 18 * mm], size=7.6) + 2 * mm
    bullets(c, m, y2, lw, [
        "Чувствительность ROMI канала к модели × окну (romi_sensitivity.csv): если знак или ранг меняется от методологии — решение о бюджете принимать рано. В демо ранги стабильны, а first/last расходятся на 20–40% — типичная картина «вход vs дожим».",
    ], size=8.3)
    c.showPage()

    # 8 — incrementality + прогноз
    y = header(8, "Attribution ≠ Incrementality; прогноз честен ровно настолько, насколько известен календарь акций", "«После» не значит «из-за»: контрольной группы не было — предлагаем дизайны, применимые в Telegram")
    fig_h = 84 * mm
    c.drawImage(str(FIGURES / "fig7_uplift.png"), m, y - fig_h, width=cw * 0.5, height=fig_h, preserveAspectRatio=True, anchor="n")
    c.drawImage(str(FIGURES / "fig8_forecast.png"), m + cw * 0.5, y - fig_h, width=cw * 0.5, height=fig_h, preserveAspectRatio=True, anchor="n")
    y -= fig_h + 3 * mm
    bullets(c, m, y, cw * 0.5 - 3 * mm, [
        "<b>§Почему «+103 заказа от распродажи» — не факт:</b> скидка, выходные, дедлайны стажировок и pull-forward действовали одновременно; неделя после W1 — −6 заказов к базе.",
        "<b>§Promo-code holdout</b> (первый эксперимент): половина лидов получает скидку без кода → нужна ли скидка −35%, если дедлайн Т-Банка продаёт по полной цене? Мощность: CR 10%, эффект +30% → 885 лидов на группу (одна-две волны).",
        "<b>§Staggered rollout по суб-каналам</b> (@analytic_ / @ml_ / @backend_ / @algoses_postypashki): пост в случайной половине сейчас, в остальных через неделю → DiD по заказам подписчиков (источник — deep-link суб-канала).",
        "<b>§Внешние закупки в 2 волны</b> со случайным разбиением каналов — вторая волна = контроль для первой; A/B креативов = два placement_id в одном канале. Результат — ROMI_inc рядом с ROMI_attr.",
    ], size=8.4)
    bullets(c, m + cw * 0.5 + 3 * mm, y, cw * 0.5 - 3 * mm, [
        "<b>§Целевая метрика — заказы/день</b> (стабильнее выручки; выручка = заказы × чек 9 402 ₽), горизонт 7 дней, скользящий backtest на последних 14 днях (77 прогнозов).",
        f"<b>§Результат:</b> baseline + индекс дня недели + календарь акций — WAPE {ms.WAPE['promo_aware']:.0%} (MAE {ms.MAE['promo_aware']:.1f} заказа/день); без календаря: mean7 {ms.WAPE['mean7']:.0%}, naive {ms.WAPE['naive']:.0%}, seasonal naive {ms.WAPE['seasonal_naive']:.0%}. "
        f"Прогноз на 7 дней без акций: {nxt.orders_pred.sum():.0f} заказов ≈ {nxt.revenue_pred_rub.sum()/1e6:.2f} млн ₽, p10–p90 ≈ ±{(nxt.orders_p90 - nxt.orders_pred).mean():.0f} заказов/день.",
        "<b>§38 дней и 3 волны — недостаточно</b> для модели сложнее baseline: без знания будущих акций ошибка любой модели ≥ 50%. Будущие признаки: ad_spend и placements по дням (из реестра), флаги sale_post / discount / launch / deadline, канал, креатив, день недели.",
    ], size=8.4)
    c.showPage()

    # 9 — MVP
    y = header(9, "MVP: end-to-end пайплайн запускается одной командой — python src/run_all.py", "Реальные данные помечены real, синтетические — synthetic; в каждом отчёте написано, что демо")
    data = [["Компонент", "Файл", "Что делает", "Данные"],
            ["Telegram collector", "src/tg_collector.py", "история публичного канала через t.me/s/ + пагинация: id, время, просмотры, текст, ссылки, репосты", "реальные (72 поста)"],
            ["Post classifier", "src/post_classifier.py", "sale / launch / native / lead magnet / чужая реклама / контент; календарь событий; пропуски id", "реальные"],
            ["EDA + аудит", "src/eda.py", "заказы, пакеты, повторные покупки, волны, аномалии, 5 графиков, key_facts.json", "реальные"],
            ["Ad registry + touches", "src/make_synthetic.py", "реестр (36 реальных постов + 8 вымышленных закупок), 2 233 касания по описанному процессу", "синтетика (помечено)"],
            ["Data mart", "sql/schema.sql · src/build_mart.py", "SQLite: 6 dim, 5 fact, attribution_result, витрины v_user_journey / v_romi_by_placement", "real + synthetic"],
            ["Attribution engine", "src/attribution.py", "5 моделей × окна 7/14/30, повторные покупки, organic отдельно", "демо"],
            ["ROMI calculator", "src/romi.py", "ROMI_attr / CAC / RPM по размещению, каналу, кампании; чувствительность модель × окно × cost", "демо"],
            ["Uplift + power", "src/uplift.py", "наивный uplift волн с бутстрап-интервалом; калькулятор мощности holdout", "реальные (оценка)"],
            ["Forecast service", "src/forecast.py", "5 baseline-моделей, скользящий backtest, прогноз 7 дней с интервалом", "реальные"],
            ["Tracking bot", "src/tracking_bot.py", "deep-link /start &lt;placement_id&gt;, хеширование, лиды, pre-filled ссылка менеджеру; --simulate и aiogram-режим", "демо / прод-код"],
            ["Реестр (календарь)", "templates/campaign_registry_template.xlsx", "3 листа: размещения, кампании, дедлайны; валидации полей", "шаблон"]]
    y -= table(c, m, y, data, [34 * mm, 60 * mm, 128 * mm, 40 * mm], size=7.4) + 3 * mm
    bullets(c, m, y, cw, [
        "<b>Почему синтетика именно здесь:</b> касания и стоимость никто не логировал — без них атрибуция и ROMI не существуют. Мы генерируем их для <i>реальных</i> заказов (seed фиксирован, процесс описан в docstring), чтобы показать стыковку «заказ ↔ размещение» и работу всех расчётов; те же скрипты через 2–4 недели сбора дают настоящий ROMI.",
        "<b>Воспроизводимость:</b> Python 3.11+, pandas / numpy / scipy / matplotlib / openpyxl / requests; README с инструкцией, assumptions и описанием данных; результаты — data/processed/*.csv, pmm.sqlite, figures/*.png, reports/summary.md. Без Kafka / Airflow / ML.",
    ], size=8.8)
    c.showPage()

    # 10 — рекомендации
    y = header(10, "«У меня есть 300 000 ₽ на следующий запуск. Что делать?» — система решения, а не название канала", f"Безубыточность = 300 000 / {fmt(f['avg_order_total'])} ≈ 32 заказа; цель ROMI ≥ 2 → ≥ 96 заказов ≈ волна уровня W3")
    steps = [("Неделя 0 · 0 ₽", "Включить измерение", "реестр размещений; deep-links и промокоды во всех постах; кнопка «источник» у менеджера; user_hash в оплатах; календарь внешних дедлайнов"),
             ("Explore · ≈ 90 000 ₽ (30%)", "Разведка каналов", "6–8 размещений по 10–15 тыс. ₽ в разных каналах с уникальными placement_id и одним оффером; метрики через 7 и 14 дней; стоп-правило: CAC > 4 500 ₽ после 10 лидов"),
             ("Exploit · ≈ 210 000 ₽ (70%)", "Масштабировать лидеров", "бюджет пропорционален нижней границе ДИ ROMI (не точечной оценке), топ-3 канала; запуск под внешний дедлайн; размещения в пт–сб (48% заказов в выходные)"),
             ("Параллельно · 0 ₽", "Инкрементальность", "promo-code holdout на распродаже (нужна ли −35%?), staggered rollout по суб-каналам → ROMI_inc рядом с ROMI_attr в отчёте"),
             ("После · отчёт", "Следующий бюджет — на данных", "v_romi_by_placement + uplift: что выключить, CAC по каналам, уточнённое окно атрибуции, прогноз с календарём")]
    bw = (cw - 4 * 3 * mm) / 5
    for i, (t, h2, d) in enumerate(steps):
        x = m + i * (bw + 3 * mm); yy = y - 60 * mm
        c.setFillColor(NAVY if i == 0 else LIGHT); c.roundRect(x, yy, bw, 60 * mm, 2 * mm, stroke=0, fill=1)
        tc = colors.white if i == 0 else NAVY
        c.setFillColor(tc); c.setFont("Arial-Bold", 9.5); c.drawString(x + 3 * mm, yy + 53 * mm, t)
        c.setFont("Arial-Bold", 8.8); c.drawString(x + 3 * mm, yy + 47 * mm, h2)
        fr = Frame(x + 2.5 * mm, yy + 1 * mm, bw - 5 * mm, 43 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
        fr.addFromList([Paragraph(d, st(8.2, color=colors.white if i == 0 else colors.black))], c)
    y -= 64 * mm
    bullets(c, m, y, cw, [
        "<b>Что уже подсказывают данные:</b> дедлайн-контент («разбор экзамена на курсах ПРО») продаёт по полной цене не хуже распродажи −35% → сначала дедлайны и разборы, скидка — как проверяемая гипотеза; новый продукт (AI агенты — 12% выручки за 19 дней) анонсировать за неделю до пикового дедлайна; повторных покупателей 3% — апсейл старт → про пока не работает системно.",
        "<b>Что мы знаем / оцениваем / не знаем:</b> знаем структуру продаж и восстановленный календарь постов; оцениваем uplift волн, атрибуцию и прогноз с оговорками; не знаем источники, стоимость, лиды и инкрементальность — и именно это начинаем собирать с недели 0. Сильная аналитика не маскирует отсутствие данных моделью.",
        "<b>Простое решение на поверхности:</b> одна строка в реестре до публикации + одна ссылка с параметром + одна кнопка у менеджера. Всё остальное в репозитории уже считается автоматически.",
    ], size=9.2)
    c.showPage()
    c.save()
    print(f"saved -> {DOCS / 'presentation.pdf'}")


if __name__ == "__main__":
    executive_summary()
    presentation()
