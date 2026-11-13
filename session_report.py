"""Menyusun isi laporan PDF dari hasil analisis sesi (modul yang belum dijalankan dilewati begitu saja)."""
import pandas as pd

import explain
import report


def assemble(a: dict) -> dict:
    out = {"sumber_data": "", "ringkasan": [], "indikator": [], "grafik": [], "tabel": [], "penjelasan": [],
           "keterbatasan": [], "rekomendasi": []}
    sources = []

    h = a.get("hoax")
    if h:
        r, e = h["result"], h["expl"]
        sources.append("Teks yang ditempel pengguna pada Hoax Analyzer")
        out["ringkasan"].append(f"Hoax Analyzer: {e['skor_label']}. Status verifikasi: {e['status_verifikasi']}.")
        out["indikator"] += [f"Hoax: {i}" for i in e["indikator_terdeteksi"]]
        out["penjelasan"] += [f"Hoax - {f['faktor']} ({f['bobot']:+d}, {f['arah']}): {f['detail']}" for f in e["faktor"]]
        out["keterbatasan"] += explain.HOAX_LIMITS
        out["rekomendasi"] += e["rekomendasi"]
        if h.get("fc"):
            out["fact_check"] = h["fc"]

    b = a.get("bot")
    if b:
        res = b["res"]
        sources.append(f"Bot Analyzer: {b['source']}")
        counts = res["level"].value_counts().to_dict()
        out["ringkasan"].append(f"Bot Analyzer: {len(res)} akun dianalisis; distribusi level {counts}.")
        out["grafik"].append(report.chart_levels(counts, "Level pola akun (indikatif)"))
        top = res[res.level == "Tinggi"].head(10)
        if len(top):
            out["tabel"].append(("Akun dengan pola perlu ditinjau (skor tinggi)", top[["username", "skor_bot", "level", "alasan"]]))
            out["indikator"] += sorted({x.split(" (")[0] for al in top["alasan"] for x in str(al).split("; ") if x and x != "-"})
        out["keterbatasan"] += explain.BOT_LIMITS
        out["rekomendasi"].append("Tinjau manual akun berskor tinggi sebelum menyimpulkan apa pun.")

    s = a.get("social")
    if s:
        sources.append(f"Social Intelligence: {s['source']}")
        out["ringkasan"].append(f"Social Intelligence: {s['n_posts']} postingan dari {s['n_accounts']} akun"
                                f"{' (filter: ' + s['issue'] + ')' if s.get('issue') else ''}; "
                                f"{len(s['clusters'])} klaster teks mirip dari >=3 akun.")
        if len(s["clusters"]):
            out["tabel"].append(("Klaster teks mirip dari banyak akun", s["clusters"][["contoh_teks", "jumlah_akun", "jumlah_post", "serempak"]]))

    w = a.get("ews")
    if w:
        r = w["result"]
        sources.append(f"Early Warning: {w['source']} (unggahan, bukan real-time)")
        al = r["alerts"]
        out["ringkasan"].append(f"Early Warning: {len(al)} peringatan pada {len(r['daily'])} hari data (metode robust z-score).")
        out["grafik"].append(report.chart_daily(r["daily"], al))
        if len(al):
            out["tabel"].append(("Peringatan dini", al[["tanggal", "jenis", "tingkat", "nilai", "baseline", "z"]]))
            out["indikator"] += sorted(set(al["jenis"]))
        out["penjelasan"].append("Early Warning membandingkan nilai harian dengan median/MAD hari-hari sebelumnya (robust z-score).")
        out["keterbatasan"] += r["limitations"]
        out["rekomendasi"].append("Cocokkan tanggal peringatan dengan peristiwa nyata dan tinjau isi unggahan pada tanggal tersebut.")

    n = a.get("net")
    if n:
        sources.append(f"Network Analysis: {n['source']}")
        g = n["groups"]
        out["ringkasan"].append(f"Network Analysis: {n['G'].number_of_nodes()} akun terhubung, {n['G'].number_of_edges()} hubungan, "
                                f"{len(g)} kelompok untuk ditinjau.")
        out["grafik"].append(report.chart_network(n["G"]))
        if len(g):
            out["tabel"].append(("Kelompok aktivitas yang perlu ditinjau", g[["kelompok", "jumlah_akun", "kerapatan", "porsi_sisi_serempak", "prioritas"]]))
        out["penjelasan"].append("Hubungan akun dibentuk dari kemiripan teks unggahan dan kedekatan waktu; kelompok = komunitas graf.")
        out["keterbatasan"] += explain.NETWORK_LIMITS
        out["rekomendasi"].append("Tinjau manual isi dan konteks unggahan kelompok berprioritas tinggi; jangan menyimpulkan bot/koordinasi dari graf saja.")

    out["sumber_data"] = "; ".join(sources) if sources else "Belum ada analisis sesi; laporan hanya memuat riwayat tersimpan."
    for k in ("indikator", "keterbatasan", "rekomendasi"):
        out[k] = list(dict.fromkeys(out[k]))
    return out
