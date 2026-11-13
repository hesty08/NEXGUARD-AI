"""Explainable AI: ubah hasil analisis menjadi penjelasan terstruktur yang mudah dipahami.

Skor yang ditampilkan adalah SKOR RISIKO INDIKATIF (gabungan aturan yang dapat diperiksa), bukan probabilitas
kebenaran. Skor belum dikalibrasi terhadap data nyata, jadi jangan dibaca sebagai 'peluang hoaks sekian persen'."""

SCORE_NOTE = ("Skor risiko indikatif (0-100) adalah ringkasan indikator, bukan probabilitas. "
              "Belum diuji kalibrasi pada data nyata.")

HOAX_LIMITS = [
    "Analisis berbasis pola bahasa dan metadata sumber; tidak memahami makna klaim secara menyeluruh.",
    "Berita benar bisa memakai gaya sensasional, dan hoaks bisa ditulis dengan nada tenang (hasil keliru mungkin terjadi).",
    "Model ML dilatih pada dataset contoh kecil/sintetis dan belum terbukti akurat pada data nyata.",
    "Daftar domain rujukan terbatas: domain yang tidak ada di daftar belum tentu tidak kredibel.",
    "Pemeriksaan fakta hanya menemukan klaim yang pernah diulas pemeriksa fakta; tidak ada hasil bukan berarti benar atau salah.",
]
BOT_LIMITS = [
    "Pola mirip bot juga muncul pada akun resmi, akun layanan, atau pengguna yang sangat aktif.",
    "Fitur dihitung dari data yang diunggah saja; konteks di luar data tidak diketahui.",
    "Ambang batas bersifat heuristik dan belum divalidasi pada dataset akun berlabel.",
    "Hasil adalah alasan untuk meninjau akun, bukan bukti bahwa akun adalah bot.",
]
NETWORK_LIMITS = [
    "Kemiripan teks dan kedekatan waktu dapat terjadi secara wajar (isu viral, kutipan berita, tagar populer).",
    "Hubungan dalam graf berasal dari data unggahan yang tersedia; interaksi sebenarnya (reply, retweet) tidak diketahui.",
    "Kelompok yang terdeteksi adalah kandidat untuk ditinjau manusia, bukan bukti operasi terkoordinasi.",
]
EWS_LIMITS = [
    "Peringatan dihitung dari berkas yang diunggah, bukan aliran data real-time.",
    "Ambang statistik (robust z-score) heuristik; peristiwa nyata (berita besar, kampanye resmi) juga memicu lonjakan.",
    "Baseline membutuhkan beberapa hari data; data pendek menghasilkan peringatan kurang andal.",
]

_REC_HOAX = {
    "Tanpa tautan sumber": "Minta/cari tautan sumber primer (rilis resmi, media kredibel) sebelum menyebarkan.",
    "Sumber tidak dikenal": "Periksa reputasi domain sumber dan bandingkan dengan media/instansi resmi.",
    "Desakan menyebarkan": "Jangan teruskan pesan; desakan 'sebarkan segera' adalah pola umum hoaks berantai.",
    "Sumber tidak jelas": "Cari narasumber yang dapat diverifikasi; 'katanya/kabarnya' bukan sumber.",
    "Tanpa atribusi narasumber": "Cari siapa yang menyatakan klaim tersebut dan di mana pernyataan aslinya.",
    "Bahasa menakut-nakuti": "Cek apakah ada pengumuman resmi terkait ancaman yang disebut.",
}


def _direction(w):
    return "menaikkan risiko" if w > 0 else "menurunkan risiko"


def explain_hoax(r: dict, factcheck: dict = None) -> dict:
    factors = [{"faktor": n, "bobot": w, "arah": _direction(w), "detail": d}
               for n, w, d in sorted(r["signals"], key=lambda s: -abs(s[1]))]
    recs = [_REC_HOAX[f["faktor"]] for f in factors if f["faktor"] in _REC_HOAX]
    recs.append("Cek manual klaim di TurnBackHoax dan Google Fact Check Explorer.")
    status = r["status"]
    if factcheck:
        status = factcheck.get("overall", status)
        if factcheck.get("overall") == "Bertentangan dengan Bukti":
            recs.insert(0, "Klaim bertentangan dengan ulasan pemeriksa fakta: baca ulasan sumber sebelum menyebarkan.")
        elif factcheck.get("overall") != "Terverifikasi":
            recs.append("Belum ada ulasan pemeriksa fakta yang cocok: ini bukan berarti klaim benar atau salah.")
    comp = [{"komponen": "Indikator linguistik/sumber (bobot 70%)", "nilai": r["rule_score"]},
            {"komponen": "Model ML, tidak terkalibrasi (bobot 30%)", "nilai": r["ml_score"]}]
    notes = []
    if r.get("capped_by_style_rule"):
        notes.append("Skor dibatasi di bawah 50 karena hanya ditemukan indikator gaya bahasa, tanpa sinyal kuat.")
    return {"skor_label": f"Skor risiko indikatif {r['score']:.0f}/100 ({r['level']})", "catatan_skor": SCORE_NOTE,
            "status_verifikasi": status, "faktor": factors, "komponen_skor": comp,
            "indikator_terdeteksi": [f["faktor"] for f in factors if f["bobot"] > 0],
            "istilah_model": r.get("ml_terms", []), "catatan": notes,
            "keterbatasan": HOAX_LIMITS, "rekomendasi": list(dict.fromkeys(recs))}


def explain_bot(username: str, score: float, level: str, signals: list, n_posts=None) -> dict:
    if level == "Data Tidak Cukup":
        return {"skor_label": f"{username}: data tidak cukup untuk dinilai", "catatan_skor": SCORE_NOTE,
                "faktor": [], "indikator_terdeteksi": [], "keterbatasan": BOT_LIMITS,
                "rekomendasi": ["Kumpulkan lebih banyak postingan akun ini sebelum menilai pola aktivitasnya."]}
    factors = [{"faktor": n, "bobot": w, "arah": "menaikkan risiko", "detail": d} for n, w, d in signals]
    recs = ["Tinjau profil dan riwayat unggahan akun secara manual sebelum menyimpulkan apa pun."]
    if level == "Tinggi":
        recs.append("Bandingkan dengan akun lain yang memiliki pola serupa pada menu Network Analysis.")
    return {"skor_label": f"{username}: skor risiko indikatif {score:.0f}/100 ({level})", "catatan_skor": SCORE_NOTE,
            "faktor": factors, "indikator_terdeteksi": [f["faktor"] for f in factors],
            "keterbatasan": BOT_LIMITS, "rekomendasi": recs}
