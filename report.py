"""Pembuat laporan PDF. build_pdf(df) = riwayat analisis (kompatibel V5); build_pdf(df, analysis=...) menambahkan
ringkasan sesi: hasil, grafik, tabel, indikator, sumber data, penjelasan, keterbatasan, dan rekomendasi."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

APP_NAME = "NEXGUARD AI"
DISCLAIMER = ("Catatan: laporan ini berfungsi sebagai alat bantu keputusan. NEXGUARD AI memberi indikasi beserta alasannya, "
              "dan penetapan akhir tetap berada pada analis (human-in-the-loop).")
NAVY, GREEN = colors.HexColor("#0a1628"), colors.HexColor("#00e676")
LEVEL_COLOR = {"Rendah": "#2ecc71", "Sedang": "#ffb020", "Tinggi": "#ff4d4d", "Data Tidak Cukup": "#8a97a8"}


def _t(x, limit=None) -> str:
    """Teks aman untuk PDF: potong, hilangkan karakter di luar WinAnsi (emoji dsb.), escape markup."""
    s = str(x)
    if limit:
        s = s[:limit]
    return escape(s.encode("cp1252", "replace").decode("cp1252"))


# ----------------------------------------------------------------------------- grafik (matplotlib -> PNG)
def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def chart_daily(daily, alerts=None) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.plot(daily["tanggal"], daily["volume"], color="#0a6cff", marker="o", ms=3, lw=1.5)
    if alerts is not None and len(alerts):
        v = alerts[alerts["jenis"].str.startswith("Lonjakan")]
        if len(v):
            m = daily.set_index(daily["tanggal"].dt.date)["volume"]
            ax.scatter([daily["tanggal"][daily["tanggal"].dt.date == t].iloc[0] for t in v["tanggal"]], [m[t] for t in v["tanggal"]],
                       color="#ff4d4d", zorder=3, label="Peringatan lonjakan")
            ax.legend(fontsize=7)
    ax.set_title("Volume percakapan per hari", fontsize=10)
    ax.tick_params(labelsize=7); ax.grid(alpha=.3); fig.autofmt_xdate()
    return _png(fig)


def chart_levels(level_counts: dict, title="Distribusi tingkat risiko") -> bytes:
    fig, ax = plt.subplots(figsize=(4.5, 2.6))
    labels = list(level_counts)
    ax.bar(labels, [level_counts[k] for k in labels], color=[LEVEL_COLOR.get(k, "#8a97a8") for k in labels])
    ax.set_title(title, fontsize=10); ax.tick_params(labelsize=8); ax.grid(axis="y", alpha=.3)
    return _png(fig)


def chart_network(G, max_nodes=150) -> bytes:
    import networkx as nx
    fig, ax = plt.subplots(figsize=(6, 4.2))
    H = G if G.number_of_nodes() <= max_nodes else G.subgraph(sorted(G.nodes, key=G.degree, reverse=True)[:max_nodes])
    if H.number_of_nodes():
        pos = nx.spring_layout(H, seed=42, weight="weight")
        sync = [e for e in H.edges if H.edges[e]["serempak"] > 0]
        rest = [e for e in H.edges if e not in set(sync)]
        nx.draw_networkx_edges(H, pos, edgelist=rest, ax=ax, edge_color="#9db4d4", alpha=.3, width=.6)
        nx.draw_networkx_edges(H, pos, edgelist=sync, ax=ax, edge_color="#ff4d4d", alpha=.6, width=.9)
        nx.draw_networkx_nodes(H, pos, ax=ax, node_size=[20 + 6 * min(H.degree(n), 10) for n in H], node_color="#0a6cff")
    ax.set_title("Jaringan akun (merah = teks mirip + serempak)", fontsize=10); ax.axis("off")
    return _png(fig)


# ----------------------------------------------------------------------------- dokumen
def _styles():
    st = getSampleStyleSheet()
    st.add(ParagraphStyle("H2", parent=st["Heading2"], textColor=NAVY, spaceBefore=10, spaceAfter=4))
    st.add(ParagraphStyle("Small", parent=st["BodyText"], fontSize=8, leading=10))
    return st


def _table(rows, header, widths, st):
    data = [header] + [[Paragraph(_t(c, 120), st["Small"]) for c in r] for r in rows]
    t = Table(data, repeatRows=1, colWidths=widths)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), GREEN),
                           ("GRID", (0, 0), (-1, -1), .3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _bullets(items, st):
    return [Paragraph("&bull; " + _t(i), st["BodyText"]) for i in items]


def _df_table(df, st, cols=None, max_rows=15, widths=None):
    cols = cols or list(df.columns)
    rows = [[("" if v is None else v) for v in r] for r in df[cols].head(max_rows).itertuples(index=False, name=None)]
    w = widths or [(A4[0] - 4 * cm) / len(cols)] * len(cols)
    return _table(rows, [c.replace("_", " ").title() for c in cols], w, st)


def build_pdf(df, analysis: dict = None) -> bytes:
    """df = riwayat analisis (kolom ts,module,subject,score,level). analysis (opsional) = ringkasan sesi, kunci:
    sumber_data, ringkasan[list], grafik[list bytes PNG], tabel[list (judul, DataFrame)], indikator[list],
    penjelasan[list], keterbatasan[list], rekomendasi[list], fact_check[dict]."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Laporan {APP_NAME}", leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm)
    st = _styles()
    el = [Paragraph(f"LAPORAN {APP_NAME.upper()}", st["Title"]),
          Paragraph(f"Waktu analisis: {datetime.now():%d-%m-%Y %H:%M:%S}", st["Normal"]), Spacer(1, 10)]
    a = analysis or {}
    if a:
        el.append(Paragraph("Sumber data", st["H2"]))
        el.append(Paragraph(_t(a.get("sumber_data", "Tidak dicantumkan")), st["BodyText"]))
        if a.get("ringkasan"):
            el.append(Paragraph("Ringkasan hasil", st["H2"])); el += _bullets(a["ringkasan"], st)
        fc = a.get("fact_check")
        if fc:
            el.append(Paragraph("Pemeriksaan fakta", st["H2"]))
            el.append(Paragraph(_t(f"Status keseluruhan: {fc.get('overall')} - {fc.get('message', '')}"), st["BodyText"]))
            rows = []
            for c in fc.get("claims", []):
                if c["sources"]:
                    for s in c["sources"][:2]:
                        rows.append([c["claim"], c["status"], f"{s['publisher']} ({s['review_date'] or 'tanggal tidak tersedia'}) {s['url']}"])
                else:
                    rows.append([c["claim"], c["status"], "Tidak ada ulasan yang cocok"])
            if rows:
                el.append(_table(rows, ["Klaim", "Status", "Sumber"], [6 * cm, 3 * cm, 8 * cm], st))
        if a.get("indikator"):
            el.append(Paragraph("Indikator yang ditemukan", st["H2"])); el += _bullets(a["indikator"], st)
        for png in a.get("grafik", []):
            el += [Spacer(1, 6), Image(io.BytesIO(png), width=15 * cm, height=15 * cm * 0.42, kind="proportional")]
        for title, tdf in a.get("tabel", []):
            if tdf is not None and len(tdf):
                el += [Paragraph(_t(title), st["H2"]), _df_table(tdf, st)]
        if a.get("penjelasan"):
            el.append(Paragraph("Penjelasan hasil", st["H2"])); el += _bullets(a["penjelasan"], st)
        if a.get("keterbatasan"):
            el.append(Paragraph("Keterbatasan analisis", st["H2"])); el += _bullets(a["keterbatasan"], st)
        if a.get("rekomendasi"):
            el.append(Paragraph("Rekomendasi verifikasi lanjutan", st["H2"])); el += _bullets(a["rekomendasi"], st)
        el.append(PageBreak())
    el.append(Paragraph("Riwayat analisis tersimpan", st["H2"]))
    if df is None or df.empty:
        el.append(Paragraph("Belum ada hasil analisis tersimpan.", st["Normal"]))
    else:
        el.append(Paragraph(f"Total analisis: {len(df)} | Tingkat Tinggi: {(df.level == 'Tinggi').sum()}", st["Normal"]))
        el.append(Spacer(1, 8))
        rows = [[r.ts, r.module, r.subject, f"{r.score:.0f}", r.level] for r in df.head(60).itertuples()]
        el.append(_table(rows, ["Waktu", "Modul", "Subjek", "Skor", "Level"], [85, 55, 230, 35, 60], st))
    el += [Spacer(1, 16), Paragraph(_t(DISCLAIMER), st["Italic"])]
    doc.build(el)
    return buf.getvalue()
