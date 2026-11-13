"""Tampilan Streamlit untuk Bot Analyzer V6: kartu statistik, tab investigasi, grafik Plotly interaktif, validasi, dan ekspor."""
import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import bot_investigation as bi

COLORS = {"Tinggi": "#ff4d4d", "Sedang": "#ffb020", "Rendah": "#00e676", "Data Tidak Cukup": "#8a97a8"}
KINDS = {  # kunci -> (label, deskripsi, warna)
    "sample": ("DATA SIMULASI", "Data contoh bawaan (sintetis), bukan data nyata.", "#ffb020"),
    "real": ("DATA ASLI", "Data yang dinyatakan pengguna sebagai hasil pengumpulan nyata; sumber dan metode tercatat.", "#00e676"),
    "sim": ("DATA SIMULASI", "Data unggahan yang dinyatakan pengguna sebagai simulasi atau uji.", "#ffb020"),
    "unset": ("DATA BELUM DIVERIFIKASI", "Jenis data belum ditetapkan; hasil tidak boleh disajikan sebagai data nyata.", "#8a97a8"),
}
KIND_CHOICES = ["Belum diverifikasi", "Data asli (hasil pengumpulan)", "Data simulasi / uji"]
CSS = """
<style>
.inv-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin: 6px 0 14px 0; }
@media (max-width: 1100px) { .inv-grid { grid-template-columns: repeat(3, 1fr); } }
.inv-card { background: rgba(10,26,18,.62); border: 1px solid rgba(0,230,118,.18); border-left: 4px solid var(--c); border-radius: 8px;
            padding: 10px 14px; backdrop-filter: blur(6px); }
.inv-l { font-family: 'Share Tech Mono', Consolas, monospace; font-size: .68rem; letter-spacing: 2px; color: #9fb7a4; text-transform: uppercase; }
.inv-v { font-family: 'Rajdhani', sans-serif; font-size: 2rem; font-weight: 700; color: var(--c); line-height: 1.15; }
.inv-s { font-size: .74rem; color: #8aa190; }
.inv-badge { display: inline-block; font-family: 'Share Tech Mono', Consolas, monospace; letter-spacing: 2px; font-size: .78rem;
             padding: 4px 12px; border-radius: 4px; border: 1px solid var(--c); color: var(--c); background: rgba(255,255,255,.03); }
.inv-box { background: rgba(10,26,18,.62); border: 1px solid rgba(138,154,91,.45); border-left: 4px solid #8a9a5b; border-radius: 8px;
           padding: 14px 18px; line-height: 1.7; color: #dbe6dc; }
.inv-note { font-size: .78rem; color: #8aa190; }
.inv-ok { font-family: 'Rajdhani', sans-serif; font-weight: 700; letter-spacing: 3px; font-size: 1.05rem; color: #00e676; margin: 10px 0 6px 0; }
.inv-stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 4px 0 14px 0; }
.inv-stat { flex: 1 1 230px; background: rgba(10,26,18,.62); border: 1px solid var(--c); border-radius: 8px; padding: 8px 12px; }
.inv-stat .c { font-family: 'Share Tech Mono', Consolas, monospace; letter-spacing: 2px; font-size: .8rem; color: var(--c); font-weight: 700; }
.inv-stat .l { font-family: 'Rajdhani', sans-serif; font-weight: 700; letter-spacing: 1px; color: #e8f1ea; }
.inv-stat .d { font-size: .74rem; color: #8aa190; }
.inv-exec { background: rgba(10,26,18,.70); border: 1px solid rgba(0,230,118,.20); border-left: 6px solid var(--c); border-radius: 10px; padding: 14px 20px; margin: 4px 0 12px 0; }
.inv-exec .k { font-family: 'Share Tech Mono', Consolas, monospace; letter-spacing: 3px; font-size: .74rem; color: #9fb7a4; }
.inv-exec .lv { font-family: 'Rajdhani', sans-serif; font-weight: 700; letter-spacing: 4px; font-size: 2.2rem; color: var(--c); line-height: 1.1; }
.inv-exec .h { color: #dbe6dc; line-height: 1.6; }
.inv-sec { font-family: 'Share Tech Mono', Consolas, monospace; letter-spacing: 3px; font-size: .8rem; color: #c5e1a5; margin: 14px 0 4px 0; text-transform: uppercase; }
.inv-ok2 { color: #00e676; } .inv-warn2 { color: #ffb020; }
</style>
"""


# ----------------------------------------------------------------------------- pilihan jenis data
def resolve_kind(choice: str, sumber: str = "", metode: str = "", pernyataan: bool = False) -> str:
    """Tetapkan jenis data dari pilihan pengguna, bukan dari nama file. DATA ASLI hanya bila sumber, metode, dan pernyataan terisi."""
    if choice == "Data simulasi / uji":
        return "sim"
    if choice == "Data asli (hasil pengumpulan)":
        return "real" if (len(sumber.strip()) >= 5 and len(metode.strip()) >= 5 and pernyataan) else "unset"
    return "unset"


def data_kind_selector(is_upload: bool, key: str = "bi_kind"):
    """Data bawaan selalu 'sample'. Data unggahan: pengguna memilih asli, simulasi/uji, atau belum diverifikasi.
    Memilih data asli mewajibkan sumber, metode pengumpulan, dan pernyataan. Mengembalikan (kind, provenance)."""
    if not is_upload:
        return "sample", {}
    pick = st.radio("Jenis data yang diunggah", KIND_CHOICES, horizontal=True, key=key,
                    help="Dipakai untuk label pada halaman dan laporan. Jenis data tidak ditentukan dari nama file.")
    prov, sumber, metode, ok = {}, "", "", False
    if pick == KIND_CHOICES[1]:
        c1, c2 = st.columns(2)
        sumber = c1.text_input("Sumber data", key=f"{key}_src", placeholder="contoh: ekspor resmi platform X, periode 1-14 Okt 2026")
        metode = c2.text_input("Metode pengumpulan", key=f"{key}_met", placeholder="contoh: API resmi sesuai ketentuan layanan")
        ok = st.checkbox("Saya menyatakan data ini dikumpulkan secara sah dan keterangan di atas benar.", key=f"{key}_ok")
        prov = {"sumber": sumber.strip(), "metode": metode.strip()}
    kind = resolve_kind(pick, sumber, metode, ok)
    if pick == KIND_CHOICES[1] and kind == "unset":
        st.warning("DATA BELUM DIVERIFIKASI: lengkapi sumber, metode pengumpulan, dan pernyataan untuk menetapkan DATA ASLI.")
    return kind, (prov if kind == "real" else {})


# ----------------------------------------------------------------------------- grafik Plotly
def _dark(fig, height=340, title=None):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=height,
                      margin=dict(l=10, r=10, t=50 if title else 20, b=10), title=title, legend=dict(orientation="h", y=-0.2))
    return fig


def fig_risk(res):
    cnt = res["level"].value_counts().reindex(bi.LEVELS, fill_value=0).reset_index()
    cnt.columns = ["Kategori", "Jumlah akun"]
    fig = px.bar(cnt, x="Kategori", y="Jumlah akun", color="Kategori", color_discrete_map=COLORS, text="Jumlah akun")
    fig.update_traces(textposition="outside")
    return _dark(fig, 320, "Distribusi tingkat risiko akun")


def _bucket(p):
    span = (p["ts"].max() - p["ts"].min()).total_seconds() / 86400
    return ("h", "jam") if span <= 3 else ("D", "hari")


def fig_activity(p):
    fr, unit = _bucket(p)
    t = p.assign(waktu=p["ts"].dt.floor(fr)).groupby(["waktu", "level"]).size().reset_index(name="Postingan")
    fig = px.line(t, x="waktu", y="Postingan", color="level", color_discrete_map=COLORS, markers=True)
    return _dark(fig, 340, f"Aktivitas posting per {unit} menurut kategori akun")


def fig_top(inv, name, n=15):
    f = inv["feats"].merge(inv["res"][["username", "level"]], on="username").sort_values("n_posts", ascending=False).head(n)
    f = f.assign(Akun=f["username"].map(name))
    fig = px.bar(f[::-1], x="n_posts", y="Akun", color="level", color_discrete_map=COLORS, orientation="h",
                 labels={"n_posts": "Jumlah postingan", "level": "Kategori"})
    return _dark(fig, 340, f"{n} akun paling aktif")


def fig_repeat(p):
    t = p.assign(Jenis=np.where(p["is_repeat"], "Berulang", "Unik")).groupby(["level", "Jenis"]).size().reset_index(name="Postingan")
    fig = px.bar(t, x="level", y="Postingan", color="Jenis", barmode="stack", color_discrete_map={"Unik": "#4da3ff", "Berulang": "#ff4d4d"},
                 category_orders={"level": [l for l in bi.LEVELS if l in set(p["level"])]}, labels={"level": "Kategori akun"})
    return _dark(fig, 340, "Postingan unik vs berulang")


def fig_trend(p):
    fr, unit = _bucket(p)
    t = p.assign(waktu=p["ts"].dt.floor(fr))
    a = t[t["level"].isin(["Tinggi", "Sedang"])].groupby("waktu").size().reset_index(name="Postingan")
    b = t[t["sync"]].groupby("waktu").size().reset_index(name="Postingan")
    fig = go.Figure()
    if len(a):
        fig.add_trace(go.Scatter(x=a["waktu"], y=a["Postingan"], mode="lines+markers", name="Akun berkategori Tinggi/Sedang", line=dict(color="#ffb020")))
    if len(b):
        fig.add_trace(go.Scatter(x=b["waktu"], y=b["Postingan"], mode="lines+markers", name="Posting serempak", line=dict(color="#ff4d4d")))
    if not len(a) and not len(b):
        fig.add_annotation(text="Tidak ada aktivitas mencurigakan pada parameter ini.", showarrow=False)
    return _dark(fig, 340, f"Tren aktivitas mencurigakan per {unit}")


def fig_network(inv, use_alias=False, max_nodes=300):
    """Graf antar-akun interaktif: warna = kategori risiko, ukuran = skor, garis merah = teks mirip + serempak."""
    G, res = inv["G"], inv["res"].set_index("username")
    name = (lambda n: bi.alias(n)) if use_alias else (lambda n: str(n))
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=600,
                      margin=dict(l=10, r=10, t=40, b=10), xaxis=dict(visible=False), yaxis=dict(visible=False),
                      legend=dict(orientation="h", y=-0.05), title="Hubungan antar-akun (teks mirip dan waktu berdekatan)")
    if G.number_of_nodes() == 0:
        fig.add_annotation(text="Tidak ada hubungan antar-akun pada ambang yang dipilih.", showarrow=False, font=dict(size=15))
        return fig
    H = G if G.number_of_nodes() <= max_nodes else G.subgraph(sorted(G.nodes, key=G.degree, reverse=True)[:max_nodes])
    pos = nx.spring_layout(H, seed=42, weight="weight", k=1.2 / max(np.sqrt(H.number_of_nodes()), 1))
    for sync, color, label in ((False, "rgba(120,160,220,.30)", "Teks mirip"), (True, "rgba(255,77,77,.55)", "Teks mirip + serempak")):
        xs, ys = [], []
        for a, b, at in H.edges(data=True):
            if (at.get("serempak", 0) > 0) == sync:
                xs += [pos[a][0], pos[b][0], None]
                ys += [pos[a][1], pos[b][1], None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=1.1, color=color), hoverinfo="skip", name=label))
    for lv in bi.LEVELS:
        nodes = [n for n in H.nodes if (res["level"].get(n, "Rendah") == lv)]
        if not nodes:
            continue
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers", name=f"Akun {lv}",
            marker=dict(size=[9 + 0.12 * float(res["skor_bot"].get(n, 0)) for n in nodes], color=COLORS[lv], line=dict(width=1, color="#06100b")),
            text=[f"{name(n)}<br>skor: {int(res['skor_bot'].get(n, 0))} ({lv})<br>koneksi: {H.degree(n)}" for n in nodes], hoverinfo="text"))
    return fig


def fig_account(tl: pd.DataFrame, title: str):
    """Aktivitas satu akun berdasarkan waktu: jumlah posting per jam/hari, dengan posting berulang dan serempak ditandai."""
    fig = go.Figure()
    if tl.empty:
        fig.add_annotation(text="Tidak ada postingan.", showarrow=False)
        return _dark(fig, 300, title)
    span = (tl["ts"].max() - tl["ts"].min()).total_seconds() / 86400
    fr, unit = ("h", "jam") if span <= 3 else ("D", "hari")
    t = tl.assign(waktu=tl["ts"].dt.floor(fr))
    a = t.groupby("waktu").size()
    b = t[t["is_repeat"]].groupby("waktu").size().reindex(a.index, fill_value=0)
    c = t[t["sync"]].groupby("waktu").size().reindex(a.index, fill_value=0)
    fig.add_trace(go.Bar(x=a.index, y=a.values, name="Semua postingan", marker_color="#4da3ff"))
    fig.add_trace(go.Scatter(x=b.index, y=b.values, mode="lines+markers", name="Berulang", line=dict(color="#ffb020")))
    fig.add_trace(go.Scatter(x=c.index, y=c.values, mode="lines+markers", name="Serempak", line=dict(color="#ff4d4d")))
    fig.update_layout(yaxis_title=f"Postingan per {unit}")
    return _dark(fig, 320, title)


def fig_spread(sp: pd.DataFrame, name):
    """Pola penyebaran klaster: kapan setiap akun pertama kali memposting konten klaster."""
    fig = go.Figure()
    if sp.empty:
        fig.add_annotation(text="Tidak ada data penyebaran.", showarrow=False)
        return _dark(fig, 320)
    fig.add_trace(go.Scatter(x=sp["muncul_pertama"], y=sp["urutan"], mode="lines+markers", line=dict(color="rgba(255,145,0,.45)"),
                             marker=dict(size=10, color="#ff9100"), text=[f"{name(a)}<br>selang {s:.0f} dtk dari inisiator" for a, s in zip(sp["akun"], sp["selang_detik"])],
                             hoverinfo="text", name="Kemunculan pertama"))
    fig.update_layout(yaxis_title="Urutan akun", xaxis_title="Waktu kemunculan pertama")
    return _dark(fig, 320, "Pola penyebaran klaster (urutan kemunculan akun)")


@st.cache_data(show_spinner="Menyusun jaringan...")
def _network_cached(sig: str, use_alias: bool, _inv: dict):
    return fig_network(_inv, use_alias)


# ----------------------------------------------------------------------------- komponen
def _cards(meta, summ):
    c = summ["counts"]
    items = [("Akun dianalisis", f"{meta['n_accounts']:,}", f"{summ['n_eval']} dinilai · {meta['n_insufficient']} data tidak cukup", "#4da3ff"),
             ("Total postingan", f"{meta['n_posts']:,}", f"{meta['span_days']:.1f} hari data", "#4da3ff"),
             ("Risiko tinggi", c["Tinggi"], f"{summ['pct_high']:.0%} dari {summ['n_eval']} akun dinilai", COLORS["Tinggi"]),
             ("Risiko sedang", c["Sedang"], "dalam pemantauan", COLORS["Sedang"]),
             ("Risiko rendah", c["Rendah"], "tanpa anomali signifikan", COLORS["Rendah"]),
             ("Anomali aktivitas", f"{summ['pct_susp']:.0%}", f"Tinggi + Sedang dari {summ['n_eval']} akun", "#c5e1a5")]
    html = '<div class="inv-grid">' + "".join(
        f'<div class="inv-card" style="--c:{col}"><div class="inv-l">{l}</div><div class="inv-v">{v}</div><div class="inv-s">{s}</div></div>'
        for l, v, s, col in items) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _table_view(tbl, use_alias):
    t = tbl.copy()
    if use_alias:
        t["username"] = t["username"].map(bi.alias)
    return t[["username", "total_postingan", "rata_interval", "persen_pengulangan", "skor_risiko", "kategori", "prioritas", "alasan"]]


def render_waiting():
    """Tampilan saat belum ada data: tidak ada hasil yang ditampilkan sebelum data dipilih."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="inv-stats"><div class="inv-stat" style="--c:#8a97a8"><div class="c">AWAITING DATA</div>'
                '<div class="l">MENUNGGU DATA</div><div class="d">Unggah CSV postingan (kolom: timestamp, username, text) untuk memulai analisis. '
                'Belum ada hasil yang ditampilkan.</div></div></div>', unsafe_allow_html=True)


def _chips(statuses):
    return '<div class="inv-stats">' + "".join(
        f'<div class="inv-stat" style="--c:{x["color"]}"><div class="c">{x["code"]}</div><div class="l">{x["label"]}</div>'
        f'<div class="d">{x["desc"]}</div></div>' for x in statuses) + "</div>"


def _exec_summary(ex, key):
    st.subheader("Executive Intelligence Summary")
    lvl = ex["level"] or "TIDAK TERSEDIA"
    st.markdown(f'<div class="inv-exec" style="--c:{ex["level_color"]}"><div class="k">CYBER INTELLIGENCE ASSESSMENT</div>'
                f'<div class="lv">{lvl}</div><div class="h">{ex["headline"]}<br><b>Alasan penetapan:</b> {ex["reason"]}</div></div>', unsafe_allow_html=True)
    a, b = st.columns([3, 2])
    with a:
        st.markdown('<div class="inv-sec">Temuan terukur</div>', unsafe_allow_html=True)
        for f in ex["findings"]:
            st.markdown(f"- {f}")
    with b:
        st.markdown('<div class="inv-sec">THREAT INDICATORS IDENTIFIED</div>', unsafe_allow_html=True)
        if ex["support"]:
            st.dataframe(pd.DataFrame([(n, c, f"{p:.0%}") for n, c, p in ex["support"]], columns=["Indikator", "Akun aktif", "% akun dinilai"]),
                         width="stretch", hide_index=True)
        else:
            st.caption("Tidak ada indikator aktif pada akun yang dinilai.")
    st.markdown('<div class="inv-sec">INVESTIGATION PRIORITY</div>', unsafe_allow_html=True)
    pr = ex["priorities"]
    st.markdown(f"**PRIORITAS INVESTIGASI TINGGI: {pr['TINGGI']} akun** · Sedang: {pr['SEDANG']} · Rendah: {pr['RENDAH']}")
    st.caption(ex["priority_note"])
    with st.expander("Kriteria pemilihan prioritas"):
        for c in ex["priority_criteria"]:
            st.markdown(f"- {c}")
    if ex["top"]:
        st.dataframe(pd.DataFrame([(t["username"], t["skor"], t["kategori"], t["prioritas"], t["dasar"]) for t in ex["top"]],
                                  columns=["Akun", "Skor", "Kategori", "Prioritas", "Dasar klasifikasi (3 indikator teratas)"]),
                     width="stretch", hide_index=True, column_config={"Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100, format="%d")})
    else:
        st.caption("Tidak ada akun yang memerlukan prioritas investigasi.")
    st.markdown('<div class="inv-sec">Status validasi</div>', unsafe_allow_html=True)
    v1, v2 = st.columns(2)
    with v1:
        st.markdown('<span class="inv-ok2"><b>TERUKUR</b></span>', unsafe_allow_html=True)
        for x in ex["measured"]:
            st.markdown(f"- {x}")
    with v2:
        st.markdown('<span class="inv-warn2"><b>BELUM TERVALIDASI</b></span>', unsafe_allow_html=True)
        for x in ex["unvalidated"]:
            st.markdown(f"- {x}")
    cf = ex["confidence"]
    st.markdown('<div class="inv-sec">Tingkat keyakinan klasifikasi</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="inv-exec" style="--c:{"#00e676" if cf["tersedia"] else "#8a97a8"}"><div class="lv" style="font-size:1.5rem">{cf["label"]}</div>'
                f'<div class="h">{cf["detail"]}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="inv-sec">Rencana tindak lanjut</div>', unsafe_allow_html=True)
    for r in ex["recommendations"]:
        st.markdown(f"- {r}")


def render(inv: dict, source: str, kind: str, mask=lambda x: x, key: str = "bi", prov: dict = None):
    """Tampilkan seluruh halaman investigasi. `mask` menyamarkan data pribadi pada teks contoh."""
    meta, res = inv["meta"], inv["res"]
    summ = bi.summarize(inv)
    st.markdown(CSS, unsafe_allow_html=True)
    label, desc, col = KINDS[kind]
    st.markdown(f'<span class="inv-badge" style="--c:{col}">{label}</span> <span class="inv-note">&nbsp;{desc} Sumber: {source}</span>', unsafe_allow_html=True)
    if kind == "real" and prov:
        st.caption(f"Sumber data: {prov.get('sumber', '-')} · Metode pengumpulan: {prov.get('metode', '-')} (berdasarkan pernyataan pengguna; sistem tidak dapat memverifikasi keaslian data).")

    # validasi dengan data berlabel (opsional); hasilnya dipakai pada ringkasan eksekutif dan tab validasi
    ev, ev_err = None, None
    with st.expander("Validasi dengan data berlabel (opsional)"):
        st.caption("Unggah CSV dengan kolom `username` dan `label` (1/0 atau bot/bukan_bot). Sistem membandingkan label dengan kategori hasil analisis "
                   "dan menghitung presisi terukur. Tingkat keyakinan klasifikasi hanya ditampilkan setelah pengujian ini.")
        up_l = st.file_uploader("CSV label akun", type="csv", key=f"{key}_labels")
        pos = st.selectbox("Anggap prediksi 'bot' bila kategori", ["Tinggi", "Sedang atau Tinggi"], key=f"{key}_pos")
        if up_l is not None:
            try:
                ev = bi.evaluate_labels(res, pd.read_csv(up_l), "Tinggi" if pos == "Tinggi" else "Sedang")
            except Exception as ex_:
                ev_err = str(ex_)
        if ev_err:
            st.error(f"Gagal membaca file label: {ev_err}")
    ex = bi.executive_summary(inv, ev)

    ok = ex["statuses"][0]["code"] == "ANALYSIS COMPLETED"
    st.markdown(f'<div class="inv-ok">{"DETEKSI BERHASIL · ANALISIS SELESAI" if ok else "DATA TIDAK MEMADAI · ANALISIS TIDAK DAPAT DISELESAIKAN"}</div>', unsafe_allow_html=True)
    st.markdown(_chips(ex["statuses"]), unsafe_allow_html=True)
    if meta["peringatan"]:
        with st.expander(f"Catatan kualitas data ({len(meta['peringatan'])})", expanded=False):
            for w in meta["peringatan"]:
                st.markdown(f"- {w}")
    _cards(meta, summ)
    tabs = st.tabs(["🛰️ Executive Summary", "🧾 Investigasi akun", "🔗 Klaster aktivitas", "📈 Analitik", "🧪 Metodologi dan validasi", "⬇️ Ekspor"])
    tbl = bi.investigation_table(inv)

    with tabs[0]:
        a, b = st.columns([3, 2])
        with a:
            _exec_summary(ex, key)
        with b:
            st.plotly_chart(fig_risk(res), width="stretch", key=f"{key}_risk")
            st.caption("Ringkasan disusun otomatis dari angka hasil perhitungan; setiap angka dan kalimat berubah mengikuti CSV yang dianalisis.")

    with tabs[1]:
        st.subheader("Tabel investigasi akun")
        f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
        q = f1.text_input("Cari username", key=f"{key}_q", placeholder="ketik sebagian nama akun")
        cats = f2.multiselect("Kategori risiko", bi.LEVELS, default=bi.LEVELS, key=f"{key}_cat")
        order = f3.selectbox("Urutkan", ["Skor tertinggi", "Skor terendah", "Postingan terbanyak", "Jeda rata-rata terpendek", "Pengulangan tertinggi"], key=f"{key}_ord")
        use_alias = f4.checkbox("Samarkan nama", key=f"{key}_alias", help="Ganti username dengan alias pada tampilan dan laporan.")
        v = tbl[tbl["kategori"].isin(cats)]
        if q.strip():
            v = v[v["username"].str.contains(q.strip(), case=False, regex=False)]
        sort = {"Skor tertinggi": ("skor_risiko", False), "Skor terendah": ("skor_risiko", True), "Postingan terbanyak": ("total_postingan", False),
                "Jeda rata-rata terpendek": ("rata_interval_detik", True), "Pengulangan tertinggi": ("persen_pengulangan", False)}[order]
        v = v.sort_values(sort[0], ascending=sort[1], kind="stable", na_position="last").reset_index(drop=True)
        st.caption(f"{len(v)} dari {len(tbl)} akun ditampilkan.")
        st.dataframe(_table_view(v, use_alias), width="stretch", hide_index=True, column_config={
            "username": "Username", "total_postingan": "Total postingan", "rata_interval": "Rata-rata interval",
            "persen_pengulangan": st.column_config.NumberColumn("Pengulangan konten (%)", format="%.0f"),
            "skor_risiko": st.column_config.ProgressColumn("Skor risiko", min_value=0, max_value=100, format="%d"),
            "kategori": "Kategori", "prioritas": "Prioritas investigasi", "alasan": st.column_config.TextColumn("Alasan klasifikasi", width="large")})
        if len(v):
            st.markdown("---")
            st.subheader("Panel investigasi akun")
            who = st.selectbox("Pilih username", v["username"].tolist()[:500], key=f"{key}_who", format_func=(bi.alias if use_alias else str))
            e, pf = bi.explain_account(inv, who), bi.account_profile(inv, who)
            shown = bi.alias(who) if use_alias else who
            col_l = COLORS[pf["level"]]
            st.markdown(f'<div class="inv-box" style="border-left-color:{col_l}"><b>{shown}</b> · {pf["level"].upper()} · skor {pf["skor"]}/100<br>'
                        f'{e["ringkasan"].replace(who, shown)}<br><span class="inv-note"><b>Status validasi:</b> {e["status_validasi"]}</span></div>', unsafe_allow_html=True)
            m1 = st.columns(5)
            m1[0].metric("Jumlah postingan", f"{pf['n_posts']:,}")
            m1[1].metric("Skor risiko", f"{pf['skor']}/100")
            m1[2].metric("Kategori", pf["level"])
            m1[3].metric("Investigation priority", pf["prioritas"])
            m1[4].metric("Frekuensi", f"{pf['posts_per_day']:.0f}/hari", f"median dataset {pf['median_ppd']:.0f}/hari", delta_color="off")
            m2 = st.columns(3)
            m2[0].metric("Pengulangan konten", f"{pf['pct_repeat']:.0%}", f"median dataset {pf['median_repeat']:.0%}", delta_color="off")
            m2[1].metric("Mirip dengan akun lain", f"{pf['pct_similar']:.0%}")
            m2[2].metric("Posting serempak", f"{pf['pct_sync']:.0%}")
            st.plotly_chart(fig_account(pf["timeline"], f"Aktivitas {shown} berdasarkan waktu"), width="stretch", key=f"{key}_acct")
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown('<div class="inv-sec">Indikator yang menaikkan risiko (bukti terukur)</div>', unsafe_allow_html=True)
                if e["bukti"]:
                    st.dataframe(pd.DataFrame([(b_["indikator"], b_["nilai"], b_["ambang"], f"{b_['poin']:.1f} / {b_['maks']}", "AKTIF" if b_["aktif"] else "-")
                                               for b_ in e["bukti"]], columns=["Indikator", "Nilai terukur", "Ambang aktif", "Poin", "Status"]),
                                 width="stretch", hide_index=True)
                else:
                    st.caption("Tidak ada bukti terukur: data tidak memadai.")
                st.markdown('<div class="inv-sec">Pola aktivitas</div>', unsafe_allow_html=True)
                for x in e["pola"]:
                    st.markdown(f"- {x}")
            with c2:
                st.markdown('<div class="inv-sec">Akun dengan aktivitas serupa</div>', unsafe_allow_html=True)
                if pf["related"]:
                    st.dataframe(pd.DataFrame([((bi.alias(a_) if use_alias else a_), w_, s_) for a_, w_, s_, _ in pf["related"]],
                                              columns=["Akun", "Teks mirip", "Serempak"]), width="stretch", hide_index=True)
                else:
                    st.caption("Tidak ada akun terhubung pada ambang yang dipilih.")
                st.markdown('<div class="inv-sec">Rekomendasi pemeriksaan lanjutan</div>', unsafe_allow_html=True)
                for x in e["rekomendasi"]:
                    st.markdown(f"- {x}")
                for x in e["catatan"]:
                    st.caption(x)

    with tabs[2]:
        st.subheader("Klaster aktivitas dan indikator koordinasi")
        st.caption("Indikator dihitung dari: (1) teks identik atau sangat mirip dari beberapa akun, (2) waktu posting berdekatan, "
                   "(3) pola berulang pada banyak akun, dan (4) tagar yang sama.")
        cl, G = inv["clusters"], inv["G"]
        sm = bi.summarize(inv)
        if sm["n_coord"]:
            st.markdown(f'<span class="inv-badge" style="--c:#ff9100">COORDINATED ACTIVITY IDENTIFIED · {sm["n_coord"]} klaster terkoordinasi</span>', unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Klaster teridentifikasi", len(cl))
        m2.metric("Terkoordinasi", sm["n_coord"])
        m3.metric("Indikasi sebagian", sm["n_partial"])
        m4.metric("Akun terhubung", G.number_of_nodes())
        m5.metric("Hubungan antar-akun", G.number_of_edges())
        st.caption(
            f"Klaster dibentuk berdasarkan kemiripan teks lintas akun. "
            f"Aktivitas serempak dihitung berdasarkan kemunculan posting "
            f"dalam jendela {meta['window_min']} menit. "
            "Temuan ini merupakan indikator untuk pemeriksaan lanjutan, bukan bukti koordinasi."
        )

        if cl.empty:
            st.success(
                f"Tidak ada klaster teks mirip lintas akun "
                f"pada ambang kemiripan {meta['threshold']:.2f}."
            )
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Klaster teks mirip", len(cl))
            m2.metric("Klaster serempak", int(cl["serempak"].sum()))
            m3.metric("Klaster tidak serempak", int((~cl["serempak"]).sum()))

            yn = {True: "Ya", False: "Tidak"}
            show = cl.copy()
            show["contoh_teks"] = show["contoh_teks"].map(mask)
            show["serempak"] = show["serempak"].map(yn)

            st.dataframe(
                show[[
                    "klaster", "contoh_teks", "jumlah_akun",
                    "jumlah_post", "akun_serempak", "serempak",
                    "mulai", "selesai", "akun"
                ]],
                width="stretch",
                hide_index=True,
                column_config={
                    "klaster": "ID Klaster",
                    "contoh_teks": "Contoh teks",
                    "jumlah_akun": "Akun",
                    "jumlah_post": "Postingan",
                    "akun_serempak": "Akun serempak",
                    "serempak": "Serempak",
                    "mulai": "Mulai",
                    "selesai": "Selesai",
                    "akun": "Akun terlibat"
                }
            )
        if meta["has_tags"]:
            st.markdown('<div class="inv-sec">Tagar yang dipakai banyak akun</div>', unsafe_allow_html=True)
            if len(inv["tags"]):
                st.dataframe(inv["tags"], width="stretch", hide_index=True,
                             column_config={"tagar": "Tagar", "jumlah_akun": "Akun", "jumlah_post": "Postingan"})
            else:
                st.caption(f"Tidak ada tagar yang dipakai >= {bi.TAG_MIN_ACCOUNTS} akun.")
        else:
            st.caption("Tidak ada tagar (#) pada teks; indikator tagar tidak dihitung.")
        alias_net = st.checkbox("Samarkan nama akun pada jaringan", key=f"{key}_alias_net")
        st.plotly_chart(_network_cached(meta["sig"], alias_net, inv), width="stretch", key=f"{key}_net")
        st.caption("Merah = teks mirip dan diposting berdekatan; biru = teks mirip. Warna titik = kategori risiko, ukuran = skor.")

    with tabs[3]:
        st.subheader("Dashboard analitik")
        p = inv["posts"]
        r1, r2 = st.columns(2)
        r1.plotly_chart(fig_risk(res), width="stretch", key=f"{key}_risk2")
        r2.plotly_chart(fig_activity(p), width="stretch", key=f"{key}_act")
        r3, r4 = st.columns(2)
        r3.plotly_chart(fig_top(inv, str), width="stretch", key=f"{key}_top")
        r4.plotly_chart(fig_repeat(p), width="stretch", key=f"{key}_rep")
        r5, r6 = st.columns(2)
        r5.plotly_chart(fig_trend(p), width="stretch", key=f"{key}_trend")
        r6.plotly_chart(_network_cached(meta["sig"], False, inv), width="stretch", key=f"{key}_net2")
        n_rep, n_all = int(p["is_repeat"].sum()), len(p)
        st.caption(f"Postingan berulang (teks yang sama muncul lebih dari sekali pada data): {n_rep:,} dari {n_all:,} ({n_rep / n_all:.0%}).")

    with tabs[4]:
        st.subheader("Metodologi skor risiko")
        ind = pd.DataFrame([{"Indikator": i["nama"], "Bobot maks": i["maks"],
                             "Nilai 0 poin": i["hi"] if i["inv"] else i["lo"], "Nilai poin penuh": i["lo"] if i["inv"] else i["hi"],
                             "Aktif bila poin >=": round(bi.ACTIVE_RATIO * i["maks"], 1)} for i in bi.INDICATORS])
        st.dataframe(ind, width="stretch", hide_index=True)
        st.markdown(f"- Skor = jumlah poin indikator yang tersedia dibagi bobot maksimum yang tersedia, dikali 100. Tidak ada angka acak atau hasil bawaan.\n"
                    f"- Kategori: **Rendah** < {bi.THRESH_MID}, **Sedang** {bi.THRESH_MID}-{bi.THRESH_HIGH - 1}, **Tinggi** >= {bi.THRESH_HIGH}.\n"
                    f"- Kategori Tinggi mensyaratkan minimal {bi.MIN_ACTIVE_HIGH} indikator aktif dan Sedang minimal {bi.MIN_ACTIVE_MID}; klasifikasi tidak ditentukan oleh satu indikator.\n"
                    f"- Akun dengan kurang dari {bi.MIN_POSTS} postingan berstatus DATA TIDAK CUKUP dan tidak diklasifikasikan; persentase dihitung dari akun berdata memadai saja.\n"
                    f"- Frekuensi posting menyumbang paling banyak {bi.IND['freq']['maks']} dari 100 poin; aktivitas tinggi saja tidak menghasilkan kategori Tinggi.\n"
                    f"- Klaster dibentuk berdasarkan kemiripan teks lintas akun. Aktivitas serempak dihitung berdasarkan waktu posting dalam jendela yang ditentukan.\n"
                    f"- Klaster teks mirip atau posting serempak merupakan indikator pemeriksaan lanjutan, bukan bukti koordinasi, otomatisasi, atau identitas bot.\n"
                    f"- Prioritas investigasi TINGGI: kategori Tinggi dengan posting serempak atau skor >= 80. SEDANG: kategori Tinggi lainnya, atau Sedang dengan posting serempak. "
                    f"RENDAH: kategori Sedang lainnya.\n"
                    f"- Tingkat risiko keseluruhan: KRITIS bila >= 30% akun dinilai berkategori Tinggi; TINGGI bila >= 15% (atau klaster terkoordinasi dengan >= 3 akun Tinggi); "
                    f"SEDANG bila ada akun Tinggi, >= 10% akun Sedang, atau klaster terkoordinasi; selain itu RENDAH. Ambang ini adalah asumsi desain.\n"
                    f"- Status: ANALYSIS COMPLETED, ANOMALOUS BEHAVIOR DETECTED, HIGH-RISK ACTIVITY DETECTED, COORDINATED ACTIVITY IDENTIFIED, THREAT INDICATORS IDENTIFIED, "
                    f"dan INSUFFICIENT DATA (kurang dari {bi.MIN_ACCOUNTS_RELIABLE} akun dinilai) ditetapkan dari hasil perhitungan.\n"
                    f"- Tingkat keyakinan klasifikasi = presisi terukur pada dataset berlabel (interval Wilson 95%), ditampilkan bila >= {bi.MIN_LABELED} akun berlabel dan "
                    f">= {bi.MIN_PRED_POS} prediksi positif. Tanpa pengujian itu, angka keyakinan tidak dihitung.")
        st.markdown("**Keterbatasan analisis**")
        for x in bi.LIMITATIONS:
            st.markdown(f"- {x}")
        with st.expander("Pemeriksaan konsistensi angka"):
            chk = bi.consistency_report(inv, ex)
            st.markdown(f"**{sum(c_['lulus'] for c_ in chk)} dari {len(chk)} pemeriksaan lulus.**")
            st.dataframe(pd.DataFrame([("LULUS" if c_["lulus"] else "GAGAL", c_["nama"], c_["detail"]) for c_ in chk], columns=["Hasil", "Pemeriksaan", "Rincian"]),
                         width="stretch", hide_index=True)
        st.divider()
        st.subheader("Hasil validasi dengan data berlabel")
        if ev is None:
            st.caption("Belum ada pengujian. Unggah CSV label pada panel 'Validasi dengan data berlabel' di bagian atas halaman. "
                       "Sampai pengujian dilakukan, akurasi sistem pada data nyata belum terbukti.")
        else:
            for w in ev["peringatan"]:
                st.warning(w)
            if ev["n"]:
                fmt = lambda x: "-" if x != x else f"{x:.2f}"
                cols = st.columns(5)
                for c, (n_, v_) in zip(cols, [("Akun dibandingkan", ev["n"]), ("Akurasi", fmt(ev["accuracy"])), ("Presisi", fmt(ev["precision"])),
                                              ("Recall", fmt(ev["recall"])), ("F1", fmt(ev["f1"]))]):
                    c.metric(n_, v_)
                st.dataframe(pd.DataFrame([[ev["tn"], ev["fp"]], [ev["fn"], ev["tp"]]], index=["Aktual: bukan bot", "Aktual: bot"],
                                          columns=["Prediksi: bukan bot", "Prediksi: bot"]), width="stretch")

    with tabs[5]:
        st.subheader("Ekspor laporan investigasi")
        alias_x = st.checkbox("Samarkan nama akun pada ekspor", key=f"{key}_alias_x")
        out = tbl.copy()
        if alias_x:
            out["username"] = out["username"].map(bi.alias)
        st.download_button("⬇️ Unduh tabel akun (CSV)", out.to_csv(index=False).encode("utf-8-sig"), "investigasi_akun_nexguard.csv", "text/csv", key=f"{key}_csv")
        if len(inv["clusters"]):
            cl2 = inv["clusters"].copy()
            cl2["contoh_teks"] = cl2["contoh_teks"].map(mask)
            st.download_button("⬇️ Unduh klaster aktivitas (CSV)", cl2.to_csv(index=False).encode("utf-8-sig"), "klaster_aktivitas_nexguard.csv", "text/csv", key=f"{key}_csv2")
        sk = f"{key}_pdf"
        sig = meta["sig"] + str(alias_x) + kind + (str(ev["n"]) + str(ev["tp"]) if ev else "")
        if st.button("Siapkan laporan PDF", type="primary", key=f"{key}_mkpdf"):
            import bot_report
            from paths import asset_file
            with st.spinner("Menyusun laporan..."):
                try:
                    st.session_state[sk] = (sig, bot_report.build_pdf(inv, summ, source, f"{label} ({desc})", mask, alias_x, asset_file("logo_512.png"), ex, prov))
                except Exception as ex_:
                    st.error(f"Laporan PDF gagal dibuat: {ex_}")
        got = st.session_state.get(sk)
        if got and got[0] == sig:
            st.download_button("⬇️ Unduh laporan PDF", got[1], "laporan_investigasi_nexguard.pdf", "application/pdf", key=f"{key}_pdfdl")
        st.caption("Laporan memuat Executive Intelligence Summary, dasar klasifikasi tiap akun risiko tinggi, grafik, tabel akun, klaster aktivitas, metodologi, dan status validasi.")
    return summ