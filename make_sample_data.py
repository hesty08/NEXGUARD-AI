"""Membuat dataset contoh (sintetis) di folder data/."""
import os
from paths import DATA_DIR, data_file
os.makedirs(DATA_DIR, exist_ok=True)
import random, csv
from datetime import datetime, timedelta as td
from datetime import date, timedelta
import pandas as pd
random.seed(7)
HOAX = ["HEBOH!!! Vaksin ternyata mematikan, SEBARKAN sebelum dihapus!!!",
 "Katanya sinyal 5G bikin bahaya kesehatan, viralkan ke semua grup!",
 "Konon bantuan Rp5 juta cair hari ini, share sebelum dihapus!!!",
 "Astaga terbongkar! Orang dalam bocorkan bencana besar minggu depan, teruskan pesan ini!",
 "DARURAT!!! Air galon mengandung racun, bagikan ke keluarga sekarang!",
 "Wajib baca! Kabarnya listrik padam total 3 hari, info dari grup tetangga",
 "Geger! Tak disangka, makanan ini mematikan, sebarkan segera!!!",
 "Dikabarkan bank akan bangkrut besok, viralkan jangan sampai tidak tahu!",
 "Viral!!! Ancaman teror di mall, share sebelum dihapus!",
 "Heboh orang dalam bilang harga naik dua kali lipat, forward ke semua kontak!",
 "Terbongkar! Obat ini bahaya, katanya disembunyikan pemerintah, sebarkan!",
 "KIAMAT internet besok, kabarnya semua data hilang, bagikan ke teman!!!"]
REAL = ["Menurut Kepala BSSN, kasus serangan siber meningkat dan masyarakat diimbau memperbarui kata sandi.",
 "Kementerian Kesehatan menyampaikan jadwal imunisasi anak tahun ini dimulai pekan depan.",
 "BMKG memprakirakan hujan ringan di sebagian wilayah Sulawesi Selatan pada Selasa sore.",
 "Presiden meresmikan jalan tol baru, kata Menteri PU, untuk memperlancar distribusi logistik.",
 "PLN menyampaikan pemeliharaan jaringan akan dilakukan Minggu pagi di tiga kecamatan.",
 "Bank Indonesia menyatakan inflasi bulan ini terkendali sesuai data resmi yang dirilis Senin.",
 "Menurut Komdigi, masyarakat dapat melaporkan situs judi online melalui kanal aduan resmi.",
 "Dinas Pendidikan menyampaikan pendaftaran sekolah dibuka mulai tanggal 1 melalui portal resmi.",
 "Polisi menangkap pelaku penipuan daring setelah laporan korban diverifikasi, kata Kapolres.",
 "Universitas mengumumkan beasiswa baru bagi mahasiswa berprestasi, menurut Rektor.",
 "Menurut data BPS, pertumbuhan ekonomi kuartal ini naik dibanding periode sebelumnya.",
 "Dinas Kesehatan menyampaikan stok vaksin mencukupi dan layanan puskesmas berjalan normal."]

# --- Dataset hoaks SINTETIS (template + contoh tulisan tangan). Hanya untuk demonstrasi alur evaluasi.
# Metrik pada data ini hampir pasti terlalu optimistis karena kalimat dibuat dari pola yang sama.
_r = random.Random(11)  # generator terpisah agar dataset lain tidak berubah
_SUBJ = ["vaksin", "air galon", "sinyal 5G", "bantuan sosial", "uang elektronik", "minyak goreng",
         "aplikasi pemerintah", "dompet digital", "pesan WhatsApp berantai", "obat herbal tertentu"]
_HCLAIM = ["mematikan", "beracun", "akan diblokir besok", "dipakai untuk menyadap warga", "merusak ginjal",
           "akan dihapus total", "disembunyikan pemerintah", "menyebabkan kelumpuhan"]
_HOPEN = ["HEBOH!!!", "DARURAT!", "Katanya", "Konon", "Menurut kabar orang dalam", "GEGER!", "Astaga terbongkar!",
          "Dikabarkan", "Info dari grup keluarga:"]
_HPUSH = ["SEBARKAN sebelum dihapus!!!", "Viralkan ke semua grup!", "Bagikan ke 10 teman sekarang!",
          "Teruskan pesan ini jangan sampai tidak tahu!", "Share sebelum dihapus!", "Forward ke semua kontak!"]
_SRC = ["Kementerian Kesehatan", "BPS", "BSSN", "Bank Indonesia", "Kepala BNPB", "juru bicara Komdigi",
        "Dinas Kesehatan", "Kapolres", "Menteri Keuangan"]
_RACT = ["menyampaikan bahwa", "menjelaskan bahwa", "menyatakan bahwa", "mengumumkan bahwa"]
_RTOP = ["stok {s} mencukupi hingga akhir bulan", "layanan {s} dapat diakses normal", "pemeriksaan {s} dilakukan sesuai prosedur",
         "jadwal pembaruan {s} telah diumumkan resmi", "data terkait {s} tersedia di situs resmi"]
_RTAIL = ["Warga diimbau mengikuti informasi dari kanal resmi.", "Data lengkap dapat dilihat di situs resmi.", ""]
rows = [{"text": t, "label": 1} for t in HOAX] + [{"text": t, "label": 0} for t in REAL]
for i in range(130):
    s_, c_ = _r.choice(_SUBJ), _r.choice(_HCLAIM)
    if i % 5 == 0:   # kasus sulit: nada tenang, tanpa kapital/tanda seru
        t = f"Dikabarkan {s_} {c_}, menurut orang dalam, mohon diteruskan ke keluarga."
    else:
        t = f"{_r.choice(_HOPEN)} {s_.capitalize()} {c_}! {_r.choice(_HPUSH)}"
    rows.append({"text": t, "label": 1})
for i in range(130):
    s_ = _r.choice(_SUBJ)
    t = f"Menurut {_r.choice(_SRC)}, {_r.choice(_RACT)} {_r.choice(_RTOP).format(s=s_)}. {_r.choice(_RTAIL)}".strip()
    if i % 6 == 0:   # kasus sulit: berita sah dengan kata gaya viral
        t = f"Viral di media sosial: {_r.choice(_SRC)} {_r.choice(_RACT)} {_r.choice(_RTOP).format(s=s_)}."
    rows.append({"text": t, "label": 0})
pd.DataFrame(rows).drop_duplicates("text").to_csv(data_file("hoax_sample.csv"), index=False)

rows = []
for i in range(30):
    rows.append(dict(username=f"user_{i:02d}", posts_per_day=round(random.uniform(1, 15), 1),
        interval_spread_sec=random.randint(300, 9000), duplicate_ratio=round(random.uniform(0, 0.15), 2),
        followers=random.randint(80, 3000), following=random.randint(50, 900),
        account_age_days=random.randint(200, 3000), has_profile_photo=1, has_bio=int(random.random() > .2)))
for i in range(10):
    rows.append(dict(username=f"akun_x{i:02d}", posts_per_day=round(random.uniform(60, 400), 1),
        interval_spread_sec=random.randint(1, 25), duplicate_ratio=round(random.uniform(0.5, 0.95), 2),
        followers=random.randint(0, 40), following=random.randint(400, 2500),
        account_age_days=random.randint(1, 25), has_profile_photo=int(random.random() > .7), has_bio=0))
pd.DataFrame(rows).to_csv(data_file("accounts_sample.csv"), index=False)

issue = ["Judi online makin parah, banyak yang rugi dan kecewa", "Pemerintah berhasil blokir situs judi online, mantap",
 "Serangan siber ancaman serius, harus waspada", "Kenaikan harga beras bikin rakyat marah dan kecewa",
 "Bantuan sosial membantu warga, terima kasih", "Hoaks soal vaksin beredar lagi, jangan percaya, bohong",
 "Kita mendukung keamanan siber nasional, setuju", "Isu kenaikan harga bahan pokok ditolak warga, tolak!"]
posts, start = [], date.today() - timedelta(days=13)
for d in range(14):
    for _ in range(random.randint(8, 20) + (d // 2) * 2):
        posts.append(dict(date=start + timedelta(days=d), username=f"user_{random.randint(0,29):02d}", text=random.choice(issue)))
    if d >= 9:
        for b in range(10):
            posts += [dict(date=start + timedelta(days=d), username=f"akun_x{b:02d}", text=issue[5])] * 60
bot_clock = {}
for p in posts:
    base = datetime.combine(p["date"], datetime.min.time())
    if p["username"].startswith("akun_x"):
        k = bot_clock.get(p["username"], 0); bot_clock[p["username"]] = k + 1
        p["timestamp"] = base + td(hours=8, minutes=10 * (k % 60))
    else:
        p["timestamp"] = base + td(seconds=random.randint(0, 86399))
pd.DataFrame(posts)[["timestamp", "date", "username", "text"]].to_csv(data_file("posts_sample.csv"), index=False)
print(f"Dataset contoh dibuat di {DATA_DIR}")
