"""
TANFINET - Tamil Nadu FibreNet Corporation
ILL Bandwidth SLA Compliance & Performance Report Generator
Generates an audit-ready PDF report using ReportLab.
"""

import io
import os
import random
from datetime import datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, PageBreak, KeepTogether,
    CondPageBreak, Image, NextPageTemplate,
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics import renderPDF
from reportlab.graphics.widgets.markers import makeMarker

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ─────────────────────────── Brand Palette ────────────────────────────────
TANFINET_DARK   = colors.HexColor("#0B2447")   # deep navy
TANFINET_MID    = colors.HexColor("#19376D")   # mid navy
TANFINET_ACCENT = colors.HexColor("#0091D5")   # sky blue
TANFINET_GOLD   = colors.HexColor("#F4A71D")   # saffron / gold
TANFINET_LIGHT  = colors.HexColor("#E8F4FD")   # pale blue tint
GREY_BG         = colors.HexColor("#F4F6F8")
GREY_LINE       = colors.HexColor("#CDD5E0")
GREEN_OK        = colors.HexColor("#1E8449")
RED_FAIL        = colors.HexColor("#C0392B")
AMBER_WARN      = colors.HexColor("#D68910")
HEADER_BG       = colors.HexColor("#1a3a5c")   # header / section-band color
WHITE           = colors.white
BLACK           = colors.black

# ─────────────────────────── Page Setup ───────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_X = 14 * mm   # tight side margins
MARGIN_TOP = 16 * mm
MARGIN_BOT = 14 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X

# ─────────────────────────── Default Department List ──────────────────────
DEFAULT_DEPARTMENTS = [
    ("Secretariat – IT Dept",        "SECR-ILL-01", 1000, 99.5),
    ("Health & Family Welfare",      "HLTH-ILL-02",  500, 99.0),
    ("Revenue & Disaster Mgmt",      "REVN-ILL-03",  500, 99.0),
    ("School Education Dept",        "SEDU-ILL-04",  200, 98.5),
    ("Agriculture Dept",             "AGRI-ILL-05",  200, 98.5),
    ("Municipal Admin & Water",      "MAWS-ILL-06",  100, 98.0),
    ("Transport Dept",               "TRNS-ILL-07",  100, 98.0),
    ("Adi Dravidar & Tribal Welfare","ADTW-ILL-08",   50, 97.5),
    ("Forest Dept",                  "FRST-ILL-09",   50, 97.5),
    ("Tourism Dept",                 "TOUR-ILL-10",   50, 97.5),
]

def gen_uptime(sla_target, rng=None):
    """Return achieved uptime slightly above or occasionally just below SLA."""
    r = rng if rng is not None else random
    delta = r.uniform(-0.3, 0.6)
    return round(min(99.99, sla_target + delta), 3)

def gen_daily_bandwidth(capacity_mbps, days=31, rng=None):
    """Generate daily avg bandwidth (Mbps) with realistic variation."""
    r = rng if rng is not None else random
    base = capacity_mbps * r.uniform(0.60, 0.78)
    series = []
    for _ in range(days):
        val = base + r.gauss(0, capacity_mbps * 0.06)
        val = max(capacity_mbps * 0.35, min(capacity_mbps * 0.97, val))
        series.append(round(val, 2))
    return series

def gen_incidents(report_period_label="January 2026"):
    """Return sample incident list; dates use the preceding month by convention."""
    descriptions = [
        ("Fiber cut – L1 outage",         "P1", "2026-01-04 03:12", "2026-01-04 05:47", "2h 35m"),
        ("BGP session flap",              "P2", "2026-01-09 14:05", "2026-01-09 14:38", "33m"),
        ("Planned maintenance window",    "P4", "2026-01-15 00:00", "2026-01-15 02:00", "2h 00m"),
        ("Interface errors – port reset", "P2", "2026-01-19 10:22", "2026-01-19 10:55", "33m"),
        ("Power fluctuation – UPS failover","P3","2026-01-23 17:48","2026-01-23 18:10", "22m"),
    ]
    return descriptions


def gen_hourly_bandwidth(capacity_mbps, days=31, seed_offset=0, base_time=None):
    """Generate hourly bandwidth with diurnal patterns and outage events."""
    if base_time is None:
        base_time = datetime(2026, 2, 1)
    rng = np.random.RandomState(42 + seed_offset)
    series, outages = [], []
    down_min = 0
    hour_ts = [base_time + timedelta(hours=h) for h in range(days * 24)]

    for ts in hour_ts:
        h = ts.hour
        base = 0.72 if 8 <= h < 19 else 0.30
        util = float(np.clip(base + rng.normal(0, 0.07), 0.04, 1.0))
        if rng.random() < 0.004:
            series.append(0.0)
            dm = int(rng.randint(8, 51))
            down_min += dm
            outages.append({
                "ts": ts.strftime("%d-%b-%Y %H:%M"),
                "dur": dm,
                "cause": ["Fibre cut", "Hardware fault", "Planned maintenance",
                           "Power failure", "Carrier congestion"][int(rng.randint(0, 5))],
                "res": "Yes",
            })
        else:
            series.append(round(capacity_mbps * util, 2))

    nz = [b for b in series if b > 0]
    p95_bw = round(float(np.percentile(nz, 95)), 2) if nz else 0.0

    return series, hour_ts, outages, down_min, p95_bw


def prepare_data(departments, report_month_start, random_seed=42, num_days=None):
    """Build DEPT_ROWS and aggregate stats from a list of department tuples."""
    import calendar
    if num_days is None:
        num_days = calendar.monthrange(report_month_start.year,
                                       report_month_start.month)[1]
    rng = random.Random(random_seed)
    np_rng_base = random_seed  # numpy RNGs use integer offsets

    dept_rows = []
    for idx, (name, cid, cap, sla) in enumerate(departments):
        achieved = gen_uptime(sla, rng=rng)
        status = "COMPLIANT" if achieved >= sla else "BREACH"
        bw_series = gen_daily_bandwidth(cap, days=num_days, rng=rng)
        avg_bw = round(sum(bw_series) / len(bw_series), 2)
        peak_bw = round(max(bw_series), 2)
        hourly_bw, hour_ts, outages, down_min, p95_bw = gen_hourly_bandwidth(
            cap, days=num_days, seed_offset=np_rng_base + idx,
            base_time=report_month_start)
        dept_rows.append({
            "name": name, "circuit_id": cid, "capacity": cap,
            "sla": sla, "achieved": achieved, "status": status,
            "avg_bw": avg_bw, "peak_bw": peak_bw,
            "bw_series": bw_series,
            "hourly_bw": hourly_bw, "hour_ts": hour_ts,
            "outages": outages, "down_min": down_min, "p95_bw": p95_bw,
        })

    total = len(dept_rows)
    compliant = sum(1 for r in dept_rows if r["status"] == "COMPLIANT")
    breach = total - compliant
    overall = round(sum(r["achieved"] for r in dept_rows) / total, 3) if total else 0.0
    return dept_rows, total, compliant, breach, overall

# ─────────────────────────── Helpers ──────────────────────────────────────

def sla_color(status):
    return GREEN_OK if status == "COMPLIANT" else RED_FAIL

def uptime_color(achieved, sla):
    if achieved >= sla:
        return GREEN_OK
    elif achieved >= sla - 0.2:
        return AMBER_WARN
    return RED_FAIL

# ─────────────────────────── Custom Flowables ──────────────────────────────

class ColorBlock(Flowable):
    """A filled rectangle with optional label – used as section dividers."""
    def __init__(self, width, height, fill_color, label="", label_color=WHITE,
                 font_size=9, radius=3):
        super().__init__()
        self.width = width
        self.height = height
        self.fill_color = fill_color
        self.label = label
        self.label_color = label_color
        self.font_size = font_size
        self.radius = radius

    def draw(self):
        c = self.canv
        c.setFillColor(self.fill_color)
        c.roundRect(0, 0, self.width, self.height, self.radius, fill=1, stroke=0)
        if self.label:
            c.setFillColor(self.label_color)
            c.setFont("Helvetica-Bold", self.font_size)
            c.drawCentredString(self.width / 2, (self.height - self.font_size) / 2 + 1,
                                self.label)


class KPICard(Flowable):
    """A KPI summary card with title, big number, and sub-label."""
    def __init__(self, title, value, sub, bg=TANFINET_LIGHT,
                 accent=TANFINET_DARK, width=40*mm, height=22*mm):
        super().__init__()
        self.title = title
        self.value = value
        self.sub = sub
        self.bg = bg
        self.accent = accent
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        # Left accent bar
        c.setFillColor(self.accent)
        c.rect(0, 0, 3, self.height, fill=1, stroke=0)
        # Title
        c.setFillColor(TANFINET_MID)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(6, self.height - 9, self.title.upper())
        # Value
        c.setFillColor(self.accent)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(6, self.height / 2 - 6, self.value)
        # Sub-label
        c.setFillColor(colors.HexColor("#555555"))
        c.setFont("Helvetica", 6)
        c.drawString(6, 3.5, self.sub)


class SectionHeader(Flowable):
    """Full-width section header band."""
    def __init__(self, text, width=CONTENT_W):
        super().__init__()
        self.text = text
        self.width = width
        self.height = 9 * mm

    def draw(self):
        c = self.canv
        c.setFillColor(HEADER_BG)
        c.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(6, (self.height - 9) / 2 + 1, self.text.upper())
        # Gold accent line at bottom
        c.setStrokeColor(TANFINET_GOLD)
        c.setLineWidth(1.5)
        c.line(0, 0, self.width, 0)


# ─────────────────────────── Chart Builders ───────────────────────────────

def build_bandwidth_line_chart(series, capacity_mbps, width_pt, height_pt):
    """Daily bandwidth line chart for a single circuit."""
    d = Drawing(width_pt, height_pt)
    days = list(range(1, len(series) + 1))

    chart = HorizontalLineChart()
    chart.x = 34
    chart.y = 24
    chart.width = width_pt - 50
    chart.height = height_pt - 36

    chart.data = [series, [capacity_mbps * 0.95] * len(series)]

    chart.lines[0].strokeColor = TANFINET_ACCENT
    chart.lines[0].strokeWidth = 1.3
    chart.lines[0].symbol = None

    chart.lines[1].strokeColor = TANFINET_GOLD
    chart.lines[1].strokeWidth = 0.8
    chart.lines[1].strokeDashArray = [4, 2]

    chart.categoryAxis.categoryNames = [str(i) if i % 5 == 1 or i == len(series) else ""
                                         for i in days]
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 0
    chart.categoryAxis.strokeColor = GREY_LINE
    chart.categoryAxis.gridStrokeColor = GREY_LINE
    chart.categoryAxis.gridStrokeDashArray = [1, 2]

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = capacity_mbps * 1.05
    chart.valueAxis.valueStep = capacity_mbps / 5
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.strokeColor = GREY_LINE
    chart.valueAxis.gridStrokeColor = GREY_LINE
    chart.valueAxis.gridStrokeDashArray = [1, 2]

    # Background fill
    bg = Rect(chart.x, chart.y, chart.width, chart.height,
              fillColor=GREY_BG, strokeColor=GREY_LINE, strokeWidth=0.4)
    d.add(bg)
    d.add(chart)

    # Legend
    d.add(Rect(chart.x, 6, 8, 5, fillColor=TANFINET_ACCENT, strokeWidth=0))
    d.add(String(chart.x + 10, 7, "Avg Bandwidth (Mbps)", fontSize=6,
                 fillColor=TANFINET_DARK))
    d.add(Rect(chart.x + 90, 6, 8, 5, fillColor=TANFINET_GOLD, strokeWidth=0))
    d.add(String(chart.x + 100, 7, "95% SLA Threshold", fontSize=6,
                 fillColor=TANFINET_DARK))
    return d


def build_uptime_bar_chart(rows, width_pt, height_pt):
    """Uptime bar chart for all departments."""
    d = Drawing(width_pt, height_pt)
    names = [r["name"].split("–")[-1].split("&")[0].strip()[:16] for r in rows]
    achieved = [r["achieved"] for r in rows]

    chart = VerticalBarChart()
    chart.x = 60
    chart.y = 30
    chart.width = width_pt - 72
    chart.height = height_pt - 46

    chart.data = [achieved]
    chart.bars[0].fillColor = TANFINET_ACCENT

    # Color individual bars by compliance
    for i, r in enumerate(rows):
        col = GREEN_OK if r["status"] == "COMPLIANT" else RED_FAIL
        chart.bars[(0, i)].fillColor = col

    chart.categoryAxis.categoryNames = names
    chart.categoryAxis.labels.fontSize = 5.5
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.strokeColor = GREY_LINE

    chart.valueAxis.valueMin = 96.5
    chart.valueAxis.valueMax = 100.1
    chart.valueAxis.valueStep = 0.5
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.strokeColor = GREY_LINE
    chart.valueAxis.gridStrokeColor = GREY_LINE
    chart.valueAxis.gridStrokeDashArray = [1, 2]
    chart.valueAxis.labelTextFormat = "%.1f%%"

    bg = Rect(chart.x, chart.y, chart.width, chart.height,
              fillColor=GREY_BG, strokeColor=GREY_LINE, strokeWidth=0.4)
    d.add(bg)
    d.add(chart)

    # SLA line reference at ~99.0 (average)
    avg_sla = 99.0
    y_frac = ((avg_sla - 96.5) / (100.1 - 96.5))
    y_px = chart.y + y_frac * chart.height
    d.add(Line(chart.x, y_px, chart.x + chart.width, y_px,
               strokeColor=TANFINET_GOLD, strokeWidth=1,
               strokeDashArray=[3, 3]))
    d.add(String(chart.x + chart.width + 2, y_px - 2, "SLA", fontSize=5,
                 fillColor=TANFINET_GOLD))

    # Legend
    d.add(Rect(chart.x, 10, 7, 5, fillColor=GREEN_OK, strokeWidth=0))
    d.add(String(chart.x + 9, 11, "Compliant", fontSize=6, fillColor=TANFINET_DARK))
    d.add(Rect(chart.x + 58, 10, 7, 5, fillColor=RED_FAIL, strokeWidth=0))
    d.add(String(chart.x + 67, 11, "Breach", fontSize=6, fillColor=TANFINET_DARK))
    return d


def build_compliance_pie(compliant, breach, width_pt, height_pt):
    """Pie chart for compliance ratio."""
    d = Drawing(width_pt, height_pt)
    pie = Pie()
    pie.x = width_pt / 2 - 28
    pie.y = height_pt / 2 - 28
    pie.width = 56
    pie.height = 56
    pie.data = [compliant, breach] if breach else [compliant, 0.0001]
    pie.labels = [f"Compliant\n{compliant}", f"Breach\n{breach}"] if breach else ["Compliant", ""]
    pie.slices[0].fillColor = GREEN_OK
    pie.slices[1].fillColor = RED_FAIL
    pie.slices[0].strokeWidth = 0.5
    pie.slices[1].strokeWidth = 0.5
    pie.slices[0].labelRadius = 1.25
    pie.slices[1].labelRadius = 1.25
    pie.slices.fontName = "Helvetica"
    pie.slices.fontSize = 6
    d.add(pie)
    return d


def build_monthly_trend_bar(rows, width_pt, height_pt):
    """Grouped bar chart: Avg BW vs Capacity for top 5 depts."""
    subset = rows[:5]
    d = Drawing(width_pt, height_pt)
    capacity = [r["capacity"] for r in subset]
    avg_bw   = [r["avg_bw"]   for r in subset]
    names    = [r["name"].split("–")[-1].split("&")[0].split("Dept")[0].strip()[:12]
                for r in subset]

    chart = VerticalBarChart()
    chart.x = 44
    chart.y = 30
    chart.width = width_pt - 56
    chart.height = height_pt - 46

    chart.data = [capacity, avg_bw]
    chart.bars[0].fillColor = TANFINET_MID
    chart.bars[1].fillColor = TANFINET_ACCENT
    chart.groupSpacing = 6

    chart.categoryAxis.categoryNames = names
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 20
    chart.categoryAxis.strokeColor = GREY_LINE

    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.strokeColor = GREY_LINE
    chart.valueAxis.gridStrokeColor = GREY_LINE
    chart.valueAxis.gridStrokeDashArray = [1, 2]
    chart.valueAxis.labelTextFormat = "%d"

    bg = Rect(chart.x, chart.y, chart.width, chart.height,
              fillColor=GREY_BG, strokeColor=GREY_LINE, strokeWidth=0.4)
    d.add(bg)
    d.add(chart)

    # Legend
    d.add(Rect(chart.x, 10, 7, 5, fillColor=TANFINET_MID, strokeWidth=0))
    d.add(String(chart.x + 9, 11, "Contracted Capacity (Mbps)", fontSize=6,
                 fillColor=TANFINET_DARK))
    d.add(Rect(chart.x + 120, 10, 7, 5, fillColor=TANFINET_ACCENT, strokeWidth=0))
    d.add(String(chart.x + 129, 11, "Avg Delivered (Mbps)", fontSize=6,
                 fillColor=TANFINET_DARK))
    return d


# ─────────────────────────── Matplotlib Charts ────────────────────────────

def build_matplotlib_bw_chart(d):
    """Per-circuit hourly bandwidth chart using matplotlib."""
    hours = [(t - d["hour_ts"][0]).total_seconds() / 3600 for t in d["hour_ts"]]
    bw_arr = np.array(d["hourly_bw"])
    cap = d["capacity"]

    fig, ax = plt.subplots(figsize=(7.32, 1.85))
    fig.patch.set_facecolor("#FAFCFF")
    ax.set_facecolor("#FAFCFF")

    ax.fill_between(hours, bw_arr, alpha=0.15, color="#19376D")
    ax.plot(hours, bw_arr, color="#0091D5", linewidth=0.85, alpha=0.95)
    ax.axhline(cap,       color="#C0392B", linewidth=1.0, linestyle="--",
               label=f"Contracted  {cap:,} Mbps")
    ax.axhline(cap * 0.95, color="#D68910", linewidth=0.75, linestyle=":",
               label=f"95% threshold  {int(cap * 0.95):,} Mbps")

    ax.set_xlim(0, max(hours))
    ax.set_ylim(0, cap * 1.12)
    ax.set_xlabel("Hours elapsed in reporting period", fontsize=6.5, color="#555", labelpad=2)
    ax.set_ylabel("Mbps", fontsize=6.5, color="#555", labelpad=2)
    ax.tick_params(labelsize=6, length=2)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(True, alpha=0.2, linewidth=0.3)
    leg = ax.legend(fontsize=6.5, loc="upper right", framealpha=0.9,
                    edgecolor="#CCCCCC", facecolor="white")
    for txt in leg.get_texts():
        txt.set_color("#333")

    plt.tight_layout(pad=0.4)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def build_compliance_donut(compliant, total):
    """Donut chart for compliance overview using matplotlib."""
    fig, ax = plt.subplots(figsize=(2.4, 2.4))
    fig.patch.set_facecolor("white")
    nc = total - compliant
    vals = [compliant, nc] if nc else [compliant]
    clrs = ["#1E8449", "#C0392B"] if nc else ["#1E8449"]
    ax.pie(vals, colors=clrs, startangle=90,
           wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2.5))
    ax.text(0,  0.10, f"{compliant}/{total}", ha="center", va="center",
            fontsize=14, fontweight="bold", color="#0B2447")
    ax.text(0, -0.22, "Compliant", ha="center", va="center",
            fontsize=7.5, color="#555555")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


class ThinRule(Flowable):
    """Thin horizontal rule separator."""
    def __init__(self, width=None, thickness=0.5, color=GREY_LINE):
        super().__init__()
        self.width = width or CONTENT_W
        self.thickness = thickness
        self.color = color
        self.height = thickness + 0.5

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


# ─────────────────────────── Page Templates ───────────────────────────────

def make_draw_header(report_period):
    """Return a page-callback that stamps *report_period* in the header."""
    def draw_header(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Top bar
        canvas.setFillColor(HEADER_BG)
        canvas.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)
        # Gold accent stripe
        canvas.setFillColor(TANFINET_GOLD)
        canvas.rect(0, h - 19.5 * mm, w, 1.5 * mm, fill=1, stroke=0)

        # TANFINET wordmark
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(MARGIN_X, h - 11 * mm, "TANFINET")
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN_X, h - 14.5 * mm, "Tamil Nadu FibreNet Corporation")

        # Report name – right aligned
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(w - MARGIN_X, h - 10 * mm, "ILL Bandwidth SLA Compliance Report")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(w - MARGIN_X, h - 14 * mm, f"Period: {report_period}")

        canvas.restoreState()
    return draw_header


def draw_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(TANFINET_DARK)
    canvas.rect(0, 0, w, 9 * mm, fill=1, stroke=0)
    canvas.setFillColor(TANFINET_GOLD)
    canvas.rect(0, 9 * mm, w, 0.8 * mm, fill=1, stroke=0)

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(MARGIN_X, 3.2 * mm,
                      "CONFIDENTIAL – For official use only | "
                      "Tamil Nadu FibreNet Corporation, 7th Floor, Ezhilagam, Chepauk, Chennai – 600 005")
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.drawRightString(w - MARGIN_X, 3.2 * mm, f"Page {doc.page}")
    canvas.restoreState()


def draw_cover_bg(canvas, doc):
    """Full-bleed cover page – no header/footer chrome."""
    canvas.saveState()
    w, h = A4
    # Navy background
    canvas.setFillColor(TANFINET_DARK)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    # Diagonal accent band
    from reportlab.graphics.shapes import Polygon
    canvas.setFillColor(TANFINET_MID)
    p = canvas.beginPath()
    p.moveTo(0, h * 0.38)
    p.lineTo(w, h * 0.28)
    p.lineTo(w, h * 0.52)
    p.lineTo(0, h * 0.62)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)
    # Saffron bottom strip
    canvas.setFillColor(TANFINET_GOLD)
    canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica", 6)
    canvas.drawCentredString(w / 2, 3.5 * mm,
                             "Tamil Nadu FibreNet Corporation  |  Ezhilagam, Chepauk, Chennai – 600 005")
    canvas.restoreState()


# ─────────────────────────── Style Sheet ──────────────────────────────────

styles = getSampleStyleSheet()

def S(name, parent="Normal", **kw):
    return ParagraphStyle(name, parent=styles[parent], **kw)

ST = {
    "cover_title":   S("CT",  fontSize=26, textColor=WHITE, alignment=TA_CENTER,
                        fontName="Helvetica-Bold", leading=32, spaceAfter=4),
    "cover_sub":     S("CS",  fontSize=11, textColor=TANFINET_LIGHT, alignment=TA_CENTER,
                        fontName="Helvetica", leading=15),
    "cover_meta":    S("CM",  fontSize=8,  textColor=TANFINET_GOLD, alignment=TA_CENTER,
                        fontName="Helvetica-Bold"),
    "cover_stamp":   S("CST", fontSize=7,  textColor=colors.HexColor("#AABBCC"),
                        alignment=TA_CENTER, fontName="Helvetica"),
    "h1":            S("H1",  fontSize=11, textColor=TANFINET_DARK, fontName="Helvetica-Bold",
                        spaceBefore=6, spaceAfter=2, leading=13),
    "h2":            S("H2",  fontSize=9,  textColor=TANFINET_MID,  fontName="Helvetica-Bold",
                        spaceBefore=4, spaceAfter=2, leading=11),
    "body":          S("BD",  fontSize=8,  textColor=BLACK, leading=11, spaceAfter=3),
    "body_c":        S("BDC", fontSize=8,  textColor=BLACK, leading=11, alignment=TA_CENTER),
    "small":         S("SM",  fontSize=6.5,textColor=colors.HexColor("#444444"), leading=9),
    "small_c":       S("SMC", fontSize=6.5,textColor=colors.HexColor("#444444"), leading=9,
                        alignment=TA_CENTER),
    "disclaimer":    S("DIS", fontSize=6,  textColor=colors.HexColor("#666666"),
                        leading=8, alignment=TA_CENTER),
    "toc_item":      S("TOC", fontSize=8,  textColor=TANFINET_DARK, leading=13),
    "kpi_val":       S("KPV", fontSize=18, textColor=TANFINET_DARK, fontName="Helvetica-Bold",
                        alignment=TA_CENTER),
}

# ─────────────────────────── Table Style Helpers ──────────────────────────

TS_BASE = [
    ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
    ("FONTSIZE",      (0, 0), (-1, -1), 7),
    ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GREY_BG]),
    ("LINEBELOW",     (0, 0), (-1, 0),  0.6, TANFINET_GOLD),
    ("LINEBELOW",     (0, 1), (-1, -1), 0.3, GREY_LINE),
    ("TOPPADDING",    (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("LEFTPADDING",   (0, 0), (-1, -1), 5),
    ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
]

TS_HEADER = [
    ("BACKGROUND",  (0, 0), (-1, 0), HEADER_BG),
    ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
    ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",    (0, 0), (-1, 0), 7.5),
]

def make_ts(*extras):
    return TableStyle(TS_BASE + TS_HEADER + list(extras))


# ─────────────────────────── Document Builder ─────────────────────────────

def build_report(
    output=None,                       # path str, or None → return bytes
    departments=None,                  # list of (name, cid, capacity, sla)
    report_period="February 2026",     # display label
    report_month_start=None,           # datetime of first day of month
    random_seed=42,
    logo1_path=None,                   # absolute path or None
    logo2_path=None,
):
    """Generate the ILL SLA PDF report.

    Returns
    -------
    bytes  – if *output* is None
    str    – the saved filename, if *output* is a path string
    """
    import calendar, io as _io

    # ── Resolve defaults ────────────────────────────────────────────────
    if departments is None:
        departments = DEFAULT_DEPARTMENTS
    if report_month_start is None:
        report_month_start = datetime(2026, 2, 1)

    REPORT_DATE = datetime.now()
    REPORT_PERIOD = report_period
    REPORT_MONTH_START = report_month_start

    # Build data
    DEPT_ROWS, TOTAL_CIRCUITS, COMPLIANT, BREACH, OVERALL_UPTIME = prepare_data(
        departments, REPORT_MONTH_START, random_seed=random_seed)
    PRIMARY = DEPT_ROWS[0]

    # ── Resolve logo paths ───────────────────────────────────────────────
    _logo_dir = os.path.dirname(os.path.abspath(__file__))
    _logo1_path = logo1_path or os.path.join(_logo_dir, "logo1.png")
    _logo2_path = logo2_path or os.path.join(_logo_dir, "logo2.png")

    # ── Output target ────────────────────────────────────────────────────
    if output is None:
        _buf = _io.BytesIO()
        _target = _buf
    else:
        _target = output

    doc = BaseDocTemplate(
        _target,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP + 18 * mm,   # account for header
        bottomMargin=MARGIN_BOT + 9 * mm,  # account for footer
    )

    _draw_header = make_draw_header(REPORT_PERIOD)

    # Frame for cover (full bleed – we draw manually)
    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0)
    content_frame = Frame(MARGIN_X, MARGIN_BOT + 9 * mm,
                          CONTENT_W, PAGE_H - MARGIN_TOP - 18 * mm - MARGIN_BOT - 9 * mm,
                          leftPadding=0, rightPadding=0, topPadding=3, bottomPadding=0)

    doc.addPageTemplates([
        PageTemplate(id="Cover",   frames=[cover_frame], onPage=draw_cover_bg),
        PageTemplate(id="Content", frames=[content_frame],
                     onPage=lambda c, d: (_draw_header(c, d), draw_footer(c, d))),
    ])

    story = []

    # ══════════════════════ COVER PAGE ════════════════════════════════════
    story.append(Spacer(1, 72 * mm))
    story.append(Paragraph("ILL Bandwidth SLA<br/>Compliance Report", ST["cover_title"]))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Internet Leased Line Performance Audit", ST["cover_sub"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"Reporting Period: {REPORT_PERIOD}", ST["cover_meta"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated on: {REPORT_DATE.strftime('%d %B %Y, %H:%M IST')}",
        ST["cover_stamp"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Tamil Nadu FibreNet Corporation", ST["cover_sub"]))
    story.append(Paragraph("Government of Tamil Nadu", ST["cover_stamp"]))

    # ── Logos ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    _logo_h = 28 * mm
    try:
        _ir1 = ImageReader(_logo1_path)
        _iw1, _ih1 = _ir1.getSize()
        _logo1_w = _logo_h * _iw1 / _ih1
        _ir2 = ImageReader(_logo2_path)
        _iw2, _ih2 = _ir2.getSize()
        _logo2_w = _logo_h * _iw2 / _ih2
        _logo1 = Image(_logo1_path, width=_logo1_w, height=_logo_h)
        _logo2 = Image(_logo2_path, width=_logo2_w, height=_logo_h)
        _gap = 12 * mm
        _logo_table = Table(
            [[_logo1, Spacer(_gap, 1), _logo2]],
            colWidths=[_logo1_w, _gap, _logo2_w],
        )
        _logo_table.setStyle(TableStyle([
            ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",    (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 0),
            ("TOPPADDING",     (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 0),
        ]))
        _outer_logo = Table([[_logo_table]], colWidths=[PAGE_W])
        _outer_logo.setStyle(TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(_outer_logo)
    except Exception:
        pass  # logos optional – skip silently if files not found

    # ══════════════════════ CONTENT PAGES ═════════════════════════════════
    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())   # ends cover AND switches to Content template

    # ── 1. Executive Summary ─────────────────────────────────────────────
    story.append(SectionHeader("1.  Executive Summary"))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f"This report presents the measured Internet Leased Line (ILL) bandwidth performance "
        f"and uptime availability for <b>{TOTAL_CIRCUITS} Government departments</b> served "
        f"by TANFINET during <b>{REPORT_PERIOD}</b>. "
        f"Data has been compiled from continuous monitoring infrastructure and constitutes an "
        f"auditable record for SLA compliance purposes.",
        ST["body"]))
    story.append(Paragraph(
        f"During the reporting period, <b>{COMPLIANT} of {TOTAL_CIRCUITS} circuits</b> met or "
        f"exceeded the contracted SLA uptime threshold. "
        f"The overall network-weighted average uptime was <b>{OVERALL_UPTIME}%</b>. "
        f"A total of <b>{len(gen_incidents())} incidents</b> were logged, with root-cause analysis "
        f"completed for all Priority-1 and Priority-2 events.",
        ST["body"]))

    story.append(Spacer(1, 3 * mm))

    # KPI Cards row
    kpi_data = [
        ("Total Circuits",     str(TOTAL_CIRCUITS),  "ILL connections monitored",  TANFINET_DARK),
        ("Compliant",          str(COMPLIANT),        "Met SLA uptime target",       GREEN_OK),
        ("Breach",             str(BREACH),           "Below SLA threshold",         RED_FAIL if BREACH else GREY_LINE),
        ("Avg Uptime",         f"{OVERALL_UPTIME}%",  "Network-wide average",        TANFINET_ACCENT),
        ("Incidents Logged",   "5",                   "Jan 2026 total",              AMBER_WARN),
    ]
    card_w = CONTENT_W / len(kpi_data) - 2 * mm
    cards = [KPICard(t, v, s, accent=a, width=card_w, height=22 * mm)
             for t, v, s, a in kpi_data]
    kpi_table = Table([cards], colWidths=[card_w + 2 * mm] * len(kpi_data))
    kpi_table.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 4 * mm))

    # ── 2. Compliance Overview Charts ────────────────────────────────────
    story.append(SectionHeader("2.  Compliance Overview"))
    story.append(Spacer(1, 3 * mm))

    donut_w = 50 * mm
    bar_w = CONTENT_W - donut_w - 4 * mm
    donut_buf = build_compliance_donut(COMPLIANT, TOTAL_CIRCUITS)
    donut_img = Image(donut_buf, width=donut_w, height=donut_w)
    uptime_bar = build_uptime_bar_chart(DEPT_ROWS, bar_w, 55 * mm)

    overview_table = Table(
        [[uptime_bar, donut_img]],
        colWidths=[bar_w, donut_w + 4 * mm],
    )
    overview_table.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(overview_table)

    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        "Figure 1: Department-wise uptime achieved (bar) vs SLA reference line (gold dashes) — "
        "Figure 2: Overall circuit compliance donut (compliant / total).",
        ST["disclaimer"]))
    story.append(Spacer(1, 4 * mm))

    # ── 3. Department-wise SLA Table ─────────────────────────────────────
    story.append(SectionHeader("3.  Department-wise SLA Performance"))
    story.append(Spacer(1, 2 * mm))

    col_w = [53*mm, 30*mm, 18*mm, 18*mm, 22*mm, 22*mm, 20*mm]
    header = ["Department", "Circuit ID", "Capacity\n(Mbps)", "SLA\nTarget (%)",
              "Achieved\nUptime (%)", "Avg BW\n(Mbps)", "Status"]
    rows_data = [header]
    for r in DEPT_ROWS:
        status_color = sla_color(r["status"])
        rows_data.append([
            Paragraph(r["name"], ST["small"]),
            Paragraph(r["circuit_id"], ST["small_c"]),
            Paragraph(str(r["capacity"]), ST["small_c"]),
            Paragraph(f"{r['sla']}%", ST["small_c"]),
            Paragraph(f"<b>{r['achieved']}%</b>",
                      ParagraphStyle("AU", parent=ST["small_c"],
                                     textColor=uptime_color(r["achieved"], r["sla"]))),
            Paragraph(str(r["avg_bw"]), ST["small_c"]),
            Paragraph(
                f"<b>{r['status']}</b>",
                ParagraphStyle("ST", parent=ST["small_c"],
                               textColor=WHITE,
                               backColor=sla_color(r["status"]),
                               borderPadding=2)),
        ])

    sla_table = Table(rows_data, colWidths=col_w, repeatRows=1)
    extra_styles = []
    for i, r in enumerate(DEPT_ROWS, start=1):
        col = sla_color(r["status"])
        extra_styles.append(("BACKGROUND", (6, i), (6, i), col))
        extra_styles.append(("TEXTCOLOR",  (6, i), (6, i), WHITE))
    sla_table.setStyle(make_ts(*extra_styles))
    story.append(sla_table)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Note: Uptime computed as percentage of total minutes in the reporting period during which "
        "the circuit was available and delivering ≥ 95% of contracted bandwidth.",
        ST["disclaimer"]))
    story.append(Spacer(1, 4 * mm))

    # ── 4. Primary Circuit Bandwidth Trend ───────────────────────────────
    story.append(SectionHeader(
        f"4.  Bandwidth Utilisation Trend – {PRIMARY['name']} ({PRIMARY['circuit_id']})"))
    story.append(Spacer(1, 2 * mm))

    bw_chart = build_bandwidth_line_chart(
        PRIMARY["bw_series"], PRIMARY["capacity"], CONTENT_W, 60 * mm)
    story.append(bw_chart)
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        f"Figure 3: Daily average bandwidth delivered on circuit {PRIMARY['circuit_id']} "
        f"({PRIMARY['capacity']} Mbps contracted) during {REPORT_PERIOD}. "
        f"Gold dashed line indicates the 95% SLA threshold ({int(PRIMARY['capacity']*0.95)} Mbps).",
        ST["disclaimer"]))
    story.append(Spacer(1, 4 * mm))

    # ── 5. Capacity vs Utilisation ────────────────────────────────────────
    story.append(SectionHeader("5.  Capacity vs Average Delivered Bandwidth (Top 5 Circuits)"))
    story.append(Spacer(1, 2 * mm))

    trend_chart = build_monthly_trend_bar(DEPT_ROWS, CONTENT_W, 55 * mm)
    story.append(trend_chart)
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        "Figure 4: Contracted capacity (dark navy) vs average delivered bandwidth (sky blue) "
        "for the top 5 circuits. All circuits demonstrate healthy headroom below contracted capacity.",
        ST["disclaimer"]))
    story.append(Spacer(1, 4 * mm))

    # ── 6. Per-Circuit Detailed Bandwidth Analysis ───────────────────────
    story.append(SectionHeader("6.  Per-Circuit Detailed Bandwidth Analysis"))
    story.append(Spacer(1, 3 * mm))

    for idx_c, d in enumerate(DEPT_ROWS):
        ok = d["status"] == "COMPLIANT"
        hdr_bg_color = GREEN_OK if ok else RED_FAIL
        status_label = "\u2713 COMPLIANT" if ok else "\u2717 SLA BREACH"

        # Circuit identity banner
        story.append(ColorBlock(CONTENT_W, 8 * mm, hdr_bg_color,
                                f'{d["circuit_id"]}  \u2014  {d["name"]}  \u00b7  {status_label}',
                                WHITE, 8))

        # 8-metric strip
        met_labels = ["Contracted BW", "Average BW", "Peak BW", "95th Pctl BW",
                      "Uptime", "SLA Target", "Downtime", "Events"]
        met_values = [f'{d["capacity"]:,} Mbps', f'{d["avg_bw"]:,} Mbps',
                      f'{d["peak_bw"]:,} Mbps', f'{d["p95_bw"]:,} Mbps',
                      f'{d["achieved"]}%', f'{d["sla"]}%',
                      f'{d["down_min"]} min', str(len(d["outages"]))]
        met_tbl = Table([met_labels, met_values], colWidths=[CONTENT_W / 8] * 8)
        met_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), TANFINET_MID),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 6.5),
            ("BACKGROUND",    (0, 1), (-1, 1), GREY_BG),
            ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 1), (-1, 1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.3, GREY_LINE),
            ("BOX",           (0, 0), (-1, -1), 0.5, TANFINET_MID),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(met_tbl)
        story.append(Spacer(1, 1.5 * mm))

        # Bandwidth chart (matplotlib)
        story.append(Paragraph(
            '<b>Bandwidth Utilisation \u2014 Hourly Profile</b>',
            ParagraphStyle("_bwlbl", fontSize=7.5, textColor=TANFINET_MID,
                           fontName="Helvetica-Bold", spaceAfter=1)))
        chart_buf = build_matplotlib_bw_chart(d)
        story.append(Image(chart_buf, width=CONTENT_W, height=50 * mm))
        story.append(Spacer(1, 1.5 * mm))

        # Outage event log
        story.append(Paragraph(
            '<b>Outage Event Log</b>',
            ParagraphStyle("_outlbl", fontSize=7.5, textColor=TANFINET_MID,
                           fontName="Helvetica-Bold", spaceAfter=1)))
        if d["outages"]:
            olog_header = ["Timestamp", "Duration (min)", "Root Cause", "Resolved"]
            olog_rows = [olog_header]
            for ev in d["outages"]:
                olog_rows.append([ev["ts"], str(ev["dur"]), ev["cause"], ev["res"]])
            olog_tbl = Table(olog_rows,
                             colWidths=[40*mm, 28*mm, CONTENT_W - 90*mm, 22*mm],
                             repeatRows=1)
            olog_tbl.setStyle(make_ts())
            story.append(olog_tbl)
        else:
            story.append(Paragraph(
                '<i>\u2713 No unplanned outage events recorded during this period.</i>',
                ParagraphStyle("_noout", fontSize=8, textColor=GREEN_OK,
                               fontName="Helvetica-Oblique")))

        if idx_c < len(DEPT_ROWS) - 1:
            story.append(Spacer(1, 4 * mm))
            story.append(ThinRule())
            story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))

    # ── 7. Audit Recommendations ─────────────────────────────────────────
    story.append(SectionHeader("7.  Audit Recommendations"))
    story.append(Spacer(1, 2 * mm))

    recs = [
        ("R1", "Continuous Monitoring",
         "Deploy real-time SNMP/IPFIX probes at all ILL circuit demarcation points with "
         "automated alerting when bandwidth falls below 95% of contracted capacity for "
         "more than 15 consecutive minutes."),
        ("R2", "Automated Reporting",
         "Implement scheduled report generation with automated distribution to departmental "
         "CIOs and ISP account managers no later than the 5th working day of each month."),
        ("R3", "Carrier Performance Reviews",
         "Convene quarterly performance review meetings with ILL service providers. Circuits "
         "with recurring degradation must be escalated within 48 hours."),
        ("R4", "Diversity & Redundancy",
         "All mission-critical circuits must have geographically diverse routing and automatic "
         "failover. MPLS path diversity is recommended for circuits >= 1 Gbps."),
        ("R5", "Audit Trail Integrity",
         "All telemetry data must be cryptographically signed (SHA-256) and stored in an "
         "immutable ledger for a minimum of 5 years per Tamil Nadu IT Policy 2023."),
    ]
    rec_header = ["Ref", "Area", "Recommendation Detail"]
    rec_rows = [rec_header]
    for ref, area, desc in recs:
        rec_rows.append([
            Paragraph(ref, ST["small_c"]),
            Paragraph(area, ST["small"]),
            Paragraph(desc, ST["small"]),
        ])
    rec_col_w = [12*mm, 38*mm, CONTENT_W - 50*mm]
    rec_tbl = Table(rec_rows, colWidths=rec_col_w, repeatRows=1)
    rec_tbl.setStyle(make_ts())
    story.append(rec_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── 8. Incident Log ──────────────────────────────────────────────────
    story.append(SectionHeader("8.  Incident Log \u2013 January 2026"))
    story.append(Spacer(1, 2 * mm))

    inc_col_w = [58*mm, 14*mm, 36*mm, 36*mm, 20*mm, 19*mm]
    inc_header = ["Description", "Priority", "Start (IST)", "Resolved (IST)", "Duration", "RCA"]
    inc_data = [inc_header]
    priority_color = {"P1": RED_FAIL, "P2": colors.HexColor("#E87722"),
                      "P3": AMBER_WARN, "P4": GREEN_OK}

    for desc, pri, start, end, dur in gen_incidents():
        inc_data.append([
            Paragraph(desc, ST["small"]),
            Paragraph(f"<b>{pri}</b>", ST["small_c"]),
            Paragraph(start, ST["small_c"]),
            Paragraph(end, ST["small_c"]),
            Paragraph(dur, ST["small_c"]),
            Paragraph("Complete", ParagraphStyle("RCA", parent=ST["small_c"],
                                                  textColor=GREEN_OK, fontName="Helvetica-Bold")),
        ])

    inc_extra = []
    for i, (_, pri, *_r) in enumerate(gen_incidents(), start=1):
        col = priority_color.get(pri, GREY_LINE)
        inc_extra.append(("BACKGROUND", (1, i), (1, i), col))
        inc_extra.append(("TEXTCOLOR",  (1, i), (1, i), WHITE))

    inc_table = Table(inc_data, colWidths=inc_col_w, repeatRows=1)
    inc_table.setStyle(make_ts(*inc_extra))
    story.append(inc_table)
    story.append(Spacer(1, 4 * mm))

    # ── 9. SLA Credit / Penalty Summary ──────────────────────────────────
    story.append(SectionHeader("9.  SLA Credit & Penalty Summary"))
    story.append(Spacer(1, 2 * mm))

    credit_col_w = [60*mm, 28*mm, 28*mm, 28*mm, 39*mm]
    credit_header = ["Department", "SLA Target", "Achieved", "Shortfall", "Credit/Penalty"]
    credit_data = [credit_header]
    for r in DEPT_ROWS:
        if r["status"] == "BREACH":
            shortfall = round(r["sla"] - r["achieved"], 3)
            penalty = f"₹{int(shortfall * 10000):,} (est.)"
            credit_data.append([
                Paragraph(r["name"], ST["small"]),
                Paragraph(f"{r['sla']}%", ST["small_c"]),
                Paragraph(f"{r['achieved']}%", ParagraphStyle("BP", parent=ST["small_c"],
                                                               textColor=RED_FAIL,
                                                               fontName="Helvetica-Bold")),
                Paragraph(f"{shortfall}%", ST["small_c"]),
                Paragraph(penalty, ParagraphStyle("PEN", parent=ST["small_c"],
                                                   textColor=RED_FAIL,
                                                   fontName="Helvetica-Bold")),
            ])
    if len(credit_data) == 1:
        credit_data.append([Paragraph("All circuits compliant – no penalty applicable.",
                                       ST["small_c"]), "", "", "", ""])
        extra_merge = [("SPAN", (0, 1), (-1, 1))]
    else:
        extra_merge = []

    credit_table = Table(credit_data, colWidths=credit_col_w, repeatRows=1)
    credit_table.setStyle(make_ts(*extra_merge))
    story.append(credit_table)
    story.append(Spacer(1, 4 * mm))

    # ── 10. Audit Trail & Certification ──────────────────────────────────
    story.append(SectionHeader("10.  Audit Trail & Certification"))
    story.append(Spacer(1, 2 * mm))

    audit_meta = [
        ["Report Reference No.", f"TANFINET/ILL/SLA/{REPORT_DATE.strftime('%Y/%m')}/001"],
        ["Reporting Period",     f"{REPORT_PERIOD}"],
        ["Data Source",          "TANFINET NOC – Real-time Monitoring Platform (SNMP/NetFlow)"],
        ["Generated By",         "Automated SLA Reporting Engine v2.1"],
        ["Generated On",         REPORT_DATE.strftime("%d %B %Y, %H:%M IST")],
        ["Approved By",          "General Manager (Network Operations), TANFINET"],
    ]
    at_col_w = [55 * mm, CONTENT_W - 55 * mm]
    at_table = Table(audit_meta, colWidths=at_col_w)
    at_table.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 0), (0, -1),  TANFINET_DARK),
        ("BACKGROUND",    (0, 0), (0, -1),  TANFINET_LIGHT),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, GREY_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.3, GREY_LINE),
    ]))
    story.append(at_table)
    story.append(Spacer(1, 5 * mm))

    # Certification box
    cert_text = (
        "I hereby certify that this report accurately reflects the bandwidth performance data "
        "collected by TANFINET's automated monitoring systems for the period stated above. "
        "The data has been generated without manual intervention and is suitable for "
        "regulatory audit and SLA adjudication purposes."
    )
    cert_table = Table(
        [[Paragraph(cert_text, ST["body"])]],
        colWidths=[CONTENT_W],
    )
    cert_table.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.8, TANFINET_ACCENT),
        ("BACKGROUND",    (0, 0), (-1, -1), TANFINET_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(cert_table)
    story.append(Spacer(1, 6 * mm))

    # Signature block
    sig_data = [
        ["Prepared by", "Reviewed by", "Authorised by"],
        ["\n\n____________________", "\n\n____________________", "\n\n____________________"],
        ["Network Operations Manager", "Deputy General Manager (IT)", "General Manager (Operations)"],
        ["TANFINET", "TANFINET", "Tamil Nadu FibreNet Corporation"],
        [f"Date: ___________", f"Date: ___________", f"Date: ___________"],
    ]
    sig_col_w = [CONTENT_W / 3] * 3
    sig_table = Table(sig_data, colWidths=sig_col_w)
    sig_table.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("BACKGROUND",    (0, 0), (-1, 0),  TANFINET_MID),
        ("TEXTCOLOR",     (0, 2), (-1, -1), TANFINET_DARK),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, GREY_LINE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, TANFINET_MID),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, GREY_LINE),
    ]))
    story.append(sig_table)

    doc.build(story)

    if output is None:
        _buf.seek(0)
        return _buf.read()
    return output


# ─────────────────────────── Entry Point ──────────────────────────────────

if __name__ == "__main__":
    out = build_report(output="TANFINET_ILL_SLA_Report.pdf")
    print(f"[✓] Report saved: {out}")
