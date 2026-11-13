"""Early Warning System berbasis dataset unggahan (BUKAN real-time).

Metode statistik yang dapat dijelaskan: robust z-score terhadap baseline median/MAD hari-hari sebelumnya
(dengan batas bawah Poisson agar baseline sepi tidak memicu alarm palsu)."""
import numpy as np
import pandas as pd

WINDOW = 7          # hari baseline
MIN_BASELINE = 5    # hari minimum sebelum peringatan dapat dihitung
Z_THRESH = 3.0
COLS = ["tanggal", "jenis", "tingkat", "nilai", "baseline", "z", "penjelasan"]
LIMITS = [
    "Peringatan dihitung dari berkas yang diunggah, bukan aliran data real-time.",
    "Ambang statistik bersifat heuristik; peristiwa nyata (berita besar, kampanye resmi) juga memicu lonjakan.",
    f"Baseline memakai {WINDOW} hari sebelumnya dan butuh minimal {MIN_BASELINE} hari data.",
]


def _robust(x: float, base: np.ndarray, floor_fn=None):
    med = float(np.median(base))
    mad = float(np.median(np.abs(base - med))) * 1.4826
    floor = floor_fn(med) if floor_fn else 1e-9
    sigma = max(mad, floor)
    return (x - med) / sigma, med


def _level(z: float) -> str:
    return "Tinggi" if z >= 6 else "Sedang" if z >= 4 else "Rendah"


def daily_series(d: pd.DataFrame) -> pd.DataFrame:
    """Rangkuman harian: volume, jumlah negatif, porsi negatif, rata-rata skor sentimen (hari kosong = volume 0)."""
    if d.empty:
        raise ValueError("Tidak ada data untuk dianalisis.")
    g = d.groupby("date")
    daily = pd.DataFrame({"volume": g.size(), "negatif": g["sentimen"].apply(lambda s: int((s == "Negatif").sum())),
                          "skor_sentimen": g["skor_sentimen"].mean() if "skor_sentimen" in d.columns else 0.0})
    daily.index = pd.to_datetime(daily.index)
    full = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full)
    daily["volume"] = daily["volume"].fillna(0).astype(int)
    daily["negatif"] = daily["negatif"].fillna(0).astype(int)
    daily["porsi_negatif"] = np.where(daily["volume"] > 0, daily["negatif"] / daily["volume"].where(daily["volume"] > 0, 1), np.nan)
    daily.index.name = "tanggal"
    return daily.reset_index()


def volume_alerts(daily: pd.DataFrame, window=WINDOW, z_thresh=Z_THRESH, min_baseline=MIN_BASELINE, min_increase=5) -> list:
    vol, dates, out, prev = daily["volume"].to_numpy(float), daily["tanggal"], [], False
    for i in range(min_baseline, len(daily)):
        base = vol[max(0, i - window):i]
        z, med = _robust(vol[i], base, lambda m: np.sqrt(max(m, 1.0)))
        hit = z >= z_thresh and vol[i] - med >= min_increase
        if hit:
            kind = "Lonjakan volume (berlanjut)" if prev else "Lonjakan volume percakapan"
            out.append(dict(tanggal=dates.iloc[i].date(), jenis=kind, tingkat=_level(z), nilai=vol[i], baseline=med, z=round(z, 1),
                            penjelasan=f"{int(vol[i])} postingan vs baseline median {med:.0f}/hari ({window} hari sebelumnya)."))
        prev = hit
    return out


def sentiment_alerts(daily: pd.DataFrame, window=WINDOW, z_thresh=Z_THRESH, min_baseline=MIN_BASELINE,
                     min_posts=10, min_delta=0.15) -> list:
    share, vol, dates, out = daily["porsi_negatif"].to_numpy(float), daily["volume"].to_numpy(float), daily["tanggal"], []
    for i in range(min_baseline, len(daily)):
        base = share[max(0, i - window):i]
        base = base[~np.isnan(base)]
        if vol[i] < min_posts or len(base) < min_baseline - 1 or np.isnan(share[i]):
            continue
        p = float(np.clip(np.median(base), 0.01, 0.99))
        z, med = _robust(share[i], base, lambda m: np.sqrt(p * (1 - p) / max(vol[i], 1)))
        delta = share[i] - med
        if abs(z) >= z_thresh and abs(delta) >= min_delta:
            neg = delta > 0
            out.append(dict(tanggal=dates.iloc[i].date(),
                            jenis="Kenaikan porsi sentimen negatif" if neg else "Penurunan porsi sentimen negatif",
                            tingkat=_level(abs(z)) if neg else "Rendah", nilai=round(share[i] * 100, 1), baseline=round(med * 100, 1),
                            z=round(abs(z), 1),
                            penjelasan=f"Porsi sentimen negatif {share[i]:.0%} vs baseline {med:.0%} ({int(vol[i])} postingan)."))
    return out


def account_alerts(d: pd.DataFrame, z_thresh=4.0, min_count=10, top=5) -> list:
    """Akun dengan jumlah unggahan harian jauh di atas pola akun-hari lain (robust z-score)."""
    per = d.groupby(["date", "username"]).size().reset_index(name="n")
    if len(per) < 10:
        return []
    med = float(per["n"].median())
    mad = float(np.median(np.abs(per["n"] - med))) * 1.4826
    sigma = max(mad, np.sqrt(max(med, 1.0)))
    per["z"] = (per["n"] - med) / sigma
    hit = per[(per["z"] >= z_thresh) & (per["n"] >= min_count)]
    out = []
    for day, g in hit.groupby("date"):
        g = g.sort_values("n", ascending=False)
        names = ", ".join(f"{r.username} ({r.n})" for r in g.head(top).itertuples())
        zmax = float(g["z"].max())
        out.append(dict(tanggal=day, jenis="Aktivitas unggahan tidak biasa", tingkat=_level(zmax), nilai=float(len(g)), baseline=med,
                        z=round(zmax, 1), penjelasan=f"{len(g)} akun jauh di atas pola unggahan harian (median {med:.0f}/akun/hari): "
                                                      f"{names}{' ...' if len(g) > top else ''}."))
    return out


def run_early_warning(d: pd.DataFrame, window=WINDOW, z_thresh=Z_THRESH) -> dict:
    daily = daily_series(d)
    notes = []
    if len(daily) < MIN_BASELINE + 1:
        notes.append(f"Data hanya {len(daily)} hari; minimal {MIN_BASELINE + 1} hari dibutuhkan untuk membangun baseline.")
    rows = volume_alerts(daily, window, z_thresh) + sentiment_alerts(daily, window, z_thresh) + account_alerts(d)
    vol_days = {r["tanggal"] for r in rows if r["jenis"].startswith("Lonjakan volume")}
    for r in rows:   # perubahan komposisi sentimen saat volume melonjak sering hanya efek teks berulang
        if r["jenis"].endswith("sentimen negatif") and r["tanggal"] in vol_days:
            r["penjelasan"] += " Terjadi bersamaan dengan lonjakan volume: perubahan komposisi dapat dipicu teks yang berulang."
    alerts = pd.DataFrame(rows, columns=COLS)
    if not alerts.empty:
        alerts = alerts.sort_values(["tanggal", "z"], ascending=[False, False]).reset_index(drop=True)
    return {"daily": daily, "alerts": alerts, "notes": notes, "limitations": LIMITS}
