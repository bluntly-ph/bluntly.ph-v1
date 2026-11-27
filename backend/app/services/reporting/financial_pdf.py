"""The financial report as a branded A4 PDF (Figma PDF/Financial report pages
8029:12942 and 8029:13078; meeting 2026-10-02, 18:06 and 29:16).

The Figma pages are 595 x 842, an A4 sheet in points, so the design's numbers
are used as they are: 40 pt side margins, a 45 pt head, 28 pt between blocks,
26 pt table rows. Poppins as on the site, with the peso sign drawn from a
one-glyph DejaVu subset (Poppins has no ₱). The head carries the `bluntly`
wordmark with its swoosh, as the owner asked in the meeting, in place of the
template's placeholder "b" tile.

Layout is a small flow: blocks are placed top to bottom and a block that does
not fit opens a new page; a table taller than a page continues on the next one
under its section title and header row. Every page gets the head and the foot
("Page n of N"), so the page count is known before anything is drawn.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.core.constants import MANILA
from app.schemas.reporting import FinancialReportOut
from app.services.reporting.financial import (
    SECTION_LABELS,
    in_label,
    marketplace_label,
    period_of,
    title_for,
)

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "report"

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 40.0, 40.0, 32.0
CONTENT_W = PAGE_W - 2 * MARGIN_X
HEAD_H = 28.0 + 16.0 + 1.0           # brand row, padding, rule
CONTENT_TOP = MARGIN_TOP + HEAD_H + 24.0
FOOT_H = 1.0 + 12.0 + 10.0           # rule, padding, caption
CONTENT_BOTTOM = PAGE_H - MARGIN_BOTTOM - FOOT_H - 24.0
BLOCK_GAP = 28.0
INNER_GAP = 10.0
ROW_H = 26.0

INK = HexColor("#202020")
SECONDARY = Color(32 / 255, 32 / 255, 32 / 255, alpha=0.7)
CENTS = HexColor("#8C8C8C")
RULE = HexColor("#E6E6E6")
BRAND = HexColor("#EF5821")
SUCCESS = HexColor("#34CA43")
INFO = HexColor("#1A6BC1")  # --semantic-info-blue
SHARE_COLOURS = {"bluntly": BRAND, "reviewers": SUCCESS, "honesty_fund": INFO}

REGULAR, MEDIUM, SEMIBOLD, PESO = "Poppins", "Poppins-Medium", "Poppins-SemiBold", "DejaVuPeso"
#: Poppins: ascender 1050, descender -350 per 1000. With the design's line
#: height of 1 the baseline sits 0.85 em below the top of the line box.
BASELINE = 0.85

_fonts_ready = False


def _fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(TTFont(REGULAR, str(ASSETS / "Poppins-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(MEDIUM, str(ASSETS / "Poppins-Medium.ttf")))
    pdfmetrics.registerFont(TTFont(SEMIBOLD, str(ASSETS / "Poppins-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont(PESO, str(ASSETS / "DejaVuSans-Peso.ttf")))
    _fonts_ready = True


# --------------------------------------------------------------------- text

def _runs(text: str, font: str) -> list[tuple[str, str]]:
    """Split around the peso sign, which only the fallback font has."""
    runs: list[tuple[str, str]] = []
    for ch in text:
        f = PESO if ch == "₱" else font
        if runs and runs[-1][1] == f:
            runs[-1] = (runs[-1][0] + ch, f)
        else:
            runs.append((ch, f))
    return runs


def width(text: str, font: str, size: float) -> float:
    return sum(pdfmetrics.stringWidth(seg, f, size) for seg, f in _runs(text, font))


def _peso_parts(amount: Decimal, *, negative: bool = False) -> tuple[str, str]:
    """('−₱1,120', '.00'): the whole part and the cents, drawn in two colours."""
    value = abs(amount) if negative else amount
    sign = "−" if negative or value < 0 else ""
    whole, cents = f"{abs(value):,.2f}".split(".")
    return f"{sign}₱{whole}", f".{cents}"


@dataclass
class Span:
    text: str
    font: str = REGULAR
    colour: Color = INK


class Pen:
    """Draws with a top-left origin, as the design is measured."""

    def __init__(self, canvas: Canvas):
        self.c = canvas

    def text(self, x: float, top: float, spans: list[Span], size: float,
             align: str = "left") -> None:
        total = sum(width(s.text, s.font, size) for s in spans)
        if align == "right":
            x -= total
        y = PAGE_H - top - BASELINE * size
        for s in spans:
            for seg, f in _runs(s.text, s.font):
                self.c.setFillColor(s.colour)
                self.c.setFont(f, size)
                self.c.drawString(x, y, seg)
                x += pdfmetrics.stringWidth(seg, f, size)

    def line(self, x1: float, top: float, x2: float, colour: Color = RULE,
             weight: float = 1.0) -> None:
        self.c.setStrokeColor(colour)
        self.c.setLineWidth(weight)
        y = PAGE_H - top - weight / 2
        self.c.line(x1, y, x2, y)

    def rect(self, x: float, top: float, w: float, h: float, *, radius: float = 0,
             fill: Color | None = None, stroke: Color | None = None) -> None:
        if w <= 0 or h <= 0:
            return
        if fill is not None:
            self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(1)
        r = min(radius, w / 2, h / 2)
        self.c.roundRect(x, PAGE_H - top - h, w, h, r,
                         stroke=1 if stroke is not None else 0,
                         fill=1 if fill is not None else 0)


def money_spans(amount: Decimal, font: str = REGULAR, *, negative: bool = False) -> list[Span]:
    whole, cents = _peso_parts(amount, negative=negative)
    return [Span(whole, font, INK), Span(cents, font, CENTS)]


def dash() -> list[Span]:
    return [Span("—", REGULAR, SECONDARY)]


# --------------------------------------------------------------------- tables

@dataclass
class Col:
    header: str
    width: float | None = None   # None: takes the remaining width
    align: str = "right"


#: A cell: spans, optionally led by a share-colour dot.
Cell = tuple[list[Span], Color | None]


def cell(spans: list[Span], dot: Color | None = None) -> Cell:
    return spans, dot


def label(text: str, font: str = REGULAR, colour: Color = INK) -> Cell:
    return [Span(text, font, colour)], None


def _x_positions(cols: list[Col]) -> list[tuple[float, float]]:
    fixed = sum(c.width or 0 for c in cols)
    flex = max(0.0, CONTENT_W - fixed)
    out, x = [], MARGIN_X
    for c in cols:
        w = c.width if c.width is not None else flex
        out.append((x, w))
        x += w
    return out


def _draw_cells(pen: Pen, cols: list[Col], cells: list[Cell], top: float, size: float = 12) -> None:
    for (x, w), col, (spans, dot) in zip(_x_positions(cols), cols, cells, strict=True):
        text_top = top + 7
        if col.align == "right":
            pen.text(x + w, text_top, spans, size, align="right")
        else:
            if dot is not None:
                pen.rect(x, text_top + 3, 6, 6, radius=3, fill=dot)
                x += 12
            pen.text(x, text_top, spans, size)


# --------------------------------------------------------------------- flow

@dataclass
class Block:
    height: float
    draw: Callable[[Pen, float], None]
    #: Stay on the same page as the next block (titles, header rows).
    keep_with_next: bool = False
    gap_after: float = INNER_GAP
    #: A table's header row, repeated when its table continues on a new page.
    table_head: bool = False


@dataclass
class Section:
    title: str
    note: str
    blocks: list[Block] = field(default_factory=list)


def _section_head(title: str, note: str) -> Block:
    def draw(pen: Pen, top: float) -> None:
        pen.text(MARGIN_X, top, [Span(title, SEMIBOLD)], 16)
        if note:
            pen.text(PAGE_W - MARGIN_X, top + 6, [Span(note, REGULAR, SECONDARY)], 10,
                     align="right")
    return Block(16, draw, keep_with_next=True)


def _table_head(cols: list[Col]) -> Block:
    def draw(pen: Pen, top: float) -> None:
        _draw_cells(pen, cols, [label(c.header, MEDIUM, SECONDARY) for c in cols], top)
        pen.line(MARGIN_X, top + ROW_H, PAGE_W - MARGIN_X)
    return Block(ROW_H + 1, draw, keep_with_next=True, gap_after=0, table_head=True)


def _row(cols: list[Col], cells: list[Cell], *, total: bool = False, last: bool = False) -> Block:
    def draw(pen: Pen, top: float) -> None:
        pen.line(MARGIN_X, top, PAGE_W - MARGIN_X, INK if total else RULE)
        _draw_cells(pen, cols, cells, top + 1)
    return Block(ROW_H + 1, draw, gap_after=INNER_GAP if last else 0)


def _table(cols: list[Col], rows: list[list[Cell]], total: list[Cell] | None) -> list[Block]:
    blocks = [_table_head(cols)]
    for i, r in enumerate(rows):
        blocks.append(_row(cols, r, last=total is None and i == len(rows) - 1))
    if total is not None:
        blocks.append(_row(cols, total, total=True, last=True))
    return blocks


@dataclass
class Placed:
    block: Block
    top: float


def _paginate(first: list[Block], sections: list[Section]) -> list[list[Placed]]:
    pages: list[list[Placed]] = [[]]
    cursor = CONTENT_TOP

    def new_page() -> None:
        nonlocal cursor
        pages.append([])
        cursor = CONTENT_TOP

    def height_of(blocks: list[Block]) -> float:
        return sum(b.height for b in blocks) + sum(b.gap_after for b in blocks[:-1])

    for b in first:
        pages[-1].append(Placed(b, cursor))
        cursor += b.height + b.gap_after

    room = CONTENT_BOTTOM - CONTENT_TOP
    for section in sections:
        head = _section_head(section.title, section.note)
        blocks = [head, *section.blocks]
        if pages[-1]:
            cursor += BLOCK_GAP - pages[-1][-1].block.gap_after
        whole = height_of(blocks)
        if cursor + whole > CONTENT_BOTTOM and whole <= room and pages[-1]:
            new_page()
        table_head: Block | None = None
        i = 0
        while i < len(blocks):
            b = blocks[i]
            if b.table_head:
                table_head = b
            # Keep a title or header row with what follows it.
            run = [b]
            j = i
            while blocks[j].keep_with_next and j + 1 < len(blocks):
                j += 1
                run.append(blocks[j])
            need = height_of(run)
            if cursor + need > CONTENT_BOTTOM and pages[-1]:
                new_page()
                if b is not head:
                    cont = _section_head(f"{section.title} (continued)", "")
                    pages[-1].append(Placed(cont, cursor))
                    cursor += cont.height + cont.gap_after
                    if table_head is not None and not b.table_head:
                        pages[-1].append(Placed(table_head, cursor))
                        cursor += table_head.height + table_head.gap_after
            for rb in run:
                pages[-1].append(Placed(rb, cursor))
                cursor += rb.height + rb.gap_after
            i = j + 1
    return pages


# --------------------------------------------------------------------- content

def _fmt_day(d: date) -> str:
    return f"{d.day} {d.strftime('%b')} {d.year}"


def _title_blocks(report: FinancialReportOut, generated_by: str | None) -> list[Block]:
    period = period_of(report)
    at = report.meta.generated_at.astimezone(MANILA)
    by = f" by {generated_by}" if generated_by else ""
    subtitle = (f"{report.span} · Generated {at.day} {at.strftime('%b %Y, %H:%M')} "
                f"Manila time{by}")

    def title(pen: Pen, top: float) -> None:
        pen.text(MARGIN_X, top, [Span(title_for(period), SEMIBOLD)], 24)
        pen.text(MARGIN_X, top + 28, [Span(subtitle, REGULAR, SECONDARY)], 12)

    k = report.kpis
    kpis = [("Net commission", k.net_commission), ("Money in", k.money_in),
            ("Money out", k.money_out), ("Still owed", k.still_owed)]

    def tiles(pen: Pen, top: float) -> None:
        w = (CONTENT_W - 3 * 8) / 4
        for i, (name, amount) in enumerate(kpis):
            x = MARGIN_X + i * (w + 8)
            pen.rect(x, top, w, 56, radius=10, stroke=RULE)
            pen.text(x + 13, top + 13, [Span(name, REGULAR, SECONDARY)], 10)
            pen.text(x + 13, top + 27, money_spans(amount, SEMIBOLD), 16)

    return [Block(40, title, gap_after=BLOCK_GAP), Block(56, tiles, gap_after=0)]


def _revenue(report: FinancialReportOut) -> Section:
    r = report.revenue
    period = period_of(report)
    s = Section(SECTION_LABELS["revenue"], f"Recognised {in_label(period)}")

    def bar(pen: Pen, top: float) -> None:
        parts = [(SHARE_COLOURS[sh.key], sh.amount) for sh in r.shares if sh.amount > 0]
        total = sum((a for _, a in parts), Decimal("0"))
        if total <= 0:
            pen.rect(MARGIN_X, top, CONTENT_W, 8, radius=4, fill=RULE)
            return
        avail = CONTENT_W - 2 * (len(parts) - 1)
        x = MARGIN_X
        for colour, amount in parts:
            w = float(amount / total) * avail
            pen.rect(x, top, w, 8, radius=4, fill=colour)
            x += w + 2

    s.blocks.append(Block(8, bar))
    amount_cols = [Col("", None, "left"), Col("Amount", 120)]
    s.blocks += _table(amount_cols, [
        [label("Commission earned"), cell(money_spans(r.earned))],
        [label("Reversed by returns"), cell(money_spans(r.reversed, negative=r.reversed > 0))],
        [label("    of which absorbed (returned after payout)", REGULAR, SECONDARY),
         cell([Span(t.text, t.font, SECONDARY) for t in money_spans(r.absorbed)])],
    ], [label("Net commission", MEDIUM), cell(money_spans(r.net, MEDIUM))])
    share_cols = [Col("Share", None, "left"), Col("Rate", 80), Col("Amount", 120)]
    s.blocks += _table(share_cols, [
        [cell([Span(sh.label)], SHARE_COLOURS[sh.key]),
         label(f"{sh.rate:.0f}%" if sh.rate is not None else "—"),
         cell(money_spans(sh.amount))]
        for sh in r.shares
    ], None)
    return s


def _by_marketplace(report: FinancialReportOut) -> Section:
    r = report.revenue
    s = Section("By marketplace", "")
    cols = [Col("Marketplace", None, "left"), Col("Orders", 90), Col("Commissions", 100),
            Col("Earned", 120)]
    rows = [[label(marketplace_label(m.marketplace)), label(f"{m.orders:,}"),
             label(f"{m.commissions:,}"), cell(money_spans(m.earned))]
            for m in r.by_marketplace]
    if not rows:
        rows = [[label("No marketplace activity in this period.", REGULAR, SECONDARY),
                 cell(dash()), cell(dash()), cell(dash())]]
    s.blocks += _table(cols, rows, [label("Total", MEDIUM), label(f"{r.orders_total:,}", MEDIUM),
                                    label(f"{r.commissions_total:,}", MEDIUM),
                                    cell(money_spans(r.earned, MEDIUM))])
    return s


def _money_in(report: FinancialReportOut) -> Section:
    m = report.money_in
    period = period_of(report)
    s = Section(SECTION_LABELS["money_in"], "Marketplace remittances")
    cols = [Col("Month", None, "left"), Col("Expected", 100), Col("Received", 100),
            Col("Shortfall", 90), Col("Status", 80)]
    rows = []
    for row in m.rows:
        rows.append([
            label(f"{marketplace_label(row.marketplace)} · {row.cycle_month.strftime('%b %Y')}"),
            cell(money_spans(row.expected)),
            cell(money_spans(row.received) if row.received is not None else dash()),
            cell(money_spans(row.shortfall) if row.shortfall is not None else dash()),
            label("Cleared" if row.status == "cleared" else "Clearing"),
        ])
    if not rows:
        rows = [[label("No remittances or commissions in this period.", REGULAR, SECONDARY),
                 cell(dash()), cell(dash()), cell(dash()), label("")]]
    s.blocks += _table(cols, rows, [
        label(f"Received {in_label(period)}", MEDIUM), label(""),
        cell(money_spans(m.received_total, MEDIUM)),
        cell(money_spans(m.shortfall_total, MEDIUM)), label("")])
    return s


def _money_out(report: FinancialReportOut) -> Section:
    m = report.money_out
    period = period_of(report)
    s = Section(SECTION_LABELS["money_out"], "Payouts and Honesty Fund")
    cols = [Col("", None, "left"), Col("Count", 80), Col("Amount", 120)]

    def line(name: str, count: int, amount: Decimal, muted: bool = False) -> list[Cell]:
        colour = SECONDARY if muted else INK
        spans = money_spans(amount)
        if muted:
            spans = [Span(sp.text, sp.font, SECONDARY) for sp in spans]
        return [label(name, REGULAR, colour), label(f"{count:,}", REGULAR, colour), cell(spans)]

    rows = [
        line("Payouts sent", m.sent.count, m.sent.amount),
        line("Payouts to send", m.to_send.count, m.to_send.amount),
        line("Failed, returned to wallets", m.failed.count, m.failed.amount),
        line("Cancelled, returned to wallets", m.cancelled.count, m.cancelled.amount),
    ]
    if m.sandbox_excluded and m.sandbox_excluded.count:
        # PayPal sandbox = QA test money: shown, never added to Paid out.
        rows.append(line("Sandbox payouts, no real money (not counted)",
                         m.sandbox_excluded.count, m.sandbox_excluded.amount, muted=True))
    for credit in m.honesty_fund:
        rows.append(line(
            f"Honesty Fund for {credit.cycle_month.strftime('%B')} "
            f"(credited to wallets {credit.credited_on.day} {credit.credited_on.strftime('%b')})",
            credit.count, credit.amount, muted=True))
    if not m.honesty_fund:
        rows.append(line("Honesty Fund distributed to wallets", 0, Decimal("0.00"), muted=True))
    s.blocks += _table(cols, rows, [label(f"Paid out {in_label(period)}", MEDIUM), label(""),
                                    cell(money_spans(m.paid_out_total, MEDIUM))])
    return s


def _liabilities(report: FinancialReportOut) -> Section:
    li = report.liabilities
    at = li.as_of.astimezone(MANILA)
    s = Section(SECTION_LABELS["liabilities"],
                f"As of {at.day} {at.strftime('%b %Y, %H:%M')} Manila time")
    cols = [Col("", None, "left"), Col("Amount", 120)]
    unattributed = "Unattributed sales (no reviewer)"
    if li.unattributed_count:
        unattributed += f" · {li.unattributed_count:,} orders"
    s.blocks += _table(cols, [
        [label("Cleared, in reviewer wallets"), cell(money_spans(li.cleared_in_wallets))],
        [label("Payouts to send"), cell(money_spans(li.payouts_to_send))],
        [label("Still clearing, awaiting remittance"), cell(money_spans(li.still_clearing))],
        [label(unattributed), cell(money_spans(li.unattributed))],
    ], None)
    return s


def _sections(report: FinancialReportOut, chosen: list[str]) -> list[Section]:
    out: list[Section] = []
    if "revenue" in chosen:
        out += [_revenue(report), _by_marketplace(report)]
    if "money_in" in chosen:
        out.append(_money_in(report))
    if "money_out" in chosen:
        out.append(_money_out(report))
    if "liabilities" in chosen:
        out.append(_liabilities(report))
    return out


def _wordmark() -> ImageReader:
    return ImageReader(str(ASSETS / "bluntly-wordmark.png"))


def _head_and_foot(pen: Pen, report: FinancialReportOut, number: int, total: int,
                   logo: ImageReader) -> None:
    period = period_of(report)
    lw, lh = logo.getSize()
    h = 20.0
    w = h * lw / lh
    pen.c.drawImage(logo, MARGIN_X, PAGE_H - MARGIN_TOP - 4 - h, width=w, height=h, mask="auto")
    right = PAGE_W - MARGIN_X
    pen.text(right, MARGIN_TOP, [Span("Financial report", REGULAR, SECONDARY)], 12, align="right")
    pen.text(right, MARGIN_TOP + 14, [Span(title_for(period), MEDIUM)], 14, align="right")
    pen.line(MARGIN_X, MARGIN_TOP + 28 + 16, right)

    foot_top = PAGE_H - MARGIN_BOTTOM - FOOT_H
    pen.line(MARGIN_X, foot_top, right)
    pen.text(MARGIN_X, foot_top + 13,
             [Span(f"Bluntly.ph · Financial report · {report.span_short}", REGULAR, SECONDARY)], 10)
    pen.text(right, foot_top + 13, [Span(f"Page {number} of {total}", REGULAR, SECONDARY)], 10,
             align="right")


def render(report: FinancialReportOut, sections: list[str], *,
           generated_by: str | None = None) -> tuple[bytes, int]:
    """The PDF bytes and its page count."""
    _fonts()
    pages = _paginate(_title_blocks(report, generated_by), _sections(report, sections))
    buffer = io.BytesIO()
    period = period_of(report)
    canvas = Canvas(buffer, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    canvas.setTitle(f"Bluntly.ph — Financial report — {title_for(period)}")
    canvas.setAuthor("Bluntly.ph")
    canvas.setSubject(f"Financial report, {report.span}")
    canvas.setCreator("Bluntly.ph admin")
    pen = Pen(canvas)
    logo = _wordmark()
    for number, placed in enumerate(pages, start=1):
        _head_and_foot(pen, report, number, len(pages), logo)
        for p in placed:
            p.block.draw(pen, p.top)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue(), len(pages)


def filename(report: FinancialReportOut) -> str:
    return f"bluntly-financial-report-{period_of(report).slug}.pdf".lower()
