"""Social Network Analysis: graf hubungan antar-akun dari kemiripan teks dan kedekatan waktu unggah.

Sisi graf = dua akun memposting teks yang mirip. Atribut sisi: jumlah pasangan unggahan mirip ('mirip') dan berapa di
antaranya berdekatan waktu ('serempak'). Hasilnya KANDIDAT untuk ditinjau manusia, bukan bukti bot/operasi terkoordinasi."""
import hashlib
from collections import Counter, defaultdict
from itertools import combinations

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

MAX_UNIQUE = 5000        # batas teks unik yang dibandingkan
MAX_ACCOUNTS_PER_CLUSTER = 60   # batas akun per klaster agar jumlah sisi terkendali
MAX_POSTS_PER_ACCOUNT = 20     # postingan per akun per klaster yang dipertimbangkan (menjaga semua akun tetap terwakili)
MAX_NODES_FOR_COMMUNITIES = 1500
SYNC_WEIGHT = 3
GROUP_COLS = ["kelompok", "jumlah_akun", "klaster_teks", "kerapatan", "porsi_sisi_serempak", "prioritas", "contoh_teks", "akun"]
CLUSTER_COLS = ["klaster", "jumlah_post", "jumlah_akun", "contoh_teks"]


def pseudonym(name: str, salt: str = "cs") -> str:
    """Alias stabil (tidak dapat dibalik secara langsung) untuk melindungi identitas akun pada tampilan/laporan."""
    return "akun_" + hashlib.sha256((salt + str(name)).encode()).hexdigest()[:6]


def _norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()


def cluster_texts(d: pd.DataFrame, threshold: float = 0.7):
    """Kelompokkan unggahan bermiripan teks (TF-IDF cosine + union-find). Mengembalikan (d dengan kolom 'klaster', capped)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    d = d.dropna(subset=["text", "username"]).copy()
    d["norm"] = _norm(d["text"])
    d = d[d["norm"] != ""]
    uniq_all = d["norm"].drop_duplicates().tolist()
    capped = len(uniq_all) > MAX_UNIQUE
    uniq = uniq_all[:MAX_UNIQUE]
    parent = list(range(len(uniq)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    if len(uniq) > 1:
        X = TfidfVectorizer().fit_transform(uniq)
        from social import similar_pairs
        for i, b in similar_pairs(X, threshold):
            parent[find(b)] = find(i)
    cid = {t: find(i) for i, t in enumerate(uniq)}
    d["klaster"] = d["norm"].map(cid)
    return d.dropna(subset=["klaster"]), capped


def text_cluster_table(d: pd.DataFrame, min_accounts: int = 2) -> pd.DataFrame:
    rows = []
    for cid, g in d.groupby("klaster"):
        n_acc = g["username"].nunique()
        if n_acc >= min_accounts:
            rows.append(dict(klaster=int(cid), jumlah_post=len(g), jumlah_akun=n_acc, contoh_teks=g["text"].iloc[0][:90]))
    out = pd.DataFrame(rows, columns=CLUSTER_COLS)
    return out.sort_values(["jumlah_akun", "jumlah_post"], ascending=False).reset_index(drop=True)


def build_graph(d: pd.DataFrame, threshold: float = 0.7, window_min: int = 15, min_accounts: int = 2):
    """Bangun graf akun. Kembalikan (G, info). info memuat 'capped', 'trimmed', 'has_time', 'window_min'."""
    d, capped = cluster_texts(d, threshold)
    d = d.reset_index(drop=True)
    has_time = "timestamp" in d.columns
    users = d["username"].to_numpy()
    BIG = np.iinfo("int64").max
    if has_time:
        from social import to_ns
        ts_ns, valid = to_ns(d["timestamp"])
        ts_ns = np.where(valid, ts_ns, BIG)
    win_ns = window_min * 60 * 1_000_000_000
    G = nx.Graph()
    edges = defaultdict(lambda: [0, 0])    # (a,b) -> [mirip, serempak]
    clusters_of = defaultdict(set)
    trimmed = False
    n_acc = d.groupby("klaster")["username"].nunique()
    groups = d.groupby("klaster").indices
    for cid in n_acc[n_acc >= min_accounts].index:
        idx = groups[cid]
        if has_time:
            idx = idx[np.argsort(ts_ns[idx], kind="stable")]
        u = users[idx]
        per_acc = pd.Series(u).groupby(u).cumcount().to_numpy()
        if (per_acc >= MAX_POSTS_PER_ACCOUNT).any():
            idx, trimmed = idx[per_acc < MAX_POSTS_PER_ACCOUNT], True
            u = users[idx]
        accs = list(dict.fromkeys(u))
        if len(accs) > MAX_ACCOUNTS_PER_CLUSTER:
            accs, trimmed = accs[:MAX_ACCOUNTS_PER_CLUSTER], True
            keep = np.isin(u, accs)
            idx, u = idx[keep], u[keep]
        first = Counter(u)
        for a_, b_ in combinations(sorted(accs), 2):
            edges[(a_, b_)][0] += int(min(first[a_], first[b_]))
        for a_ in accs:
            clusters_of[a_].add(int(cid))
        if has_time:
            ok = valid[idx]
            t_, us = ts_ns[idx][ok].tolist(), u[ok].tolist()
            seen, lo = set(), 0
            for hi in range(len(t_)):
                while t_[hi] - t_[lo] > win_ns:
                    lo += 1
                for k in range(lo, hi):
                    if us[k] != us[hi]:
                        seen.add((us[k], us[hi]) if us[k] < us[hi] else (us[hi], us[k]))
            for pair in seen:
                edges[pair][1] += 1
    for (a_, b_), (sim, sync) in edges.items():
        G.add_edge(a_, b_, mirip=sim, serempak=sync, weight=sim + SYNC_WEIGHT * sync)
    for n in G.nodes:
        G.nodes[n]["klaster"] = sorted(clusters_of[n])
    return G, {"capped": capped, "trimmed": trimmed, "has_time": has_time, "window_min": window_min}


def communities(G: nx.Graph) -> list:
    """Komunitas berbobot (modularity). Untuk graf sangat besar dipakai komponen terhubung agar tetap cepat."""
    if G.number_of_nodes() == 0:
        return []
    if G.number_of_nodes() > MAX_NODES_FOR_COMMUNITIES:
        return [set(c) for c in nx.connected_components(G)]
    return [set(c) for c in nx.algorithms.community.greedy_modularity_communities(G, weight="weight")]


def review_groups(G: nx.Graph, d: pd.DataFrame, min_size: int = 3) -> pd.DataFrame:
    """Kelompok (komponen terhubung) yang layak ditinjau. 'prioritas' hanya urutan peninjauan, bukan vonis."""
    rows = []
    texts = d.dropna(subset=["text"]).groupby("username")["text"].first() if not d.empty else pd.Series(dtype=str)
    comps = sorted(communities(G), key=len, reverse=True)
    for i, comp in enumerate(comps, 1):
        if len(comp) < min_size:
            continue
        sub = G.subgraph(comp)
        sync_edges = sum(1 for _, _, a in sub.edges(data=True) if a["serempak"] > 0)
        share = sync_edges / max(sub.number_of_edges(), 1)
        density = nx.density(sub)
        n_clusters = len({c for n in comp for c in G.nodes[n]["klaster"]})
        prio = "Tinggi" if (share >= 0.5 and len(comp) >= 5) else "Sedang" if share >= 0.2 else "Rendah"
        accs = sorted(comp, key=lambda n: -sub.degree(n, weight="weight"))
        rows.append(dict(kelompok=i, jumlah_akun=len(comp), klaster_teks=n_clusters, kerapatan=round(density, 2),
                         porsi_sisi_serempak=round(share, 2), prioritas=prio,
                         contoh_teks=str(texts.get(accs[0], ""))[:90],
                         akun=", ".join(accs[:8]) + (" ..." if len(accs) > 8 else "")))
    return pd.DataFrame(rows, columns=GROUP_COLS)


def figure(G: nx.Graph, alias: bool = False, title: str = "Jaringan akun berdasarkan kemiripan teks") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, showlegend=True, template="plotly_dark", height=620, margin=dict(l=10, r=10, t=50, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False), legend=dict(orientation="h", y=-0.05))
    if G.number_of_nodes() == 0:
        fig.add_annotation(text="Tidak ada hubungan antar-akun pada ambang yang dipilih.", showarrow=False, font=dict(size=15))
        return fig
    pos = nx.spring_layout(G, seed=42, weight="weight", k=1.2 / max(np.sqrt(G.number_of_nodes()), 1))
    name = (lambda n: pseudonym(n)) if alias else (lambda n: str(n))
    for sync, color, label in ((False, "rgba(120,160,220,.35)", "Teks mirip"), (True, "rgba(255,77,77,.55)", "Teks mirip + serempak")):
        xs, ys = [], []
        for a, b, at in G.edges(data=True):
            if (at["serempak"] > 0) == sync:
                xs += [pos[a][0], pos[b][0], None]
                ys += [pos[a][1], pos[b][1], None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=1.2, color=color), hoverinfo="skip", name=label))
    comp_id = {n: i for i, c in enumerate(sorted(communities(G), key=len, reverse=True)) for n in c}
    palette = ["#00e676", "#4da3ff", "#ffb020", "#c084fc", "#2dd4bf", "#f472b6", "#a3e635", "#fb923c"]
    nodes = list(G.nodes)
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers", name="Akun",
        marker=dict(size=[8 + 2.2 * min(G.degree(n), 12) for n in nodes], line=dict(width=1, color="#0a1628"),
                    color=[palette[comp_id[n] % len(palette)] for n in nodes]),
        text=[f"{name(n)}<br>koneksi: {G.degree(n)}<br>kelompok: {comp_id[n] + 1}" for n in nodes], hoverinfo="text"))
    return fig
