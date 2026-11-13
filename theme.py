"""Tema Cyber Threat Intelligence: biru gelap, hijau (aman/aksen), merah (peringatan). Font sistem (tanpa unduhan
eksternal) agar tampil konsisten saat demo offline. Tidak ada overlay yang dapat menutupi konten."""
import plotly.express as px
import streamlit as st

NAVY, PANEL, BORDER = "#0a1628", "#0f2038", "#1c3a5e"
GREEN, AMBER, RED, BLUE, TEXT, MUTED = "#00e676", "#ffb020", "#ff4d4d", "#4da3ff", "#e6edf3", "#9fb3c8"
COLORS = {"Rendah": GREEN, "Sedang": AMBER, "Tinggi": RED, "Data Tidak Cukup": "#8a97a8"}

CSS = f"""
<style>
html, body, [class*="css"], .stMarkdown, p, label, li {{ font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
code, pre {{ font-family: Consolas, "Courier New", monospace !important; }}
[data-testid="stAppViewContainer"] {{ background: linear-gradient(180deg, {NAVY} 0%, #0c1c33 100%) !important; }}
[data-testid="stHeader"] {{ background: transparent !important; }}
.block-container {{ padding-top: 2.2rem; max-width: 1280px; }}

[data-testid="stSidebar"] {{ background: #081120 !important; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] h1 {{ color: {GREEN} !important; letter-spacing: 2px; font-size: 1.5rem; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 6px 8px; border-radius: 6px; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: {PANEL}; }}

h1, h2, h3 {{ color: {TEXT} !important; letter-spacing: .5px; }}
h1 {{ border-bottom: 2px solid {GREEN}; padding-bottom: .3rem; }}

[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 4px solid {GREEN};
  border-radius: 8px; padding: 14px 16px; box-shadow: 0 4px 14px rgba(0,0,0,.35); }}
[data-testid="stMetricLabel"] {{ color: {MUTED} !important; text-transform: uppercase; letter-spacing: 1px; }}
[data-testid="stMetricValue"] {{ color: {TEXT} !important; }}

.stButton > button, .stDownloadButton > button {{ background: {GREEN} !important; color: #04210f !important; border: 0 !important;
  border-radius: 6px !important; font-weight: 700; padding: .5rem 1.1rem; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ filter: brightness(1.08); }}

textarea, input, [data-baseweb="select"] > div {{ background: #0a1930 !important; color: {TEXT} !important; border: 1px solid {BORDER} !important; }}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {{ border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; background: rgba(15,32,56,.6); }}
[data-testid="stExpander"] {{ border: 1px solid {BORDER}; border-radius: 8px; }}
[data-testid="stAlert"] {{ border-radius: 8px; }}

.cti-banner {{ display: inline-block; font-family: Consolas, monospace; color: {GREEN}; border: 1px solid {GREEN};
  padding: 2px 12px; letter-spacing: 3px; border-radius: 4px; margin-bottom: 8px; font-size: .85rem; }}
.risk-card {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 8px solid var(--c); border-radius: 8px;
  padding: 14px 18px; margin: 8px 0 14px 0; }}
.risk-card .lvl {{ color: var(--c); font-weight: 800; font-size: 1.5rem; letter-spacing: 1px; }}
.risk-card .sub {{ color: {MUTED}; font-size: .9rem; }}
.pill {{ display: inline-block; padding: 1px 10px; border-radius: 999px; font-size: .8rem; font-weight: 700;
  color: #07111f; background: var(--c); }}

@media (max-width: 768px) {{
  .block-container {{ padding: 1rem .6rem; }}
  h1 {{ font-size: 1.5rem !important; }}
  .risk-card .lvl {{ font-size: 1.15rem; }}
}}
</style>
"""

def apply():
    st.markdown(CSS, unsafe_allow_html=True)
    px.defaults.template = "plotly_dark"
    px.defaults.color_discrete_sequence = [GREEN, BLUE, AMBER, RED, "#c084fc", "#2dd4bf", "#f472b6"]

def banner(text="THREAT INTELLIGENCE // COGNITIVE DOMAIN"):
    st.markdown(f'<span class="cti-banner">{text}</span>', unsafe_allow_html=True)

def risk_card(level: str, score: float, title="SKOR RISIKO INDIKATIF", note="Bukan probabilitas; belum dikalibrasi."):
    c = COLORS.get(level, "#8a97a8")
    st.markdown(f'<div class="risk-card" style="--c:{c}"><div class="sub">{title}</div>'
                f'<div class="lvl">{score:.0f}/100 &middot; {level.upper()}</div><div class="sub">{note}</div></div>',
                unsafe_allow_html=True)

def pill(level: str) -> str:
    return f'<span class="pill" style="--c:{COLORS.get(level, "#8a97a8")}">{level}</span>'


