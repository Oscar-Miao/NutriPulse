"""On-demand PDF export of the same selected analytics period as the app."""

from __future__ import annotations

import os
import threading
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from app.application.analytics.service import (body_composition_series, energy_series,
                                               habit_summary, macro_summary, rule_diagnosis)
from app.shared.errors import ApiError, require
from app.shared.util import today, utc_now, valid_date


FONT_NAME = "NutriPulseChinese"
_font_lock = threading.Lock()
PERIOD_LABELS = {"day": "日", "week": "周", "month": "月", "year": "年"}
PALETTE = {"green": "#2ECC71", "red": "#FF5252", "blue": "#3498DB",
           "ice": "#00BEC5", "muted": "#667487", "light": "#F8F9FA"}


def period_bounds(period: str, end: str) -> tuple[str, str, str]:
    require(isinstance(period, str) and period in PERIOD_LABELS, "报告周期无效")
    day = date.fromisoformat(valid_date(end))
    if period == "day":
        start = day
    elif period == "week":
        start = day - timedelta(days=6)
    elif period == "month":
        start = day.replace(day=1)
    else:
        start = day.replace(month=1, day=1)
    granularity = {"day": "day", "week": "day", "month": "week", "year": "month"}[period]
    return start.isoformat(), day.isoformat(), granularity


def report_snapshot(period: str, end: str) -> dict:
    start, end, granularity = period_bounds(period, end)
    energy = energy_series(start, end, granularity)
    macros = macro_summary(start, end)
    habits = habit_summary(start, end)
    trend_start = date.fromisoformat(end) - timedelta(weeks=7)
    trend_start -= timedelta(days=trend_start.weekday())
    composition = body_composition_series(trend_start.isoformat(), end)
    diagnosis = rule_diagnosis(start, end, allow_agent=False)
    points = energy["series"]
    target_days = sum(point["target_days"] for point in points)
    return {"period": period, "start": start, "end": end, "granularity": granularity,
            "energy": energy, "macros": macros, "habits": habits, "composition": composition,
            "diagnosis": diagnosis,
            "totals": {"intake_kcal": round(sum(p["intake_kcal"] for p in points), 1),
                       "expenditure_kcal": round(sum(p["expenditure_kcal"] or 0 for p in points), 1)
                       if target_days else None,
                       "net_kcal": round(sum(p["net_kcal"] or 0 for p in points), 1)
                       if target_days else None,
                       "training_volume_kg": round(sum(p["training_volume"] for p in points), 1),
                       "water_ml": sum(p["water_ml"] for p in points),
                       "target_days": target_days,
                       "logged_days": sum(p["logged_days"] for p in points),
                       "days": sum(p["days"] for p in points)}}


def _registered_font() -> str:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as error:
        raise ApiError("PDF_UNAVAILABLE", "PDF 组件未安装，请在服务端安装 requirements.txt", 503) from error
    with _font_lock:
        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return FONT_NAME
        configured = os.environ.get("NUTRIPULSE_REPORT_FONT")
        candidates = ([Path(configured)] if configured else []) + [
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ]
        for path in candidates:
            if path.is_file():
                try:
                    pdfmetrics.registerFont(TTFont(FONT_NAME, str(path)))
                    return FONT_NAME
                except Exception:
                    continue
    raise ApiError("PDF_FONT_UNAVAILABLE",
                   "未找到可嵌入的中文字体，请设置 NUTRIPULSE_REPORT_FONT 为 TTF 字体路径", 503)


def _number(value: float | None, unit: str = "") -> str:
    if value is None:
        return "--"
    suffix = f" {unit}" if unit else ""
    return f"{value:,.1f}{suffix}"


def build_report(data: dict, *, synthetic_sample: bool = False) -> bytes:
    period = data.get("period", "week")
    end = data.get("end") or today()
    snapshot = report_snapshot(period, end)
    font_name = _registered_font()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (Flowable, KeepTogether, Paragraph, SimpleDocTemplate,
                                   Spacer, Table, TableStyle)

    green, red, blue, ice = [colors.HexColor(PALETTE[key]) for key in ("green", "red", "blue", "ice")]
    ink, muted, light = colors.HexColor("#203041"), colors.HexColor(PALETTE["muted"]), colors.HexColor(PALETTE["light"])

    class EnergyBars(Flowable):
        def __init__(self, points: list[dict]):
            super().__init__()
            self.points = points
            self.width, self.height = 500, 170

        def draw(self):
            canvas = self.canv
            left, base, top, right = 30, 34, 143, self.width - 5
            canvas.setStrokeColor(colors.HexColor("#DCE5E6"))
            canvas.line(left, base, right, base)
            scale = max(1.0, *(max(p["intake_kcal"], p["expenditure_kcal"] or 0,
                                   p["bmr_kcal"] or 0) for p in self.points))
            group = (right - left) / max(1, len(self.points))
            bar_width = min(17, max(5, group * 0.25))
            previous = None
            for index, point in enumerate(self.points):
                x = left + group * (index + 0.5)
                intake_h = (point["intake_kcal"] / scale) * (top - base)
                canvas.setFillColor(green)
                canvas.rect(x - bar_width - 1, base, bar_width, intake_h, stroke=0, fill=1)
                if point["expenditure_kcal"] is not None:
                    spent_h = (point["expenditure_kcal"] / scale) * (top - base)
                    canvas.setFillColor(red)
                    canvas.rect(x + 1, base, bar_width, spent_h, stroke=0, fill=1)
                if point["bmr_kcal"] is not None:
                    y = base + point["bmr_kcal"] / scale * (top - base)
                    if previous is not None:
                        canvas.setStrokeColor(ice)
                        canvas.setLineWidth(1.6)
                        canvas.line(previous[0], previous[1], x, y)
                    previous = (x, y)
                else:
                    previous = None
                canvas.setFillColor(muted)
                canvas.setFont(font_name, 7)
                label = point["period"][-5:] if len(self.points) > 1 else point["period"]
                canvas.drawCentredString(x, 20, label)
            canvas.setFont(font_name, 8)
            canvas.setFillColor(muted)
            canvas.drawString(left, 151, "每周期 kcal")
            canvas.drawRightString(right, 151, f"最高 {_number(scale)}")

    class BodyTrend(Flowable):
        def __init__(self, points: list[dict]):
            super().__init__()
            self.points = points
            self.width, self.height = 500, 150

        def draw(self):
            canvas = self.canv
            left, right, base, top = 34, self.width - 32, 29, 126
            canvas.setStrokeColor(colors.HexColor("#DCE5E6"))
            canvas.line(left, base, right, base)
            fats = [p["body_fat_pct"] for p in self.points if p["body_fat_pct"] is not None]
            minimum = min(fats) - 1 if fats else 0
            maximum = max(fats) + 1 if fats else 1
            volume_max = max(1, *(p["training_volume_kg"] for p in self.points))
            canvas.setFont(font_name, 7)
            canvas.setFillColor(muted)
            canvas.drawString(left, 132, "左轴：体脂 %")
            canvas.drawRightString(right, 132, "右轴：训练容量 kg")
            prior_fat = prior_volume = None
            for index, point in enumerate(self.points):
                x = left + (right - left) * index / max(1, len(self.points) - 1)
                canvas.setFillColor(muted)
                canvas.drawCentredString(x, 15, point["week"][-3:])
                volume_y = base + point["training_volume_kg"] / volume_max * (top - base)
                canvas.setStrokeColor(blue)
                canvas.setLineWidth(1.7)
                if prior_volume is not None:
                    canvas.line(prior_volume[0], prior_volume[1], x, volume_y)
                prior_volume = (x, volume_y)
                if point["body_fat_pct"] is None:
                    prior_fat = None  # missing observations are not interpolated
                    continue
                fat_y = base + (point["body_fat_pct"] - minimum) / (maximum - minimum) * (top - base)
                canvas.setStrokeColor(red)
                if prior_fat is not None:
                    canvas.line(prior_fat[0], prior_fat[1], x, fat_y)
                canvas.setFillColor(red)
                canvas.circle(x, fat_y, 2.5, stroke=0, fill=1)
                prior_fat = (x, fat_y)

    title = ParagraphStyle("title", fontName=font_name, fontSize=20, leading=27, textColor=ink)
    subtitle = ParagraphStyle("subtitle", fontName=font_name, fontSize=10, leading=16, textColor=muted)
    section = ParagraphStyle("section", fontName=font_name, fontSize=13, leading=20,
                             textColor=ink, spaceBefore=14, spaceAfter=7, keepWithNext=True)
    body = ParagraphStyle("body", fontName=font_name, fontSize=9, leading=15, textColor=ink)
    note = ParagraphStyle("note", fontName=font_name, fontSize=8.5, leading=14, textColor=muted)

    def styled_table(rows: list[list[str]], widths: list[float]) -> Table:
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("BACKGROUND", (0, 0), (-1, 0), light),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#DCE5E6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFCFC")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    totals, macros, energy, composition, habits = (snapshot[key] for key in
                                                 ("totals", "macros", "energy", "composition", "habits"))
    story = [Paragraph("合成样例 · NutriPulse 数据分析报告" if synthetic_sample
                       else "NutriPulse 数据分析报告", title),
             Paragraph(f"{PERIOD_LABELS[period]}统计 · {snapshot['start']} 至 {snapshot['end']} · "
                       f"生成时间 {utc_now()[:16].replace('T', ' ')} UTC", subtitle),
             *([Paragraph("此文件仅含临时合成数据，用于 PDF 版式验收，并非真实用户报告。", note)]
               if synthetic_sample else []),
             Spacer(1, 12),
             styled_table([
                 ["摄入热量", "估算总消耗", "净能量差", "训练容量"],
                 [_number(totals["intake_kcal"], "kcal"),
                  _number(totals["expenditure_kcal"], "kcal"),
                  _number(totals["net_kcal"], "kcal"),
                  _number(totals["training_volume_kg"], "kg")]], [120] * 4),
             Spacer(1, 5),
             Paragraph(f"有记录 {totals['logged_days']}/{totals['days']} 天；代谢目标覆盖 "
                       f"{totals['target_days']}/{totals['days']} 天；饮水记录 {totals['water_ml']} ml。"
                       "净差 = 摄入 - 估算总消耗，负值为估算赤字；无目标日不填造消耗或净差。", note),
             Paragraph("摄入与消耗", section),
             Paragraph("<font color='#2ECC71'>■ 摄入</font>　"
                       "<font color='#FF5252'>■ 总消耗</font>　"
                       "<font color='#00BEC5'>─ BMR 基线</font>（有目标时显示）", note),
             EnergyBars(energy["series"]),
             styled_table([["周期", "摄入", "总消耗", "BMR", "净差", "容量 kg"]] + [
                 [p["period"], _number(p["intake_kcal"]), _number(p["expenditure_kcal"]),
                  _number(p["bmr_kcal"]), _number(p["net_kcal"]),
                  _number(p["training_volume"])] for p in energy["series"]],
                 [95, 76, 76, 76, 76, 76]),
             Paragraph("三大营养素", section)]
    actual, target = macros["actual"], macros["target"]
    macro_kcal = sum(actual[key] * (9 if key == "fat_g" else 4)
                     for key in ("carb_g", "protein_g", "fat_g"))
    macro_rows = [["营养素", "实际 g", "目标 g", "已记录供能占比"]]
    for label, key in (("碳水化合物", "carb_g"), ("蛋白质", "protein_g"), ("脂肪", "fat_g")):
        kcal = actual[key] * (9 if key == "fat_g" else 4)
        macro_rows.append([label, _number(actual[key]), _number(target[key]) if macros["target_days"] else "--",
                           f"{kcal / macro_kcal * 100:.1f}%" if macro_kcal else "--"])
    story.append(styled_table(macro_rows, [120, 95, 95, 170]))
    if macros["incomplete_items"]:
        story.append(Paragraph(f"注意：{macros['incomplete_items']} 项实记食物未填写三大营养素；比例仅基于已填写值。", note))
    if not macros["target_days"]:
        story.append(Paragraph("所选周期无有效营养目标，目标克数留空。", note))
    water, fiber, meals, training = (habits[key] for key in ("water", "fiber", "meals", "training"))
    meal_rate = f"{meals['three_meal_logging_pct']:.1f}%" if meals["three_meal_logging_pct"] is not None else "样本不足"
    training_rate = f"{training['completion_pct']:.1f}%" if training["completion_pct"] is not None else "样本不足"
    story.extend([
        Paragraph("生活习惯记录", section),
        styled_table([
            ["维度", "所选周期的实记情况"],
            ["饮水", f"{water['recorded_ml']} ml；有记录 {water['recorded_days']}/{habits['observed_days']} 天；"
             f"达标 {water['met_goal_days']}/{water['evaluated_goal_days']} 个可评估已结束日"],
            ["膳食纤维", f"已知 {_number(fiber['known_g'], 'g')}；已知 {fiber['known_items']}/"
             f"{fiber['consumed_items']} 个实记食物；未知 {fiber['unknown_items']} 个"],
            ["三餐记录", f"早餐、午餐、晚餐均有记录 {meals['three_main_meals_logged_days']}/"
             f"{meals['logged_closed_days']} 个有餐记录的已结束日；占比 {meal_rate}"],
            ["计划跟练", f"完成 {training['completed_sessions']}/"
             f"{training['scheduled_closed_sessions']} 个已结束排程；部分完成 "
             f"{training['partial_sessions']} 个；完成率 {training_rate}"],
        ], [96, 384]),
        Paragraph("缺失记录不当作零摄入；膳食纤维未知项不参与克数合计；三餐与跟练占比至少有 3 个可评估样本才显示。"
                  + ("今天尚未结束，以上含今天的摄入/饮水仅为阶段性记录。" if habits["today_is_partial"] else ""), note),
    ])
    if training["legacy_stop_unknown_sessions"]:
        story.append(Paragraph(f"另有 {training['legacy_stop_unknown_sessions']} 个旧版停练排程缺少停练日期，"
                               "未计入完成率分母。", note))
    story.extend([Paragraph("体重、体脂率与周训练容量（最近 8 周）", section),
                  Paragraph("图中红线为体脂率、蓝线为训练容量；体重按周列于表中。"
                            "不同量纲仅供并列观察；缺失测量不插值，也不推断因果。", note),
                  BodyTrend(composition["series"]),
                  styled_table([["周", "体重 kg", "体脂率 %", "训练容量 kg"]] + [
                      [point["week"], _number(point["weight_kg"]), _number(point["body_fat_pct"]),
                       _number(point["training_volume_kg"])] for point in composition["series"]],
                      [92, 122, 122, 144]),
                  Paragraph("规则分析与建议", section)])
    for observation in snapshot["diagnosis"]["observations"]:
        story.append(Paragraph("观察：" + escape(observation), body))
    for advice in snapshot["diagnosis"]["advice"]:
        story.append(Paragraph("建议：" + escape(advice), body))
    story.append(Spacer(1, 8))
    story.append(Paragraph("此报告包含个人健康记录，请妥善保存。食品营养、活动消耗和体脂均为估算或设备记录，"
                           "报告不构成医疗诊断。算法版本：energy-v1；报告版本：analytics-pdf-v3。", note))

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=52, bottomMargin=47, title="NutriPulse 数据分析报告",
                            author="NutriPulse")

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(muted)
        canvas.drawString(42, A4[1] - 30, "NutriPulse · 健康数据报告")
        canvas.setStrokeColor(colors.HexColor("#DCE5E6"))
        canvas.line(42, A4[1] - 36, A4[0] - 42, A4[1] - 36)
        canvas.drawString(42, 27, "仅供个人记录与复盘")
        canvas.drawRightString(A4[0] - 42, 27, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    pdf = output.getvalue()
    if not pdf.startswith(b"%PDF-"):
        raise ApiError("PDF_RENDER_FAILED", "PDF 报告生成失败", 500)
    return pdf
