"""Laporan PDF Investigasi Aktivitas Akun (Bot Analyzer V6): identitas NEXGUARD AI, ringkasan, grafik, tabel akun,
indikator risiko, koordinasi, kesimpulan, metodologi, dan keterbatasan. Semua isi berasal dari hasil analisis."""
import io
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import bot_investigation as bi
import report as rp

LEVEL_HEX = {"Tinggi": "#d93030", "Sedang": "#d98a00", "Rendah": "#1a9e55", "Data Tidak Cukup": "#6b7785"}
NAVY, GREEN, INK = rp.NAVY, rp.GREEN, colors.HexColor("#0b1f17")


# ----------------------------------------------------------------------------- grafik (matplotlib -> PNG)
def _style(ax, title):
    ax.set_title(title, fontsize=10, loc="left", color="#0a1628", fontweight="bold")
    ax.tick_params(labelsize=7)
    ax.grid(alpha=.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def chart_risk(cnt: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    labels = [k for k in bi.LEVELS if cnt.get(k, 0) or k != "Data Tidak Cukup"]
    bars = ax.bar(labels, [cnt.get(k, 0) for k in labels], color=[LEVEL_HEX[k] for k in labels])
    ax.bar_label(bars, fontsize=8)
    _style(ax, "Distribusi tingkat risiko akun")
    return rp._png(fig)


def chart_top(inv, name, n=12) -> bytes:
    f = inv["feats"].merge(inv["res"][["username", "level"]], on="username").sort_values("n_posts", ascending=False).head(n)[::-1]
    fig, ax = plt.subplots(figsize=(4.4, 2.9))
    ax.barh([name(u) for u in f["username"]], f["n_posts"], color=[LEVEL_HEX[l] for l in f["level"]])
    _style(ax, "Akun paling aktif (jumlah postingan)")
    return rp._png(fig)


def _buckets(p):
    span = (p["ts"].max() - p["ts"].min()).total_seconds() / 86400
    return ("h", "Jam") if span <= 3 else ("D", "Hari")


def chart_activity(inv) -> bytes:
    p = inv["posts"]
    fr, unit = _buckets(p)
    t = p.assign(t=p["ts"].dt.floor(fr)).groupby(["t", "level"]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    for lv in bi.LEVELS:
        if lv in t.columns:
            ax.plot(t.index, t[lv], label=lv, color=LEVEL_HEX[lv], lw=1.4)
    ax.legend(fontsize=6)
    _style(ax, f"Aktivitas posting per {unit.lower()}")
    fig.autofmt_xdate()
    return rp._png(fig)


def chart_repeat(inv) -> bytes:
    p = inv["posts"]
    t = p.groupby(["level", "is_repeat"]).size().unstack(fill_value=0).reindex([l for l in bi.LEVELS if l in set(p["level"])])
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    uniq, rep = t.get(False, pd.Series(0, index=t.index)), t.get(True, pd.Series(0, index=t.index))
    ax.bar(t.index, uniq, color="#4da3ff", label="Unik")
    ax.bar(t.index, rep, bottom=uniq, color="#d93030", label="Berulang")
    ax.legend(fontsize=7)
    _style(ax, "Postingan unik vs berulang")
    return rp._png(fig)


def chart_trend(inv) -> bytes:
    p = inv["posts"]
    fr, unit = _buckets(p)
    t = p.assign(t=p["ts"].dt.floor(fr))
    risky = t[t["level"].isin(["Tinggi", "Sedang"])].groupby("t").size()
    sync = t[t["sync"]].groupby("t").size()
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    if len(risky):
        ax.plot(risky.index, risky.values, color="#d98a00", lw=1.5, label="Akun Tinggi/Sedang")
    if len(sync):
        ax.plot(sync.index, sync.values, color="#d93030", lw=1.5, label="Posting serempak")
    if len(risky) or len(sync):
        ax.legend(fontsize=7)
    _style(ax, f"Tren aktivitas mencurigakan per {unit.lower()}")
    fig.autofmt_xdate()
    return rp._png(fig)


def chart_network(inv, name, max_nodes=120) -> bytes:
    G = inv["G"]
    fig, ax = plt.subplots(figsize=(4.4, 3.2))
    if G.number_of_nodes():
        H = G if G.number_of_nodes() <= max_nodes else G.subgraph(sorted(G.nodes, key=G.degree, reverse=True)[:max_nodes])
        lvl = inv["res"].set_index("username")["level"]
        pos = nx.spring_layout(H, seed=42, weight="weight")
        nx.draw_networkx_edges(H, pos, ax=ax, edge_color="#9db4d4", alpha=.25, width=.5)
        nx.draw_networkx_nodes(H, pos, ax=ax, node_size=[18 + 5 * min(H.degree(n), 10) for n in H],
                               node_color=[LEVEL_HEX.get(lvl.get(n, "Rendah"), "#6b7785") for n in H])
    ax.set_title("Hubungan antar-akun (warna = kategori risiko)", fontsize=10, loc="left", color="#0a1628", fontweight="bold")
    ax.axis("off")
    return rp._png(fig)


# ----------------------------------------------------------------------------- halaman
def _decor(logo_path):
    def draw(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 1.1 * cm, w, 1.1 * cm, stroke=0, fill=1)
        canvas.setFillColor(GREEN)
        canvas.rect(0, h - 1.15 * cm, w, 0.05 * cm, stroke=0, fill=1)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(2 * cm, h - 0.72 * cm, "NEXGUARD AI  |  LAPORAN INVESTIGASI AKTIVITAS AKUN")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#9fb3c8"))
        canvas.drawRightString(w - 2 * cm, h - 0.72 * cm, "THREAT INTELLIGENCE REPORT")
        canvas.setFillColor(colors.HexColor("#6b7785"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(2 * cm, 0.9 * cm, "Klasifikasi berbasis indikator terukur; konfirmasi identitas akun memerlukan validasi.")
        canvas.drawRightString(w - 2 * cm, 0.9 * cm, f"Halaman {doc.page}")
        canvas.restoreState()
    return draw


def _title_block(st, kind_text, source, meta, logo_path, p_style):
    left = [Paragraph("LAPORAN INVESTIGASI AKTIVITAS AKUN", p_style["Title2"]),
            Paragraph("NEXGUARD AI &middot; Bot Analyzer", p_style["Sub"]),
            Paragraph(rp._t(f"Dibuat: {datetime.now():%d-%m-%Y %H:%M} | Jenis data: {kind_text}"), p_style["Small"])]
    cells = [[Image(logo_path, width=2.4 * cm, height=2.4 * cm), left]] if logo_path and os.path.exists(logo_path) else [[left]]
    t = Table(cells, colWidths=[2.8 * cm, 14 * cm] if len(cells[0]) == 2 else [16.8 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _h(n, text, st):
    return Paragraph(f"{n}. {text}", st["H2"])


def build_pdf(inv: dict, summ: dict, source: str, kind_text: str, mask=lambda x: x, use_alias: bool = False,
              logo_path: str = None, ex: dict = None, prov: dict = None) -> bytes:
    """Laporan intelijen 10 bagian: identitas, ringkasan eksekutif, dataset, statistik, grafik, akun prioritas, koordinasi,
    penjelasan klasifikasi, metodologi, serta kesimpulan dan rekomendasi. Semua isi dihitung dari hasil analisis."""
    name = (lambda u: bi.alias(u)) if use_alias else (lambda u: str(u))
    meta, res, cnt = inv["meta"], inv["res"], summ["counts"]
    ex = ex or bi.executive_summary(inv)
    cl = inv["clusters"]
    st = rp._styles()
    st.add(ParagraphStyle("Title2", parent=st["Title"], fontSize=17, textColor=NAVY, alignment=0, spaceAfter=2))
    st.add(ParagraphStyle("Sub", parent=st["BodyText"], fontSize=10, textColor=colors.HexColor("#0a7d4a")))
    st.add(ParagraphStyle("Big", parent=st["BodyText"], leading=26, spaceBefore=4, spaceAfter=4))
    st.add(ParagraphStyle("H3", parent=st["Heading3"], textColor=NAVY, spaceBefore=6, spaceAfter=2, fontSize=10))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Laporan Intelijen Aktivitas Akun - NEXGUARD AI", leftMargin=2 * cm,
                            rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=1.7 * cm)
    W = A4[0] - 4 * cm
    grid = [("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c9d3dc")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f0")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    kv = lambda rows, w0=3.8 * cm: _kv(rows, W, w0, st, grid)

    # 1. identitas
    el = [_title_block(st, kind_text, source, meta, logo_path, st), Spacer(1, 2), _h(1, "Identitas dan keterangan laporan", st)]
    ident = [["Platform", "NEXGUARD AI - Deteksi, Analisis, Lindungi"], ["Modul", "Bot Analyzer - investigasi aktivitas akun"],
             ["Dibuat", f"{datetime.now():%d-%m-%Y %H:%M}"], ["Jenis data", rp._t(kind_text, 160)]]
    if prov:
        ident += [["Sumber data (pernyataan pengguna)", rp._t(prov.get("sumber", "-"), 160)], ["Metode pengumpulan", rp._t(prov.get("metode", "-"), 160)]]
    el += [kv(ident, 4.6 * cm)]

    # 2. executive intelligence summary
    chips = [[Paragraph(f'<font size="7" color="{x["color"]}"><b>{x["code"]}</b></font><br/><font size="9"><b>{rp._t(x["label"])}</b></font><br/>'
                        f'<font size="7" color="#5b6b78">{rp._t(x["desc"], 90)}</font>', st["BodyText"]) for x in ex["statuses"]]]
    n_chip = len(ex["statuses"])
    chip_t = Table(chips, colWidths=[W / n_chip] * n_chip)
    chip_t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#c9d3dc")), ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#dfe6ec")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")] + [("LINEABOVE", (i, 0), (i, 0), 2.5, colors.HexColor(x["color"])) for i, x in enumerate(ex["statuses"])]))
    el += [_h(2, "Executive Intelligence Summary", st), chip_t, Spacer(1, 6),
           Paragraph(f'<font size="8" color="#5b6b78">CYBER INTELLIGENCE ASSESSMENT</font><br/><font size="18" color="{ex["level_color"] if ex["level_color"].startswith("#") else "#000000"}"><b>'
                     f'{ex["level"] or "TIDAK TERSEDIA"}</b></font>', st["Big"]),
           Paragraph(rp._t(ex["headline"]), st["BodyText"]), Paragraph(f"<b>Alasan penetapan:</b> {rp._t(ex['reason'])}", st["BodyText"]),
           Paragraph("Temuan terukur", st["H3"])] + rp._bullets(ex["findings"], st)
    if ex["support"]:
        el += [Paragraph("THREAT INDICATORS IDENTIFIED", st["H3"]),
               rp._table([[n, c, f"{pc:.0%}"] for n, c, pc in ex["support"]], ["Indikator", "Akun aktif", "% akun dinilai"], [W * .55, W * .2, W * .25], st)]
    pr = ex["priorities"]
    el += [Paragraph(f"INVESTIGATION PRIORITY: TINGGI {pr['TINGGI']} akun, SEDANG {pr['SEDANG']}, RENDAH {pr['RENDAH']}", st["H3"]),
           Paragraph(rp._t(ex["priority_note"]), st["Small"])] + rp._bullets(ex["priority_criteria"], st)
    if ex["top"]:
        el += [rp._table([[name(t["username"]), t["skor"], t["prioritas"], rp._t(t["dasar"], 90)] for t in ex["top"]],
                         ["Akun", "Skor", "Prioritas", "Dasar klasifikasi"], [W * .2, W * .1, W * .15, W * .55], st)]
    el += [Paragraph("Status validasi", st["H3"]), Paragraph("<b>Terukur</b>", st["BodyText"])] + rp._bullets(ex["measured"], st)
    el += [Paragraph("<b>Belum tervalidasi</b>", st["BodyText"])] + rp._bullets(ex["unvalidated"], st)
    cf = ex["confidence"]
    el += [Paragraph("Tingkat keyakinan klasifikasi", st["H3"]), Paragraph(f"<b>{rp._t(cf['label'])}</b>. {rp._t(cf['detail'])}", st["BodyText"])]

    # 3. informasi dan periode dataset
    info = [["Sumber data", rp._t(source, 160)], ["Jenis data", rp._t(kind_text, 160)],
            ["Periode data", f"{meta['first_ts']:%d-%m-%Y %H:%M} s.d. {meta['last_ts']:%d-%m-%Y %H:%M} ({meta['span_days']:.1f} hari)"],
            ["Cakupan", f"{meta['n_posts']:,} postingan dari {meta['n_accounts']:,} akun ({summ['n_eval']:,} akun berdata memadai)"],
            ["Parameter koordinasi", f"kemiripan teks >= {meta['threshold']:.2f}; jendela waktu {meta['window_min']} menit; min. {meta['min_accounts']} akun per klaster"]]
    el += [_h(3, "Informasi dan periode dataset", st), kv(info)]
    if meta["peringatan"]:
        el += [Paragraph("Catatan kualitas data", st["H3"])] + rp._bullets(meta["peringatan"], st)

    # 4. statistik hasil analisis
    def card(label, value, hexc):
        return Paragraph(f'<font size="7" color="#5b6b78">{label}</font><br/><font size="15" color="{hexc}"><b>{value}</b></font>', st["BodyText"])
    cards = [[card("AKUN DIANALISIS", f"{meta['n_accounts']:,}", "#0a1628"), card("TOTAL POSTINGAN", f"{meta['n_posts']:,}", "#0a1628"),
              card("RISIKO TINGGI", cnt["Tinggi"], LEVEL_HEX["Tinggi"]), card("RISIKO SEDANG", cnt["Sedang"], LEVEL_HEX["Sedang"]),
              card("RISIKO RENDAH", cnt["Rendah"], LEVEL_HEX["Rendah"]), card("ANOMALI AKTIVITAS", f"{summ['pct_susp']:.0%}", "#0a1628")]]
    ct = Table(cards, colWidths=[W / 6] * 6)
    ct.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#c9d3dc")), ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#dfe6ec")),
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6faf8")), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    n_ev = summ["n_eval"]
    dist = [[k, cnt[k], (f"{cnt[k] / n_ev:.0%}" if (n_ev and k != "Data Tidak Cukup") else "-")] for k in bi.LEVELS]
    chk = bi.consistency_report(inv, ex)
    el += [_h(4, "Statistik hasil analisis", st), ct, Spacer(1, 6),
           rp._table(dist, ["Kategori", "Jumlah akun", f"% dari {n_ev} akun dinilai"], [W * .4, W * .3, W * .3], st),
           Paragraph(rp._t(f"Klaster teks mirip: {len(cl)}; terkoordinasi: {summ['n_coord']}; indikasi sebagian: {summ['n_partial']}; klaster dengan posting serempak: {summ['n_sync']}. "
                           f"Pemeriksaan konsistensi angka: {sum(c['lulus'] for c in chk)} dari {len(chk)} lulus."), st["BodyText"])]

    # 5. grafik
    def pair(a_, b_):
        return Table([[Image(io.BytesIO(a_), width=W / 2 - 4, height=(W / 2 - 4) * .62, kind="proportional"),
                       Image(io.BytesIO(b_), width=W / 2 - 4, height=(W / 2 - 4) * .62, kind="proportional")]], colWidths=[W / 2, W / 2])
    el += [_h(5, "Grafik distribusi dan aktivitas", st), pair(chart_risk(cnt), chart_top(inv, name)), pair(chart_activity(inv), chart_repeat(inv)),
           pair(chart_trend(inv), chart_network(inv, name))]

    # 6. daftar akun prioritas investigasi
    ranked = res[res["prioritas"] != "-"].assign(o=lambda d: d["prioritas"].map(bi.PRIORITY_ORDER)).sort_values(["o", "skor_bot"], ascending=[True, False]).head(25)
    el += [_h(6, "Daftar akun prioritas investigasi", st)]
    if len(ranked):
        tbl = bi.investigation_table(inv).set_index("username")
        data = [["Akun", "Prioritas", "Skor", "Kategori", "Post", "Rata-rata jeda", "% ulang", "Alasan klasifikasi"]]
        for r in ranked.itertuples():
            x = tbl.loc[r.username]
            data.append([Paragraph(rp._t(c, 330), st["Small"]) for c in
                         (name(r.username), r.prioritas, r.skor_bot, r.level, int(x["total_postingan"]), x["rata_interval"], f"{x['persen_pengulangan']:.0f}%", r.alasan)])
        at = Table(data, repeatRows=1, colWidths=[2.1 * cm, 1.5 * cm, 1.0 * cm, 1.5 * cm, 1.0 * cm, 2.0 * cm, 1.2 * cm, W - 10.3 * cm])
        at.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), GREEN), ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c9d3dc")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6faf8")])]))
        el += [Paragraph(rp._t(ex["priority_note"]) + " Daftar ini memuat maksimal 25 akun.", st["Small"]), at]
    else:
        el += [Paragraph("Tidak ada akun yang memerlukan prioritas investigasi.", st["BodyText"])]

    
    # 7. indikator aktivitas terkoordinasi
    el += [
        _h(7, "Indikator aktivitas terkoordinasi", st),
        Paragraph(
            rp._t(
                f"Klaster dibentuk berdasarkan kemiripan teks lintas akun. "
                f"Aktivitas serempak dihitung dalam jendela "
                f"{meta['window_min']} menit. "
                "Temuan ini merupakan indikator untuk pemeriksaan lanjutan, "
                "bukan bukti bahwa akun melakukan koordinasi."
            ),
            st["BodyText"]
        )
    ]

    if len(cl):
        yn = lambda v: "Ya" if v else "Tidak"
        rows = [
            [
                r.klaster,
                rp._t(mask(r.contoh_teks), 70),
                r.jumlah_akun,
                r.jumlah_post,
                r.akun_serempak,
                yn(r.serempak),
                str(r.mulai),
                str(r.selesai),
                rp._t(r.akun, 80)
            ]
            for r in cl.head(12).itertuples()
        ]

        el += [rp._table(
            rows,
            [
                "ID", "Contoh teks", "Akun", "Post",
                "Akun serempak", "Serempak",
                "Mulai", "Selesai", "Akun terlibat"
            ],
            [
                W * .06, W * .23, W * .07, W * .07,
                W * .10, W * .08, W * .12, W * .12, W * .15
            ],
            st
        )]
    else:
        el += [
            Paragraph(
                "Tidak ditemukan klaster teks mirip lintas akun pada parameter yang dipilih.",
                st["BodyText"]
            )
        ]

    # 8. penjelasan hasil klasifikasi
    hi = res[res["level"] == "Tinggi"]
    el += [_h(8, "Penjelasan hasil klasifikasi akun risiko tinggi", st)]
    if len(hi):
        el += [Paragraph(rp._t(f"{len(hi)} akun berkategori Tinggi. Setiap akun menampilkan indikator aktif beserta nilai terukur dan ambang aktifnya (maksimal 20 akun ditampilkan)."), st["BodyText"])]
        for r in hi.head(20).itertuples():
            rows = [[b["indikator"], b["nilai"], b["ambang"], f"{b['poin']:.1f}/{b['maks']}"] for b in bi.evidence(inv, r.username) if b["aktif"]]
            el += [KeepTogether([Paragraph(rp._t(f"{name(r.username)} - skor {r.skor_bot}/100, prioritas investigasi {r.prioritas}, {r.n_aktif} indikator aktif"), st["H3"]),
                                 Paragraph(rp._t(bi.explain_account(inv, r.username)["ringkasan"].replace(r.username, name(r.username))), st["Small"]),
                                 rp._table(rows, ["Indikator aktif", "Nilai terukur", "Ambang aktif", "Poin"], [W * .35, W * .25, W * .25, W * .15], st)])]
    else:
        el += [Paragraph("Tidak ada akun berkategori Tinggi pada data ini.", st["BodyText"])]

    # 9. metodologi
    ind_rows = [[i["nama"], i["maks"], f"{i['lo']:g} - {i['hi']:g}" + (" (makin kecil makin berisiko)" if i["inv"] else "")] for i in bi.INDICATORS]
    el += [KeepTogether([_h(9, "Metodologi analisis", st),
                         Paragraph(rp._t(f"Skor 0-100 = jumlah poin indikator yang tersedia dibagi bobot maksimum yang tersedia. Kategori: Rendah < {bi.THRESH_MID}, "
                                         f"Sedang {bi.THRESH_MID}-{bi.THRESH_HIGH - 1}, Tinggi >= {bi.THRESH_HIGH}. Kategori Tinggi mensyaratkan minimal "
                                         f"{bi.MIN_ACTIVE_HIGH} indikator aktif dan Sedang minimal {bi.MIN_ACTIVE_MID}, sehingga tidak ada kesimpulan dari satu indikator. "
                                         f"Akun dengan kurang dari {bi.MIN_POSTS} postingan tidak dinilai dan tidak dihitung dalam persentase."), st["BodyText"]),
                         rp._table(ind_rows, ["Indikator", "Bobot maks", "Rentang nilai (0 - penuh)"], [W * .4, W * .2, W * .4], st)])]
    el += [Paragraph("Keterbatasan analisis", st["H3"])] + rp._bullets(bi.LIMITATIONS, st)

    # 10. kesimpulan dan rekomendasi
    el += [_h(10, "Kesimpulan dan rekomendasi", st), Paragraph(rp._t(summ["conclusion"]), st["BodyText"]), Paragraph("Rekomendasi tindak lanjut", st["H3"])]
    el += rp._bullets(ex["recommendations"], st)
    el += [Spacer(1, 10), Paragraph(rp._t("Klasifikasi dalam laporan ini berbasis indikator terukur dari data yang dianalisis. "
                                           "Konfirmasi identitas akun (bot atau pengguna asli) memerlukan validasi metadata dan konteks di luar data ini."), st["Italic"])]
    deco = _decor(logo_path)
    doc.build(el, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


def _kv(rows, W, w0, st, grid):
    t = Table([[Paragraph(f"<b>{a}</b>", st["Small"]), Paragraph(str(b), st["Small"])] for a, b in rows], colWidths=[w0, W - w0])
    t.setStyle(TableStyle(grid))
    return t