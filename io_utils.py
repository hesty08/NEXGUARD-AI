"""Pembacaan CSV yang aman: batas ukuran/baris, deteksi file bukan-teks, fallback encoding,
dan pesan kesalahan berbahasa Indonesia yang mudah dipahami (selalu ValueError)."""
import io
import pandas as pd

MAX_MB = 20
MAX_ROWS = 200_000
ENCODINGS = ("utf-8-sig", "cp1252")  # cp1252 = fallback untuk file Excel/Windows lama


def _to_bytes(src) -> bytes:
    if hasattr(src, "getvalue"):          # UploadedFile / BytesIO / StringIO
        data = src.getvalue()
    elif hasattr(src, "read"):
        data = src.read()
    else:
        with open(src, "rb") as f:        # path file
            data = f.read()
    return data.encode("utf-8") if isinstance(data, str) else data


def safe_read_csv(src, max_mb=MAX_MB, max_rows=MAX_ROWS) -> pd.DataFrame:
    size = getattr(src, "size", None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValueError(f"File terlalu besar (maks {max_mb} MB).")
    try:
        raw = _to_bytes(src)
    except OSError:
        raise ValueError("File tidak dapat dibuka. Periksa nama dan lokasi file.") from None
    if len(raw) > max_mb * 1024 * 1024:
        raise ValueError(f"File terlalu besar (maks {max_mb} MB).")
    if not raw.strip():
        raise ValueError("File CSV kosong.")
    if b"\x00" in raw[:4096]:
        raise ValueError("File tampak bukan CSV teks (berisi data biner). Unggah file berformat .csv.")
    df, last = None, None
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(io.BytesIO(raw), nrows=max_rows + 1, encoding=enc)
            break
        except UnicodeDecodeError as e:
            last = e
        except (pd.errors.ParserError, pd.errors.EmptyDataError):
            raise ValueError("Format CSV tidak valid. Pastikan file berformat CSV dengan baris judul kolom.") from None
    if df is None:
        raise ValueError("Encoding file tidak dikenali. Simpan ulang sebagai CSV UTF-8.") from last
    df.columns = [str(c).strip() for c in df.columns]
    if len(df) > max_rows:
        raise ValueError(f"Terlalu banyak baris (maks {max_rows:,}).")
    if df.empty:
        raise ValueError("File CSV tidak berisi data (hanya baris judul).")
    return df
