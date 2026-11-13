"""Multi-Source Intelligence untuk Fact Check Explorer NEXGUARD AI.

Modul ini TIDAK mengubah factcheck.py. Semua data berasal dari Google Fact Check Tools API (factcheck.explore).
Tidak ada klaim, ulasan, penilaian, atau tautan yang dibuat sendiri: bila API tidak mengembalikan data, hasilnya kosong.

Isi: katalog sumber, pengambilan paralel per sumber, uji kesehatan sumber, penghapusan duplikat, dan perbandingan
penilaian antar-penerbit (tanpa membuat kesimpulan baru)."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import factcheck

ST_ACTIVE = "Aktif"
ST_IDLE = "Terindeks, tanpa ulasan pada rentang ini"
ST_NONE = "Tidak ada data dari API"
ST_ERROR = "Kesalahan"
STATUS_ICON = {ST_ACTIVE: "🟢", ST_IDLE: "🟡", ST_NONE: "⚪", ST_ERROR: "🔴"}

# Domain di bawah adalah DUGAAN domain penerbit. API tidak menjamin semuanya terindeks; gunakan uji sumber (probe) untuk
# memastikan. Bila domain pertama tidak mengembalikan data, domain berikutnya dicoba.
SOURCES = [
    {"id": "turnbackhoax", "name": "TurnBackHoax", "domains": ["turnbackhoax.id"], "region": "Indonesia"},
    {"id": "cekfakta", "name": "CekFakta", "domains": ["cekfakta.com"], "region": "Indonesia"},
    {"id": "tempo", "name": "Tempo Cek Fakta", "domains": ["cekfakta.tempo.co", "tempo.co"], "region": "Indonesia"},
    {"id": "kompas", "name": "Kompas Cek Fakta", "domains": ["kompas.com"], "region": "Indonesia"},
    {"id": "antara", "name": "ANTARA Cek Fakta", "domains": ["antaranews.com"], "region": "Indonesia"},
    {"id": "afp", "name": "AFP Fact Check", "domains": ["factcheck.afp.com", "afp.com"], "region": "Internasional"},
    {"id": "reuters", "name": "Reuters Fact Check", "domains": ["reuters.com"], "region": "Internasional"},
]
SIM_THRESHOLD = 0.85     # kemiripan token (Jaccard) minimum agar dua klaim dianggap duplikat
MIN_TOKENS_FUZZY = 4     # klaim yang lebih pendek hanya digabung bila teksnya identik
_DOMAIN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")


# ----------------------------------------------------------------------------- util
def host_of(x) -> str:
    s = str(x or "").strip().lower()
    if not s:
        return ""
    if "//" not in s:
        s = "//" + s
    try:
        host = urlparse(s).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _safe(u) -> str:
    u = str(u or "").strip()
    return u if u.startswith(("http://", "https://")) else ""


def _norm(s) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(s or "").lower()))


def _urlkey(u) -> str:
    s = re.sub(r"^https?://(www\.)?", "", str(u or "").strip().lower())
    return s.split("#")[0].rstrip("/")


def parse_custom(text, limit: int = 5) -> list:
    """Sumber tambahan buatan pengguna: satu domain per baris. Domain tidak valid/duplikat diabaikan."""
    known = {d for s in SOURCES for d in s["domains"]}
    out, seen = [], set()
    for line in str(text or "").splitlines():
        d = host_of(line.strip())
        if d and _DOMAIN.fullmatch(d) and d not in known and d not in seen:
            seen.add(d)
            out.append({"id": f"custom:{d}", "name": d, "domains": [d], "region": "Kustom"})
        if len(out) >= limit:
            break
    return out


def source_name(sid) -> str:
    for s in SOURCES:
        if s["id"] == sid:
            return s["name"]
    sid = str(sid or "")
    if sid == "manual":
        return "pencarian manual"
    return sid[len("custom:"):] if sid.startswith("custom:") else (sid or "tidak diketahui")


def identify_source(review: dict, sources) -> str:
    """Cocokkan penerbit ulasan ke sumber katalog berdasarkan domain (yang paling spesifik menang). None bila tidak cocok."""
    host = host_of(review.get("site")) or host_of(review.get("url"))
    best = None
    for s in sources:
        for d in s["domains"]:
            if host and (host == d or host.endswith("." + d)) and (best is None or len(d) > best[0]):
                best = (len(d), s["id"])
    return best[1] if best else None


# ----------------------------------------------------------------------------- pengambilan
def fetch_source(api_key, source, query=None, language="id", max_age_days=30, page_size=10, fetch=None,
                 page_token=None, domain=None) -> dict:
    """Ambil ulasan satu sumber. Mencoba domain kandidat berurutan sampai ada data. Kesalahan tidak melempar exception."""
    fetch = fetch or factcheck.explore
    t0 = time.perf_counter()
    res = {"id": source["id"], "name": source["name"], "domain": source["domains"][0], "status": ST_NONE, "claims": [],
           "next": None, "error": "", "window_days": max_age_days, "latency_ms": 0, "n_claims": 0, "n_reviews": 0, "newest": ""}
    errors, answered = [], False
    for dom in ([domain] if domain else source["domains"]):
        try:
            data = fetch(api_key, query=query, publisher=dom, language=language, max_age_days=max_age_days,
                         page_size=page_size, page_token=page_token)
        except (RuntimeError, ValueError) as e:      # pesan dari factcheck.py (sudah aman, tanpa URL/API key)
            errors.append(str(e))
            continue
        except Exception as e:                       # galat tak terduga: jangan bocorkan teks asli (bisa memuat URL + API key)
            errors.append(f"Gagal menghubungi layanan pemeriksa fakta ({type(e).__name__}).")
            continue
        answered = True
        if data["claims"]:
            res.update(domain=dom, status=ST_ACTIVE, claims=data["claims"], next=data.get("next_page_token"))
            break
    if res["status"] != ST_ACTIVE and errors:
        res["error"] = errors[0]
        if not answered:
            res["status"] = ST_ERROR
    res["n_claims"] = len(res["claims"])
    res["n_reviews"] = sum(len(c["reviews"]) for c in res["claims"])
    res["newest"] = max((factcheck.newest_review_date(c) for c in res["claims"]), default="") or ""
    res["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return res


def probe_source(api_key, source, max_age_days=30, language=None, widen_days=365, fetch=None) -> dict:
    """Uji satu sumber (semua bahasa). Jika kosong pada rentang terpilih, perluas ke widen_days untuk membedakan
    'terindeks tapi tidak ada ulasan baru' dari 'tidak ada data sama sekali'."""
    res = fetch_source(api_key, source, None, language, max_age_days, 5, fetch)
    if res["status"] == ST_NONE and max_age_days and max_age_days < widen_days:
        wide = fetch_source(api_key, source, None, language, widen_days, 5, fetch)
        res["latency_ms"] += wide["latency_ms"]
        if wide["status"] == ST_ACTIVE:
            res.update(status=ST_IDLE, domain=wide["domain"], window_days=widen_days, n_claims=wide["n_claims"],
                       n_reviews=wide["n_reviews"], newest=wide["newest"], error="")
        elif wide["status"] == ST_ERROR:
            res.update(status=ST_ERROR, error=wide["error"])
    res["claims"] = []   # uji hanya menyimpan hitungan, bukan isi
    return res


def _map(fn, sources, workers=4):
    if not sources:
        return []
    return [fn(s) for s in sources]


def collect(api_key, sources, query=None, language="id", max_age_days=30, page_size=10, fetch=None) -> list:
    return _map(lambda s: fetch_source(api_key, s, query, language, max_age_days, page_size, fetch), sources)


def probe_all(api_key, sources, max_age_days=30, language=None, fetch=None) -> list:
    return _map(lambda s: probe_source(api_key, s, max_age_days, language, fetch=fetch), sources)


def run_multi(api_key, sources, query, language, max_age_days, page_size=10, fetch=None) -> dict:
    """Ambil dari semua sumber sekaligus. 'raw' = daftar [klaim, id_sumber]; 'results' = status per sumber (tanpa isi klaim)."""
    results = collect(api_key, sources, query, language, max_age_days, page_size, fetch)
    raw = [[c, r["id"]] for r in results for c in r["claims"]]
    for r in results:
        r["claims"] = []
    return {"raw": raw, "results": results}


def run_more(api_key, results, query, language, max_age_days, page_size=10, fetch=None) -> list:
    """Halaman berikutnya untuk sumber yang masih punya nextPageToken. Memperbarui 'results' di tempat; mengembalikan raw baru."""
    todo = [r for r in results if r.get("next")]
    by_id = {r["id"]: r for r in results}

    def one(r):
        src = {"id": r["id"], "name": r["name"], "domains": [r["domain"]]}
        return fetch_source(api_key, src, query, language, max_age_days, page_size, fetch, page_token=r["next"], domain=r["domain"])

    raw = []
    for n in _map(one, todo):
        o = by_id[n["id"]]
        raw += [[c, n["id"]] for c in n["claims"]]
        o["next"] = n["next"]
        o["n_claims"] += n["n_claims"]
        o["n_reviews"] += n["n_reviews"]
        o["latency_ms"] += n["latency_ms"]
        o["newest"] = max(o["newest"], n["newest"])
        if n["status"] == ST_ERROR:
            o["error"] = n["error"]
    return raw


# ----------------------------------------------------------------------------- pembersihan + deduplikasi
def _similar(a, ta, b, tb) -> bool:
    if a and a == b:
        return True
    if min(len(ta), len(tb)) < MIN_TOKENS_FUZZY:
        return False
    return len(ta & tb) / len(ta | tb) >= SIM_THRESHOLD


def _merge_into(primary: dict, other: dict):
    seen = {_urlkey(r["url"]) for r in primary["reviews"]}
    for r in other["reviews"]:
        k = _urlkey(r["url"])
        if k not in seen:
            seen.add(k)
            primary["reviews"].append(r)
    for sid in other["found_in"]:
        if sid not in primary["found_in"]:
            primary["found_in"].append(sid)
    t = other.get("claim_text") or ""
    if t and _norm(t) != _norm(primary.get("claim_text")) and t not in primary["variants"]:
        primary["variants"].append(t)
    primary["merged_from"] += other["merged_from"]
    for k in ("claim_date", "claimant"):
        if not primary.get(k) and other.get(k):
            primary[k] = other[k]


def dedupe(claims: list) -> list:
    groups = []
    for c in claims:
        norm, toks = _norm(c.get("claim_text")), factcheck._tokens(c.get("claim_text"))
        target = None
        if norm:   # klaim tanpa teks tidak pernah digabung
            target = next((g for g in groups if _similar(norm, toks, g["norm"], g["toks"])), None)
        if target is None:
            groups.append({"claim": c, "norm": norm, "toks": toks})
        else:
            _merge_into(target["claim"], c)
    return [g["claim"] for g in groups]


def process(raw: list, sources) -> dict:
    """raw: [[klaim, id_sumber], ...] -> klaim bersih, tanpa duplikat. Ulasan tanpa tautan http(s) asli disembunyikan
    (tidak dapat diverifikasi). Nama penerbit hanya diturunkan dari data API (situs/tautan), tidak dikarang."""
    stats = {"raw_claims": len(raw), "raw_reviews": 0, "dropped_no_link": 0, "dup_merged": 0}
    cleaned = []
    for c, sid in raw:
        revs = []
        for r in c.get("reviews") or []:
            stats["raw_reviews"] += 1
            link = _safe(r.get("url"))
            if not link:
                stats["dropped_no_link"] += 1
                continue
            r2 = dict(r)
            r2["url"] = link
            r2["publisher"] = r.get("publisher") or host_of(r.get("site")) or host_of(link)
            r2["kategori"] = r.get("kategori") or factcheck.classify_rating(r.get("rating"))
            r2["source"] = identify_source(r2, sources)
            revs.append(r2)
        if revs:
            cleaned.append({**c, "reviews": revs, "found_in": [sid], "variants": [], "merged_from": 1})
    claims = dedupe(cleaned)
    stats["dup_merged"] = len(cleaned) - len(claims)
    return {"claims": claims, "stats": stats}


def sort_newest(claims: list) -> list:
    """Terbaru dulu berdasarkan tanggal ulasan (atau tanggal klaim). Tanpa tanggal ditaruh di akhir."""
    return sorted(claims, key=lambda c: factcheck.newest_review_date(c) or "", reverse=True)


# ----------------------------------------------------------------------------- cross-source
def cross_check(claim: dict) -> dict:
    """Bandingkan penilaian antar-penerbit pada satu klaim. Hanya membandingkan; tidak membuat kesimpulan baru.
    verdict: 'single' (1 penerbit), 'agree' (searah), 'differ' (berbeda)."""
    pubs = {}
    for r in claim["reviews"]:
        key = r.get("source") or host_of(r.get("site")) or host_of(r.get("url")) or _norm(r.get("publisher"))
        pubs.setdefault(key, []).append(r)
    cats = {r["kategori"] for rs in pubs.values() for r in rs}
    n = len(pubs)
    verdict = "single" if n < 2 else ("agree" if len(cats) == 1 else "differ")
    return {"n": n, "verdict": verdict, "category": next(iter(cats)) if len(cats) == 1 else None}


def cross_stats(claims: list) -> dict:
    out = {"multi": 0, "agree": 0, "differ": 0}
    for c in claims:
        v = cross_check(c)["verdict"]
        if v != "single":
            out["multi"] += 1
            out[v] += 1
    return out


# ----------------------------------------------------------------------------- tabel kesehatan sumber
def health_rows(results: list) -> list:
    rows = []
    for r in results:
        note = r.get("error") or {ST_NONE: "Belum ada data dari API (mungkin belum terindeks atau tidak ada ulasan).",
                                  ST_IDLE: f"Ada data dalam {r['window_days']} hari terakhir.", ST_ACTIVE: ""}.get(r["status"], "")
        rows.append({"Sumber": r["name"], "Domain": r["domain"], "Status": f"{STATUS_ICON[r['status']]} {r['status']}",
                     "Klaim": r["n_claims"], "Ulasan": r["n_reviews"], "Ulasan terbaru": r["newest"] or "-",
                     "Rentang (hari)": r["window_days"] or "semua", "Latensi (ms)": r["latency_ms"], "Keterangan": note})
    return rows


def health_summary(results: list) -> dict:
    out = {"diuji": len(results), ST_ACTIVE: 0, ST_IDLE: 0, ST_NONE: 0, ST_ERROR: 0}
    for r in results:
        out[r["status"]] += 1
    return out