"""Generate PDF reports from analysis results using reportlab."""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Register CJK fonts globally for reportlab
_pdfs_cjk_registered = False


def _register_cjk_fonts():
    global _pdfs_cjk_registered
    if _pdfs_cjk_registered:
        return
    for font_path in [
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
    ]:
        if Path(font_path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", font_path))
                pdfmetrics.registerFont(TTFont("CJK-Bold", font_path))
                _pdfs_cjk_registered = True
                return
            except Exception:
                pass
    _pdfs_cjk_registered = True  # mark as done even if no fonts found


def _strip_think(text: str) -> str:
    return re.sub(r"\<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _strip_md_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _signal_color(signal: str) -> tuple:
    s = signal.upper()
    if "BUY" in s:
        return colors.HexColor("#22c55e")
    if "SELL" in s:
        return colors.HexColor("#ef4444")
    return colors.HexColor("#fbbf24")


_REPORT_SECTIONS = [
    ("market_report", "技术分析报告"),
    ("sentiment_report", "市场情绪报告"),
    ("news_report", "新闻舆情报告"),
    ("fundamentals_report", "基本面报告"),
    ("policy_report", "政策分析报告"),
    ("hot_money_report", "游资追踪报告"),
    ("lockup_report", "解禁/减持报告"),
]


class _ReportPDF:
    def __init__(self, ticker: str, trade_date: str, signal: str) -> None:
        self.ticker = ticker
        self.trade_date = trade_date
        self.signal = signal
        self._buffer = io.BytesIO()
        _register_cjk_fonts()

        if pdfmetrics.getFont("CJK"):
            self._body_font = "CJK"
            self._bold_font = "CJK-Bold"
        else:
            self._body_font = "Helvetica"
            self._bold_font = "Helvetica-Bold"

        self._styles = getSampleStyleSheet()
        self._create_styles()

        self._doc = SimpleDocTemplate(
            self._buffer,
            pagesize=A4,
            leftMargin=20*mm,
            rightMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm,
            title=f"A股多Agent投研分析 {ticker}",
            author="TradingAgents-Astock",
        )
        self._story: list = []

    def _create_styles(self) -> None:
        self._styles.add(ParagraphStyle(
            name="RL_CoverTitle",
            fontName=self._bold_font,
            fontSize=24,
            textColor=colors.HexColor("#ff5a1f"),
            alignment=TA_CENTER,
            spaceAfter=20,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_CoverTicker",
            fontName=self._bold_font,
            fontSize=36,
            textColor=colors.HexColor("#1a1a2e"),
            alignment=TA_CENTER,
            spaceAfter=16,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_CoverInfo",
            fontName=self._body_font,
            fontSize=14,
            textColor=colors.HexColor("#666666"),
            alignment=TA_CENTER,
            spaceAfter=8,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_CoverSignal",
            fontName=self._bold_font,
            fontSize=40,
            alignment=TA_CENTER,
            spaceAfter=20,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_CoverDisclaimer",
            fontName=self._body_font,
            fontSize=9,
            textColor=colors.HexColor("#888888"),
            alignment=TA_CENTER,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_SectionTitle",
            fontName=self._bold_font,
            fontSize=16,
            textColor=colors.HexColor("#ff5a1f"),
            spaceBefore=12,
            spaceAfter=12,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_Body",
            fontName=self._body_font,
            fontSize=10,
            textColor=colors.HexColor("#333333"),
            leading=14,
            spaceAfter=6,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_Heading2",
            fontName=self._bold_font,
            fontSize=13,
            textColor=colors.HexColor("#333333"),
            spaceBefore=10,
            spaceAfter=6,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_Heading3",
            fontName=self._bold_font,
            fontSize=11,
            textColor=colors.HexColor("#555555"),
            spaceBefore=8,
            spaceAfter=4,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_Bullet",
            fontName=self._body_font,
            fontSize=10,
            textColor=colors.HexColor("#333333"),
            leading=14,
            leftIndent=20,
            spaceAfter=4,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_TableCell",
            fontName=self._body_font,
            fontSize=9,
            textColor=colors.HexColor("#555555"),
            leading=12,
        ))
        self._styles.add(ParagraphStyle(
            name="RL_Footer",
            fontName=self._body_font,
            fontSize=8,
            textColor=colors.HexColor("#999999"),
            alignment=TA_CENTER,
        ))

    def _make_font(self, bold: bool = False, size: int = 10) -> str:
        if self._body_font == "CJK":
            return "CJK" if not bold else "CJK"
        return "Helvetica-Bold" if bold else "Helvetica"

    def _add_cover(self) -> None:
        self._story.append(Spacer(1, 60*mm))
        self._story.append(Paragraph("A股多Agent投研分析报告", self._styles["RL_CoverTitle"]))
        self._story.append(Spacer(1, 10*mm))
        self._story.append(Paragraph(self.ticker, self._styles["RL_CoverTicker"]))
        self._story.append(Spacer(1, 8*mm))
        self._story.append(Paragraph(f"分析日期: {self.trade_date}", self._styles["RL_CoverInfo"]))
        self._story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", self._styles["RL_CoverInfo"]))
        self._story.append(Spacer(1, 10*mm))

        signal_color = _signal_color(self.signal)
        signal_style = ParagraphStyle(
            name="CoverSignalColor",
            fontName=self._bold_font,
            fontSize=40,
            textColor=signal_color,
            alignment=TA_CENTER,
        )
        self._story.append(Paragraph(self.signal.upper(), signal_style))
        self._story.append(Spacer(1, 10*mm))
        self._story.append(Paragraph(
            "免责声明: 本报告由 AI 多 Agent 系统自动生成, 仅供学习研究与技术演示, "
            "不构成任何投资建议。投资决策请咨询持牌专业机构。",
            self._styles["RL_CoverDisclaimer"],
        ))
        self._story.append(PageBreak())

    def _add_section(self, title: str, content: str) -> None:
        self._story.append(Paragraph(title, self._styles["RL_SectionTitle"]))
        cleaned = _strip_think(content)
        self._render_markdown(cleaned)
        self._story.append(PageBreak())

    def _render_markdown(self, text: str) -> None:
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                self._story.append(Spacer(1, 3*mm))
                i += 1
                continue

            if stripped.startswith("###"):
                self._story.append(Paragraph(stripped.lstrip("#").strip(), self._styles["RL_Heading3"]))
                i += 1
                continue
            if stripped.startswith("##"):
                self._story.append(Paragraph(stripped.lstrip("#").strip(), self._styles["RL_Heading2"]))
                i += 1
                continue
            if stripped.startswith("#"):
                self._story.append(Paragraph(stripped.lstrip("#").strip(), self._styles["RL_SectionTitle"]))
                i += 1
                continue

            if stripped in ("---", "***", "___"):
                self._story.append(Spacer(1, 6*mm))
                i += 1
                continue

            if re.match(r"^[-*]\s", stripped) or re.match(r"^\d+[.)]\s", stripped):
                body = stripped[2:].strip() if re.match(r"^[-*]\s", stripped) else stripped.split(" ", 1)[1]
                body = _strip_md_inline(body)
                self._story.append(Paragraph(f"• {body}", self._styles["RL_Bullet"]))
                i += 1
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                if re.match(r"^\|[-:\s|]+\|$", stripped):
                    i += 1
                    continue
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                cells = [_strip_md_inline(c) for c in cells]
                row_data = [[Paragraph(c, self._styles["RL_TableCell"]) for c in cells]]
                col_count = len(cells)
                col_widths = [(self._doc.width / col_count)] * col_count
                tbl = Table(row_data, colWidths=col_widths)
                tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                self._story.append(tbl)
                i += 1
                continue

            para_lines = []
            while i < len(lines):
                ln = lines[i].strip()
                if not ln or ln.startswith("#") or ln.startswith("|") or re.match(r"^[-*]\s", ln) or re.match(r"^\d+[.)]\s", ln) or ln in ("---", "***", "___"):
                    break
                para_lines.append(ln)
                i += 1

            if para_lines:
                para = " ".join(para_lines)
                para = _strip_md_inline(para)
                self._story.append(Paragraph(para, self._styles["RL_Body"]))
                self._story.append(Spacer(1, 2*mm))
                continue

            i += 1

    def build(self) -> bytes:
        self._add_cover()
        self._doc.build(self._story)
        return self._buffer.getvalue()


def generate_pdf(final_state: dict[str, Any], ticker: str, trade_date: str, signal: str) -> bytes:
    pdf = _ReportPDF(ticker, trade_date, signal)

    for key, title in _REPORT_SECTIONS:
        content = final_state.get(key, "")
        if content:
            pdf._add_section(title, str(content))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        parts = []
        if debate.get("bull_history"):
            parts.append(f"=== 多方论点 ===\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"\n=== 空方论点 ===\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"\n=== 研究经理决策 ===\n{debate['judge_decision']}")
        if parts:
            pdf._add_section("多空辩论", "\n".join(parts))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        pdf._add_section("交易员决策", _strip_think(str(trader_decision)))

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        pdf._add_section("最终投资建议", _strip_think(str(inv_plan)))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        parts = []
        for key_name, label in [("aggressive_history", "激进观点"),
                                 ("conservative_history", "保守观点"),
                                 ("neutral_history", "中性观点")]:
            if risk.get(key_name):
                parts.append(f"=== {label} ===\n{risk[key_name]}")
        if risk.get("judge_decision"):
            parts.append(f"\n=== 风控决策 ===\n{risk['judge_decision']}")
        if parts:
            pdf._add_section("风控评估", "\n".join(parts))

    final_decision = final_state.get("final_trade_decision", "")
    if final_decision:
        pdf._add_section("最终决策", _strip_think(str(final_decision)))

    return bytes(pdf.build())