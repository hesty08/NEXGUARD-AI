# 🛡️ NEXGUARD AI

Platform analisis keamanan informasi untuk **Kartika Cyber Hackathon 2026 — Siber Sosial (Cognitive Domain)**.
Python + Streamlit. Menganalisis indikasi disinformasi, pola aktivitas akun, dan perkembangan isu dari teks/CSV yang diunggah.

> **Semua hasil bersifat indikatif**, bukan bukti bahwa suatu berita adalah hoaks, suatu akun adalah bot, atau sekelompok
> akun berkoordinasi. Data contoh bawaan adalah **sintetis**. Aplikasi ini **tidak real-time**: data diproses dari unggahan CSV.

## Fitur

| Menu | Fungsi |
|---|---|
| 🏠 Dashboard | Kartu statistik, ringkasan tiga modul utama (sesi), analisis terbaru, peringatan dini terbaru |
| 🔍 Hoax Analyzer | Indikator linguistik + model ML + **AI Fact-Checking** (Google Fact Check Tools API) + penjelasan (Explainable AI) |
| 🔎 Fact Check Explorer | Telusuri klaim yang sudah diperiksa (mirip Google Fact Check Explorer): pencarian, filter bahasa/umur/penerbit/penilaian, tab *Terbaru*, paginasi, ekspor CSV |
| 🤖 Bot Analyzer | Skor pola akun mirip bot dari fitur akun/CSV postingan, penjelasan per akun |
| 🌐 Social Intelligence | Sentimen, kata kunci, evolusi isu, klaster teks mirip & aktivitas serempak |
| 🚨 Early Warning | Lonjakan volume, perubahan tren sentimen, unggahan tidak biasa, grafik waktu, **riwayat peringatan** (SQLite) |
| 🕸️ Network Analysis | Graf akun (NetworkX + Plotly) dari kemiripan teks & kedekatan waktu, kelompok untuk ditinjau |
| 📈 Analytics | Evaluasi model: split latih/uji, accuracy/precision/recall/F1, confusion matrix, cek ketidakseimbangan kelas, unggah dataset berlabel |
| 📑 Reports | Laporan PDF: ringkasan, grafik, tabel, indikator, sumber data, penjelasan, keterbatasan, rekomendasi |

### Fact Check Explorer
Menu ini meniru pengalaman [Google Fact Check Explorer](https://toolbox.google.com/factcheck/explorer) memakai **API resmi** (`claims:search`):
kartu klaim dengan pengklaim, tanggal klaim, penerbit, peringkat asli, tanggal ulasan, dan tautan. Batasan yang perlu diketahui:
- API mewajibkan **kata kunci atau filter penerbit**; tidak ada endpoint "terbaru" tanpa kata kunci. Tab *Terbaru* karena itu dikumpulkan **per penerbit**
  (daftar dapat Anda ubah; `turnbackhoax.id`, `cekfakta.com`, `cekfakta.tempo.co` hanya nilai awal dan tidak dijamin selalu terindeks) lalu diurutkan dari ulasan terbaru.
- Hasil bisa berbeda dari situs Explorer karena Explorer memakai sumber data internal Google; aplikasi ini hanya menampilkan apa yang dikembalikan API.
- Memerlukan API key dan internet. Teks dari sumber eksternal ditampilkan sebagai teks biasa (di-escape) dan tautan non-http(s) dibuang.

### Status fact-check
`Terverifikasi` · `Bertentangan dengan Bukti` · `Belum Terverifikasi`. Hanya ulasan yang benar-benar dikembalikan API yang ditampilkan
(penerbit, peringkat, tanggal ulasan, tautan). **Tidak ada sumber yang dibuat sendiri.** Jika tidak ada ulasan yang cocok, API tidak
tersedia, key salah, atau terjadi kesalahan jaringan, status selalu *Belum Terverifikasi* — ini **tidak** berarti klaim benar atau salah.
Klaim yang dikirim ke Google sudah disamarkan dari email/telepon/NIK.

## Instalasi

Butuh **Python 3.10+**.

### Windows (PowerShell)
```powershell
cd cybershield
py -m venv venv
venv\Scripts\Activate.ps1          # jika diblokir: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python make_sample_data.py         # (opsional) membuat ulang dataset contoh
streamlit run app.py
```
Command Prompt: gunakan `venv\Scripts\activate.bat`.

### Kali Linux
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
cd cybershield
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python make_sample_data.py         # (opsional)
streamlit run app.py
```
Buka alamat yang ditampilkan (biasanya http://localhost:8501).

## API key Fact Check (opsional)
Aktifkan **Fact Check Tools API** di Google Cloud Console, lalu buat API key. **Jangan menulis key di kode atau meng-commit-nya.**

- Environment variable — Windows PowerShell: `$env:FACTCHECK_API_KEY="KEY_ANDA"` · Kali/Linux: `export FACTCHECK_API_KEY="KEY_ANDA"` (jalankan sebelum `streamlit run app.py`)
- Atau Streamlit Secrets: salin `.streamlit/secrets.toml.example` menjadi `.streamlit/secrets.toml` dan isi `FACTCHECK_API_KEY`.

Tanpa key, fitur fact-check dinonaktifkan dan seluruh modul lain tetap berjalan. Pemanggilan API membutuhkan internet.

## Format CSV
| Menu | Kolom |
|---|---|
| Bot Analyzer (postingan) | `timestamp, username, text` |
| Bot Analyzer (fitur akun) | wajib `username, posts_per_day, interval_spread_sec, duplicate_ratio`; opsional `followers, following, account_age_days, has_profile_photo, has_bio` |
| Social Intelligence / Early Warning / Network | `date` atau `timestamp`, `username`, `text` (`timestamp` diperlukan untuk analisis kedekatan waktu) |
| Evaluasi model | `text, label` (0 = bukan hoaks, 1 = hoaks) |

## Keamanan & privasi
- Validasi CSV: maks. 20 MB / 200.000 baris, deteksi file biner, fallback encoding (UTF-8 → Windows-1252), data kosong/tidak valid dilewati dengan pesan jelas.
- Data pribadi (email, telepon, NIK 16 digit) disamarkan sebelum disimpan, ditampilkan pada tabel teks, dan dikirim ke API. Masking berbasis pola
  (regex) dan **tidak menjamin** semua data pribadi tersamarkan. Opsi *Samarkan nama akun* tersedia di Network Analysis.
- Riwayat disimpan lokal di SQLite (`cybershield.db`) dan dihapus otomatis setelah 30 hari. Tombol *Hapus semua riwayat* di menu Reports.
- API key hanya dari environment variable / Streamlit Secrets; pesan error tidak memuat key.
- Lokasi database dapat diganti dengan environment variable `CYBERSHIELD_DB`.

## Pengujian
```bash
python -m pytest -q          # unit + integrasi + input tidak valid + performa + seluruh 9 menu Streamlit
python test_smoke.py         # smoke test cepat (9 menu, PDF)
python evaluate.py           # metrik evaluasi model pada dataset contoh
```
Pengujian fact-check memakai respons API tiruan (mock); **panggilan ke API Google yang sebenarnya perlu diuji dengan key Anda sendiri.**

## Evaluasi model & keterbatasan (transparansi)
- Model ML (TF-IDF + Logistic Regression) dilatih pada dataset contoh **sintetis berbasis templat**. Pada data ini metrik hold-out mendekati 1,00 —
  itu **tanda data terlalu mudah**, bukan bukti akurasi. Aplikasi menampilkan peringatan otomatis untuk kasus ini, dan **tidak ada klaim akurasi pada data nyata**.
- Skor ML **tidak terkalibrasi** (Brier score hanya indikasi awal). Skor risiko adalah *skor risiko indikatif*, bukan probabilitas.
- Untuk klaim akurasi yang layak: unggah dataset berlabel nyata (mis. TurnBackHoax) pada Analytics dan evaluasi dengan data uji terpisah.
- Analisis sentimen berbasis leksikon kecil (dengan penanganan negasi); akurasinya tidak diukur.
- Bot Analyzer memakai ambang heuristik yang belum divalidasi pada dataset akun berlabel.
- Early Warning memakai robust z-score (median/MAD) atas data unggahan; lonjakan nyata yang sah (berita besar) juga memicu peringatan.
- Network Analysis: kemiripan teks/waktu dapat terjadi wajar (isu viral, kutipan berita). Kelompok adalah kandidat tinjauan manusia.

## Struktur
`app.py` dashboard · `hoax.py` · `factcheck.py` · `explain.py` · `bot.py` · `social.py` · `early_warning.py` · `network.py` ·
`evaluate.py` · `report.py` + `session_report.py` · `db.py` · `io_utils.py` · `paths.py` · `theme.py` · `make_sample_data.py` · `test_*.py`

## Saran alur demo
1. Dashboard → 2. Hoax Analyzer (tempel pesan berantai; aktifkan fact-check bila key tersedia) → 2b. Fact Check Explorer → 3. Bot Analyzer (data contoh: `akun_x*` berada di peringkat atas) →
4. Social Intelligence → 5. Early Warning (lonjakan 16 Okt pada data contoh) → 6. Network Analysis (kelompok prioritas *Tinggi*) →
7. Analytics (tunjukkan peringatan skor sempurna pada data sintetis) → 8. Reports (unduh PDF).
