"""Tampilan Streamlit untuk hasil verify.py. Dipakai oleh halaman 'Verifikasi AI' dan menu Hoax Analyzer."""
import html
import re

import pandas as pd
import streamlit as st

import factcheck
import theme
import verify

COLOR = {verify.BENAR: theme.GREEN, verify.SALAH: theme.RED, verify.SEBAGIAN: theme.AMBER, verify.TIDAK_PASTI: "#8a97a8"}


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def md_escape(text) -> str:
    """Teks dari AI/situs luar ditampilkan apa adanya, bukan sebagai markdown (mencegah tautan/gambar sisipan)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-!|<>~$])", r"\\\1", str(text))


def safe_link(u: str) -> str:
    return u if str(u).startswith(("http://", "https://")) else ""


def _evidence_df(rows, with_no=False):
    out = []
    for b in rows:
        r = {"No": b["idx"]} if with_no else {}
        r.update({"Penerbit": b["publisher"], "Penilaian": b["rating"], "Klaim yang diulas": b["claim_text"][:160],
                  "Kemiripan": b["match"], "Tautan": safe_link(b["url"])})
        out.append(r)
    return pd.DataFrame(out)


def show(res: dict):
    """Tampilkan hasil verify.verify()."""
    color = COLOR[res["putusan"]]
    st.markdown(f'<div class="risk-card" style="--c:{color}"><div class="sub">PUTUSAN AI (BANTUAN, BUKAN VONIS)</div>'
                f'<div class="lvl">{esc(res["putusan"].upper())}</div>'
                f'<div class="sub">{esc(res["penjelasan"])}</div></div>', unsafe_allow_html=True)
    st.warning("⚠️ Ini hasil bantuan AI, bukan putusan mutlak. Periksa tautan bukti sebelum mempercayai atau menyebarkan.")
    for w in res.get("peringatan", []):
        st.info(w)
    page = res.get("page")
    if page:
        st.markdown(f"📄 **Halaman dibaca:** {esc(page['title'] or '(tanpa judul)')} — `{esc(page['host'])}`"
                    + (f" · {esc(page['published'])}" if page["published"] else ""))

    for c in res["klaim"]:
        col = COLOR[c["putusan"]]
        with st.expander(f"{c['putusan']} — {md_escape(c['klaim'][:120])}", expanded=True):
            st.markdown(f'<span class="pill" style="--c:{col}">{esc(c["putusan"])}</span> &nbsp; '
                        f'keyakinan: **{esc(c["keyakinan"])}** · dasar: **{esc(c["dasar"])}**', unsafe_allow_html=True)
            st.markdown(md_escape(c["alasan"]))
            for n in c["catatan"]:
                st.warning(n)
            if c["bukti"]:
                st.markdown("**Bukti dari pemeriksa fakta**")
                st.dataframe(_evidence_df(c["bukti"]), width="stretch", hide_index=True,
                             column_config={"Tautan": st.column_config.LinkColumn()})
            if c["kutipan"]:
                st.markdown("**Kutipan dari halaman**")
                for q in c["kutipan"]:
                    st.text("“" + q.replace("\n", " ") + "”")
            if not c["bukti"] and not c["kutipan"]:
                st.caption("Tidak ada bukti yang dapat ditautkan untuk klaim ini.")

    with st.expander("Semua ulasan pemeriksa fakta yang ditemukan"):
        if res["bukti"]:
            st.dataframe(_evidence_df(res["bukti"], with_no=True), width="stretch", hide_index=True,
                         column_config={"Tautan": st.column_config.LinkColumn()})
        else:
            st.caption("Tidak ada ulasan yang cocok. Ini tidak berarti klaim benar atau salah, hanya belum pernah diulas.")
    if res.get("model"):
        st.caption(f"Model: {res['model']}")


def run_and_show(text: str, url: str):
    """Jalankan verifikasi lalu tampilkan. Mengembalikan hasil, atau None bila gagal (pesan error sudah ditampilkan)."""
    gem, fck = verify.get_gemini_key(), factcheck.get_api_key()
    if not gem:
        st.error("`GEMINI_API_KEY` belum diatur. Isi di `.streamlit/secrets.toml` lalu jalankan ulang aplikasi.")
        return None
    res = None
    try:
        with st.status("Memeriksa dengan AI...", expanded=True) as status:
            res = verify.verify(text, url, gem, fck, progress=lambda s: status.write(s))
            status.update(label="Selesai", state="complete", expanded=False)
    except verify.VerifyError as e:
        st.error(str(e))
        return None
    except Exception:
        st.error("Terjadi kesalahan tak terduga saat memeriksa. Coba lagi atau persingkat teksnya.")
        return None
    show(res)
    return res
