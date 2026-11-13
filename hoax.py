"""Modul 01 - Deteksi indikasi hoaks (rule-based + model ML sederhana, explainable)."""
import re
from urllib.parse import urlparse
import pandas as pd
from paths import data_file

CLICKBAIT = ["heboh", "geger", "viral", "terbongkar", "mengejutkan", "astaga", "wajib baca",
             "akhirnya terungkap", "tak disangka", "bikin merinding", "ternyata"]
URGENCY = ["sebarkan", "viralkan", "bagikan ke", "share sebelum", "sebelum dihapus",
           "teruskan pesan", "jangan sampai tidak tahu", "forward ke"]
FEAR = ["bahaya", "darurat", "ancaman", "mematikan", "kiamat", "bencana", "teror", "hancur"]
UNSOURCED = ["katanya", "konon", "menurut kabar", "kabarnya", "info dari grup", "dikabarkan", "orang dalam"]
CREDIBLE = ["antaranews.com", "kompas.com", "detik.com", "tempo.co", "cnnindonesia.com",
            "tni.mil.id", "bssn.go.id", "komdigi.go.id", "kominfo.go.id", "turnbackhoax.id"]

def is_credible(host: str) -> bool:
    """Domain harus sama persis atau subdomain sah (bukan sekadar berakhiran sama)."""
    host = host.strip(".").lower()
    return any(host == d or host.endswith("." + d) for d in CREDIBLE)

def _count(text, words):
    t = text.lower()
    return [w for w in words if w in t]

def rule_analysis(text: str, source_url: str = ""):
    """Return (skor 0-100, list sinyal). Tiap sinyal = (nama, bobot, penjelasan)."""
    signals = []
    letters = [c for c in text if c.isalpha()]
    caps = sum(c.isupper() for c in letters) / max(len(letters), 1)
    if caps > 0.3:
        signals.append(("Huruf kapital berlebihan", 15, f"{caps:.0%} huruf berupa kapital"))
    ex = text.count("!")
    if ex >= 3:
        signals.append(("Tanda seru berlebihan", 10, f"{ex} tanda seru"))
    for name, words, w in [("Bahasa clickbait", CLICKBAIT, 8), ("Desakan menyebarkan", URGENCY, 15),
                           ("Bahasa menakut-nakuti", FEAR, 7), ("Sumber tidak jelas", UNSOURCED, 12)]:
        hit = _count(text, words)
        if hit:
            signals.append((name, min(w * len(hit), 30), "Ditemukan: " + ", ".join(hit)))
    if not re.search(r"\b(menurut|dikatakan|disampaikan|kata)\s+[A-Z][a-z]+", text) and len(text.split()) > 15:
        signals.append(("Tanpa atribusi narasumber", 10, "Tidak ada rujukan narasumber yang jelas"))
    if source_url.strip():
        host = (urlparse(source_url if "//" in source_url else "//" + source_url).hostname or "").lower()
        if is_credible(host):
            signals.append(("Sumber kredibel", -25, f"Domain {host} ada di daftar rujukan"))
        else:
            signals.append(("Sumber tidak dikenal", 10, f"Domain {host or '-'} tidak ada di daftar rujukan"))
    else:
        signals.append(("Tanpa tautan sumber", 8, "Tidak ada sumber yang dapat diverifikasi"))
    score = max(0, min(100, sum(s[1] for s in signals)))
    return score, signals

_model = None
def _train():
    global _model
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    df = pd.read_csv(data_file("hoax_sample.csv"))
    _model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2)), LogisticRegression(max_iter=1000))
    _model.fit(df["text"], df["label"])

def ml_probability(text: str) -> float:
    if _model is None:
        _train()
    return float(_model.predict_proba([text])[0][1]) * 100

def ml_top_terms(text: str, n: int = 5):
    """Kata/frasa yang paling mendorong skor model ke arah hoaks (+) atau non-hoaks (-)."""
    if _model is None:
        _train()
    vec, clf = _model.steps[0][1], _model.steps[-1][1]
    X = vec.transform([text])
    if X.nnz == 0:
        return []
    names = vec.get_feature_names_out()
    contrib = X.multiply(clf.coef_[0]).tocoo()
    items = sorted(((names[j], float(v)) for j, v in zip(contrib.col, contrib.data)), key=lambda x: -abs(x[1]))
    return [(t, round(v, 3)) for t, v in items[:n]]


MAX_CHARS = 20_000
WEIGHT_RULE, WEIGHT_ML = 0.7, 0.3
_QWORDS = re.compile(r"^\s*(apakah|apakh|apa\s+benar|benarkah|benerkah|betulkah|bener(an)?|beneran|kenapa|mengapa|bagaimana|gimana|siapa|kapan|dimana|di\s+mana|berapa)\b", re.I)


def input_kind(text: str) -> str:
    """'klaim' | 'pertanyaan' | 'terlalu_pendek'. Analyzer menilai teks klaim/berita, bukan menjawab pertanyaan."""
    t = str(text).strip()
    n = len(t.split())
    if n < 5:
        return "terlalu_pendek"
    if (t.endswith("?") or _QWORDS.search(t)) and n <= 25 and "." not in t.rstrip("?").strip()[:-1]:
        return "pertanyaan"
    return "klaim"

def analyze(text: str, source_url: str = ""):
    text = str(text)[:MAX_CHARS]
    rule_score, signals = rule_analysis(text, source_url)
    ml = ml_probability(text)
    final = round(WEIGHT_RULE * rule_score + WEIGHT_ML * ml, 1)
    # Gaya bahasa (clickbait/kapital) saja tidak cukup untuk menyatakan risiko tinggi
    strong = {"Desakan menyebarkan", "Sumber tidak jelas", "Sumber tidak dikenal"}
    capped = False
    if not any(n in strong for n, w, _ in signals) and final >= 50:
        final, capped = 49.0, True
    level = "Rendah" if final < 30 else "Sedang" if final < 60 else "Tinggi"
    credible = any(n == "Sumber kredibel" for n, _, _ in signals)
    return {"status": "Sumber kredibel (tetap perlu cek klaim)" if credible else "Belum Terverifikasi",
            "score": final, "level": level, "rule_score": rule_score,
            "ml_score": round(ml, 1), "signals": signals, "ml_terms": ml_top_terms(text),
            "capped_by_style_rule": capped, "input_kind": input_kind(text)}
