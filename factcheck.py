"""AI Fact-Checking berbasis bukti: ekstraksi klaim -> pencarian ulasan pemeriksa fakta -> kesesuaian -> status.

Sumber pembanding: Google Fact Check Tools API (claims:search). Hanya ulasan yang BENAR-BENAR dikembalikan API yang
ditampilkan. Tidak ada sumber/bukti yang dibuat sendiri. Jika tidak ada ulasan yang cocok, API tidak tersedia, atau
terjadi kesalahan, statusnya selalu 'Belum Terverifikasi'.

API key dibaca dari environment variable FACTCHECK_API_KEY atau Streamlit Secrets, tidak pernah ditulis di kode."""
import os
import re
import requests

from db import mask_pii

API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
VERIFIED, CONTRADICTED, UNVERIFIED = "Terverifikasi", "Bertentangan dengan Bukti", "Belum Terverifikasi"
MAX_CLAIMS = 5
MIN_MATCH = 0.5   # kemiripan token minimum antara klaim dan klaim yang diulas pemeriksa fakta

_STOP = set("yang dan di ke dari ini itu untuk dengan pada adalah juga akan sudah ada tidak saya kita kami mereka atau "
            "karena sebuah oleh dalam bisa lebih bahwa the a an of to in is are was were for on".split())
_ACTION = re.compile(r"\b(sebarkan|viralkan|bagikan|teruskan|forward|share)\b", re.I)
_FACTUAL = re.compile(r"\d|\b(menurut|dikatakan|menyatakan|mengumumkan|ditemukan|terbukti|meninggal|naik|turun|"
                      r"akan|telah|sudah|mengandung|menyebabkan|dilarang|diblokir|dihapus|ditutup|beredar|cair)\b", re.I)

# Peringkat (textualRating) -> kategori. 'tidak benar' diperiksa SEBELUM 'benar'.
_FALSE = ("salah", "hoaks", "hoax", "false", "fake", "palsu", "menyesatkan", "misleading", "keliru", "disinformasi",
          "tidak benar", "not true", "not correct", "not accurate", "bohong", "pants on fire",
          "incorrect", "fabricated", "tidak akurat")
_MIXED = ("sebagian", "partly", "partially", "mixture", "mixed", "unproven", "belum terbukti", "tanpa bukti",
          "unsupported", "lacks context", "kurang konteks", "satire", "opini", "belum dapat")
_TRUE = ("benar", "true", "correct", "akurat", "fakta", "sesuai fakta", "terbukti benar", "valid")


def get_api_key():
    key = os.environ.get("FACTCHECK_API_KEY")
    if key:
        return key.strip()
    try:  # Streamlit Secrets (tidak ada saat dijalankan di luar Streamlit / tanpa secrets.toml)
        import streamlit as st
        return str(st.secrets["FACTCHECK_API_KEY"]).strip()
    except Exception:
        return None


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", str(s).lower()) if t not in _STOP and len(t) > 1}


def extract_claims(text: str, max_claims: int = MAX_CLAIMS) -> list:
    """Ambil kalimat yang berpotensi memuat klaim faktual (bukan pertanyaan/ajakan menyebarkan).
    Data pribadi disamarkan sebelum dikirim ke API eksternal."""
    text = mask_pii(str(text)[:20_000])
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    scored = []
    for i, s in enumerate(sents):
        n_words = len(s.split())
        if n_words < 5 or n_words > 60 or s.endswith("?"):
            continue
        body = _ACTION.sub("", s)
        if len(body.split()) < 4:
            continue
        if _FACTUAL.search(s):
            scored.append((-(1 + bool(re.search(r"\d", s))), i, s.strip(" !")))
    scored.sort()
    return [s for _, _, s in sorted(scored[:max_claims], key=lambda x: x[1])]

def classify_rating(rating: str) -> str:
    r = str(rating or "").lower()
    if any(k in r for k in _MIXED):
        return UNVERIFIED
    if any(k in r for k in _FALSE):
        return CONTRADICTED
    if any(k in r for k in _TRUE):
        return VERIFIED
    return UNVERIFIED


def match_score(claim: str, reviewed: str) -> float:
    """Proporsi token klaim pengguna yang juga muncul pada klaim yang diulas (0-1)."""
    a, b = _tokens(claim), _tokens(reviewed)
    return len(a & b) / len(a) if a else 0.0


def _request(params: dict, session=None, timeout: int = 10) -> dict:
    """GET ke claims:search. Melempar RuntimeError berbahasa Indonesia tanpa membocorkan API key."""
    get = (session or requests).get
    try:
        resp = get(API_URL, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"Tidak dapat terhubung ke layanan pemeriksa fakta ({type(e).__name__}).") from None
    if resp.status_code in (400, 401, 403):
        raise RuntimeError("API key ditolak atau tidak valid, atau parameter pencarian salah. Periksa FACTCHECK_API_KEY dan izin Fact Check Tools API.")
    if resp.status_code == 429:
        raise RuntimeError("Batas kuota API tercapai. Coba lagi nanti.")
    if resp.status_code != 200:
        raise RuntimeError(f"Layanan pemeriksa fakta mengembalikan kode {resp.status_code}.")
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError("Respons layanan pemeriksa fakta tidak dapat dibaca.") from None


def _review(c: dict, rv: dict) -> dict:
    pub = rv.get("publisher") or {}
    return {"claim_text": c.get("text", ""), "claimant": c.get("claimant", ""), "publisher": pub.get("name", ""),
            "site": pub.get("site", ""), "url": rv.get("url", ""), "title": rv.get("title", ""),
            "rating": rv.get("textualRating", ""), "review_date": (rv.get("reviewDate") or "")[:10]}


def search_claim(claim: str, api_key: str, language: str = "id", page_size: int = 5, timeout: int = 10, session=None) -> list:
    """Panggil API. Mengembalikan list ulasan apa adanya (satu entri per ulasan)."""
    data = _request({"query": claim[:500], "languageCode": language, "pageSize": page_size, "key": api_key}, session, timeout)
    return [_review(c, rv) for c in data.get("claims", []) or [] for rv in c.get("claimReview", []) or []]


# ----------------------------------------------------------------------------- Explorer (mirip Google Fact Check Explorer)
DEFAULT_PUBLISHERS = ("turnbackhoax.id", "cekfakta.com", "cekfakta.tempo.co")   # dapat diubah; tidak semua penerbit selalu terindeks


def explore(api_key: str, query: str = None, publisher: str = None, language: str = "id", max_age_days: int = None,
            page_size: int = 10, page_token: str = None, session=None, timeout: int = 10) -> dict:
    """Cari klaim yang sudah diperiksa. API mewajibkan query ATAU publisher. Hasil dinormalisasi dan hanya memuat data dari API."""
    query, publisher = (query or "").strip(), (publisher or "").strip()
    if not query and not publisher:
        raise ValueError("Isi kata kunci pencarian atau filter penerbit (API mewajibkan salah satunya).")
    params = {"key": api_key, "pageSize": max(1, min(int(page_size), 50))}
    if query:
        params["query"] = query[:500]
    if publisher:
        params["reviewPublisherSiteFilter"] = publisher
    if language:
        params["languageCode"] = language
    if max_age_days:
        params["maxAgeDays"] = int(max_age_days)
    if page_token:
        params["pageToken"] = page_token
    data = _request(params, session, timeout)
    claims = []
    for c in data.get("claims", []) or []:
        reviews = []
        for rv in c.get("claimReview", []) or []:
            r = _review(c, rv)
            r["kategori"] = classify_rating(r["rating"])
            reviews.append(r)
        claims.append({"claim_text": c.get("text", ""), "claimant": c.get("claimant", ""),
                       "claim_date": (c.get("claimDate") or "")[:10], "reviews": reviews})
    return {"claims": claims, "next_page_token": data.get("nextPageToken")}


def newest_review_date(claim: dict) -> str:
    return max((r["review_date"] for r in claim["reviews"]), default="") or claim.get("claim_date", "")


def recent(api_key: str, publishers=DEFAULT_PUBLISHERS, language: str = "id", max_age_days: int = 30,
           per_publisher: int = 10, fetch=explore) -> dict:
    """Daftar 'terbaru': API tidak punya endpoint terbaru tanpa kata kunci, sehingga dikumpulkan per penerbit
    (reviewPublisherSiteFilter + maxAgeDays) lalu diurutkan dari ulasan terbaru. Kegagalan satu penerbit tidak menggagalkan yang lain."""
    claims, errors = [], []
    for pub in publishers:
        try:
            claims += fetch(api_key, publisher=pub, language=language, max_age_days=max_age_days, page_size=per_publisher)["claims"]
        except RuntimeError as e:
            errors.append(f"{pub}: {e}")
    seen, uniq = set(), []
    for c in sorted(claims, key=newest_review_date, reverse=True):
        key = (c["claim_text"], tuple(r["url"] for r in c["reviews"]))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return {"claims": uniq, "errors": errors}


def check_claim(claim: str, api_key: str, search=search_claim, min_match: float = MIN_MATCH) -> dict:
    res = {"claim": claim, "status": UNVERIFIED, "sources": [], "reason": "", "error": None}
    try:
        reviews = search(claim, api_key)
    except RuntimeError as e:
        res["error"], res["reason"] = str(e), "Pencarian gagal, status tidak dapat ditentukan."
        return res
    matched = []
    for rv in reviews:
        m = match_score(claim, rv["claim_text"])
        if m >= min_match and rv["url"]:
            matched.append({**rv, "match": round(m, 2), "kategori": classify_rating(rv["rating"])})
    matched.sort(key=lambda x: -x["match"])
    res["sources"] = matched
    cats = {m["kategori"] for m in matched}
    if not matched:
        res["reason"] = ("Tidak ditemukan ulasan pemeriksa fakta yang cocok. Ini TIDAK berarti klaim benar atau salah, "
                         "hanya belum ada ulasan yang ditemukan.")
    elif CONTRADICTED in cats and VERIFIED in cats:
        res["reason"] = "Sumber pemeriksa fakta memberikan penilaian berbeda; ditinjau manual."
    elif cats == {CONTRADICTED}:
        res["status"], res["reason"] = CONTRADICTED, "Ulasan pemeriksa fakta yang cocok menilai klaim ini salah/menyesatkan."
    elif cats == {VERIFIED}:
        res["status"], res["reason"] = VERIFIED, "Ulasan pemeriksa fakta yang cocok menilai klaim ini benar."
    elif CONTRADICTED in cats:
        res["status"], res["reason"] = CONTRADICTED, "Ulasan yang cocok menilai klaim salah/menyesatkan (ada ulasan lain yang tidak tegas)."
    else:
        res["reason"] = "Ulasan yang cocok tidak memberi penilaian tegas (sebagian benar/belum terbukti)."
    return res



def fact_check_text(text: str, api_key=None, search=search_claim) -> dict:
    """Periksa klaim pada teks."""
    if api_key is None:
        api_key = os.environ.get("FACTCHECK_API_KEY")

    base = {"available": bool(api_key), "claims": [], "overall": UNVERIFIED, "message": ""}
    if not api_key:
        base["message"] = (
            "Pemeriksaan fakta dinonaktifkan: API key belum diatur. "
            "Setel FACTCHECK_API_KEY (environment variable) atau Streamlit Secrets."
        )
        return base

    claims = extract_claims(text)
    if not claims:
        base["message"] = "Tidak ditemukan kalimat yang cukup jelas sebagai klaim faktual."
        return base

    results = [check_claim(c, api_key, search) for c in claims]
    base["claims"] = results
    errors = [r["error"] for r in results if r["error"]]
    if errors:
        base["message"] = errors[0]

    statuses = [r["status"] for r in results]
    if CONTRADICTED in statuses:
        base["overall"] = CONTRADICTED
    elif statuses and all(s == VERIFIED for s in statuses):
        base["overall"] = VERIFIED

    if not base["message"]:
        base["message"] = (
            f"{len(results)} klaim diperiksa terhadap ulasan pemeriksa fakta yang tersedia."
        )
    return base

























