"""Modul 02 - Pola akun menyerupai bot (rule-based, explainable)."""
import pandas as pd

# interval_spread_sec = penyebaran jeda antar-posting (MAD terskala, detik). Nama lama interval_std_sec tetap diterima.
CORE = ["username", "posts_per_day", "interval_spread_sec", "duplicate_ratio"]
OPTIONAL = ["followers", "following", "account_age_days", "has_profile_photo", "has_bio"]
REQUIRED = CORE + OPTIONAL
MIN_POSTS = 5
# Jendela minimum 6 jam: akun dengan sedikit postingan dalam rentang sangat singkat tidak langsung
# diekstrapolasi menjadi ribuan post/hari, tetapi burst tetap terlihat (200 post/33 menit ~ 800 post/hari).
MIN_WINDOW_DAYS = 0.25  # di bawah ini pola aktivitas belum andal

def features_from_posts(posts: pd.DataFrame) -> pd.DataFrame:
    """Hitung fitur perilaku otomatis dari CSV postingan (kolom: timestamp, username, text)."""
    for c in ("timestamp", "username", "text"):
        if c not in posts.columns:
            raise ValueError("CSV postingan harus berisi: timestamp, username, text")
    p = posts.copy()
    p["timestamp"] = pd.to_datetime(p["timestamp"], errors="coerce")
    p = p.dropna(subset=["timestamp", "username"])
    if p.empty:
        raise ValueError("Tidak ada baris valid (timestamp kosong/format salah).")
    p["norm"] = p["text"].astype(str).str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
    rows = []
    for u, g in p.sort_values("timestamp").groupby("username"):
        days = max((g.timestamp.max() - g.timestamp.min()).total_seconds() / 86400, MIN_WINDOW_DAYS)
        gaps = g.timestamp.diff().dt.total_seconds().dropna()
        # Penyebaran jeda yang robust (MAD): bot berjeda tetap tidak terganggu jeda antarhari
        spread = (gaps - gaps.median()).abs().median() * 1.4826 if len(gaps) > 1 else float("nan")
        rows.append(dict(username=u, posts_per_day=len(g) / days,
                         interval_spread_sec=spread,
                         duplicate_ratio=1 - g.norm.nunique() / len(g), n_posts=len(g)))
    return pd.DataFrame(rows)

def _clean(df: pd.DataFrame):
    if "interval_std_sec" in df.columns and "interval_spread_sec" not in df.columns:
        df = df.rename(columns={"interval_std_sec": "interval_spread_sec"})
    missing = [c for c in CORE if c not in df.columns]
    if missing:
        raise ValueError("Kolom CSV kurang: " + ", ".join(missing))
    d = df.copy()
    for c in CORE[1:] + [x for x in OPTIONAL if x in d.columns]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    before = len(d)
    d = d.dropna(subset=["username", "posts_per_day", "duplicate_ratio"])
    d = d[(d.posts_per_day >= 0) & d.duplicate_ratio.between(0, 1)]
    return d, before - len(d)

def score_account(r):
    strong, weak = [], []
    g = lambda k: getattr(r, k, float("nan"))
    if g("posts_per_day") > 100: strong.append(("Frekuensi posting sangat tinggi", 25, f"{r.posts_per_day:.0f} post/hari"))
    elif g("posts_per_day") > 50: strong.append(("Frekuensi posting tinggi", 15, f"{r.posts_per_day:.0f} post/hari"))
    if g("interval_spread_sec") < 30: strong.append(("Jeda posting terlalu seragam", 20, f"penyebaran jeda (MAD) {r.interval_spread_sec:.0f} detik"))
    if g("duplicate_ratio") > 0.6: strong.append(("Konten banyak duplikat", 25, f"{r.duplicate_ratio:.0%} konten sama"))
    elif g("duplicate_ratio") > 0.3: strong.append(("Konten cukup banyak duplikat", 12, f"{r.duplicate_ratio:.0%} konten sama"))
    if g("followers") >= 0 and g("following") >= 0 and g("following") / max(g("followers"), 1) > 10:
        strong.append(("Following jauh melebihi followers", 15, f"rasio {r.following / max(r.followers, 1):.1f}x"))
    if g("account_age_days") < 30: weak.append(("Akun sangat baru", 10, f"{r.account_age_days:.0f} hari"))
    if g("has_profile_photo") == 0: weak.append(("Tanpa foto profil", 5, ""))
    if g("has_bio") == 0: weak.append(("Tanpa bio", 5, ""))
    # Sinyal lemah hanya dihitung jika sudah ada >=2 sinyal perilaku (hindari salah tuduh akun biasa)
    sig = strong + (weak if len(strong) >= 2 else [])
    return min(100, sum(x[1] for x in sig)), sig

def analyze_df(df: pd.DataFrame) -> pd.DataFrame:
    d, dropped = _clean(df)
    rows, sigmap = [], {}
    for r in d.itertuples():
        n = getattr(r, "n_posts", None)
        if n is not None and n < MIN_POSTS:
            rows.append({"username": r.username, "skor_bot": 0, "level": "Data Tidak Cukup",
                         "alasan": f"Hanya {int(n)} postingan (minimal {MIN_POSTS})"})
            continue
        score, sig = score_account(r)
        sigmap[r.username] = [(n, w, x) for n, w, x in sig]
        level = "Rendah" if score < 30 else "Sedang" if score < 60 else "Tinggi"
        rows.append({"username": r.username, "skor_bot": score, "level": level,
                     "alasan": "; ".join(f"{n} ({x})" if x else n for n, _, x in sig) or "-"})
    out = pd.DataFrame(rows, columns=["username", "skor_bot", "level", "alasan"])
    out = out.sort_values("skor_bot", ascending=False).reset_index(drop=True)
    out.attrs["dropped"] = dropped
    out.attrs["signals"] = sigmap   # username -> [(faktor, bobot, detail)] untuk Explainable AI
    return out
