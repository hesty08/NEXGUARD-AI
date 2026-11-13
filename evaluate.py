"""Evaluasi model hoaks: hold-out train/test, cross-validation, pemeriksaan kelas, Brier score.

Semua angka hanya bermakna untuk dataset yang dipakai mengevaluasi. Pada data sintetis bawaan,
metrik hampir pasti terlalu optimistis. Gunakan dataset berlabel nyata (kolom: text,label)."""
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from paths import data_file

MIN_PER_CLASS = 5          # di bawah ini pemisahan latih/uji tidak layak
SMALL_DATASET = 200        # di bawah ini hasil dianggap sangat tidak stabil
IMBALANCE_RATIO = 0.4      # kelas minoritas / mayoritas di bawah ini = tidak seimbang


def make_model(balanced: bool = False):
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2)),
                         LogisticRegression(max_iter=1000, class_weight="balanced" if balanced else None))


def load_labeled(src) -> pd.DataFrame:
    """Baca & validasi dataset berlabel: kolom text, label (0 = bukan hoaks, 1 = hoaks)."""
    df = src if isinstance(src, pd.DataFrame) else pd.read_csv(src)
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if not {"text", "label"} <= set(df.columns):
        raise ValueError("Dataset berlabel harus memiliki kolom: text, label")
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df = df.dropna(subset=["text", "label"])
    df["text"] = df["text"].astype(str)
    df = df[df["text"].str.strip() != ""]
    if not set(df["label"].unique()) <= {0, 1}:
        raise ValueError("Kolom label hanya boleh berisi 0 (bukan hoaks) atau 1 (hoaks).")
    df["label"] = df["label"].astype(int)
    df = df.drop_duplicates("text")
    counts = df["label"].value_counts()
    if len(counts) < 2 or counts.min() < MIN_PER_CLASS:
        raise ValueError(f"Setiap kelas butuh minimal {MIN_PER_CLASS} contoh unik untuk dievaluasi.")
    return df.reset_index(drop=True)


def class_balance(df: pd.DataFrame) -> dict:
    c = df["label"].value_counts().to_dict()
    n0, n1 = c.get(0, 0), c.get(1, 0)
    ratio = min(n0, n1) / max(n0, n1, 1)
    return {"bukan_hoaks": n0, "hoaks": n1, "rasio_minoritas": round(ratio, 3), "tidak_seimbang": ratio < IMBALANCE_RATIO}


def _warnings(df, bal) -> list:
    w = []
    if len(df) < SMALL_DATASET:
        w.append(f"Dataset hanya {len(df)} contoh (<{SMALL_DATASET}); metrik sangat tidak stabil.")
    if bal["tidak_seimbang"]:
        w.append(f"Kelas tidak seimbang (rasio minoritas {bal['rasio_minoritas']:.2f}); accuracy bisa menyesatkan, "
                 "perhatikan precision/recall/F1 dan model memakai class_weight='balanced'.")
    w.append("Evaluasi hanya menggambarkan dataset ini. Performa pada hoaks nyata belum terbukti.")
    return w


def _metrics(y_true, y_pred, proba=None) -> dict:
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    out = {"accuracy": accuracy_score(y_true, y_pred), "precision": p, "recall": r, "f1": f,
           "confusion": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist()}
    if proba is not None:
        out["brier"] = brier_score_loss(y_true, proba)
    return out


def _perfect_warning(res: dict, warns: list) -> None:
    if min(res["accuracy"], res["precision"], res["recall"], res["f1"]) >= 0.99:
        warns.insert(0, "Skor (hampir) sempurna pada dataset sekecil/sesederhana ini patut dicurigai: kemungkinan data terlalu "
                        "mudah atau pola kalimatnya seragam (data sintetis). Jangan dipakai sebagai klaim akurasi.")


def holdout_evaluate(df: pd.DataFrame, test_size: float = 0.25, seed: int = 0) -> dict:
    """Latih pada sebagian data, uji pada data yang tidak pernah dilihat model (stratified)."""
    df = load_labeled(df)
    bal = class_balance(df)
    Xtr, Xte, ytr, yte = train_test_split(df["text"], df["label"], test_size=test_size,
                                          stratify=df["label"], random_state=seed)
    model = make_model(balanced=bal["tidak_seimbang"]).fit(Xtr, ytr)
    proba = model.predict_proba(Xte)[:, 1]
    res = _metrics(yte, model.predict(Xte), proba)
    res.update(n=len(df), n_train=len(Xtr), n_test=len(Xte), balance=bal, warnings=_warnings(df, bal),
               catatan_brier="Brier score: semakin kecil semakin baik; hanya indikasi awal, bukan bukti kalibrasi.")
    _perfect_warning(res, res["warnings"])
    return res


def cross_validate(path=None, folds=4) -> dict:
    """Stratified k-fold. Kunci hasil lama (n, precision, recall, f1, confusion) dipertahankan."""
    df = load_labeled(path if path is not None else data_file("hoax_sample.csv"))
    bal = class_balance(df)
    folds = max(2, min(folds, int(df["label"].value_counts().min())))
    pred = cross_val_predict(make_model(bal["tidak_seimbang"]), df["text"], df["label"],
                             cv=StratifiedKFold(folds, shuffle=True, random_state=0))
    res = _metrics(df["label"], pred)
    res.update(n=len(df), folds=folds, balance=bal, warnings=_warnings(df, bal))
    _perfect_warning(res, res["warnings"])
    return res


def rule_based_evaluate(df, threshold: float = 30.0) -> dict:
    """Evaluasi indikator linguistik (tanpa pelatihan) pada dataset berlabel yang sama.
    Skor >= threshold dianggap 'terindikasi hoaks'. Tidak ada tautan sumber yang diberikan."""
    import hoax
    df = load_labeled(df)
    pred = [int(hoax.rule_analysis(t, "")[0] >= threshold) for t in df["text"]]
    res = _metrics(df["label"], pred)
    res.update(n=len(df), threshold=threshold, balance=class_balance(df))
    return res


if __name__ == "__main__":
    import json
    d = load_labeled(data_file("hoax_sample.csv"))
    print(json.dumps(holdout_evaluate(d), indent=1, default=float))
