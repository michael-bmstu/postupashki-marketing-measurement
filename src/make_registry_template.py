"""Создаёт templates/campaign_registry_template.xlsx — операционный календарь / реестр размещений (Задача 5)."""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from common import ROOT

OUT = ROOT / "templates" / "campaign_registry_template.xlsx"
OUT.parent.mkdir(exist_ok=True)

HEAD = PatternFill("solid", fgColor="1F4E79")
REQ = PatternFill("solid", fgColor="FDE9D9")


def sheet(wb, title, columns, rows, required, widths=None, validations=None):
    ws = wb.create_sheet(title)
    ws.append(columns)
    for i, c in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = HEAD; cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(c, 18)
    for r in rows:
        ws.append(r)
    for i, c in enumerate(columns, start=1):
        if c in required:
            for row in range(2, 40):
                ws.cell(row=row, column=i).fill = REQ
    ws.freeze_panes = "A2"; ws.row_dimensions[1].height = 42
    for col, opts in (validations or {}).items():
        dv = DataValidation(type="list", formula1=f'"{",".join(opts)}"', allow_blank=True)
        ws.add_data_validation(dv); dv.add(f"{get_column_letter(columns.index(col) + 1)}2:{get_column_letter(columns.index(col) + 1)}500")
    return ws


def main() -> None:
    wb = Workbook(); wb.remove(wb.active)
    cols = ["placement_id", "campaign_id", "channel_id", "channel_name", "channel_type", "publication_time (МСК)", "cost_rub",
            "cost_type", "creative_id", "offer_type", "discount_pct", "promo_code", "deep_link", "post_url", "views_48h", "views_7d",
            "status", "deadline_offer", "comment"]
    rows = [
        ["p_own_1880", "cmp_2026-09_tbank_season", "own_tg_main", "Поступашки (@postypashki_old)", "own_tg", "2026-09-06 12:06", 0, "opportunity",
         "cr_native_tbank_v1", "native", 0, "", "https://t.me/PostupashkiTrackBot?start=p_own_1880", "https://t.me/postypashki_old/1880", 12600, "", "published", "2026-09-06", "реальный пост; cost — упущенный рекламный слот"],
        ["p_ext_ds_memes_0904", "cmp_2026-09_tbank_season", "ext_tg_ds_memes", "[пример] DS Memes", "external_tg", "2026-09-04 12:00", 18000, "fixed",
         "cr_native_tbank_v1", "native", 0, "MEMES0904", "https://t.me/PostupashkiTrackBot?start=p_ext_ds_memes_0904", "", 28000, "", "published", "2026-09-06", "СИНТЕТИЧЕСКИЙ пример"],
    ]
    sheet(wb, "Размещения", cols, rows, required={"placement_id", "channel_id", "publication_time (МСК)", "cost_rub", "cost_type", "creative_id", "deep_link", "status"},
          widths={"channel_name": 30, "deep_link": 46, "post_url": 34, "comment": 40, "publication_time (МСК)": 20},
          validations={"channel_type": ["own_tg", "external_tg", "youtube", "instagram", "other"], "cost_type": ["fixed", "cpm", "barter", "opportunity", "zero"],
                       "offer_type": ["sale", "launch", "native", "content", "lead_magnet"], "status": ["planned", "published", "deleted"]})
    sheet(wb, "Кампании", ["campaign_id", "campaign_name", "objective", "product_line", "start_date", "end_date", "budget_rub", "owner", "hypothesis", "kpi"],
          [["cmp_2026-09_tbank_season", "Сезон стажировок: разборы Т-Банк/Яндекс на ПРО", "native", "ПРО", "2026-08-28", "2026-09-10", 0, "", "разбор экзамена продаёт ПРО без скидки", "CAC ≤ 3 000 ₽"]],
          required={"campaign_id", "campaign_name", "start_date", "end_date", "budget_rub"}, widths={"campaign_name": 44, "hypothesis": 40},
          validations={"objective": ["sale", "launch", "lead_gen", "brand", "native"], "product_line": ["СТАРТ", "ПРО", "all"]})
    sheet(wb, "Календарь дедлайнов", ["event_id", "event", "company", "deadline", "relevant_courses", "our_post_planned", "source_url"],
          [["ext_tbank_2026-09", "Отбор на стажировку Т-Банк", "Т-Банк", "2026-09-06", "Аналитика ПРО, ML ПРО, Backend ПРО", "2026-08-31; 2026-09-03; 2026-09-06", "https://education.tbank.ru/start/"],
           ["ext_yandex_2026-09", "Контест на стажировку Яндекс", "Яндекс", "", "Алгоритмы ПРО, ML ПРО", "2026-08-29", "https://yandex.ru/yaintern/internship"]],
          required={"event_id", "event", "deadline"}, widths={"event": 34, "relevant_courses": 34, "our_post_planned": 30, "source_url": 40})
    sheet(wb, "Справочник", ["Поле", "Правило"],
          [["placement_id", "p_<канал>_<ммдд>[_n]; одно размещение = одна строка; уникален"],
           ["publication_time", "МСК, до минуты; для planned — план, после публикации — факт"],
           ["cost_rub", "фактическая стоимость; для своего канала — opportunity (цена рекламного слота)"],
           ["deep_link", "t.me/<bot>?start=<placement_id> — печатает src/tracking_bot.py --make-links"],
           ["promo_code", "уникален для размещения; используется для стыковки оплат и holdout-тестов"],
           ["status=deleted", "пост удалён из канала, строка остаётся — история не теряется"],
           ["views_48h / views_7d", "публичный счётчик просмотров (снимок вручную или tg_collector)"]],
          required=set(), widths={"Поле": 22, "Правило": 90})
    wb.save(OUT)
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
