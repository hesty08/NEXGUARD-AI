"""Modul 03 - Social Intelligence: sentimen, evolusi isu, aktivitas terkoordinasi."""
import re
from collections import Counter
import pandas as pd

POS = {"bagus", "baik", "mendukung", "setuju", "aman", "berhasil", "mantap", "positif", "membantu", "sukses"}
NEG = {"buruk", "bahaya", "gagal", "marah", "tolak", "bohong", "hoaks", "hoax", "rugi", "menipu",
       "kecewa", "ancaman", "curang", "parah"}
NEGATORS = {"tidak", "tak", "bukan", "belum", "jangan", "nggak", "gak"}
STOP = set("yang dan di ke dari ini itu untuk dengan pada adalah juga akan sudah ada tidak saya kita kami mereka atau karena sebuah oleh dalam bisa lebih rt amp".split())

def sentiment(text: str) -> int:
    toks = re.findall(r"[a-z]+", str(text).lower())
    score = 0
    for i, w in enumerate(toks):
        v = 1 if w in POS else -1 if w in NEG else 0
        if v and any(t in NEGATORS for t in toks[max(0, i - 2):i]):
            v = -v  # negasi membalik polaritas ("tidak buruk" -> positif)
        score += v
    if "terima kasih" in str(text).lower():
        score += 1
    return score

def label(v: int) -> str:
    return "Positif" if v > 0 else "Negatif" if v < 0 else "Netral"

def prepare(df: pd.DataFrame, issue: str = "") -> pd.DataFrame:
    d = df.copy()
    if "date" not in d.columns and "timestamp" in d.columns:
        d["date"] = d["timestamp"]
    for c in ("date", "username", "text"):
        if c not in d.columns:
            raise ValueError("Kolom CSV harus berisi: date (atau timestamp), username, text")
    d["date"] = pd.to_datetime(d["date"].astype(str), errors="coerce", format="mixed").dt.date
    d = d.dropna(subset=["date", "text", "username"])
    if d.empty:
        raise ValueError("Tidak ada baris valid. Pastikan kolom date/timestamp berisi tanggal yang dapat dibaca "
                         "(contoh 2026-10-21 atau 2026-10-21 14:30:00) dan kolom username serta text tidak kosong.")
    d["text"] = d["text"].astype(str)
    d["username"] = d["username"].astype(str)
    if issue.strip():
        d = d[d["text"].str.contains(issue.strip(), case=False, na=False, regex=False)]
    d["skor_sentimen"] = d["text"].map(sentiment)
    d["sentimen"] = d["skor_sentimen"].map(label)
    return d

def top_keywords(d: pd.DataFrame, n=15):
    words = Counter(w for t in d["text"] for w in re.findall(r"[a-zA-Z]{4,}", t.lower()) if w not in STOP)
    return pd.DataFrame(words.most_common(n), columns=["kata", "jumlah"])

def daily_trend(d: pd.DataFrame) -> pd.DataFrame:
    return d.groupby(["date", "sentimen"]).size().reset_index(name="jumlah")

MAX_UNIQUE = 5000


def similar_pairs(X, threshold: float, block: int = 500):
    """Pasangan indeks (i, j), i < j, dengan cosine similarity >= threshold. X = matriks TF-IDF ternormalisasi (sparse).
    Perkalian sparse jauh lebih cepat daripada cosine_similarity padat pada teks pendek."""
    Xt = X.T.tocsc()
    for start in range(0, X.shape[0], block):
        prod = (X[start:start + block] @ Xt).tocoo()
        keep = (prod.data >= threshold - 1e-9) & (prod.col > start + prod.row)   # saring secara vektor (cepat)
        for a, b in zip(prod.row[keep], prod.col[keep]):
            yield start + int(a), int(b)
COLS = ["contoh_teks", "jumlah_akun", "jumlah_post", "akun_serempak", "serempak", "akun"]

def _max_accounts_in_window(g: pd.DataFrame, minutes: int) -> int:
    """Jumlah akun berbeda terbanyak yang memposting dalam satu jendela waktu (two-pointer)."""
    g = g.sort_values("ts"); ts, us = g["ts"].tolist(), g["username"].tolist()
    best, lo, win = 0, 0, Counter()
    for hi in range(len(ts)):
        win[us[hi]] += 1
        while (ts[hi] - ts[lo]).total_seconds() > minutes * 60:
            win[us[lo]] -= 1
            if win[us[lo]] == 0: del win[us[lo]]
            lo += 1
        best = max(best, len(win))
    return best

def to_ns(series: pd.Series):
    """Waktu -> (int64 nanodetik, mask valid). Resolusi pandas bisa s/ms/us/ns, maka dinormalkan eksplisit ke ns."""
    ts = pd.to_datetime(series, errors="coerce")
    valid = ts.notna().to_numpy()
    ns = ts.fillna(pd.Timestamp(0)).astype("datetime64[ns]").astype("int64").to_numpy()
    return ns, valid


def _max_window_accounts(ts_ns, codes, window_ns) -> int:
    """Akun berbeda terbanyak dalam satu jendela waktu (two-pointer). ts_ns harus terurut naik."""
    best, lo, win = 0, 0, Counter()
    for hi in range(len(ts_ns)):
        win[codes[hi]] += 1
        while ts_ns[hi] - ts_ns[lo] > window_ns:
            win[codes[lo]] -= 1
            if win[codes[lo]] == 0:
                del win[codes[lo]]
            lo += 1
        best = max(best, len(win))
    return best


def coordinated_clusters(d: pd.DataFrame, threshold=0.8, min_accounts=3, window_min=15) -> pd.DataFrame:
    """Klaster teks mirip dari >= min_accounts akun. Jika ada kolom timestamp, hitung juga
    akun yang memposting dalam jendela window_min menit ('serempak'). Indikatif, bukan bukti."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    d = d.dropna(subset=["text", "username"]).reset_index(drop=True)
    d["norm"] = d["text"].astype(str).str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
    uniq_all = d["norm"].drop_duplicates().tolist()
    capped = len(uniq_all) > MAX_UNIQUE
    uniq = uniq_all[:MAX_UNIQUE]
    empty = pd.DataFrame(columns=COLS); empty.attrs["capped"] = capped
    if not uniq:
        return empty
    parent = list(range(len(uniq)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    if len(uniq) > 1:
        X = TfidfVectorizer().fit_transform(uniq)
        for i, b in similar_pairs(X, threshold):  # per blok agar memori terkendali
            parent[find(b)] = find(i)
    cid = {t: find(i) for i, t in enumerate(uniq)}
    d["cluster"] = d["norm"].map(cid)
    d = d.dropna(subset=["cluster"]).reset_index(drop=True)
    has_time = "timestamp" in d.columns
    users, texts = d["username"].to_numpy(), d["text"].astype(str).to_numpy()
    if has_time:
        ts_ns, valid = to_ns(d["timestamp"])
    codes = pd.factorize(d["username"])[0]
    n_acc = d.groupby("cluster")["username"].nunique()
    groups = d.groupby("cluster").indices
    rows = []
    for c in n_acc[n_acc >= min_accounts].index:
        idx = groups[c]
        accs = sorted(set(users[idx]))
        sync = None
        if has_time:
            sel = idx[valid[idx]]
            sel = sel[np.argsort(ts_ns[sel], kind="stable")]
            sync = _max_window_accounts(ts_ns[sel], codes[sel], window_min * 60 * 1_000_000_000) if len(sel) else 0
        rows.append(dict(contoh_teks=texts[idx[0]][:90], jumlah_akun=len(accs), jumlah_post=len(idx),
                         akun_serempak=sync, serempak=(sync is not None and sync >= min_accounts),
                         akun=", ".join(accs[:8]) + (" ..." if len(accs) > 8 else "")))
    out = pd.DataFrame(rows, columns=COLS).sort_values(["serempak", "jumlah_akun"], ascending=False).reset_index(drop=True)
    out.attrs["capped"] = capped
    return out
