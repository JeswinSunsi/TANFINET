"""
TANFINET – ILL SLA Report Generator
Streamlit UI  ·  run with:  streamlit run app.py
"""

import calendar
import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TANFINET Report Generator",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main header */
    .tanfinet-header {
        background: linear-gradient(135deg, #0B2447 0%, #19376D 60%, #0091D5 100%);
        padding: 1.4rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border-bottom: 4px solid #F4A71D;
    }
    .tanfinet-header h1 {
        color: white;
        margin: 0;
        font-size: 1.9rem;
        letter-spacing: 0.04em;
    }
    .tanfinet-header p {
        color: #A8D4F0;
        margin: 0.3rem 0 0 0;
        font-size: 0.92rem;
    }
    /* Section labels */
    .section-label {
        background: #1a3a5c;
        color: white;
        padding: 0.35rem 0.9rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.82rem;
        letter-spacing: 0.06em;
        border-left: 4px solid #F4A71D;
        margin-bottom: 0.8rem;
        margin-top: 0.4rem;
    }
    /* Metric cards */
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(90deg, #0B2447, #0091D5);
        color: white;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 1.8rem;
        font-size: 1rem;
        width: 100%;
    }
    .stDownloadButton > button:hover { opacity: 0.88; }
</style>
""", unsafe_allow_html=True)

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="tanfinet-header">
  <h1>📡 TANFINET &nbsp;|&nbsp; ILL SLA Report Generator</h1>
  <p>Tamil Nadu FibreNet Corporation — Internet Leased Line Bandwidth Performance Audit</p>
</div>
""", unsafe_allow_html=True)

# ── Import report module (lazy, so Streamlit can reload cleanly) ────────────
@st.cache_resource
def _import_report():
    import importlib, sys
    # Ensure the module directory is on the path
    mod_dir = os.path.dirname(os.path.abspath(__file__))
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    import report as rpt
    return rpt

rpt = _import_report()

# ═══════════════════════════════════════════════════════════════════════════
#  SIDEBAR – global report settings
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ Report Settings")
    st.divider()

    # ── Reporting Period ───────────────────────────────────────────────────
    st.markdown("**Reporting Period**")
    col_m, col_y = st.columns(2)
    with col_m:
        month_num = st.selectbox(
            "Month", range(1, 13),
            index=1,                                # default Feb
            format_func=lambda m: calendar.month_abbr[m],
            label_visibility="collapsed",
        )
    with col_y:
        year_val = st.number_input(
            "Year", min_value=2020, max_value=2035,
            value=2026, step=1,
            label_visibility="collapsed",
        )
    report_period = f"{calendar.month_name[month_num]} {year_val}"
    report_month_start = datetime(int(year_val), int(month_num), 1)

    st.divider()

    # ── Logos ──────────────────────────────────────────────────────────────
    st.markdown("**Cover Page Logos** *(optional)*")
    logo1_file = st.file_uploader("Logo 1 (left)", type=["png", "jpg", "jpeg"],
                                  label_visibility="visible")
    logo2_file = st.file_uploader("Logo 2 (right)", type=["png", "jpg", "jpeg"],
                                  label_visibility="visible")

    st.divider()

    # ── Advanced ──────────────────────────────────────────────────────────
    with st.expander("🔧 Advanced"):
        random_seed = st.number_input(
            "Random Seed", min_value=0, max_value=9999,
            value=42, step=1,
            help="Controls simulated bandwidth & uptime data. Same seed = identical report.",
        )
        output_fname = st.text_input(
            "Output Filename",
            value=f"TANFINET_ILL_SLA_{year_val}_{month_num:02d}.pdf",
        )

    st.divider()
    st.caption("TANFINET Report Generator v1.0")

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN AREA – Department configuration
# ═══════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-label">DEPARTMENT CONFIGURATION</div>', unsafe_allow_html=True)
st.markdown(
    "Tick the departments to include, then adjust **Capacity (Mbps)** and **SLA Target (%)** "
    "inline. All changes are reflected immediately in the report."
)

# Build editable dataframe from defaults
_default_depts = rpt.DEFAULT_DEPARTMENTS
_df_init = pd.DataFrame(
    [
        {
            "Include": True,
            "Department Name": name,
            "Circuit ID": cid,
            "Capacity (Mbps)": cap,
            "SLA Target (%)": sla,
        }
        for name, cid, cap, sla in _default_depts
    ]
)

# ── Bulk-selection helper buttons ──────────────────────────────────────────
if "dept_df" not in st.session_state:
    st.session_state["dept_df"] = _df_init.copy()

btn_col1, btn_col2, btn_col3, _ = st.columns([1, 1, 1, 5])
with btn_col1:
    if st.button("✅ Select All"):
        st.session_state["dept_df"]["Include"] = True
with btn_col2:
    if st.button("❌ Deselect All"):
        st.session_state["dept_df"]["Include"] = False
with btn_col3:
    if st.button("🔄 Reset Defaults"):
        st.session_state["dept_df"] = _df_init.copy()

# ── Editable table ─────────────────────────────────────────────────────────
edited_df = st.data_editor(
    st.session_state["dept_df"],
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Include": st.column_config.CheckboxColumn("Include", width="small"),
        "Department Name": st.column_config.TextColumn("Department Name", width="large"),
        "Circuit ID": st.column_config.TextColumn("Circuit ID", width="medium"),
        "Capacity (Mbps)": st.column_config.NumberColumn(
            "Capacity (Mbps)", min_value=1, max_value=100_000, step=50, width="medium"
        ),
        "SLA Target (%)": st.column_config.NumberColumn(
            "SLA Target (%)", min_value=90.0, max_value=99.99,
            step=0.5, format="%.2f %%", width="medium"
        ),
    },
    key="dept_editor",
    hide_index=True,
)

# Persist edits back to session state
st.session_state["dept_df"] = edited_df

# ── Selection summary ──────────────────────────────────────────────────────
selected = edited_df[edited_df["Include"] == True]   # noqa: E712
n_sel = len(selected)

st.divider()
m1, m2, m3 = st.columns(3)
m1.metric("Departments selected", n_sel)
m2.metric("Reporting period", report_period)
m3.metric("Total contracted BW",
          f"{int(selected['Capacity (Mbps)'].sum()):,} Mbps" if n_sel else "—")

# ═══════════════════════════════════════════════════════════════════════════
#  GENERATE REPORT
# ═══════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown('<div class="section-label">GENERATE REPORT</div>', unsafe_allow_html=True)

if n_sel == 0:
    st.warning("⚠️ Select at least one department before generating the report.")
    st.stop()

generate_col, _ = st.columns([2, 5])
with generate_col:
    generate_btn = st.button("🚀 Generate PDF Report", type="primary", use_container_width=True)

if generate_btn:
    # Build departments list from selection
    departments = [
        (row["Department Name"], row["Circuit ID"],
         int(row["Capacity (Mbps)"]), float(row["SLA Target (%)"]))
        for _, row in selected.iterrows()
    ]

    # Handle logo uploads → save to temp files
    import tempfile, shutil

    logo1_path = None
    logo2_path = None
    _tmp_dir = tempfile.mkdtemp()

    try:
        if logo1_file:
            logo1_path = os.path.join(_tmp_dir, f"logo1_{logo1_file.name}")
            with open(logo1_path, "wb") as f:
                f.write(logo1_file.read())
        else:
            # Fall back to workspace file if present
            _default1 = os.path.join(os.path.dirname(__file__), "logo1.png")
            if os.path.exists(_default1):
                logo1_path = _default1

        if logo2_file:
            logo2_path = os.path.join(_tmp_dir, f"logo2_{logo2_file.name}")
            with open(logo2_path, "wb") as f:
                f.write(logo2_file.read())
        else:
            _default2 = os.path.join(os.path.dirname(__file__), "logo2.png")
            if os.path.exists(_default2):
                logo2_path = _default2

        # ── Generate ─────────────────────────────────────────────────────
        with st.spinner("Generating PDF report… this may take 10–30 seconds."):
            pdf_bytes = rpt.build_report(
                output=None,                    # return bytes
                departments=departments,
                report_period=report_period,
                report_month_start=report_month_start,
                random_seed=int(random_seed),
                logo1_path=logo1_path,
                logo2_path=logo2_path,
            )

    finally:
        shutil.rmtree(_tmp_dir, ignore_errors=True)

    # Store in session so the download button persists across reruns
    st.session_state["pdf_bytes"] = pdf_bytes
    st.session_state["pdf_fname"] = output_fname
    st.success(f"✅ Report generated — {len(pdf_bytes) / 1024:.0f} KB")

# ── Download button (persists after generation) ────────────────────────────
if "pdf_bytes" in st.session_state:
    st.download_button(
        label="⬇️  Download PDF Report",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_fname"],
        mime="application/pdf",
        use_container_width=False,
    )
    st.caption(
        f"**File:** `{st.session_state['pdf_fname']}`  ·  "
        f"**Size:** {len(st.session_state['pdf_bytes']) / 1024:.0f} KB"
    )

# ═══════════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════════
st.divider()
st.caption(
    "CONFIDENTIAL – For official use only  |  Tamil Nadu FibreNet Corporation  |  "
    "Ezhilagam, Chepauk, Chennai – 600 005"
)
