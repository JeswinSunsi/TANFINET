"""
TANFINET – ILL SLA Report Generator
"""

import calendar
import os
from datetime import datetime

import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TANFINET Report Generator",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Minimalist CSS (Theme Adaptive) ─────────────────────────────────────────
st.markdown("""
<style>
    /* Clean, flat header adapting to light/dark mode */
    .app-header {
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        padding-bottom: 1.5rem;
        margin-bottom: 2rem;
        margin-top: 1rem;
    }
    .app-title {
        color: var(--text-color);
        font-size: 1.75rem;
        font-weight: 600;
        margin: 0;
        letter-spacing: -0.025em;
    }
    .app-subtitle {
        color: var(--text-color);
        opacity: 0.7;
        font-size: 0.95rem;
        margin-top: 0.25rem;
    }
    /* Subdued section headers */
    .section-title {
        color: var(--text-color);
        font-size: 1.1rem;
        font-weight: 600;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        padding-bottom: 0.5rem;
    }
    /* Primary Action Button */
    .stButton > button[kind="primary"] {
        background-color: var(--primary-color);
        color: white;
        font-weight: 500;
        border-radius: 6px;
        padding: 0.5rem 1rem;
    }
    /* Hide top padding for cleaner look */
    .block-container {
        padding-top: 3rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <p class="app-title">TANFINET ILL SLA Report Generator</p>
  <p class="app-subtitle">Tamil Nadu FibreNet Corporation — Bandwidth Performance Audit</p>
</div>
""", unsafe_allow_html=True)

# ── Import report module ────────────────────────────────────────────────────
@st.cache_resource
def _import_report():
    import importlib, sys
    mod_dir = os.path.dirname(os.path.abspath(__file__))
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    import report as rpt
    return rpt

rpt = _import_report()

# ═══════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<p style='font-size: 1.1rem; font-weight: 600; color: var(--text-color);'>Report Settings</p>", unsafe_allow_html=True)
    
    st.markdown("<p style='font-size: 0.85rem; font-weight: 600; color: var(--text-color); opacity: 0.7; margin-bottom: 0.5rem;'>PERIOD</p>", unsafe_allow_html=True)
    col_m, col_y = st.columns(2)
    with col_m:
        month_num = st.selectbox("Month", range(1, 13), index=2, format_func=lambda m: calendar.month_abbr[m], label_visibility="collapsed")
    with col_y:
        year_val = st.number_input("Year", min_value=2020, max_value=2035, value=2026, step=1, label_visibility="collapsed")
    
    report_period = f"{calendar.month_name[month_num]} {year_val}"
    report_month_start = datetime(int(year_val), int(month_num), 1)

    st.write("")
    with st.expander("Advanced Configuration"):
        random_seed = st.number_input("Random Seed", min_value=0, max_value=9999, value=42, step=1)
        output_fname = st.text_input("Output Filename", value=f"TANFINET_ILL_SLA_{year_val}_{month_num:02d}.pdf")

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN AREA
# ═══════════════════════════════════════════════════════════════════════════

st.markdown('<p class="section-title">Department Configuration</p>', unsafe_allow_html=True)

# Build editable dataframe from defaults
_default_depts = rpt.DEFAULT_DEPARTMENTS
_df_init = pd.DataFrame([
    {"Include": True, "Department Name": name, "Circuit ID": cid, "Capacity (Mbps)": cap, "SLA Target (%)": sla}
    for name, cid, cap, sla in _default_depts
])

if "dept_df" not in st.session_state:
    st.session_state["dept_df"] = _df_init.copy()

# Utility row with state-clearing to prevent checkbox bugs
btn_col1, btn_col2, btn_col3, _ = st.columns([1.5, 1.5, 1.5, 5.5])
with btn_col1:
    if st.button("Select All", use_container_width=True):
        st.session_state["dept_df"]["Include"] = True
        if "dept_editor" in st.session_state: del st.session_state["dept_editor"]
        st.rerun()
with btn_col2:
    if st.button("Deselect All", use_container_width=True):
        st.session_state["dept_df"]["Include"] = False
        if "dept_editor" in st.session_state: del st.session_state["dept_editor"]
        st.rerun()
with btn_col3:
    if st.button("Reset Defaults", use_container_width=True):
        st.session_state["dept_df"] = _df_init.copy()
        if "dept_editor" in st.session_state: del st.session_state["dept_editor"]
        st.rerun()

# Editable table
edited_df = st.data_editor(
    st.session_state["dept_df"],
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Include": st.column_config.CheckboxColumn("Include", width="small"),
        "Department Name": st.column_config.TextColumn("Department Name", width="large", disabled=True),
        "Circuit ID": st.column_config.TextColumn("Circuit ID", width="medium", disabled=True),
        "Capacity (Mbps)": st.column_config.NumberColumn("Capacity (Mbps)", min_value=1, max_value=100_000, step=50, width="medium"),
        "SLA Target (%)": st.column_config.NumberColumn("SLA Target (%)", min_value=90.0, max_value=99.99, step=0.5, format="%.2f %%", width="medium"),
    },
    key="dept_editor",
    hide_index=True,
)

# Selection summary based on the output of the data_editor
selected = edited_df[edited_df["Include"] == True]   
n_sel = len(selected)

st.write("")
m1, m2, m3 = st.columns(3)
m1.metric("Selected Departments", n_sel)
m2.metric("Reporting Period", report_period)
m3.metric("Total Contracted BW", f"{int(selected['Capacity (Mbps)'].sum()):,} Mbps" if n_sel else "—")

# ═══════════════════════════════════════════════════════════════════════════
#  GENERATE REPORT
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<p class="section-title">Report Generation</p>', unsafe_allow_html=True)

if n_sel == 0:
    st.error("Select at least one department to generate a report.")
else:
    generate_col, _ = st.columns([2, 6])
    with generate_col:
        generate_btn = st.button("Generate PDF Report", type="primary", use_container_width=True)

    if generate_btn:
        departments = [
            (row["Department Name"], row["Circuit ID"], int(row["Capacity (Mbps)"]), float(row["SLA Target (%)"]))
            for _, row in selected.iterrows()
        ]

        try:
            with st.spinner("Compiling PDF..."):
                pdf_bytes = rpt.build_report(
                    output=None,
                    departments=departments,
                    report_period=report_period,
                    report_month_start=report_month_start,
                    random_seed=int(random_seed),
                    logo1_path=None,
                    logo2_path=None,
                )

            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["pdf_fname"] = output_fname
            
        except Exception as e:
            st.error(f"Error generating report: {e}")

    # Persisted Download Button
    if "pdf_bytes" in st.session_state:
        dl_col, _ = st.columns([2, 6])
        with dl_col:
            st.download_button(
                label="Download PDF",
                data=st.session_state["pdf_bytes"],
                file_name=st.session_state["pdf_fname"],
                mime="application/pdf",
                use_container_width=True,
            )
        st.caption(f"File: {st.session_state['pdf_fname']} ({len(st.session_state['pdf_bytes']) / 1024:.0f} KB)")

# ═══════════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style='margin-top: 4rem; padding-top: 1rem; border-top: 1px solid rgba(128, 128, 128, 0.2); color: var(--text-color); opacity: 0.6; font-size: 0.8rem;'>
    For official use only. Tamil Nadu FibreNet Corporation.
</div>
""", unsafe_allow_html=True)