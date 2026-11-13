"""Penyimpanan hasil analisis (SQLite)."""
import sqlite3, json, re
from datetime import datetime
import pandas as pd

from paths import DB_PATH

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS analyses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, module TEXT,
        subject TEXT, score REAL, level TEXT, detail TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, source TEXT, date TEXT, kind TEXT,
        level TEXT, value REAL, baseline REAL, z REAL, detail TEXT,
        UNIQUE(source, date, kind))""")
    return c

def mask_pii(text: str) -> str:
    """Samarkan data pribadi (email, nomor telepon, NIK 16 digit) sebelum disimpan."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", str(text))
    text = re.sub(r"\b\d{16}\b", "[nik]", text)
    return re.sub(r"(?<!\d)(\+?62|0)8\d{7,11}(?!\d)", "[telepon]", text)

def purge(days: int = 30):
    """Kebijakan retensi: hapus hasil analisis yang lebih lama dari N hari."""
    with _conn() as c:
        c.execute("DELETE FROM analyses WHERE ts < datetime('now', 'localtime', ?)", (f"-{int(days)} days",))
        c.execute("DELETE FROM alerts WHERE ts < datetime('now', 'localtime', ?)", (f"-{int(days)} days",))

def save(module, subject, score, level, detail):
    with _conn() as c:
        c.execute("INSERT INTO analyses(ts,module,subject,score,level,detail) VALUES(?,?,?,?,?,?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), module,
                   mask_pii(subject)[:120], float(score), level, json.dumps(detail, ensure_ascii=False)))

def load() -> pd.DataFrame:
    with _conn() as c:
        return pd.read_sql_query("SELECT * FROM analyses ORDER BY id DESC", c)

def clear():
    with _conn() as c:
        c.execute("DELETE FROM analyses")
        c.execute("DELETE FROM alerts")


def save_alerts(alerts: pd.DataFrame, source: str) -> int:
    """Simpan peringatan dini ke riwayat (satu baris per sumber+tanggal+jenis; menjalankan ulang memperbarui)."""
    if alerts is None or alerts.empty:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        for r in alerts.itertuples():
            c.execute("INSERT OR REPLACE INTO alerts(ts,source,date,kind,level,value,baseline,z,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                      (now, mask_pii(source)[:80], str(r.tanggal), r.jenis, r.tingkat, float(r.nilai), float(r.baseline),
                       float(r.z), mask_pii(r.penjelasan)[:400]))
    return len(alerts)

def load_alerts() -> pd.DataFrame:
    with _conn() as c:
        return pd.read_sql_query("SELECT ts, source, date, kind, level, value, baseline, z, detail FROM alerts "
                                 "ORDER BY id DESC", c)

def clear_alerts():
    with _conn() as c:
        c.execute("DELETE FROM alerts")
