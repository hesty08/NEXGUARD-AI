"""NEXGUARD AI - Platform Analisis Keamanan Informasi (Cognitive Domain)."""

import os
import sys

# Pakai penyimpanan sertifikat Windows agar HTTPS tidak gagal oleh antivirus/proxy.
# Harus dijalankan sebelum modul lain (factcheck, intel, requests) dipakai.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass  # tetap jalan dengan sertifikat bawaan Python bila truststore tidak ada

import sys

# Pastikan semua modul diambil dari folder proyek yang sedang dijalankan.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR_NORM = os.path.normcase(os.path.abspath(PROJECT_DIR))

sys.path[:] = [
    p for p in sys.path
    if os.path.normcase(os.path.abspath(p or os.getcwd()))
    != os.path.normcase(
        os.path.abspath(
            os.path.join(
                os.path.expanduser("~"),
                "Downloads",
                "cybershield_v6_audited",
                "cybershield",
            )
        )
    )
]

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.chdir(PROJECT_DIR)

# Buang modul proyek yang telanjur dimuat dari folder lain.
LOCAL_MODULES = (
    "bot", "db", "early_warning", "evaluate", "explain",
    "factcheck", "hoax", "network", "report", "session_report",
    "social", "theme", "bot_investigation", "bot_ui", "intel",
    "verify", "verify_ui", "io_utils", "paths",
)

for module_name in LOCAL_MODULES:
    module = sys.modules.get(module_name)
    module_file = getattr(module, "__file__", None)

    if module_file:
        try:
            module_dir = os.path.normcase(os.path.abspath(module_file))
            if os.path.commonpath([PROJECT_DIR_NORM, module_dir]) != PROJECT_DIR_NORM:
                sys.modules.pop(module_name, None)
        except (ValueError, OSError):
            sys.modules.pop(module_name, None)

from urllib.parse import quote
from io import BytesIO
import html
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import bot, db, early_warning, evaluate, explain, factcheck, hoax, network, report, session_report, social, theme
import bot_investigation, bot_ui
import intel
import verify, verify_ui
from io_utils import safe_read_csv
from paths import data_file, asset_file

st.set_page_config(page_title="NEXGUARD AI", page_icon=asset_file("icon_128.png"), layout="wide",
                   initial_sidebar_state="collapsed")
# Cegah terjemahan otomatis browser (Edge/Chrome) yang merusak pembaruan halaman Streamlit.
_NOTRANSLATE_JS = ("<script>const d=window.parent.document;d.documentElement.setAttribute('translate','no');"
                   "d.documentElement.classList.add('notranslate');d.body.setAttribute('translate','no');"
                   "if(!d.querySelector('meta[name=google]')){const m=d.createElement('meta');m.name='google';m.content='notranslate';d.head.appendChild(m);}"
                   "</script>")
try:
    st.iframe(_NOTRANSLATE_JS, height=1)          # Streamlit versi baru
except Exception:
    try:
        import streamlit.components.v1 as components
        components.html(_NOTRANSLATE_JS, height=0)  # Streamlit versi lama
    except Exception:
        pass
DISCLAIMER = ("Hasil NEXGUARD AI berfungsi sebagai **alat bantu keputusan**: sistem memberi indikasi beserta alasannya, "
              "dan penetapan akhir tetap berada pada analis (human-in-the-loop).")
COLORS = theme.COLORS
STATUS_COLOR = {factcheck.VERIFIED: theme.GREEN, factcheck.CONTRADICTED: theme.RED, factcheck.UNVERIFIED: theme.AMBER}

theme.apply()
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&display=swap');
:root { --g: #00e676; --g2: #b2ff59; --olive: #8a9a5b; --khaki: #c5e1a5; }
h1, h2, h3 { font-family: 'Rajdhani', 'Segoe UI', sans-serif !important; letter-spacing: .8px; }
.side-title { font-family: 'Rajdhani', sans-serif; font-weight: 700; letter-spacing: 4px; color: var(--g); font-size: 1.2rem; }
[data-testid="stSidebarNav"] { display: none; }

@keyframes logo-glow {
    0%, 100% { filter: drop-shadow(0 0 6px rgba(0,230,118,.45)) drop-shadow(0 0 14px rgba(139,195,74,.25)); }
    50%      { filter: drop-shadow(0 0 14px rgba(0,230,118,.90)) drop-shadow(0 0 30px rgba(139,195,74,.50)); }
}
@keyframes menu-in { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes dot-blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }

/* ===== NAVBAR ATAS ===== */
.st-key-topnav {
    position: sticky; top: 3rem; z-index: 999;
    background: rgba(4,10,7,.94);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border-top: 2px solid var(--g);
    border-bottom: 1px solid rgba(0,230,118,.20);
    padding: 10px 6px 4px 6px; margin-bottom: 14px;
}
.cs-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 6px 8px 6px; }
.cs-brand { display: flex; align-items: center; gap: 12px; }
.cs-logo { width: 46px; height: 46px; border-radius: 10px; animation: logo-glow 3s ease-in-out infinite; }
.cs-name { font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 1.35rem; letter-spacing: 3px; color: #ffffff; line-height: 1.1; }
.cs-tag  { font-family: 'Share Tech Mono', Consolas, monospace; font-size: .72rem; letter-spacing: 3px; color: #8fae8f; }
.cs-chip { font-family: 'Share Tech Mono', Consolas, monospace; font-size: .74rem; letter-spacing: 2px; color: var(--g);
           border: 1px solid rgba(0,230,118,.45); border-radius: 4px; padding: 4px 12px; white-space: nowrap; }
.cs-chip i { font-style: normal; animation: dot-blink 1.6s ease-in-out infinite; }

.st-key-topnav [role="radiogroup"] {
    display: flex; flex-flow: row wrap; align-items: center; gap: 2px 6px;
    border-top: 1px solid rgba(255,255,255,.06); padding-top: 6px;
}
.st-key-topnav [role="radiogroup"] label {
    background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 4px 4px 0 0;
    padding: 6px 12px; margin: 0; cursor: pointer;
    transition: background .2s ease, border-color .2s ease;
    animation: menu-in .5s ease both;
}
.st-key-topnav [role="radiogroup"] label p {
    font-family: 'Rajdhani', sans-serif; font-size: 1.02rem; font-weight: 700; letter-spacing: .8px;
    text-transform: uppercase; color: #b9cbb9;
}
.st-key-topnav [role="radiogroup"] label:hover { background: rgba(0,230,118,.08); border-bottom-color: rgba(0,230,118,.6); }
.st-key-topnav [role="radiogroup"] label:hover p { color: #ffffff; }
.st-key-topnav [role="radiogroup"] label:has(input:checked) {
    border-bottom-color: var(--g);
    background: linear-gradient(180deg, rgba(0,230,118,0), rgba(0,230,118,.16));
}
.st-key-topnav [role="radiogroup"] label:has(input:checked) p { color: #ffffff; text-shadow: 0 0 12px rgba(0,230,118,.75); }
/* sembunyikan bulatan radio bawaan */
.st-key-topnav [data-testid="stRadioOption"] > div > div:first-child { display: none; }
</style>
""", unsafe_allow_html=True)
# ---- Latar belakang futuristik: lencana transparan + grid siber + cahaya ----
@st.cache_resource
def _bg_uri() -> str:
    """Versi kecil lencana (JPEG ~30 KB) untuk latar; kosong jika file tidak ada."""
    try:
        import base64, io
        from PIL import Image
        im = Image.open(asset_file("logo.png")).convert("RGB").resize((480, 480))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


@st.cache_resource
def _camo_uri() -> str:
    """Pola kamuflase digital (piksel) hijau gelap untuk latar; dibuat dari kode, tanpa file gambar."""
    import base64, random
    rnd = random.Random(11)
    tile, px = 240, 24
    cols = ["#1f3a24", "#2b4a2c", "#3b5a2a", "#13281a"]
    rects = []
    for y in range(tile // px):
        for x in range(tile // px):
            c = rnd.choice(cols + [None, None])
            if c:
                rects.append(f'<rect x="{x * px}" y="{y * px}" width="{px}" height="{px}" fill="{c}"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{tile}" height="{tile}">' + "".join(rects) + "</svg>"
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


_BG_CSS = """
<style>
@keyframes grid-drift {
    from { background-position: 0 0, 0 0, 0 -160px; }
    to   { background-position: 48px 48px, 48px 48px, 0 110vh; }
}
@keyframes orb-shift { 0%, 100% { background-position: 0% 0%, 100% 100%, 0 0; } 50% { background-position: 12% 8%, 88% 92%, 0 0; } }

/* cahaya hijau (kiri atas) dan zaitun (kanan bawah) di atas dasar hitam kehijauan */
.stApp {
    background:
        radial-gradient(ellipse 60% 50% at 12% 6%,  rgba(0,230,118,.12), transparent 70%),
        radial-gradient(ellipse 60% 55% at 90% 94%, rgba(138,154,91,.18), transparent 70%),
        #060d0a !important;
    background-attachment: fixed !important;
    background-size: 140% 140%, 140% 140%, auto !important;
    animation: orb-shift 18s ease-in-out infinite;
}
/* kamuflase digital, hanya terlihat di sudut kiri atas dan kanan bawah */
.stApp::before {
    content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image: url("__CAMO__"); background-size: 240px 240px; opacity: .55;
    -webkit-mask-image: linear-gradient(135deg, #000 0%, transparent 40%, transparent 62%, #000 100%);
    mask-image: linear-gradient(135deg, #000 0%, transparent 40%, transparent 62%, #000 100%);
}
/* grid taktis + garis pemindai yang turun pelan */
.stApp::after {
    content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
        linear-gradient(rgba(0,230,118,.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,230,118,.06) 1px, transparent 1px),
        linear-gradient(180deg, transparent, rgba(0,230,118,.10), transparent);
    background-size: 48px 48px, 48px 48px, 100% 160px;
    background-repeat: repeat, repeat, no-repeat;
    -webkit-mask-image: radial-gradient(ellipse at center, #000 25%, transparent 88%);
    mask-image: radial-gradient(ellipse at center, #000 25%, transparent 88%);
    animation: grid-drift 22s linear infinite;
}
[data-testid="stMain"], [data-testid="stSidebar"] { position: relative; z-index: 1; }
[data-testid="stMetric"] { background: rgba(10,26,18,.60) !important; backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); }
[data-testid="stSidebar"] { background: rgba(5,12,8,.85) !important; backdrop-filter: blur(8px); }
@media (prefers-reduced-motion: reduce) { .stApp, .stApp::after { animation: none; } }
</style>
"""
st.markdown(_BG_CSS.replace("__CAMO__", _camo_uri()), unsafe_allow_html=True)


@st.cache_resource
def _logo_uri() -> str:
    """Logo kecil (PNG 96 px) untuk header navbar; kosong jika file tidak ada."""
    try:
        import base64, io
        from PIL import Image
        im = Image.open(asset_file("logo.png")).convert("RGBA").resize((96, 96))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


_NAV_HEAD = ('<div class="cs-head"><div class="cs-brand"><img class="cs-logo" src="__LOGO__" alt="">'
             '<div><div class="cs-name">NEXGUARD AI</div><div class="cs-tag">DETEKSI · ANALISIS · LINDUNGI</div></div></div>'
             '<div class="cs-chip"><i>●</i> SISTEM AKTIF</div></div>')

db.purge(30)  # retensi data 30 hari
ss = st.session_state
ss.setdefault("analysis", {})

# Menu mendatar di bagian paling atas halaman utama (tidak perlu scroll).
with st.container(key="topnav"):
    st.markdown(_NAV_HEAD.replace("__LOGO__", _logo_uri()), unsafe_allow_html=True)
    page = st.radio("Menu", ["🏠 Dashboard", "🔍 Hoax Analyzer", "🔎 Fact Check Explorer", "🧪 Verifikasi Klaim", "🤖 Bot Analyzer", "🌐 Social Intelligence",
                             "🚨 Early Warning", "🕸️ Network Analysis", "📈 Analytics", "📑 Reports"],
                    horizontal=True, label_visibility="collapsed", key="nav")
st.sidebar.markdown('<div class="side-title">STATUS SISTEM</div>', unsafe_allow_html=True)
st.sidebar.caption("NEXGUARD AI · analisis ranah kognitif")
st.sidebar.divider()
st.sidebar.caption("Fact-check API: " + ("✅ terkonfigurasi" if factcheck.get_api_key() else "⛔ belum diatur"))
st.sidebar.caption("Verifikasi klaim: " + ("✅ aktif" if verify.get_gemini_key() else "⛔ belum diatur"))
st.sidebar.caption("Data dari unggahan CSV, bukan real-time.")


# ---------------------------------------------------------------- util
def load_csv(uploaded, fallback):
    return safe_read_csv(uploaded if uploaded else fallback)


def source_label(uploaded, fallback_name):
    return f"unggahan '{uploaded.name}'" if uploaded else f"data contoh bawaan ({fallback_name}, sintetis)"


def mask_df(df, cols):
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].map(db.mask_pii)
    return df


def show_explanation(e: dict):
    st.subheader("Penjelasan hasil (Explainable AI)")
    st.caption(e["catatan_skor"])
    if e.get("faktor"):
        st.markdown("**Faktor yang memengaruhi hasil**")
        st.dataframe(pd.DataFrame(e["faktor"]).rename(columns={"faktor": "Faktor", "bobot": "Bobot", "arah": "Arah", "detail": "Detail"}),
                     width="stretch", hide_index=True)
    if e.get("komponen_skor"):
        st.dataframe(pd.DataFrame(e["komponen_skor"]).rename(columns={"komponen": "Komponen", "nilai": "Nilai"}), width="stretch", hide_index=True)
    if e.get("istilah_model"):
        st.caption("Kata/frasa yang paling memengaruhi model ML (+ ke arah hoaks): " +
                   ", ".join(f"{t} ({v:+.2f})" for t, v in e["istilah_model"]))
    for n in e.get("catatan", []):
        st.info(n)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Keterbatasan analisis**")
        for x in e["keterbatasan"]:
            st.markdown(f"- {x}")
    with c2:
        st.markdown("**Rekomendasi pemeriksaan lanjutan**")
        for x in e["rekomendasi"]:
            st.markdown(f"- {x}")


def show_fact_check(fc: dict):
    st.subheader("🔎 Pemeriksaan fakta berbasis sumber")
    color = STATUS_COLOR[fc["overall"]]
    st.markdown(f'<div class="risk-card" style="--c:{color}"><div class="sub">STATUS KESELURUHAN</div>'
                f'<div class="lvl">{fc["overall"].upper()}</div><div class="sub">{fc["message"]}</div></div>', unsafe_allow_html=True)
    for c in fc["claims"]:
        with st.expander(f"{c['status']} — {c['claim'][:110]}"):
            st.write(c["reason"])
            if c["sources"]:
                st.dataframe(pd.DataFrame([{"Penerbit": s["publisher"], "Penilaian": s["rating"], "Kategori": s["kategori"],
                                            "Tanggal ulasan": s["review_date"] or "-", "Kemiripan": s["match"], "Tautan": s["url"]}
                                           for s in c["sources"]]),
                             width="stretch", hide_index=True, column_config={"Tautan": st.column_config.LinkColumn()})


def md_escape(text) -> str:
    """Teks dari sumber eksternal ditampilkan apa adanya (bukan sebagai markdown/HTML)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-!|<>~$])", r"\\\1", str(text))


def safe_url(u) -> str:
    return u if str(u).startswith(("http://", "https://")) else ""


# ---------------------------------------------------------------- Fact Check Explorer: tampilan Cyber Intelligence
FX_CSS = """
<style>
.fx-bar{display:flex;align-items:center;gap:10px;background:#0f2038;border:1px solid #1c3a5e;border-left:4px solid #00e676;border-radius:8px;padding:10px 16px;margin:4px 0 12px 0;color:#e6edf3;font-family:Consolas,monospace;letter-spacing:1.5px;font-size:.85rem}
.fx-bar b{color:#00e676;font-size:1.1rem}
.fx-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:6px 0 6px 0}
.fx-stat{background:#0f2038;border:1px solid #1c3a5e;border-top:3px solid var(--c);border-radius:8px;padding:12px 14px}
.fx-stat .n{color:var(--c);font-size:1.8rem;font-weight:800;line-height:1.1}
.fx-stat .l{color:#9fb3c8;font-size:.7rem;letter-spacing:1.2px;text-transform:uppercase;margin-top:4px}
.fx-card{background:linear-gradient(135deg,#0f2038 0%,#0b1a2e 100%);border:1px solid #1c3a5e;border-left:6px solid var(--c);border-radius:10px;padding:16px 18px;margin:14px 0 4px 0;box-shadow:0 4px 14px rgba(0,0,0,.35)}
.fx-badge{display:inline-block;color:var(--c);border:1px solid var(--c);border-radius:999px;padding:2px 12px;font-size:.75rem;font-weight:800;letter-spacing:1.2px}
.fx-claim{color:#e6edf3;font-size:1.08rem;font-weight:700;line-height:1.4;margin:10px 0 8px 0}
.fx-row{color:#c5d3e2;font-size:.9rem;margin:3px 0;line-height:1.45}
.fx-row b{color:#9fb3c8;font-weight:600}
.fx-row a{color:#4da3ff!important;text-decoration:none}
.fx-dates{color:#9fb3c8;font-size:.8rem;margin-top:8px}
a.fx-btn{display:inline-block;margin-top:12px;background:#00e676;color:#04210f!important;font-weight:700;font-size:.85rem;border-radius:6px;padding:7px 14px;text-decoration:none!important}
a.fx-btn:hover{filter:brightness(1.1)}
.fx-rev{border-top:1px solid #1c3a5e;margin-top:12px;padding-top:10px}
.fx-meta{color:#9fb3c8;font-size:.8rem;margin-bottom:4px}
.fx-cross{border:1px dashed var(--c);border-radius:8px;padding:8px 12px;margin:8px 0 2px 0;color:#e6edf3;font-size:.85rem;line-height:1.45}
@media (max-width:768px){.fx-claim{font-size:1rem}.fx-stat .n{font-size:1.5rem}}
</style>
"""

# Label sederhana hanya pengelompokan tampilan; penilaian asli penerbit tetap ditampilkan apa adanya.
FX_STATUS = {
    factcheck.CONTRADICTED: ("KLAIM TERBANTAH", "🛑",
                             "Klaim dinilai salah atau menyesatkan berdasarkan sumber pemeriksaan fakta."),
    factcheck.VERIFIED: ("KLAIM TERVERIFIKASI", "✅",
                         "Klaim dinilai benar berdasarkan sumber pemeriksaan fakta."),
    factcheck.UNVERIFIED: ("PERLU KONTEKS TAMBAHAN", "⚠️",
                           "Pemeriksa fakta tidak memberi penilaian benar/salah yang tegas (misalnya sebagian benar atau "
                           "belum terbukti). Baca sumber asli untuk konteksnya."),
}


def fx_h(x) -> str:
    """Escape teks eksternal untuk HTML ($ dan [ ] dinetralkan agar tidak dibaca sebagai rumus/tautan markdown)."""
    return html.escape(" ".join(str(x or "").split())).replace("$", "&#36;").replace("[", "&#91;").replace("]", "&#93;")


def fx_flat(x) -> str:
    return " ".join(str(x or "").split())


def fx_site_url(site) -> str:
    s = re.sub(r"^https?://", "", str(site or "").strip()).rstrip("/")
    return f"https://{s}" if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s) else ""


def render_fx_summary(claims, stats=None):
    """Panel ringkasan. Semua angka dihitung dari data yang benar-benar diterima dari API."""
    revs = [r for c in claims for r in c["reviews"]]
    n = lambda k: sum(r["kategori"] == k for r in revs)
    cs = intel.cross_stats(claims)
    items = [("Total klaim ditemukan", len(claims), theme.BLUE),
             ("Klaim terbantah", n(factcheck.CONTRADICTED), theme.RED),
             ("Klaim terverifikasi", n(factcheck.VERIFIED), theme.GREEN),
             ("Klaim dengan penilaian lain", n(factcheck.UNVERIFIED), theme.AMBER),
             ("Sumber pemeriksa pada hasil", len({r.get("source") or r["publisher"] for r in revs if r["publisher"]}), "#c084fc"),
             ("Klaim ditinjau ≥2 sumber", cs["multi"], "#2dd4bf"),
             ("Penilaian antar-sumber berbeda", cs["differ"], theme.AMBER)]
    st.markdown('<div class="fx-stats">' + "".join(
        f'<div class="fx-stat" style="--c:{c}"><div class="n">{v}</div><div class="l">{l}</div></div>' for l, v, c in items
    ) + "</div>", unsafe_allow_html=True)
    extra = ""
    if stats:
        if stats["dup_merged"]:
            extra += f" {stats['dup_merged']} entri duplikat digabung."
        if stats["dropped_no_link"]:
            extra += f" {stats['dropped_no_link']} ulasan disembunyikan karena API tidak menyertakan tautan asli."
    st.caption("Angka dihitung dari ulasan yang diterima API (sebelum filter penilaian). Satu klaim dapat memiliki beberapa "
               "ulasan; kategori dihitung per ulasan. Seluruh hasil adalah ulasan pihak ketiga, bukan verifikasi independen NEXGUARD AI." + extra)


def fx_badge_html(r) -> str:
    label, icon, _ = FX_STATUS[r["kategori"]]
    return f'<span class="fx-badge" style="--c:{STATUS_COLOR[r["kategori"]]}">{icon} STATUS VERIFIKASI: {label}</span>'


def fx_review_html(r, solo: bool) -> str:
    label, icon, summary = FX_STATUS[r["kategori"]]
    site = fx_site_url(r["site"]) or fx_site_url(intel.host_of(r["url"]))
    pub_name = fx_h(r["publisher"])
    pub_html = f'<a href="{fx_h(site)}" target="_blank" rel="noopener noreferrer">{pub_name}</a>' if site else pub_name
    body = (f'<div class="fx-row"><b>Hasil Pemeriksaan:</b> {summary}</div>'
            + (f'<div class="fx-row"><b>Penilaian pemeriksa:</b> “{fx_h(r["rating"])}”</div>' if r["rating"] else "")
            + f'<div class="fx-row"><b>Sumber Verifikasi:</b> {pub_html}</div>'
            + (f'<div class="fx-dates">🗓️ Tanggal pemeriksaan: {fx_h(r["review_date"])}</div>' if r["review_date"] else "")
            + f'<a class="fx-btn" href="{fx_h(r["url"])}" target="_blank" rel="noopener noreferrer">🔗 Lihat Bukti / Sumber Asli</a>')
    return body if solo else f'<div class="fx-rev" style="--c:{STATUS_COLOR[r["kategori"]]}">{fx_badge_html(r)}{body}</div>'


def fx_cross_html(c) -> str:
    cc = intel.cross_check(c)
    if cc["verdict"] == "agree":
        return (f'<div class="fx-cross" style="--c:{STATUS_COLOR[cc["category"]]}">🔀 <b>CROSS-SOURCE VERIFICATION</b> · {cc["n"]} pemeriksa fakta '
                f'memberi penilaian yang searah ({FX_STATUS[cc["category"]][0]}). Penilaian asli tiap penerbit tetap ditampilkan.</div>')
    if cc["verdict"] == "differ":
        return (f'<div class="fx-cross" style="--c:{theme.AMBER}">🔀 <b>CROSS-SOURCE VERIFICATION</b> · {cc["n"]} pemeriksa fakta memberi '
                f'penilaian yang berbeda. NEXGUARD AI tidak membuat kesimpulan gabungan; baca setiap sumber.</div>')
    return ""


def fx_detail_md(c) -> str:
    na = "tidak tersedia"
    cc = intel.cross_check(c)
    verdict = {"single": "Hanya 1 pemeriksa fakta yang meninjau klaim ini.",
               "agree": f"{cc['n']} pemeriksa fakta memberi penilaian yang searah ({FX_STATUS[cc['category']][0].title() if cc['category'] else ''}).",
               "differ": f"{cc['n']} pemeriksa fakta memberi penilaian yang berbeda; tidak ada kesimpulan gabungan."}[cc["verdict"]]
    lines = [f"- **Klaim asli:** {md_escape(fx_flat(c['claim_text'])) or na}"]
    if c.get("variants"):
        lines.append("- **Redaksi lain yang digabung sebagai duplikat:** " + "; ".join(md_escape(fx_flat(v)) for v in c["variants"]))
    lines += [f"- **Pengklaim:** {md_escape(fx_flat(c.get('claimant'))) or na}",
              f"- **Tanggal klaim:** {c.get('claim_date') or na}",
              f"- **Perbandingan antar-sumber:** {verdict}",
              f"- **Ditemukan melalui sumber:** {', '.join(intel.source_name(s) for s in c['found_in'])}"
              + (f" (digabung dari {c['merged_from']} entri)" if c.get("merged_from", 1) > 1 else "")]
    for i, r in enumerate(c["reviews"], 1):
        label, _, summary = FX_STATUS[r["kategori"]]
        link = r["url"]
        lines += [f"- **Ulasan {i} — {md_escape(fx_flat(r['publisher']))}**",
                  f"  - Hasil pemeriksaan: {label.title()} — {summary}",
                  f"  - Penilaian asli dari API: {md_escape(fx_flat(r['rating'])) or na}",
                  f"  - Judul ulasan: {md_escape(fx_flat(r['title'])) or na}",
                  f"  - Tanggal pemeriksaan: {r['review_date'] or na}",
                  f"  - Tautan sumber: [{md_escape(link)}]({link.replace('(', '%28').replace(')', '%29')})"]
    return "\n".join(lines)


def render_fx_claims(claims, categories, stats=None):
    """Kartu per klaim (hasil sudah digabung & bebas duplikat). Klaim tampil bila minimal satu ulasannya sesuai filter penilaian."""
    render_fx_summary(claims, stats)
    shown = 0
    for c in claims:
        if not any(r["kategori"] in categories for r in c["reviews"]):
            continue
        shown += 1
        cats_in = {r["kategori"] for r in c["reviews"]}
        color = STATUS_COLOR[next(iter(cats_in))] if len(cats_in) == 1 else theme.BLUE
        solo = len(c["reviews"]) == 1
        meta = " &nbsp;·&nbsp; ".join(x for x in [f"Pengklaim: {fx_h(c['claimant'])}" if c.get("claimant") else "",
                                                  f"📅 Tanggal klaim: {fx_h(c['claim_date'])}" if c.get("claim_date") else ""] if x)
        card = (f'<div class="fx-card" style="--c:{color}">'
                + (fx_badge_html(c["reviews"][0]) if solo else "")
                + f'<div class="fx-claim">{fx_h(c["claim_text"] or "(teks klaim tidak tersedia)")}</div>'
                + (f'<div class="fx-meta">{meta}</div>' if meta else "")
                + fx_cross_html(c) + "".join(fx_review_html(r, solo) for r in c["reviews"]) + "</div>")
        st.markdown(card, unsafe_allow_html=True)
        with st.expander("🔍 LIHAT DETAIL INVESTIGASI"):
            st.markdown(fx_detail_md(c))
            st.caption("Label status adalah pengelompokan otomatis dari penilaian asli penerbit. Penilaian asli tetap menjadi acuan.")
    if not shown:
        st.info("Tidak ada hasil yang sesuai filter.")
    return shown


def render_fetch_status(results):
    """Galat per sumber (dikelompokkan) + tabel status pengambilan."""
    errs = {}
    for r in results:
        if r["status"] == intel.ST_ERROR:
            errs.setdefault(r["error"], []).append(r["name"])
    for msg, names in errs.items():
        st.warning(f"{', '.join(names)}: {msg}")
    with st.expander("📡 Status pengambilan per sumber"):
        st.dataframe(pd.DataFrame(intel.health_rows(results)), width="stretch", hide_index=True)


def fx_to_csv(claims) -> bytes:
    rows = [{"klaim": c["claim_text"], "pengklaim": c["claimant"], "tanggal_klaim": c["claim_date"], "penerbit": r["publisher"],
             "peringkat_asli": r["rating"], "kategori": r["kategori"], "tanggal_ulasan": r["review_date"], "judul": r["title"], "tautan": r["url"]}
            for c in claims for r in c["reviews"]]
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def _enable_sources(ids, known):
    ss["fx_enabled"], ss["fx_known"] = ids, known


def _set_bi_sample(v: bool):
    ss["bi_sample"] = v


def mark_issue(d_df, issue):
    return d_df[d_df["text"].str.contains(issue.strip(), case=False, na=False, regex=False)] if issue.strip() else d_df


# ---------------------------------------------------------------- Level ancaman
THREAT_LEVELS = [(25, "AMAN", "#00e676", "Tidak ada indikasi menonjol pada data yang dianalisis."),
                 (50, "WASPADA", "#ffd600", "Ada beberapa indikasi; lanjutkan pemantauan."),
                 (75, "SIAGA", "#ff9100", "Indikasi kuat di beberapa modul; tinjau manual segera."),
                 (101, "KRITIS", "#ff1744", "Indikasi sangat kuat dan berlapis; prioritaskan peninjauan.")]
THREAT_NAMES = ["Risiko hoaks", "Akun berpola bot", "Peringatan dini", "Aktivitas terkoordinasi"]
THREAT_CSS = """
<style>
@keyframes thr-pulse { 0%, 100% { box-shadow: 0 0 8px var(--c); } 50% { box-shadow: 0 0 28px var(--c); } }
.thr-badge { border: 1px solid var(--c); border-left: 6px solid var(--c); border-radius: 12px; padding: 14px 18px;
             background: rgba(15,32,56,.55); animation: thr-pulse 2.2s ease-in-out infinite; }
.thr-lvl { font-size: 2.1rem; font-weight: 800; letter-spacing: 3px; color: var(--c); line-height: 1.2; }
.thr-sub { font-size: .8rem; opacity: .85; letter-spacing: 1px; }
</style>
"""


def threat_level(df, al, a):
    """Skor ancaman gabungan 0-100 dari komponen yang punya data (bobot dinormalisasi). None bila belum ada data."""
    parts = []  # (komponen, nilai 0-100, bobot, dasar)
    if len(df) and "module" in df.columns:
        sc = pd.to_numeric(df.loc[df["module"] == "Hoax", "score"], errors="coerce").dropna().head(10)
        if len(sc):
            parts.append((THREAT_NAMES[0], float(sc.mean()), 0.30, f"rata-rata {len(sc)} analisis hoaks terakhir"))
    b = a.get("bot")
    if b is not None and len(b["res"]):
        n_hi = int((b["res"]["level"] == "Tinggi").sum())
        parts.append((THREAT_NAMES[1], min(100.0, 200.0 * n_hi / len(b["res"])), 0.25, f"{n_hi} dari {len(b['res'])} akun berpola tinggi"))
    if len(al):
        hi = int((al["level"] == "Tinggi").sum()) if "level" in al.columns else 0
        parts.append((THREAT_NAMES[2], float(min(100, 40 * hi + 15 * (len(al) - hi))), 0.25, f"{hi} tingkat tinggi, {len(al) - hi} lainnya"))
    so = a.get("social")
    if so is not None:
        cc = so["clusters"]
        sync = int(cc["serempak"].sum()) if len(cc) and "serempak" in cc.columns else 0
        parts.append((THREAT_NAMES[3], float(min(100, 20 * len(cc) + 20 * sync)), 0.20, f"{len(cc)} klaster teks mirip, {sync} serempak"))
    if not parts:
        return None
    wsum = sum(p[2] for p in parts)
    score = sum(p[1] * p[2] for p in parts) / wsum
    _, name, color, desc = next(x for x in THREAT_LEVELS if score < x[0])
    return {"score": score, "name": name, "color": color, "desc": desc, "parts": parts, "wsum": wsum}


def render_threat(df, al, a):
    t = threat_level(df, al, a)
    st.subheader("🎯 Level Ancaman Keseluruhan")
    score, color = (t["score"], t["color"]) if t else (0.0, "#5c6b7a")
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        number={"suffix": " / 100", "valueformat": ".0f", "font": {"size": 38, "color": color}},
        gauge={"axis": {"range": [0, 100], "tickcolor": "#8fa3b8", "tickvals": [0, 25, 50, 75, 100]},
               "bar": {"color": color, "thickness": 0.28}, "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
               "steps": [{"range": [0, 25], "color": "rgba(0,230,118,.22)"}, {"range": [25, 50], "color": "rgba(255,214,0,.22)"},
                         {"range": [50, 75], "color": "rgba(255,145,0,.25)"}, {"range": [75, 100], "color": "rgba(255,23,68,.28)"}]}))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=20, b=0), paper_bgcolor="rgba(0,0,0,0)", font={"color": "#e6edf3"})
    g, d = st.columns([2, 3])
    g.plotly_chart(fig, width="stretch")
    with d:
        st.markdown(THREAT_CSS, unsafe_allow_html=True)
        if t:
            st.markdown(f'<div class="thr-badge" style="--c:{t["color"]}"><div class="thr-sub">STATUS SAAT INI</div>'
                        f'<div class="thr-lvl">{t["name"]}</div><div class="thr-sub">{t["desc"]}</div></div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"Komponen": n, "Nilai (0-100)": round(v), "Bobot": f"{w / t['wsum']:.0%}", "Dasar": dsr}
                                       for n, v, w, dsr in t["parts"]]), width="stretch", hide_index=True)
            missing = [n for n in THREAT_NAMES if n not in {p[0] for p in t["parts"]}]
            if missing:
                st.caption("Belum ada data untuk: " + ", ".join(missing) + ". Jalankan analisis pada menu terkait agar skor lebih lengkap.")
        else:
            st.markdown('<div class="thr-badge" style="--c:#5c6b7a"><div class="thr-sub">STATUS SAAT INI</div>'
                        '<div class="thr-lvl">BELUM ADA DATA</div><div class="thr-sub">Jalankan analisis pada menu lain untuk mengisi indikator ini.</div></div>',
                        unsafe_allow_html=True)
    with st.expander("Cara menghitung dan keterbatasan"):
        st.markdown("- Skor adalah **rata-rata berbobot** dari komponen yang punya data; bobot dinormalisasi bila ada komponen yang kosong.\n"
                    "- Bobot awal: risiko hoaks 30%, akun berpola bot 25%, peringatan dini 25%, aktivitas terkoordinasi 20%. Bobot ini **asumsi desain**, belum divalidasi.\n"
                    "- Ambang level: **Aman** < 25, **Waspada** 25-49, **Siaga** 50-74, **Kritis** ≥ 75.\n"
                    "- Ini ringkasan **indikatif** dari data yang diunggah atau dianalisis, bukan penilaian ancaman resmi dan bukan bukti.")


# ---------------------------------------------------------------- Hero (halaman pembuka)
HERO_CSS = """
<style>
@keyframes hero-up { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: translateY(0); } }
@keyframes hero-sway {
    0%, 100% { transform: translateY(0) rotate(-2.5deg) scale(1); }
    25%      { transform: translateY(-12px) rotate(0deg) scale(1.02); }
    50%      { transform: translateY(0) rotate(2.5deg) scale(1); }
    75%      { transform: translateY(9px) rotate(0deg) scale(.99); }
}
@keyframes hero-pulse { 0%, 100% { opacity: .5; transform: scale(1); } 50% { opacity: .9; transform: scale(1.08); } }
@keyframes radar-spin { to { transform: rotate(360deg); } }
@keyframes blip { 0%, 100% { opacity: .15; transform: scale(.6); } 50% { opacity: 1; transform: scale(1.5); } }

.hero-left > div, .hero-left > p { animation: hero-up .8s ease both; }
.hero-left > :nth-child(2) { animation-delay: .08s; }
.hero-left > :nth-child(3) { animation-delay: .16s; }
.hero-left > :nth-child(4) { animation-delay: .24s; }
.hero-left > :nth-child(5) { animation-delay: .34s; }
.hero-left > :nth-child(6) { animation-delay: .44s; }
.hero-left > :nth-child(7) { animation-delay: .54s; }
.hero-hud { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.hero-hud span { font-family: 'Share Tech Mono', Consolas, monospace; font-size: .74rem; letter-spacing: 2px; color: var(--khaki);
                 border: 1px solid rgba(138,154,91,.5); background: rgba(138,154,91,.08); padding: 3px 10px; border-radius: 3px; }
.hero-hud span:first-child { color: var(--g); border-color: rgba(0,230,118,.5); background: rgba(0,230,118,.08); }
.hero-t1, .hero-t2, .hero-t3 { font-family: 'Rajdhani', sans-serif; font-size: clamp(3.2rem, 6.6vw, 5.8rem); font-weight: 700;
                               line-height: 1; letter-spacing: 3px; width: fit-content; }
.hero-t1 { color: #ffffff; }
.hero-t2, .hero-t3 {
    background: linear-gradient(90deg, #00e676 0%, #76ff03 60%, #c5e1a5 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent; -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 18px rgba(0,230,118,.35));
}
.hero-sub { font-family: 'Share Tech Mono', Consolas, monospace; margin: 18px 0 14px; letter-spacing: 5px; color: var(--khaki); font-size: 1rem; }
.hero-desc { font-size: 1.08rem; line-height: 1.75; color: #cbd5cb; max-width: 34rem; margin: 0; }
.hero-info { border-left: 3px solid var(--olive); padding: 4px 0 4px 16px; margin: 18px 0 14px; color: #93a593; line-height: 1.9; }
.hero-info b { color: #ffffff; }

.hero-art { position: relative; display: flex; justify-content: center; align-items: center; min-height: 400px; }
.hero-radar {
    position: absolute; left: 50%; top: 50%; width: 94%; aspect-ratio: 1; transform: translate(-50%, -50%); border-radius: 50%;
    border: 1px solid rgba(0,230,118,.35);
    background:
        linear-gradient(rgba(0,230,118,.22), rgba(0,230,118,.22)) center / 1px 100% no-repeat,
        linear-gradient(rgba(0,230,118,.22), rgba(0,230,118,.22)) center / 100% 1px no-repeat,
        repeating-radial-gradient(circle closest-side, transparent 0 24%, rgba(0,230,118,.20) 24% 25%);
    box-shadow: inset 0 0 40px rgba(0,230,118,.10), 0 0 30px rgba(0,230,118,.10);
}
.hero-radar::after {
    content: ""; position: absolute; inset: 0; border-radius: 50%;
    background: conic-gradient(from 0deg, rgba(0,230,118,0) 0deg, rgba(0,230,118,.50) 68deg, rgba(0,230,118,0) 69deg 360deg);
    animation: radar-spin 5s linear infinite;
}
.blip { position: absolute; width: 8px; height: 8px; border-radius: 50%; background: #ffb300; box-shadow: 0 0 10px #ffb300; animation: blip 3s ease-in-out infinite; }
.b1 { top: 22%; left: 70%; } .b2 { top: 68%; left: 22%; animation-delay: 1s; background: #00e676; box-shadow: 0 0 10px #00e676; } .b3 { top: 40%; left: 16%; animation-delay: 2s; }
.hero-glow {
    position: absolute; width: 74%; aspect-ratio: 1; border-radius: 50%;
    background: radial-gradient(circle, rgba(0,230,118,.30), rgba(138,154,91,.18) 45%, transparent 70%);
    filter: blur(26px); animation: hero-pulse 4.5s ease-in-out infinite;
}
.hero-logo {
    position: relative; width: min(78%, 430px); aspect-ratio: 1; object-fit: contain; mix-blend-mode: screen;
    -webkit-mask-image: radial-gradient(closest-side, #000 82%, transparent 100%);
    mask-image: radial-gradient(closest-side, #000 82%, transparent 100%);
    animation: hero-sway 7s ease-in-out infinite; transform-origin: 50% 60%;
}
.hero-brackets {
    position: absolute; inset: 0; pointer-events: none; --c: rgba(0,230,118,.85);
    background:
        linear-gradient(var(--c), var(--c)) top left / 30px 2px no-repeat, linear-gradient(var(--c), var(--c)) top left / 2px 30px no-repeat,
        linear-gradient(var(--c), var(--c)) top right / 30px 2px no-repeat, linear-gradient(var(--c), var(--c)) top right / 2px 30px no-repeat,
        linear-gradient(var(--c), var(--c)) bottom left / 30px 2px no-repeat, linear-gradient(var(--c), var(--c)) bottom left / 2px 30px no-repeat,
        linear-gradient(var(--c), var(--c)) bottom right / 30px 2px no-repeat, linear-gradient(var(--c), var(--c)) bottom right / 2px 30px no-repeat;
}
.hero-cap { position: absolute; bottom: 8px; left: 0; right: 0; text-align: center; font-family: 'Share Tech Mono', Consolas, monospace;
            font-size: .72rem; letter-spacing: 3px; color: rgba(197,225,165,.8); }

/* tombol hero */
.st-key-hero_cta button { height: 54px; border-radius: 6px; font-family: 'Rajdhani', sans-serif; font-size: 1.1rem; font-weight: 700; letter-spacing: 1.5px;
                          text-transform: uppercase; transition: transform .2s ease, filter .2s ease, box-shadow .2s ease; }
.st-key-hero_cta [data-testid="stBaseButton-primary"] { background: linear-gradient(135deg, #00e676, #76ff03); color: #04130a; border: none; box-shadow: 0 0 20px rgba(0,230,118,.35); }
.st-key-hero_cta [data-testid="stBaseButton-secondary"] { background: rgba(10,26,18,.65); color: #ffffff; border: 1px solid rgba(138,154,91,.7); }
.st-key-hero_cta button:hover { transform: translateY(-3px); filter: brightness(1.12); box-shadow: 0 6px 26px rgba(0,230,118,.45); }
.st-key-hero_cta button:active { transform: scale(.97); }

@media (prefers-reduced-motion: reduce) {
    .hero-left > div, .hero-left > p, .hero-logo, .hero-glow, .hero-radar::after, .blip { animation: none; }
}
</style>
"""
HERO_LEFT = ('<div class="hero-left"><div class="hero-hud"><span>● SINYAL AKTIF</span><span>MODE: DATA UNGGAHAN</span><span>RETENSI 30 HARI</span></div>'
             '<div class="hero-t1">NEX</div><div class="hero-t2">GUARD</div><div class="hero-t3">AI</div>'
             '<div class="hero-sub">DETEKSI · ANALISIS · LINDUNGI</div>'
             '<p class="hero-desc">Platform analisis keamanan informasi di ranah kognitif. Mendeteksi indikasi hoaks, pola akun mencurigakan, '
             'dan aktivitas terkoordinasi, lalu menjelaskan alasannya agar mudah ditinjau manusia.</p>'
             '<div class="hero-info">Kategori <b>Siber Sosial (Cognitive Domain)</b><br>Ajang <b>Kartika Cyber Hackathon 2026</b></div></div>')


def _goto(p: str):
    ss["nav"] = p


def render_hero():
    st.markdown(HERO_CSS, unsafe_allow_html=True)
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        st.markdown(HERO_LEFT, unsafe_allow_html=True)
        with st.container(key="hero_cta"):
            b1, b2, _ = st.columns([3, 3, 2])
            b1.button("Mulai analisis hoaks →", type="primary", on_click=_goto, args=("🔍 Hoax Analyzer",), key="hero_b1")
            b2.button("Lihat peringatan dini", on_click=_goto, args=("🚨 Early Warning",), key="hero_b2")
    with right:
        st.markdown('<div class="hero-art"><div class="hero-radar"><i class="blip b1"></i><i class="blip b2"></i><i class="blip b3"></i></div>'
                    '<div class="hero-glow"></div>' + f'<img class="hero-logo" src="{_bg_uri()}" alt="">' +
                    '<div class="hero-brackets"></div><div class="hero-cap">RADAR ANALISIS · SIMULASI VISUAL</div></div>',
                    unsafe_allow_html=True)


# ---------------------------------------------------------------- Dashboard
if page == "🏠 Dashboard":
    render_hero()
    df, al = db.load(), db.load_alerts()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total analisis", len(df))
    c2.metric("Hoax Analyzer", int((df.module == "Hoax").sum()) if len(df) else 0)
    c3.metric("Bot Analyzer", int((df.module == "Bot").sum()) if len(df) else 0)
    c4.metric("Risiko tinggi", int((df.level == "Tinggi").sum()) if len(df) else 0)
    c5.metric("Peringatan dini", len(al))

    a = ss["analysis"]
    render_threat(df, al, a)
    st.subheader("Ringkasan sesi (tiga modul utama)")
    m1, m2, m3 = st.columns(3)
    h, b, s = a.get("hoax"), a.get("bot"), a.get("social")
    m1.metric("Hoax: skor risiko indikatif", f"{h['result']['score']:.0f}" if h else "—", h["result"]["level"] if h else "belum dianalisis", delta_color="off")
    m2.metric("Bot: akun pola tinggi", int((b["res"].level == "Tinggi").sum()) if b else "—", f"dari {len(b['res'])} akun" if b else "belum dianalisis", delta_color="off")
    m3.metric("Sosial: klaster teks mirip", len(s["clusters"]) if s else "—", f"{s['n_posts']} postingan" if s else "belum dianalisis", delta_color="off")

    if len(df):
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Analisis terbaru")
            st.dataframe(df[["ts", "module", "subject", "score", "level"]].head(10), width="stretch", hide_index=True)
        with right:
            st.subheader("Distribusi risiko")
            st.plotly_chart(px.histogram(df, x="level", color="level", color_discrete_map=COLORS), width="stretch")
    else:
        st.info("Belum ada analisis tersimpan. Mulai dari **Hoax Analyzer**, **Bot Analyzer**, atau **Early Warning**.")
    if len(al):
        st.subheader("🚨 Peringatan dini terbaru")
        st.dataframe(al[["date", "kind", "level", "value", "baseline", "z", "source"]].head(5), width="stretch", hide_index=True)
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------- Hoax
elif page == "🔍 Hoax Analyzer":
    st.title("🔍 Hoax Analyzer")
    text = st.text_area("Tempel teks berita / pesan berantai", height=180)
    url = st.text_input("Tautan sumber (opsional)", placeholder="contoh: kompas.com/artikel...")
    if len(text) > hoax.MAX_CHARS:
        st.warning(f"Teks dipotong ke {hoax.MAX_CHARS:,} karakter pertama.")
    api_key = factcheck.get_api_key()
    use_fc = st.checkbox("Periksa fakta dengan Google Fact Check Tools API (klaim dikirim ke Google; data pribadi disamarkan)",
                         value=bool(api_key), disabled=not api_key)
    if not api_key:
        st.caption("Pemeriksaan fakta nonaktif: setel `FACTCHECK_API_KEY` (environment variable atau `.streamlit/secrets.toml`). Lihat README.")
    gem_key = verify.get_gemini_key()
    use_ai = st.checkbox("Putusan AI (Gemini): jawab benar/tidak + bukti, dan baca isi tautan (teks & isi tautan dikirim ke Google; data pribadi disamarkan)",
                         value=bool(gem_key), disabled=not gem_key)
    if not gem_key:
        st.caption("Putusan AI nonaktif: setel `GEMINI_API_KEY` di `.streamlit/secrets.toml`.")
    if st.button("Analisis", type="primary") and (text.strip() or (use_ai and url.strip())):
        if use_ai:
            verify_ui.run_and_show(text, url)
            if not text.strip():
                st.stop()          # hanya tautan: putusan AI sudah ditampilkan
        r = hoax.analyze(text, url)
        q = quote(" ".join(text.split()[:12]))
        links = (f"🔎 **Cek manual klaim:** [TurnBackHoax](https://turnbackhoax.id/?s={q}) · "
                 f"[Google Fact Check Explorer](https://toolbox.google.com/factcheck/explorer/search/{q})")
        if r["input_kind"] != "klaim":
            if use_ai:
                st.caption("Skor indikator gaya hoaks tidak ditampilkan untuk teks sependek/sebentuk ini; lihat putusan AI di atas.")
                st.markdown(links)
                st.stop()
            st.warning("**Teks ini tidak dapat dinilai.** " + ("Isinya berupa **pertanyaan**, bukan klaim atau berita. "
                       if r["input_kind"] == "pertanyaan" else "Teksnya terlalu pendek untuk dianalisis. ") +
                       "Hoax Analyzer menilai *teks klaim/berita*, bukan menjawab pertanyaan, dan skor untuk input seperti ini "
                       "tidak bermakna. Ubah menjadi pernyataan lengkap, misalnya: *\"Prabowo adalah Presiden Indonesia.\"*, "
                       "lalu aktifkan pemeriksaan fakta (butuh API key) atau cek manual lewat tautan di bawah.")
            st.markdown(links)
            st.stop()
        fc = None
        if use_fc:
            with st.spinner("Mencari ulasan pemeriksa fakta..."):
                try:
                    fc = factcheck.fact_check_text(text, api_key)
                except Exception:
                    st.warning("Pemeriksaan fakta gagal dijalankan. Status dianggap Belum Terverifikasi.")
        e = explain.explain_hoax(r, fc)
        theme.risk_card(r["level"], r["score"])
        if r["level"] == "Rendah":
            st.caption("⚠️ Skor Rendah hanya berarti **tidak ada indikator gaya hoaks** (mis. desakan menyebarkan, huruf kapital berlebihan). "
                       "Ini **bukan** bukti klaim benar: klaim yang ditulis rapi tetap bisa keliru. Periksa isinya lewat pemeriksaan fakta.")
        if fc:
            show_fact_check(fc)
        else:
            st.info(f"Status verifikasi: **{r['status']}** — tanpa pemeriksaan fakta, aplikasi hanya mendeteksi indikasi.")
        a1, b1 = st.columns(2)
        a1.metric("Skor indikator linguistik", f"{r['rule_score']:.0f}")
        b1.metric("Skor model ML (belum terkalibrasi)", f"{r['ml_score']:.0f}")
        st.markdown(links)
        show_explanation(e)
        ss["analysis"]["hoax"] = {"result": r, "expl": e, "fc": fc}
        try:
            db.save("Hoax", text, r["score"], r["level"], {"signals": [x[0] for x in r["signals"]]})
        except Exception:
            st.warning("Hasil tidak dapat disimpan ke riwayat (kesalahan database).")
        st.warning(DISCLAIMER)

# ---------------------------------------------------------------- Fact Check Explorer
elif page == "🔎 Fact Check Explorer":
    st.title("🔎 Fact Check Explorer")
    st.caption("Telusuri klaim yang **sudah diperiksa** pemeriksa fakta, melalui Google Fact Check Tools API. "
               "Hanya ulasan asli dari API yang ditampilkan; tidak ada sumber yang dibuat sendiri.")
    api_key = factcheck.get_api_key()
    if not api_key:
        st.warning("Fitur ini membutuhkan API key. Setel `FACTCHECK_API_KEY` (environment variable atau `.streamlit/secrets.toml`) "
                   "lalu jalankan ulang aplikasi. Lihat README.")
        st.stop()
    f1, f2, f3 = st.columns(3)
    lang_label = f1.selectbox("Bahasa", ["Indonesia", "English", "Semua bahasa"])
    lang = {"Indonesia": "id", "English": "en", "Semua bahasa": None}[lang_label]
    age_label = f2.selectbox("Umur klaim/ulasan", ["7 hari", "30 hari", "90 hari", "1 tahun", "Semua"], index=1)
    age = {"7 hari": 7, "30 hari": 30, "90 hari": 90, "1 tahun": 365, "Semua": None}[age_label]
    cats = f3.multiselect("Tampilkan penilaian", [factcheck.CONTRADICTED, factcheck.VERIFIED, factcheck.UNVERIFIED],
                          default=[factcheck.CONTRADICTED, factcheck.VERIFIED, factcheck.UNVERIFIED])
    st.markdown(FX_CSS, unsafe_allow_html=True)
    src_bar = st.empty()   # indikator diisi di akhir halaman agar ikut hasil uji terbaru
    with st.expander("⚙️ Pengaturan Sumber Intelijen"):
        st.caption("Sumber yang dikumpulkan untuk **Multi-Source** (tab Cari klaim) dan **Latest Intelligence Feed** (tab Terbaru). "
                   "Google Fact Check Tools API tidak menjamin semua penerbit terindeks; gunakan tab **Source Health** untuk menguji "
                   "sumber mana yang benar-benar memberi data.")
        sel_box = st.container()
        custom_txt = st.text_area("Sumber tambahan (domain penerbit, satu per baris, maks. 5)", ss.get("fx_custom", ""),
                                  placeholder="contoh: liputan6.com", height=80)
        ss["fx_custom"] = custom_txt
        all_src = intel.SOURCES + intel.parse_custom(custom_txt)
        ids = [s["id"] for s in all_src]
        enabled = (set(ss.get("fx_enabled", ids)) | (set(ids) - set(ss.get("fx_known", [])))) & set(ids)   # sumber baru otomatis aktif
        by_name = {s["name"]: s for s in all_src}
        with sel_box:
            chosen = st.multiselect("Sumber aktif", list(by_name), default=[s["name"] for s in all_src if s["id"] in enabled])
        ss["fx_known"], ss["fx_enabled"] = ids, [by_name[n]["id"] for n in chosen]
    active = [s for s in all_src if s["id"] in ss["fx_enabled"]]
    tab_s, tab_r, tab_h = st.tabs(["🔍 Cari klaim", "🕒 Terbaru", "🩺 Source Health"])
    with tab_s:
        q1, q2 = st.columns([3, 2])
        query = q1.text_input("Kata kunci", placeholder="contoh: vaksin, bantuan sosial, judi online")
        pub = q2.text_input("Filter penerbit (opsional)", placeholder="contoh: turnbackhoax.id")
        multi = st.checkbox("🌐 Multi-Source Intelligence: gabungkan hasil semua sumber aktif (duplikat dihapus)", value=True, key="fx_multi")
        st.caption("Mengisi **Filter penerbit** atau mematikan opsi ini memakai pencarian satu arah (semua penerbit yang diindeks Google).")
        if st.button("Cari", type="primary", key="fx_go"):
            try:
                if multi and not pub.strip():
                    if not query.strip():
                        raise ValueError("Isi kata kunci pencarian atau filter penerbit (API mewajibkan salah satunya).")
                    if not active:
                        raise ValueError("Pilih minimal satu sumber aktif di ⚙️ Pengaturan Sumber Intelijen.")
                    with st.spinner(f"Mengumpulkan hasil dari {len(active)} sumber..."):
                        run = intel.run_multi(api_key, active, query.strip(), lang, age)
                    ss["fx_search"] = {"mode": "multi", "args": (query.strip(), pub, lang, age), **run}
                else:
                    with st.spinner("Mencari..."):
                        r = factcheck.explore(api_key, query, pub, lang, age)
                    ss["fx_search"] = {"mode": "single", "args": (query, pub, lang, age), "results": [],
                                       "raw": [[c, "manual"] for c in r["claims"]], "next": r["next_page_token"]}
            except (ValueError, RuntimeError) as e:
                st.error(str(e))
        fx = ss.get("fx_search")
        if fx:
            built = intel.process(fx["raw"], all_src)
            if fx["mode"] == "multi":
                render_fetch_status(fx["results"])
            if not built["claims"]:
                st.info("Tidak ada klaim yang diperiksa untuk pencarian ini. Ini bukan berarti klaim benar atau salah, "
                        "hanya belum ada ulasan yang ditemukan.")
            else:
                render_fx_claims(built["claims"], cats, built["stats"])
                has_more = bool(fx["next"]) if fx["mode"] == "single" else any(r.get("next") for r in fx["results"])
                if has_more and st.button("Muat lebih banyak", key="fx_more"):
                    try:
                        if fx["mode"] == "single":
                            more = factcheck.explore(api_key, *fx["args"], page_token=fx["next"])
                            fx["raw"] += [[c, "manual"] for c in more["claims"]]
                            fx["next"] = more["next_page_token"]
                        else:
                            fx["raw"] += intel.run_more(api_key, fx["results"], fx["args"][0], fx["args"][2], fx["args"][3])
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
                st.download_button("⬇️ Unduh hasil (CSV)", fx_to_csv(built["claims"]), "fact_check_explorer.csv", "text/csv", key="fx_csv")
    with tab_r:
        st.caption("**Latest Intelligence Feed**: ulasan terbaru dari semua sumber aktif (sesuai filter bahasa dan umur di atas), digabung tanpa "
                   "duplikat dan diurutkan dari tanggal pemeriksaan terbaru. Klaim tanpa tanggal ditaruh di bagian akhir.")
        if st.button("Muat terbaru", key="fx_recent_go"):
            if not active:
                st.error("Pilih minimal satu sumber aktif di ⚙️ Pengaturan Sumber Intelijen.")
            else:
                with st.spinner(f"Mengumpulkan ulasan terbaru dari {len(active)} sumber..."):
                    ss["fx_recent"] = intel.run_multi(api_key, active, None, lang, age or 30)
        fr = ss.get("fx_recent")
        if fr:
            render_fetch_status(fr["results"])
            built = intel.process(fr["raw"], all_src)
            feed = intel.sort_newest(built["claims"])
            if feed:
                dates = [d for d in (factcheck.newest_review_date(c) for c in feed) if d]
                st.caption(f"Tanggal terbaru {dates[0]} · terlama {dates[-1]} · {len(feed) - len(dates)} klaim tanpa tanggal."
                           if dates else "Tidak ada tanggal yang tersedia pada hasil ini.")
                render_fx_claims(feed, cats, built["stats"])
                st.download_button("⬇️ Unduh hasil (CSV)", fx_to_csv(feed), "fact_check_terbaru.csv", "text/csv", key="fx_csv2")
            elif not any(r["status"] == intel.ST_ERROR for r in fr["results"]):
                st.info("Tidak ada ulasan pada rentang waktu dan sumber ini.")
    with tab_h:
        st.caption("Menguji langsung setiap sumber ke Google Fact Check Tools API (semua bahasa). Status *Tidak ada data* tidak selalu berarti "
                   "penerbit itu tidak ada: bisa karena belum terindeks atau memang tidak ada ulasan.")
        if st.button("🩺 Uji semua sumber", type="primary", key="fx_health_go"):
            with st.spinner(f"Menguji {len(all_src)} sumber..."):
                ss["fx_health"] = {"results": intel.probe_all(api_key, all_src, age), "age_label": age_label,
                                   "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        hs = ss.get("fx_health")
        if hs:
            res, sm = hs["results"], intel.health_summary(hs["results"])
            tiles = [("Sumber diuji", sm["diuji"], theme.BLUE), ("Aktif (ada data)", sm[intel.ST_ACTIVE], theme.GREEN),
                     ("Terindeks, tanpa ulasan baru", sm[intel.ST_IDLE], theme.AMBER), ("Tidak ada data dari API", sm[intel.ST_NONE], "#8fa3b8"),
                     ("Kesalahan koneksi / API", sm[intel.ST_ERROR], theme.RED)]
            st.markdown('<div class="fx-stats">' + "".join(
                f'<div class="fx-stat" style="--c:{c}"><div class="n">{v}</div><div class="l">{l}</div></div>' for l, v, c in tiles) + "</div>",
                unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(intel.health_rows(res)), width="stretch", hide_index=True)
            working = [r["id"] for r in res if r["status"] in (intel.ST_ACTIVE, intel.ST_IDLE)]
            st.button("✅ Aktifkan hanya sumber yang memberi data", on_click=_enable_sources, args=(working, [s["id"] for s in all_src]),
                      key="fx_health_apply", disabled=not working)
            st.caption(f"Diuji pada {hs['ts']} · rentang {hs['age_label']} (diperluas ke 365 hari bila kosong) · semua bahasa. "
                       "Domain efektif adalah domain yang pertama kali mengembalikan data.")
        else:
            st.info("Belum ada hasil uji. Klik **Uji semua sumber** untuk melihat sumber mana yang benar-benar memberi data.")
    hs = ss.get("fx_health")
    n_ok = sum(r["status"] in (intel.ST_ACTIVE, intel.ST_IDLE) for r in hs["results"]) if hs else 0
    src_bar.markdown(f'<div class="fx-bar">📡 SUMBER PEMERIKSAAN FAKTA AKTIF: <b>{len(active)}</b>'
                     + (f' &nbsp;·&nbsp; UJI TERAKHIR: <b>{n_ok}</b>/{len(hs["results"])} SUMBER MEMBERI DATA' if hs else "") + "</div>",
                     unsafe_allow_html=True)
    st.caption("Ingin memeriksa teks Anda sendiri? Gunakan menu 🔍 Hoax Analyzer. Daftar ini hanya klaim yang pernah diulas pemeriksa fakta.")

# ---------------------------------------------------------------- Verifikasi Klaim
elif page == "🧪 Verifikasi Klaim":
    st.title("🧪 Verifikasi Klaim")
    st.caption("Periksa klaim atau isi sebuah tautan berita. Teks dan isi tautan dikirim ke layanan model bahasa eksternal "
               "(Google Gemini); data pribadi disamarkan.")
    if not verify.get_gemini_key():
        st.warning("Fitur ini nonaktif: setel `GEMINI_API_KEY` di `.streamlit/secrets.toml`.")
        st.stop()
    v_text = st.text_area("Klaim atau teks berita", height=160, key="vk_text")
    v_url = st.text_input("Tautan sumber (opsional)", placeholder="contoh: kompas.com/artikel...", key="vk_url")
    if st.button("Verifikasi", type="primary", key="vk_go"):
        if v_text.strip() or v_url.strip():
            verify_ui.run_and_show(v_text, v_url)
        else:
            st.info("Isi teks atau tautan terlebih dahulu.")
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------- Bot
elif page == "🤖 Bot Analyzer":
    st.title("🤖 Bot Analyzer")
    mode = st.radio("Sumber data", ["CSV postingan (fitur dihitung otomatis)", "CSV fitur akun"], horizontal=True)
    if mode.startswith("CSV postingan"):
        # Investigasi akun V6: skor risiko berbasis indikator, koordinasi, penjelasan, ringkasan, dashboard, dan ekspor
        st.caption("Kolom CSV: timestamp, username, text")
        up = st.file_uploader("Unggah CSV postingan", type="csv", key="bp")
        if up is None and not ss.get("bi_sample"):
            bot_ui.render_waiting()
            st.button("Gunakan data contoh bawaan", type="primary", on_click=_set_bi_sample, args=(True,), key="bi_use_sample_btn")
            st.stop()
        if up is None:
            st.button("Tutup data contoh", on_click=_set_bi_sample, args=(False,), key="bi_close_sample_btn")
        kind, prov = bot_ui.data_kind_selector(up is not None)
        with st.expander("Pengaturan deteksi koordinasi"):
            s1, s2, s3 = st.columns(3)
            b_thr = s1.slider("Ambang kemiripan teks", 0.5, 1.0, 0.8, 0.05, key="bi_thr")
            b_win = s2.slider("Jendela waktu serempak (menit)", 1, 120, 15, key="bi_win")
            b_min = s3.slider("Minimal akun per klaster", 2, 10, 3, key="bi_min")
        try:
            inv = st.cache_data(show_spinner="Menganalisis akun...")(bot_investigation.investigate)(
                load_csv(up, data_file("posts_sample.csv")), b_thr, b_win, b_min)
        except ValueError as e:
            st.error(str(e)); st.stop()
        res = inv["res"].copy()
        res.attrs["signals"], res.attrs["dropped"] = inv["signals"], inv["meta"]["dropped"]
        src = source_label(up, "posts_sample.csv")
        ss["analysis"]["bot"] = {"res": res, "source": f"{src} [{bot_ui.KINDS[kind][0].lower()}]"}
        bot_ui.render(inv, src, kind, mask=db.mask_pii, prov=prov)
        if st.button("Simpan akun berisiko tinggi ke laporan"):
            for r in res[res.level == "Tinggi"].itertuples():
                db.save("Bot", r.username, r.skor_bot, r.level, {"alasan": r.alasan})
            st.success("Tersimpan.")
        st.warning(DISCLAIMER)
        st.stop()
    try:
        st.caption("Kolom wajib: " + ", ".join(bot.CORE) + " · opsional: " + ", ".join(bot.OPTIONAL))
        up = st.file_uploader("Unggah CSV akun", type="csv", key="ba")
        res, src = bot.analyze_df(load_csv(up, data_file("accounts_sample.csv"))), source_label(up, "accounts_sample.csv")
    except ValueError as e:
        st.error(str(e)); st.stop()
    if res.attrs.get("dropped"):
        st.warning(f"{res.attrs['dropped']} baris dilewati karena data kosong/tidak valid.")
    ss["analysis"]["bot"] = {"res": res, "source": src}
    st.metric("Akun berpola tinggi (perlu ditinjau)", int((res.level == "Tinggi").sum()), f"dari {len(res)} akun", delta_color="off")
    st.plotly_chart(px.histogram(res, x="skor_bot", color="level", color_discrete_map=COLORS, nbins=20), width="stretch")
    st.dataframe(res, width="stretch")
    if len(res):
        st.subheader("Penjelasan per akun")
        who = st.selectbox("Pilih akun", res["username"].tolist())
        row = res[res.username == who].iloc[0]
        e = explain.explain_bot(who, row.skor_bot, row.level, res.attrs.get("signals", {}).get(who, []))
        theme.risk_card(row.level, row.skor_bot, title=f"AKUN {who}", note="Pola aktivitas indikatif, bukan vonis bot.")
        show_explanation(e)
    if st.button("Simpan akun berisiko tinggi ke laporan"):
        for r in res[res.level == "Tinggi"].itertuples():
            db.save("Bot", r.username, r.skor_bot, r.level, {"alasan": r.alasan})
        st.success("Tersimpan.")
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------- Social
elif page == "🌐 Social Intelligence":
    st.title("🌐 Social Intelligence")
    st.caption("Kolom CSV: date (atau timestamp), username, text")
    up = st.file_uploader("Unggah CSV postingan (kosongkan untuk data contoh)", type="csv")
    issue = st.text_input("Filter isu / kata kunci", placeholder="contoh: judi online")
    try:
        d = social.prepare(load_csv(up, data_file("posts_sample.csv")), issue)
    except ValueError as e:
        st.error(str(e)); st.stop()
    if d.empty:
        st.info("Tidak ada postingan yang cocok."); st.stop()
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.line(social.daily_trend(d), x="date", y="jumlah", color="sentimen", title="Evolusi isu per hari"), width="stretch")
    c2.plotly_chart(px.pie(d, names="sentimen", title="Komposisi sentimen", hole=.4), width="stretch")
    st.subheader("Kata kunci teratas")
    st.bar_chart(social.top_keywords(d).set_index("kata"))
    st.subheader("🕸️ Deteksi aktivitas terkoordinasi")
    thr = st.slider("Ambang kemiripan teks", 0.5, 1.0, 0.8, 0.05)
    cc = social.coordinated_clusters(d, thr)
    ss["analysis"]["social"] = {"clusters": cc, "n_posts": len(d), "n_accounts": d["username"].nunique(), "issue": issue,
                                "source": source_label(up, "posts_sample.csv")}
    if cc.empty:
        st.success("Tidak ada klaster teks mirip dari ≥3 akun berbeda.")
    else:
        n_sync = int(cc["serempak"].sum())
        st.error(f"{len(cc)} klaster teks mirip dari banyak akun, {n_sync} di antaranya diposting serempak "
                 f"(dalam 15 menit). Indikatif, bukan bukti koordinasi.")
        if cc.attrs.get("capped"):
            st.warning(f"Data sangat besar: hanya {social.MAX_UNIQUE} teks unik pertama yang dianalisis.")
        st.dataframe(mask_df(cc, ["contoh_teks"]), width="stretch")
        st.caption("Lihat visualisasi hubungan antar-akun pada menu 🕸️ Network Analysis dan peringatan statistik pada 🚨 Early Warning.")
    daily = d.groupby("date").size()
    if len(daily) > 3 and daily.iloc[-1] > 2 * daily.iloc[:-1].mean():
        st.error(f"🚨 Lonjakan volume terdeteksi: {daily.iloc[-1]} postingan pada {daily.index[-1]} "
                 f"(rata-rata sebelumnya {daily.iloc[:-1].mean():.0f}).")
    st.dataframe(mask_df(d.tail(30), ["text"]), width="stretch")

# ---------------------------------------------------------------- Early Warning
elif page == "🚨 Early Warning":
    st.title("🚨 Early Warning System")
    st.info("Peringatan dihitung dari **berkas CSV yang diunggah** (bukan data real-time) menggunakan robust z-score "
            "terhadap median/MAD hari-hari sebelumnya.")
    up = st.file_uploader("Unggah CSV postingan (kolom: date/timestamp, username, text)", type="csv", key="ew")
    issue = st.text_input("Filter isu / kata kunci (opsional)", key="ewissue")
    p1, p2 = st.columns(2)
    window = p1.slider("Jendela baseline (hari)", 3, 14, early_warning.WINDOW)
    z_thr = p2.slider("Ambang z-score", 2.0, 6.0, early_warning.Z_THRESH, 0.5)
    try:
        d = social.prepare(load_csv(up, data_file("posts_sample.csv")), issue)
        if d.empty:
            st.info("Tidak ada postingan yang cocok."); st.stop()
        res = early_warning.run_early_warning(d, window, z_thr)
    except ValueError as e:
        st.error(str(e)); st.stop()
    src = source_label(up, "posts_sample.csv")
    daily, al = res["daily"], res["alerts"]
    ss["analysis"]["ews"] = {"result": res, "source": src}
    for n in res["notes"]:
        st.warning(n)
    m1, m2, m3 = st.columns(3)
    m1.metric("Hari data", len(daily)); m2.metric("Peringatan", len(al))
    m3.metric("Tingkat tinggi", int((al.tingkat == "Tinggi").sum()) if len(al) else 0)
    fig = go.Figure(go.Scatter(x=daily["tanggal"], y=daily["volume"], mode="lines+markers", name="Volume", line=dict(color=theme.BLUE)))
    vol_al = al[al.jenis.str.startswith("Lonjakan")] if len(al) else al
    if len(vol_al):
        pts = daily[daily["tanggal"].dt.date.isin(set(vol_al["tanggal"]))]
        fig.add_trace(go.Scatter(x=pts["tanggal"], y=pts["volume"], mode="markers", name="Peringatan lonjakan",
                                 marker=dict(color=theme.RED, size=11, symbol="diamond")))
    fig.update_layout(title="Perkembangan isu: volume percakapan per hari", height=360)
    st.plotly_chart(fig, width="stretch")
    sent = daily.dropna(subset=["porsi_negatif"])
    st.plotly_chart(px.line(sent, x="tanggal", y="porsi_negatif", title="Tren porsi sentimen negatif", markers=True)
                    .update_yaxes(tickformat=".0%").update_layout(height=300), width="stretch")
    st.subheader("Peringatan yang terdeteksi")
    if al.empty:
        st.success("Tidak ada peringatan pada parameter ini.")
    else:
        st.dataframe(al, width="stretch", hide_index=True)
        if st.button("Simpan peringatan ke riwayat"):
            st.success(f"{db.save_alerts(al, src)} peringatan tersimpan.")
    with st.expander("Metode dan keterbatasan"):
        st.markdown("Nilai harian dibandingkan dengan **median** dan **MAD** hari-hari sebelumnya (robust z-score, batas bawah Poisson). "
                    "Peringatan berturut-turut ditandai *berlanjut*.")
        for x in res["limitations"]:
            st.markdown(f"- {x}")
    st.subheader("Riwayat peringatan")
    hist = db.load_alerts()
    st.dataframe(hist if len(hist) else pd.DataFrame({"info": ["Belum ada riwayat peringatan."]}), width="stretch", hide_index=True)

# ---------------------------------------------------------------- Network
elif page == "🕸️ Network Analysis":
    st.title("🕸️ Social Network Analysis")
    st.caption("Hubungan antar-akun dibentuk dari kemiripan teks unggahan dan kedekatan waktu. Hasilnya kandidat untuk **ditinjau**, "
               "bukan bukti bot atau operasi terkoordinasi.")
    up = st.file_uploader("Unggah CSV postingan (kolom: timestamp, username, text)", type="csv", key="net")
    n1, n2, n3 = st.columns(3)
    thr = n1.slider("Ambang kemiripan teks", 0.5, 1.0, 0.7, 0.05, key="nthr")
    win = n2.slider("Jendela kedekatan waktu (menit)", 1, 120, 15)
    alias = n3.checkbox("Samarkan nama akun", value=False)
    try:
        d = social.prepare(load_csv(up, data_file("posts_sample.csv")))
        G, info = st.cache_data(show_spinner="Membangun graf...")(network.build_graph)(d, thr, win)
    except ValueError as e:
        st.error(str(e)); st.stop()
    groups = network.review_groups(G, d)
    src = source_label(up, "posts_sample.csv")
    ss["analysis"]["net"] = {"G": G, "groups": groups, "source": src}
    if not info["has_time"]:
        st.warning("Kolom timestamp tidak ada: kedekatan waktu tidak dapat dianalisis, hanya kemiripan teks.")
    if info["capped"] or info["trimmed"]:
        st.warning("Data besar: sebagian unggahan dipangkas (maks. 20 unggahan per akun per klaster, 60 akun per klaster) agar tetap cepat.")
    m1, m2, m3 = st.columns(3)
    m1.metric("Akun terhubung", G.number_of_nodes()); m2.metric("Hubungan", G.number_of_edges()); m3.metric("Kelompok ditinjau", len(groups))
    st.plotly_chart(network.figure(G, alias), width="stretch")
    st.subheader("Kelompok aktivitas yang perlu ditinjau")
    if groups.empty:
        st.success("Tidak ada kelompok ≥3 akun pada ambang ini.")
    else:
        show = mask_df(groups, ["contoh_teks"])
        if alias:
            show["akun"] = show["akun"].map(lambda s: ", ".join(network.pseudonym(x.strip()) if x.strip() != "..." else "..." for x in s.replace(" ...", "").split(",")))
        st.dataframe(show, width="stretch", hide_index=True)
        st.caption("Prioritas hanya urutan peninjauan (porsi hubungan serempak & ukuran kelompok), bukan vonis.")
    with st.expander("Klaster teks yang mirip"):
        cl, _ = network.cluster_texts(d, thr)
        st.dataframe(mask_df(network.text_cluster_table(cl), ["contoh_teks"]), width="stretch", hide_index=True)
    with st.expander("Keterbatasan"):
        for x in explain.NETWORK_LIMITS:
            st.markdown(f"- {x}")

# ---------------------------------------------------------------- Analytics
elif page == "📈 Analytics":
    st.title("📈 Analytics & Evaluasi Model")
    st.subheader("🧪 Evaluasi model hoaks")
    src_mode = st.radio("Dataset evaluasi", ["Dataset contoh bawaan (sintetis)", "Unggah dataset berlabel (text,label)"], horizontal=True)
    try:
        if src_mode.startswith("Unggah"):
            up = st.file_uploader("CSV berlabel: kolom text, label (0 = bukan hoaks, 1 = hoaks)", type="csv", key="lab")
            if not up:
                st.info("Unggah dataset berlabel untuk dievaluasi."); st.stop()
            lab = evaluate.load_labeled(safe_read_csv(up)); note = f"dataset unggahan '{up.name}'"
        else:
            lab = evaluate.load_labeled(data_file("hoax_sample.csv")); note = "dataset contoh SINTETIS"
        ho = st.cache_data(show_spinner="Mengevaluasi...")(evaluate.holdout_evaluate)(lab)
        cv = st.cache_data(show_spinner=False)(evaluate.cross_validate)(lab)
        rb = st.cache_data(show_spinner=False)(evaluate.rule_based_evaluate)(lab)
    except ValueError as e:
        st.error(str(e)); st.stop()
    st.caption(f"Sumber: {note} · {ho['n']} contoh unik ({ho['n_train']} latih / {ho['n_test']} uji, stratified).")
    for w in ho["warnings"]:
        st.warning(w)
    k = st.columns(4)
    for col, name in zip(k, ["accuracy", "precision", "recall", "f1"]):
        col.metric(name.capitalize() if name != "f1" else "F1-score", f"{ho[name]:.2f}")
    c1, c2 = st.columns(2)
    cm = pd.DataFrame(ho["confusion"], index=["Aktual: bukan hoaks", "Aktual: hoaks"], columns=["Prediksi: bukan hoaks", "Prediksi: hoaks"])
    c1.plotly_chart(px.imshow(cm, text_auto=True, color_continuous_scale="Blues", title="Confusion matrix (data uji)"), width="stretch")
    bal = ho["balance"]
    c2.plotly_chart(px.bar(x=["Bukan hoaks", "Hoaks"], y=[bal["bukan_hoaks"], bal["hoaks"]], labels={"x": "Kelas", "y": "Jumlah"},
                           title=f"Keseimbangan kelas (rasio minoritas {bal['rasio_minoritas']:.2f})"), width="stretch")
    st.caption(f"Cross-validation {cv['folds']}-fold: F1 {cv['f1']:.2f} · Indikator aturan saja (ambang {rb['threshold']:.0f}): "
               f"F1 {rb['f1']:.2f} · Brier score hold-out: {ho['brier']:.3f}. {ho['catatan_brier']}")
    with st.expander("Dokumentasi keterbatasan model"):
        st.markdown("- Model TF-IDF + Logistic Regression dilatih pada dataset contoh sintetis; **tidak ada klaim akurasi pada data nyata**.\n"
                    "- Skor ML **tidak terkalibrasi**; jangan dibaca sebagai probabilitas.\n"
                    "- Untuk klaim akurasi yang layak, evaluasi dengan dataset berlabel nyata (mis. TurnBackHoax) dan data uji terpisah.")
    st.divider()
    df = db.load()
    if df.empty:
        st.info("Belum ada data analisis tersimpan."); st.stop()
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.histogram(df, x="level", color="level", color_discrete_map=COLORS, title="Distribusi tingkat risiko"), width="stretch")
    c2.plotly_chart(px.box(df, x="module", y="score", title="Sebaran skor per modul"), width="stretch")

# ---------------------------------------------------------------- Reports
else:
    st.title("📑 Reports")
    df = db.load()
    st.dataframe(df[["ts", "module", "subject", "score", "level"]] if len(df) else df, width="stretch")
    a = ss["analysis"]
    done = [n for k, n in [("hoax", "Hoax"), ("bot", "Bot"), ("social", "Social"), ("ews", "Early Warning"), ("net", "Network")] if k in a]
    st.caption("Ringkasan sesi pada laporan: " + (", ".join(done) if done else "belum ada (jalankan analisis pada menu lain)") + " · ditambah riwayat tersimpan.")
    try:
        pdf = report.build_pdf(df, session_report.assemble(a))
        st.download_button("⬇️ Unduh laporan PDF", pdf, "laporan_nexguard_ai.pdf", "application/pdf")
    except Exception:
        st.error("Laporan PDF gagal dibuat. Coba jalankan ulang analisis, lalu ulangi.")
    c1, c2 = st.columns(2)
    if c1.button("Hapus semua riwayat"):
        db.clear(); st.rerun()
    st.warning(DISCLAIMER)