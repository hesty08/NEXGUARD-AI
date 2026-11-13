"""Bot Analyzer V6 - investigasi aktivitas akun (skor risiko, koordinasi, penjelasan, ringkasan, evaluasi).

Modul ini murni pandas/numpy/networkx (tanpa Streamlit) agar mudah diuji. Semua angka dihitung dari data yang
diunggah; tidak ada nilai acak atau hasil bawaan. Skor adalah RINGKASAN INDIKATOR yang dapat diperiksa, bukan
probabilitas, dan bukan vonis bahwa suatu akun adalah bot.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np
import pandas as pd

COORD_MIN_EXTRA = 2
MIN_POSTS = 5               
MIN_WINDOW_DAYS = 0.25      
MAX_ROWS = 200_000          
TAG_MIN_ACCOUNTS = 3        
THRESH_MID, THRESH_HIGH = 30, 60
ACTIVE_RATIO = 0.4          
MIN_ACTIVE_HIGH, MIN_ACTIVE_MID = 3, 2   
CORE_COLS = ("timestamp", "username", "text")
LEVELS = ["Tinggi", "Sedang", "Rendah", "Data Tidak Cukup"]
MIN_ACCOUNTS_RELIABLE = 10          
MIN_LABELED, MIN_PRED_POS = 20, 5   
PRIORITY_ORDER = {"TINGGI": 0, "SEDANG": 1, "RENDAH": 2, "-": 3}
STATUS_DEF = {  # kode -> (label Indonesia, warna)
    "ANALYSIS COMPLETED": ("ANALISIS SELESAI", "#00e676"),
    "HIGH-RISK ACTIVITY DETECTED": ("RISIKO TINGGI TERDETEKSI", "#ff4d4d"),
    "COORDINATED PATTERN IDENTIFIED": ("INDIKATOR KOORDINASI TERDETEKSI", "#ffb020"),
    "INSUFFICIENT DATA": ("DATA TIDAK MEMADAI", "#8a97a8"),
}
OVERALL_COLOR = {"KRITIS": "#ff1744", "TINGGI": "#ff4d4d", "SEDANG": "#ffb020", "RENDAH": "#00e676"}

# key, nama, bobot maksimum (total 100), batas bawah, batas atas, inv = semakin KECIL semakin berisiko
INDICATORS = [
    dict(key="freq", nama="Frekuensi posting", maks=20, lo=20.0, hi=100.0, inv=False, kolom="posts_per_day"),
    dict(key="interval", nama="Jeda posting seragam", maks=25, lo=10.0, hi=120.0, inv=True, kolom="interval_spread_sec"),
    dict(key="repeat", nama="Pengulangan konten", maks=25, lo=0.2, hi=0.8, inv=False, kolom="duplicate_ratio"),
    dict(key="similar", nama="Kemiripan dengan akun lain", maks=15, lo=0.1, hi=0.7, inv=False, kolom="pct_similar"),
    dict(key="sync", nama="Posting serempak", maks=10, lo=0.05, hi=0.5, inv=False, kolom="sync_share"),
    dict(key="tags", nama="Tagar seragam", maks=5, lo=0.3, hi=1.0, inv=False, kolom="tag_overlap"),
]
IND = {i["key"]: i for i in INDICATORS}

LIMITATIONS = [
    "Pola mirip bot juga muncul pada akun resmi, akun layanan/berita otomatis, dan pengguna yang sangat aktif.",
    "Perhitungan hanya memakai data yang diunggah (waktu, username, teks); konteks di luar data tidak diketahui.",
    "Bobot dan ambang indikator bersifat heuristik dan belum divalidasi pada dataset akun berlabel yang besar.",
    "Kemiripan teks dan kedekatan waktu bisa terjadi secara wajar (isu viral, kutipan berita, tagar populer).",
    "Hasil adalah alasan untuk meninjau akun secara manual, bukan bukti identitas atau niat suatu akun.",
]


# ----------------------------------------------------------------------------- utilitas
def fmt_interval(sec) -> str:
    """Detik -> teks singkat (mis. '2 mnt 05 dtk', '3 jam 12 mnt', '1 hr 4 jam')."""
    if sec is None or (isinstance(sec, float) and np.isnan(sec)):
        return "-"
    sec = float(sec)
    if sec < 60:
        return f"{sec:.0f} dtk"
    if sec < 3600:
        return f"{int(sec // 60)} mnt {int(sec % 60):02d} dtk"
    if sec < 86400:
        return f"{int(sec // 3600)} jam {int((sec % 3600) // 60):02d} mnt"
    return f"{int(sec // 86400)} hr {int((sec % 86400) // 3600)} jam"


def alias(name: str, salt: str = "cs") -> str:
    """Alias stabil untuk menyamarkan nama akun pada tampilan/laporan."""
    return "akun_" + hashlib.sha256((salt + str(name)).encode()).hexdigest()[:6]


def _ramp(x: np.ndarray, ind: dict) -> np.ndarray:
    """0..1 linear antara batas bawah dan atas; NaN dihitung 0."""
    x = np.asarray(x, dtype=float)
    lo, hi = ind["lo"], ind["hi"]
    r = (hi - x) / (hi - lo) if ind["inv"] else (x - lo) / (hi - lo)
    return np.nan_to_num(np.clip(r, 0, 1), nan=0.0)


# ----------------------------------------------------------------------------- persiapan data
def prepare(posts: pd.DataFrame):
    """Validasi dan bersihkan CSV postingan. Kembalikan (p, baris_dilewati, terpotong)."""
    missing = [c for c in CORE_COLS if c not in posts.columns]
    if missing:
        raise ValueError("CSV postingan harus berisi kolom: timestamp, username, text (kurang: " + ", ".join(missing) + ").")
    p = posts[list(CORE_COLS)].copy()
    n0 = len(p)
    p = p.dropna(subset=["timestamp", "username", "text"])
    p["ts"] = pd.to_datetime(p["timestamp"].astype(str), errors="coerce", format="mixed")
    p["username"] = p["username"].astype(str).str.strip()
    p["text"] = p["text"].astype(str)
    p = p[p["ts"].notna() & (p["username"] != "") & (p["text"].str.strip() != "")]
    dropped = n0 - len(p)
    if p.empty:
        raise ValueError("Tidak ada baris valid. Pastikan timestamp dapat dibaca (contoh 2026-10-21 14:30:00), "
                         "serta username dan text tidak kosong.")
    truncated = len(p) > MAX_ROWS
    p = p.sort_values("ts", kind="stable").head(MAX_ROWS).reset_index(drop=True)
    p["norm"] = p["text"].str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
    p["tags"] = p["text"].str.lower().str.findall(r"#(\w+)")
    p["is_repeat"] = (p["norm"] != "") & (p.groupby("norm")["norm"].transform("size") > 1)
    return p, int(dropped), bool(truncated)


def account_features(p: pd.DataFrame) -> pd.DataFrame:
    """Fitur perilaku per akun: total posting, frekuensi, jeda, penyebaran jeda (MAD), pengulangan."""
    q = p.sort_values(["username", "ts"], kind="stable")
    q = q.assign(_gap=q.groupby("username")["ts"].diff().dt.total_seconds())
    g = q.groupby("username", sort=True)
    n, first, last = g.size(), g["ts"].min(), g["ts"].max()
    n_gap, mean_gap, med_gap = g["_gap"].count(), g["_gap"].mean(), g["_gap"].median()
    dev = (q["_gap"] - q["username"].map(med_gap)).abs()
    spread = (dev.groupby(q["username"]).median() * 1.4826).where(n_gap > 1)
    span = ((last - first).dt.total_seconds() / 86400).clip(lower=MIN_WINDOW_DAYS)
    out = pd.DataFrame({"n_posts": n, "span_days": span, "posts_per_day": n / span, "mean_gap_sec": mean_gap,
                        "median_gap_sec": med_gap, "interval_spread_sec": spread,
                        "duplicate_ratio": 1 - g["norm"].nunique() / n, "first_ts": first, "last_ts": last})
    return out.reset_index().rename(columns={"index": "username"})


# ----------------------------------------------------------------------------- koordinasi
def _mark_sync(ts_ns: np.ndarray, codes: np.ndarray, win_ns: int, k: int):
    """Two-pointer: tandai postingan yang berada dalam jendela waktu berisi >= k akun berbeda. ts_ns terurut naik."""
    n = len(ts_ns)
    diff = np.zeros(n + 1, dtype=int)
    best, lo, win = 0, 0, Counter()
    for hi in range(n):
        win[codes[hi]] += 1
        while ts_ns[hi] - ts_ns[lo] > win_ns:
            c = codes[lo]
            win[c] -= 1
            if win[c] == 0:
                del win[c]
            lo += 1
        best = max(best, len(win))
        if len(win) >= k:
            diff[lo] += 1
            diff[hi + 1] -= 1
    return best, np.cumsum(diff[:n]) > 0


def detect_coordination(p: pd.DataFrame, threshold: float = 0.8, window_min: int = 15, min_accounts: int = 3):
    """Deteksi teks identik/mirip lintas akun, kedekatan waktu, tagar bersama, dan graf hubungan antar-akun.
    Mengembalikan (p dengan kolom klaster/similar_xacc/sync, tabel_klaster, tabel_tagar, graf, info)."""
    import network
    from social import to_ns
    d = p[["username", "text", "ts"]].rename(columns={"ts": "timestamp"})
    dd, capped = network.cluster_texts(d, threshold)         # indeks p dipertahankan
    p = p.copy()
    p["klaster"], p["similar_xacc"], p["sync"] = np.nan, False, False
    cols = ["klaster", "contoh_teks", "jumlah_akun", "jumlah_post", "akun_serempak", "serempak", "mulai", "selesai", "akun"]
    rows = []
    if len(dd):
        n_acc = dd.groupby("klaster")["username"].nunique()
        multi = n_acc[n_acc >= 2].index
        p.loc[dd.index, "klaster"] = dd["klaster"]
        p.loc[dd.index[dd["klaster"].isin(multi)], "similar_xacc"] = True
        labels = dd.index.to_numpy()
        z = dd.reset_index(drop=True)
        ts_ns, _ = to_ns(z["timestamp"])
        codes, users, texts = pd.factorize(z["username"])[0], z["username"].to_numpy(), z["text"].to_numpy()
        groups = z.groupby("klaster").indices
        sync_pos = np.zeros(len(z), dtype=bool)
        win_ns = int(window_min) * 60 * 1_000_000_000
        for cid in n_acc[n_acc >= min_accounts].index:
            idx = groups[cid]
            order = idx[np.argsort(ts_ns[idx], kind="stable")]
            best, mark = _mark_sync(ts_ns[order], codes[order], win_ns, min_accounts)
            sync_pos[order[mark]] = True
            accs = sorted(set(users[idx]))
            rows.append(dict(klaster=int(cid), contoh_teks=str(texts[order[0]])[:120], jumlah_akun=len(accs), jumlah_post=len(idx),
                             akun_serempak=int(best), serempak=bool(best >= min_accounts),
                             mulai=z["timestamp"].iloc[order[0]], selesai=z["timestamp"].iloc[order[-1]],
                             akun=", ".join(accs[:10]) + (" ..." if len(accs) > 10 else "")))
        p.loc[labels[sync_pos], "sync"] = True
    clusters = pd.DataFrame(rows, columns=cols)
    if len(clusters):
        clusters = clusters.sort_values(["serempak", "jumlah_akun", "jumlah_post"], ascending=False).reset_index(drop=True)
    # tagar bersama
    tg = p[["username", "tags"]].explode("tags").dropna(subset=["tags"])
    tags_tbl = pd.DataFrame(columns=["tagar", "jumlah_akun", "jumlah_post"])
    if len(tg):
        agg = tg.groupby("tags").agg(jumlah_akun=("username", "nunique"), jumlah_post=("username", "size")).reset_index()
        agg = agg.rename(columns={"tags": "tagar"})
        tags_tbl = agg[agg["jumlah_akun"] >= TAG_MIN_ACCOUNTS].sort_values(["jumlah_akun", "jumlah_post"], ascending=False).reset_index(drop=True)
    G, ginfo = network.build_graph(d, threshold, window_min, min_accounts=2)
    return p, clusters, tags_tbl, G, {"capped": bool(capped) or bool(ginfo.get("capped")), "trimmed": bool(ginfo.get("trimmed"))}


def _tag_overlap(p: pd.DataFrame, tags_tbl: pd.DataFrame) -> pd.Series:
    """Porsi tagar milik akun yang juga dipakai >= TAG_MIN_ACCOUNTS akun berbeda (NaN bila akun tak memakai tagar)."""
    tg = p[["username", "tags"]].explode("tags").dropna(subset=["tags"]).drop_duplicates()
    if tg.empty:
        return pd.Series(dtype=float)
    shared = set(tags_tbl["tagar"]) if len(tags_tbl) else set()
    return tg.assign(s=tg["tags"].isin(shared)).groupby("username")["s"].mean()


# ----------------------------------------------------------------------------- skor
def _detail(key: str, r) -> str:
    if key == "freq":
        return f"{r.posts_per_day:.0f} post/hari"
    if key == "interval":
        return f"median jeda {fmt_interval(r.median_gap_sec)}, penyebaran jeda {r.interval_spread_sec:.0f} dtk"
    if key == "repeat":
        return f"{r.duplicate_ratio:.0%} konten berulang"
    if key == "similar":
        return f"{r.pct_similar:.0%} postingan mirip dengan akun lain"
    if key == "sync":
        return f"{r.sync_share:.0%} postingan serempak dengan akun lain"
    return f"{r.tag_overlap:.0%} tagarnya juga dipakai >= {TAG_MIN_ACCOUNTS} akun lain"


def score_accounts(feats: pd.DataFrame, has_tags: bool):
    """Hitung skor risiko 0-100 per akun dari indikator yang tersedia. Kembalikan (res, signals)."""
    inds = [i for i in INDICATORS if i["key"] != "tags" or has_tags]
    total_max = float(sum(i["maks"] for i in inds))
    f = feats.copy()
    pts, active = {}, {}
    for i in inds:
        r = _ramp(f[i["kolom"]].to_numpy(), i)
        pts[i["key"]] = r * i["maks"]
        active[i["key"]] = r >= ACTIVE_RATIO
    score = sum(pts.values()) / total_max * 100
    n_active = sum(a.astype(int) for a in active.values())
    base = np.where(score >= THRESH_HIGH, "Tinggi", np.where(score >= THRESH_MID, "Sedang", "Rendah")).astype(object)
    level, held = base.copy(), np.zeros(len(f), dtype=bool)
    m = (level == "Tinggi") & (n_active < MIN_ACTIVE_HIGH)
    level[m], held[m] = "Sedang", True
    m = (level == "Sedang") & (n_active < MIN_ACTIVE_MID)
    level[m], held[m] = "Rendah", True
    insufficient = f["n_posts"].to_numpy() < MIN_POSTS
    level[insufficient] = "Data Tidak Cukup"
    score = np.where(insufficient, 0.0, score)
    for k in pts:
        pts[k] = np.where(insufficient, 0.0, pts[k])
    rows, signals = [], {}
    for pos, r in enumerate(f.itertuples()):
        if insufficient[pos]:
            alasan, sig = f"Hanya {int(r.n_posts)} postingan (minimal {MIN_POSTS} untuk dinilai)", []
        else:
            sig = sorted([(IND[k]["nama"], int(round(pts[k][pos])), _detail(k, r)) for k in pts if active[k][pos]],
                         key=lambda x: -x[1])
            alasan = "; ".join(f"{n} ({d})" for n, _, d in sig) or "-"
            if held[pos]:
                alasan += f" [kategori ditahan: hanya {int(n_active[pos])} indikator aktif]"
        signals[r.username] = sig
        rows.append(alasan)
    res = pd.DataFrame({"username": f["username"], "skor_bot": np.round(score).astype(int), "level": level, "alasan": rows,
                        "n_posts": f["n_posts"].astype(int), "n_aktif": n_active.astype(int), "ditahan": held})
    for k in pts:
        res["poin_" + k] = np.round(pts[k], 1)
    res = res.sort_values(["skor_bot", "n_posts"], ascending=False).reset_index(drop=True)
    return res, signals


# ----------------------------------------------------------------------------- analisis utama
def investigate(posts: pd.DataFrame, threshold: float = 0.8, window_min: int = 15, min_accounts: int = 3) -> dict:
    """Jalankan seluruh analisis. Hasil berupa dict: posts, feats, res, signals, clusters, tags, G, meta."""
    p, dropped, truncated = prepare(posts)
    feats = account_features(p)
    p, clusters, tags_tbl, G, ginfo = detect_coordination(p, threshold, window_min, min_accounts)
    feats["pct_similar"] = feats["username"].map(p.groupby("username")["similar_xacc"].mean()).fillna(0.0)
    feats["sync_share"] = feats["username"].map(p.groupby("username")["sync"].mean()).fillna(0.0)
    feats["tag_overlap"] = feats["username"].map(_tag_overlap(p, tags_tbl))
    has_tags = bool(p["tags"].map(len).sum() > 0)
    res, signals = score_accounts(feats, has_tags)
    sync_by_user = feats.set_index("username")["sync_share"]
    res["prioritas"] = [investigation_priority(l, sc, float(sync_by_user.get(u, 0.0)))
                        for u, l, sc in zip(res["username"], res["level"], res["skor_bot"])]
    lvl = res.set_index("username")["level"]
    p["level"] = p["username"].map(lvl)
    span_days = float((p["ts"].max() - p["ts"].min()).total_seconds() / 86400)
    n_acc, n_insuf = int(len(res)), int((res["level"] == "Data Tidak Cukup").sum())
    warn = []
    if dropped:
        warn.append(f"{dropped} baris dilewati karena timestamp, username, atau teks kosong/tidak valid.")
    if truncated:
        warn.append(f"Data sangat besar: hanya {MAX_ROWS:,} postingan paling awal yang dianalisis.")
    if n_acc < 10:
        warn.append(f"Hanya {n_acc} akun pada data: pembanding antar-akun terbatas, hasil kurang andal.")
    if n_insuf:
        warn.append(f"{n_insuf} akun memiliki kurang dari {MIN_POSTS} postingan sehingga tidak dinilai (Data Tidak Cukup).")
    if n_acc and n_insuf == n_acc:
        warn.append("Tidak ada akun dengan data cukup; skor risiko tidak dapat dihitung.")
    if span_days < 1:
        warn.append("Rentang waktu data kurang dari 1 hari: frekuensi harian diekstrapolasi (jendela minimum 6 jam) dan kurang andal.")
    if not has_tags:
        warn.append("Tidak ditemukan tagar (#) pada teks: indikator tagar tidak dihitung dan bobot disesuaikan.")
    if ginfo["capped"]:
        warn.append("Data besar: hanya sebagian teks unik yang dibandingkan untuk kemiripan.")
    sig = hashlib.md5(pd.util.hash_pandas_object(p[["username", "ts", "text"]], index=False).to_numpy().tobytes()
                      + f"{threshold}|{window_min}|{min_accounts}".encode()).hexdigest()
    meta = dict(sig=sig, n_posts=int(len(p)), n_accounts=n_acc, n_insufficient=n_insuf, span_days=span_days, has_tags=has_tags,
                dropped=dropped, threshold=float(threshold), window_min=int(window_min), min_accounts=int(min_accounts),
                first_ts=p["ts"].min(), last_ts=p["ts"].max(), peringatan=warn)
    return dict(posts=p, feats=feats, res=res, signals=signals, clusters=clusters, tags=tags_tbl, G=G, meta=meta)


# ----------------------------------------------------------------------------- ringkasan dan penjelasan
def investigation_table(inv: dict) -> pd.DataFrame:
    """Tabel investigasi akun (angka mentah) untuk tampilan dan CSV."""
    f, r = inv["feats"].set_index("username"), inv["res"].set_index("username")
    t = pd.DataFrame({"username": r.index, "total_postingan": r["n_posts"].to_numpy(),
                      "rata_interval_detik": f.loc[r.index, "mean_gap_sec"].round(1).to_numpy(),
                      "rata_interval": [fmt_interval(v) for v in f.loc[r.index, "mean_gap_sec"]],
                      "persen_pengulangan": (f.loc[r.index, "duplicate_ratio"] * 100).round(1).to_numpy(),
                      "persen_mirip_akun_lain": (f.loc[r.index, "pct_similar"] * 100).round(1).to_numpy(),
                      "persen_serempak": (f.loc[r.index, "sync_share"] * 100).round(1).to_numpy(),
                      "skor_risiko": r["skor_bot"].to_numpy(), "kategori": r["level"].to_numpy(),
                      "prioritas": r["prioritas"].to_numpy(), "alasan": r["alasan"].to_numpy()})
    return t.reset_index(drop=True)


def wilson(k: int, n: int, z: float = 1.96):
    """Interval keyakinan Wilson 95% untuk proporsi k/n (NaN bila n = 0)."""
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    lo, hi = max(0.0, c - h), min(1.0, c + h)
    return (0.0 if k == 0 else lo), (1.0 if k == n else hi)   # batas eksak pada kasus ekstrem (hindari galat pembulatan)


def investigation_priority(level: str, score, sync_share: float) -> str:
    """Prioritas investigasi dari variabel terukur. TINGGI: kategori Tinggi dengan keterlibatan posting serempak atau skor >= 80;
    SEDANG: kategori Tinggi lainnya atau Sedang dengan posting serempak; RENDAH: kategori Sedang lainnya; '-' selain itu."""
    if level == "Tinggi" and (sync_share > 0 or score >= 80):
        return "TINGGI"
    if level == "Tinggi" or (level == "Sedang" and sync_share > 0):
        return "SEDANG"
    if level == "Sedang":
        return "RENDAH"
    return "-"


def active_threshold(key: str) -> float:
    """Nilai indikator saat indikator dianggap aktif (>= ACTIVE_RATIO dari bobot maksimum)."""
    i = IND[key]
    span = i["hi"] - i["lo"]
    return i["hi"] - ACTIVE_RATIO * span if i["inv"] else i["lo"] + ACTIVE_RATIO * span


def _value_text(key: str, f) -> str:
    v = f[IND[key]["kolom"]]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "tanpa tagar" if key == "tags" else "-"
    return {"freq": f"{v:.0f} post/hari", "interval": f"penyebaran jeda {v:.0f} dtk"}.get(key, f"{v:.0%}")


def _threshold_text(key: str) -> str:
    th = active_threshold(key)
    return {"freq": f">= {th:.0f} post/hari", "interval": f"<= {th:.0f} dtk"}.get(key, f">= {th:.0%}")


def evidence(inv: dict, username: str) -> list:
    """Bukti terukur per indikator untuk satu akun: nilai, ambang aktif, poin, dan status aktif."""
    f = inv["feats"].set_index("username").loc[username]
    r = inv["res"].set_index("username").loc[username]
    rows = []
    for i in INDICATORS:
        if i["key"] == "tags" and not inv["meta"]["has_tags"]:
            continue
        pts = float(r["poin_" + i["key"]])
        rows.append(dict(indikator=i["nama"], nilai=_value_text(i["key"], f), ambang=_threshold_text(i["key"]), poin=pts, maks=i["maks"],
                         aktif=bool(pts >= ACTIVE_RATIO * i["maks"] and r["level"] != "Data Tidak Cukup")))
    return rows


def summarize(inv: dict) -> dict:
    """Ringkasan investigasi otomatis: seluruh angka dan kalimat dihitung dari hasil analisis CSV (bukan teks tetap)."""
    res, meta, cl = inv["res"], inv["meta"], inv["clusters"]
    cnt = {k: int((res["level"] == k).sum()) for k in LEVELS}
    n_eval = cnt["Tinggi"] + cnt["Sedang"] + cnt["Rendah"]
    pct_high = cnt["Tinggi"] / n_eval if n_eval else 0.0
    pct_susp = (cnt["Tinggi"] + cnt["Sedang"]) / n_eval if n_eval else 0.0
    evald = res[res["level"] != "Data Tidak Cukup"]
    main = []
    for i in INDICATORS:
        k = i["key"]
        if k == "tags" and not meta["has_tags"]:
            continue
        n_act = int((evald["poin_" + k] >= ACTIVE_RATIO * i["maks"]).sum())
        if n_act:
            main.append((i["nama"], n_act))
    main.sort(key=lambda x: -x[1])
    n_sync = int(cl["serempak"].sum()) if len(cl) else 0
    prio = {k: int((res["prioritas"] == k).sum()) for k in ("TINGGI", "SEDANG", "RENDAH")}
    susp = cnt["Tinggi"] + cnt["Sedang"]
    if n_eval == 0:
        conclusion = f"INSUFFICIENT DATA. Tidak ada akun dengan minimal {MIN_POSTS} postingan, sehingga klasifikasi risiko tidak dapat dihitung."
    elif n_eval < MIN_ACCOUNTS_RELIABLE:
        conclusion = (f"ANALISIS SELESAI dengan data terbatas: {n_eval} akun dinilai ({cnt['Tinggi']} Tinggi, {cnt['Sedang']} Sedang). "
                      f"Jumlah akun di bawah {MIN_ACCOUNTS_RELIABLE}; tambahkan data sebelum menarik kesimpulan agregat.")
    elif susp == 0:
        conclusion = f"ANALISIS SELESAI. Tidak ada anomali aktivitas teridentifikasi: seluruh {n_eval} akun yang dinilai berkategori Rendah."
    else:
        conclusion = (f"ANALISIS SELESAI. ANOMALI AKTIVITAS TERIDENTIFIKASI pada {susp} dari {n_eval} akun ({pct_susp:.0%}): "
                      f"{cnt['Tinggi']} RISIKO TINGGI dan {cnt['Sedang']} SEDANG. ")
        conclusion += (f"KLASTER AKTIVITAS TERIDENTIFIKASI: {len(cl)} klaster teks mirip, {n_sync} serempak. " if len(cl)
                       else "Tidak ada klaster aktivitas teridentifikasi pada ambang yang dipilih. ")
        conclusion += "Klasifikasi berbasis indikator terukur; konfirmasi identitas akun memerlukan validasi metadata."
    rec = []
    if prio["TINGGI"]:
        rec.append(f"Investigasi {prio['TINGGI']} akun berprioritas TINGGI lebih dulu: verifikasi metadata akun (usia, pengikut, profil) dan konteks isi.")
    elif cnt["Tinggi"]:
        rec.append(f"Investigasi {cnt['Tinggi']} akun berkategori Tinggi: verifikasi metadata akun (usia, pengikut, profil) dan konteks isi.")
    if n_sync:
        rec.append(f"Telusuri {n_sync} klaster serempak: bandingkan sumber teks asli dan urutan waktu posting antar akun.")
    if cnt["Sedang"]:
        rec.append(f"Pantau {cnt['Sedang']} akun kategori Sedang pada periode data berikutnya.")
    if meta["n_insufficient"]:
        rec.append(f"Kumpulkan minimal {MIN_POSTS} postingan per akun untuk {meta['n_insufficient']} akun berstatus DATA TIDAK CUKUP.")
    rec.append("Dokumentasikan temuan (tangkapan layar dan tautan asli) sebagai barang bukti investigasi.")
    rec.append("Validasi akurasi dengan dataset berlabel pada panel Validasi sebelum hasil dipakai sebagai dasar keputusan.")
    return dict(
    counts=cnt,
    n_eval=n_eval,
    pct_high=pct_high,
    pct_susp=pct_susp,
    main_indicators=main,
    n_clusters=int(len(cl)),
    n_coord=int(cl["koordinasi"].sum()) if len(cl) and "koordinasi" in cl.columns else 0,
    n_partial=int(cl["parsial"].sum()) if len(cl) and "parsial" in cl.columns else 0,
    n_sync=n_sync,
    conclusion=conclusion,
     priorities=prio,
    recommendations=rec
)
    

    

def analysis_status(inv: dict) -> list:
    """Status analisis (kode, label, warna, keterangan) yang dihitung dari hasil: tidak ada status tetap."""
    s = summarize(inv)
    meta, out = inv["meta"], []

    def add(code, desc):
        out.append(dict(code=code, label=STATUS_DEF[code][0], color=STATUS_DEF[code][1], desc=desc))
    if s["n_eval"] == 0:
        add("INSUFFICIENT DATA", f"Tidak ada akun dengan minimal {MIN_POSTS} postingan.")
        return out
    add("ANALYSIS COMPLETED", f"{s['n_eval']} akun dinilai dari {meta['n_posts']:,} postingan.")
    if s["n_eval"] < MIN_ACCOUNTS_RELIABLE:
        add("INSUFFICIENT DATA", f"Jumlah akun dinilai ({s['n_eval']}) di bawah {MIN_ACCOUNTS_RELIABLE}; kesimpulan agregat belum memadai.")
    if s["counts"]["Tinggi"]:
        add("HIGH-RISK ACTIVITY DETECTED", f"{s['counts']['Tinggi']} akun berkategori Tinggi ({s['pct_high']:.0%} dari akun dinilai).")
    if s["n_sync"]:
        add("COORDINATED PATTERN IDENTIFIED", f"{s['n_sync']} klaster teks mirip diposting serempak (jendela {meta['window_min']} menit).")
    return out


def overall_risk(inv: dict):
    """Tingkat risiko keseluruhan dataset (RENDAH, SEDANG, TINGGI, KRITIS) dari proporsi akun Tinggi dan klaster serempak."""
    s = summarize(inv)
    if s["n_eval"] == 0:
        return None
    hi, sy = s["pct_high"], s["n_sync"]
    if hi >= 0.30:
        return "KRITIS"
    if hi >= 0.15 or (sy and s["counts"]["Tinggi"] >= 3):
        return "TINGGI"
    if s["counts"]["Tinggi"] or s["counts"]["Sedang"] / s["n_eval"] >= 0.10 or sy:
        return "SEDANG"
    return "RENDAH"


def confidence(ev) -> dict:
    """Tingkat keyakinan klasifikasi: hanya dari presisi terukur pada dataset berlabel (interval Wilson). Tanpa itu: tidak dihitung."""
    if ev is None:
        return dict(tersedia=False, label="TIDAK DIHITUNG",
                    detail="Tingkat keyakinan hanya ditampilkan setelah sistem diuji pada dataset berlabel. Unggah label pada panel Validasi untuk menghitung presisi terukur.")
    if ev["n"] < MIN_LABELED or (ev["tp"] + ev["fp"]) < MIN_PRED_POS:
        return dict(tersedia=False, label="DATA LABEL BELUM CUKUP",
                    detail=f"{ev['n']} akun berlabel dengan {ev['tp'] + ev['fp']} prediksi positif; dibutuhkan minimal {MIN_LABELED} akun dan {MIN_PRED_POS} prediksi positif.")
    lo, hi = ev["precision_ci"]
    return dict(tersedia=True, label=f"{ev['precision']:.0%}",
                detail=(f"Presisi terukur kategori {ev['positive_from']} pada {ev['n']} akun berlabel ({ev['tp']} benar dari {ev['tp'] + ev['fp']} prediksi positif); "
                        f"interval keyakinan 95% (Wilson) {lo:.0%} - {hi:.0%}. Berlaku untuk data sejenis dataset berlabel tersebut."))



def executive_summary(inv: dict, ev=None) -> dict:
    """Ringkasan eksekutif berdasarkan hasil analisis dan bukti terukur."""
    s = summarize(inv)
    meta = inv["meta"]
    cl = inv["clusters"]
    res = inv["res"]

    cnt = s["counts"]
    n_eval = s["n_eval"]
    level = overall_risk(inv)

    # ---------------------------------------------------------
    # Tingkat risiko dan alasan penetapan
    # ---------------------------------------------------------
    if level is None:
        headline = (
            "STATUS: INSUFFICIENT DATA. "
            "Tingkat risiko keseluruhan tidak dapat dihitung."
        )
        reason = (
            f"Tidak ada akun yang memenuhi jumlah minimum "
            f"{MIN_POSTS} postingan. Data belum cukup untuk "
            "menetapkan tingkat risiko keseluruhan."
        )
    else:
        headline = (
            f"TINGKAT RISIKO KESELURUHAN: {level}. "
            f"{cnt['Tinggi']} dari {n_eval} akun dinilai "
            f"({s['pct_high']:.0%}) memenuhi kriteria RISIKO TINGGI"
            + (
                f"; {s['n_sync']} klaster aktivitas serempak teridentifikasi."
                if s["n_sync"]
                else "; tidak ada klaster serempak teridentifikasi."
            )
        )

        if level == "KRITIS":
            reason = (
                f"Kategori KRITIS ditetapkan karena proporsi akun "
                f"berkategori Tinggi mencapai {s['pct_high']:.0%} "
                "dari seluruh akun yang dapat dinilai."
            )
        elif level == "TINGGI":
            reason = (
                f"Kategori TINGGI ditetapkan berdasarkan proporsi "
                f"akun berkategori Tinggi sebesar {s['pct_high']:.0%}"
                + (
                    f" dan terdapat {s['n_sync']} klaster serempak."
                    if s["n_sync"]
                    else "."
                )
            )
        elif level == "SEDANG":
            reason = (
                f"Kategori SEDANG ditetapkan berdasarkan temuan "
                f"{cnt['Tinggi']} akun berkategori Tinggi, "
                f"{cnt['Sedang']} akun berkategori Sedang, "
                f"dan {s['n_sync']} klaster serempak."
            )
        else:
            reason = (
                "Kategori RENDAH ditetapkan karena tidak ditemukan "
                "proporsi risiko tinggi atau pola aktivitas serempak "
                "yang memenuhi ambang penetapan kategori lebih tinggi."
            )

    # ---------------------------------------------------------
    # Temuan utama
    # ---------------------------------------------------------
    findings = [
        f"Cakupan: {meta['n_posts']:,} postingan dari "
        f"{meta['n_accounts']:,} akun, periode "
        f"{meta['first_ts']:%d-%m-%Y} s.d. "
        f"{meta['last_ts']:%d-%m-%Y} ({meta['span_days']:.1f} hari).",
        f"Distribusi risiko: Tinggi {cnt['Tinggi']}, "
        f"Sedang {cnt['Sedang']}, Rendah {cnt['Rendah']}, "
        f"Data Tidak Cukup {cnt['Data Tidak Cukup']}."
    ]

    if len(cl):
        n_acc_cl = int(
            inv["posts"]
            .loc[
                inv["posts"]["klaster"].isin(cl["klaster"]),
                "username"
            ]
            .nunique()
        )

        findings.append(
            f"KLASTER AKTIVITAS TERIDENTIFIKASI: {len(cl)} "
            f"klaster teks mirip lintas akun "
            f"(ambang kemiripan {meta['threshold']:.2f}); "
            f"{s['n_sync']} serempak dalam jendela "
            f"{meta['window_min']} menit; {n_acc_cl} akun terlibat."
        )
    else:
        findings.append(
            f"Tidak ada klaster aktivitas teridentifikasi pada "
            f"ambang kemiripan {meta['threshold']:.2f} "
            f"dan minimal {meta['min_accounts']} akun."
        )

    hi = res[res["level"] == "Tinggi"]

    if len(hi):
        findings.append(
            f"Akun risiko tinggi: skor median "
            f"{hi['skor_bot'].median():.0f} "
            f"(rentang {int(hi['skor_bot'].min())}-"
            f"{int(hi['skor_bot'].max())}); "
            f"{int((hi['prioritas'] == 'TINGGI').sum())} "
            f"akun berprioritas investigasi TINGGI; "
            f"rata-rata {hi['n_aktif'].mean():.1f} "
            "indikator aktif per akun."
        )

    # ---------------------------------------------------------
    # Indikator pendukung
    # ---------------------------------------------------------
    support = [
        (name, count, count / n_eval if n_eval else 0.0)
        for name, count in s["main_indicators"]
    ]

    # ---------------------------------------------------------
    # Akun prioritas investigasi
    # ---------------------------------------------------------
    order = (
        res[res["prioritas"] != "-"]
        .assign(o=lambda d: d["prioritas"].map(PRIORITY_ORDER))
        .sort_values(["o", "skor_bot"], ascending=[True, False])
        .head(10)
    )

    top = [
        dict(
            username=r.username,
            skor=int(r.skor_bot),
            prioritas=r.prioritas,
            kategori=r.level,
            dasar=", ".join(
                name
                for name, _, _ in
                inv["signals"].get(r.username, [])[:3]
            ) or "-"
        )
        for r in order.itertuples()
    ]

    # ---------------------------------------------------------
    # Catatan prioritas dan kriteria investigasi
    # ---------------------------------------------------------
    priorities = s["priorities"]

    priority_note = (
        f"Terdapat {priorities['TINGGI']} akun berprioritas TINGGI, "
        f"{priorities['SEDANG']} akun berprioritas SEDANG, dan "
        f"{priorities['RENDAH']} akun berprioritas RENDAH. "
        "Prioritas merupakan urutan pemeriksaan, bukan bukti bahwa "
        "akun merupakan bot."
    )

    priority_criteria = [
        "TINGGI: akun kategori Tinggi dengan aktivitas serempak "
        "atau skor risiko minimal 80.",
        "SEDANG: akun kategori Tinggi lainnya atau akun kategori "
        "Sedang yang memiliki aktivitas serempak.",
        "RENDAH: akun kategori Sedang tanpa aktivitas serempak.",
        "Tanda '-' berarti akun tidak masuk kategori prioritas "
        "berdasarkan kriteria tersebut."
    ]

    # ---------------------------------------------------------
    # Tingkat keyakinan dan validasi
    # ---------------------------------------------------------
    conf = confidence(ev)

    measured = [
        "Seluruh angka pada ringkasan ini dihitung langsung "
        "dari CSV yang dianalisis.",
        "Skor risiko merupakan jumlah poin indikator terukur; "
        "bobot dan ambang tercantum pada tab Metodologi."
    ]

    unvalidated = [
        "Identitas akun (bot atau pengguna asli) BELUM TERKONFIRMASI: "
        "skor risiko tidak membuktikan otomasi.",
        "Kemiripan teks dan kedekatan waktu dapat berasal dari isu viral; "
        "validasi dengan metadata akun dan konteks isi diperlukan."
    ]

    if not conf["tersedia"]:
        unvalidated.append(
            "Skor belum dikalibrasi terhadap dataset berlabel."
        )
    else:
        unvalidated.append(
            f"Akurasi diuji pada {ev['n']} akun berlabel "
            f"(presisi {ev['precision']:.0%}); berlaku untuk data sejenis."
        )

    # ---------------------------------------------------------
    # Hasil akhir
    # ---------------------------------------------------------
    return dict(
        statuses=analysis_status(inv),
        level=level,
        level_color=OVERALL_COLOR.get(level, "#8a97a8"),
        headline=headline,
        reason=reason,
        findings=findings,
        support=support,
        priorities=priorities,
        priority_note=priority_note,
        priority_criteria=priority_criteria,
        top=top,
        measured=measured,
        unvalidated=unvalidated,
        confidence=conf,
        recommendations=s["recommendations"],
        conclusion=s["conclusion"]
    )


def related_accounts(inv: dict, username: str, top: int = 5) -> list:
    """Akun yang paling terhubung dengan `username` pada graf (teks mirip, waktu berdekatan)."""
    G = inv["G"]
    if username not in G:
        return []
    out = [(n, int(d.get("mirip", 0)), int(d.get("serempak", 0)), float(d.get("weight", 0))) for n, d in
           ((n, G[username][n]) for n in G[username])]
    out.sort(key=lambda x: -x[3])
    return out[:top]


def explain_account(inv: dict, username: str) -> dict:
    """Laporan klasifikasi satu akun: alasan, bukti terukur, pola, prioritas, status validasi, dan rekomendasi."""
    r = inv["res"].set_index("username").loc[username]
    f = inv["feats"].set_index("username").loc[username]
    level, score, n, prio = r["level"], int(r["skor_bot"]), int(r["n_posts"]), r["prioritas"]
    sig = inv["signals"].get(username, [])
    rel = related_accounts(inv, username)
    notes = ["Skor adalah ringkasan indikator terukur (0-100), bukan probabilitas."]
    if level == "Data Tidak Cukup":
        return dict(ringkasan=f"INSUFFICIENT DATA. Akun {username} memiliki {n} postingan (minimal {MIN_POSTS}); klasifikasi tidak dihitung.",
                    indikator=[], bukti=[], pola=[], prioritas="-", status_validasi="Tidak diklasifikasikan.",
                    rekomendasi=[f"Kumpulkan minimal {MIN_POSTS} postingan akun ini agar dapat diklasifikasikan."], catatan=notes)
    names = [x[0].lower() for x in sig]
    if level == "Tinggi":
        head = (f"RISIKO TINGGI TERDETEKSI. Akun {username} memperoleh skor {score}/100 dengan {len(sig)} indikator aktif: "
                f"{', '.join(names)}. Prioritas investigasi: {prio}.")
        status = "Klasifikasi terukur dari data. Identitas akun (bot atau pengguna asli) BELUM TERKONFIRMASI; validasi metadata diperlukan."
    elif level == "Sedang":
        head = (f"ANOMALI AKTIVITAS TERIDENTIFIKASI. Akun {username} memperoleh skor {score}/100 (kategori Sedang); "
                f"indikator aktif: {', '.join(names) if names else 'tidak ada'}. Prioritas investigasi: {prio}.")
        status = "Klasifikasi terukur dari data. Identitas akun BELUM TERKONFIRMASI."
    else:
        head = (f"Tidak ada anomali signifikan. Akun {username} memperoleh skor {score}/100 (kategori Rendah)"
                + (f"; indikator terpantau: {', '.join(names)}." if names else "."))
        status = "Tidak ada temuan yang memerlukan validasi."
    if bool(r["ditahan"]):
        notes.append(f"Kategori ditahan satu tingkat: hanya {int(r['n_aktif'])} indikator aktif, di bawah syarat minimum kategori yang lebih tinggi.")
    pola = [f"Total {n} postingan dalam {f['span_days']:.1f} hari (rata-rata {f['posts_per_day']:.0f} post/hari).",
            f"Median jeda antarposting {fmt_interval(f['median_gap_sec'])}; rata-rata {fmt_interval(f['mean_gap_sec'])}.",
            f"Konten berulang {f['duplicate_ratio']:.0%}; mirip dengan akun lain {f['pct_similar']:.0%}; "
            f"serempak {f['sync_share']:.0%} (jendela {inv['meta']['window_min']} menit)."]
    if rel:
        pola.append("Keterhubungan tertinggi: " + ", ".join(f"{a} ({w} teks mirip, {s} serempak)" for a, w, s, _ in rel[:3]) + ".")
    rec = ["Verifikasi metadata akun (usia akun, foto, bio, jumlah pengikut) dan konteks isi postingan."]
    if f["duplicate_ratio"] >= active_threshold("repeat") or f["pct_similar"] >= active_threshold("similar"):
        rec.append("Bandingkan teks berulang dengan sumber aslinya (kutipan berita atau slogan kampanye resmi).")
    if rel:
        rec.append("Telusuri akun-akun terhubung di atas: bandingkan pola dan waktu posting.")
    if f["interval_spread_sec"] <= active_threshold("interval"):
        rec.append("Periksa apakah jeda seragam berasal dari penjadwal resmi (akun media atau layanan).")
    return dict(ringkasan=head, indikator=sig, bukti=evidence(inv, username), pola=pola, prioritas=prio, status_validasi=status,
                rekomendasi=rec, catatan=notes)


# ----------------------------------------------------------------------------- evaluasi dengan data berlabel
def _to_binary(v):
    s = str(v).strip().lower()
    if s in {"1", "1.0", "true", "ya", "yes", "bot", "y"}:
        return 1
    if s in {"0", "0.0", "false", "tidak", "no", "bukan", "bukan_bot", "bukan bot", "manusia", "human", "n"}:
        return 0
    return None


def evaluate_labels(res: pd.DataFrame, labels: pd.DataFrame, positive_from: str = "Tinggi") -> dict:
    """Bandingkan kategori sistem dengan label (kolom username, label). positive_from: 'Tinggi' atau 'Sedang'."""
    if not {"username", "label"}.issubset(labels.columns):
        raise ValueError("CSV berlabel harus berisi kolom: username, label (1/0 atau bot/bukan_bot).")
    lab = labels[["username", "label"]].copy()
    lab["username"] = lab["username"].astype(str).str.strip()
    lab["y"] = lab["label"].map(_to_binary)
    n_bad = int(lab["y"].isna().sum())
    lab = lab.dropna(subset=["y"]).drop_duplicates("username")
    m = lab.merge(res[["username", "level"]], on="username", how="inner")
    n_unmatched = int(len(lab) - len(m))
    n_insuf = int((m["level"] == "Data Tidak Cukup").sum())
    m = m[m["level"] != "Data Tidak Cukup"]
    pos_levels = {"Tinggi"} if positive_from == "Tinggi" else {"Tinggi", "Sedang"}
    y, yhat = m["y"].astype(int).to_numpy(), m["level"].isin(pos_levels).astype(int).to_numpy()
    tp, fp = int(((y == 1) & (yhat == 1)).sum()), int(((y == 0) & (yhat == 1)).sum())
    fn, tn = int(((y == 1) & (yhat == 0)).sum()), int(((y == 0) & (yhat == 0)).sum())
    div = lambda a, b: float(a / b) if b else float("nan")
    prec, rec = div(tp, tp + fp), div(tp, tp + fn)
    warn = []
    if len(m) < 20:
        warn.append(f"Hanya {len(m)} akun berlabel yang dapat dibandingkan; metrik belum stabil (disarankan >= 20 dan beragam).")
    if len(set(y.tolist())) < 2 and len(m):
        warn.append("Label hanya berisi satu kelas; presisi/recall tidak bermakna.")
    if n_unmatched:
        warn.append(f"{n_unmatched} username pada file label tidak ditemukan pada data postingan.")
    if n_insuf:
        warn.append(f"{n_insuf} akun berlabel dikecualikan karena Data Tidak Cukup.")
    if n_bad:
        warn.append(f"{n_bad} baris label tidak dikenali (gunakan 1/0 atau bot/bukan_bot).")
    return dict(n=int(len(m)), tp=tp, fp=fp, fn=fn, tn=tn, accuracy=div(tp + tn, len(m)), precision=prec, recall=rec,
                precision_ci=wilson(tp, tp + fp), recall_ci=wilson(tp, tp + fn),
                f1=(div(2 * prec * rec, prec + rec) if prec == prec and rec == rec else float("nan")),
                positive_from=positive_from, peringatan=warn)


def account_profile(inv: dict, username: str) -> dict:
    """Menghasilkan profil statistik dan timeline aktivitas satu akun."""
    feats = inv["feats"].set_index("username")
    res = inv["res"].set_index("username")

    if username not in feats.index or username not in res.index:
        raise KeyError(f"Akun tidak ditemukan: {username}")

    f = feats.loc[username]
    r = res.loc[username]

    posts = inv["posts"]
    timeline = posts.loc[posts["username"] == username].copy()
    timeline = timeline.sort_values("ts").reset_index(drop=True)

    # Pastikan kolom grafik tersedia.
    for col in ("is_repeat", "sync"):
        if col not in timeline.columns:
            timeline[col] = False

    median_ppd = float(feats["posts_per_day"].median())
    median_repeat = float(feats["duplicate_ratio"].median())

    return {
        "username": username,
        "level": str(r["level"]),
        "skor": int(r["skor_bot"]),
        "prioritas": str(r["prioritas"]),
        "n_posts": int(r["n_posts"]),
        "posts_per_day": float(f["posts_per_day"]),
        "median_ppd": median_ppd,
        "pct_repeat": float(f["duplicate_ratio"]),
        "median_repeat": median_repeat,
        "pct_similar": float(f.get("pct_similar", 0.0)),
        "pct_sync": float(f.get("sync_share", 0.0)),
        "timeline": timeline,
        "related": related_accounts(inv, username)
    }


def consistency_report(inv: dict, ex: dict = None) -> list:
    """Memeriksa konsistensi angka antara hasil analisis dan ringkasan."""
    summ = summarize(inv)
    meta = inv["meta"]
    res = inv["res"]

    checks = []

    def add_check(name, condition, detail):
        checks.append({
            "nama": name,
            "lulus": bool(condition),
            "detail": detail
        })

    # Jumlah akun pada hasil analisis harus sesuai metadata.
    add_check(
        "Jumlah akun",
        len(res) == meta["n_accounts"],
        f"Hasil: {len(res)}, metadata: {meta['n_accounts']}"
    )

    # Jumlah postingan harus sesuai metadata.
    add_check(
        "Jumlah postingan",
        len(inv["posts"]) == meta["n_posts"],
        f"Hasil: {len(inv['posts'])}, metadata: {meta['n_posts']}"
    )

    # Distribusi kategori harus mencakup seluruh akun.
    total_categories = sum(summ["counts"].values())
    add_check(
        "Distribusi kategori",
        total_categories == meta["n_accounts"],
        f"Total kategori: {total_categories}, akun: {meta['n_accounts']}"
    )

    # Jumlah akun yang dapat dinilai harus konsisten.
    add_check(
        "Jumlah akun dinilai",
        summ["n_eval"] == meta["n_accounts"] - meta["n_insufficient"],
        f"Dinilai: {summ['n_eval']}, tidak cukup data: {meta['n_insufficient']}"
    )

    # Ringkasan eksekutif harus menggunakan angka yang sama.
    if ex is not None:
        add_check(
            "Ringkasan eksekutif",
            ex.get("priorities") == summ["priorities"],
            "Membandingkan distribusi prioritas investigasi."
        )

        add_check(
            "Tingkat risiko",
            ex.get("level") == overall_risk(inv),
            "Membandingkan tingkat risiko keseluruhan."
        )

    return checks
