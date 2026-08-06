#!/usr/bin/env python3
"""
MÉTRICAS REAIS via PostProxy (substitui o Metricool).

A MESMA API que posta, mede: GET /api/posts/stats?post_ids=... devolve, por rede,
impressions/likes/comments/shares (TikTok), +saved/profile_visits/follows (IG),
+clicks (FB). Sem sessão viva, sem navegador, sem Metricool.

O que faz:
  1. varre o ledger e coleta os post_id que são HASHID do PostProxy
     (ignora legado 'metricool-*' e ids nativos de plataforma — o /stats não os aceita);
  2. bate no /stats em lotes de 50, pega o snapshot MAIS RECENTE por plataforma;
  3. grava metrics.json {vid: {title, yt_views, <net>: {impressions, likes, ...}}};
  4. (opcional) manda no Telegram o ranking dos campeões por rede.

Uso:
  POSTPROXY_KEY=... python metrics.py           -> atualiza metrics.json
  POSTPROXY_KEY=... python metrics.py --report   -> + manda ranking no Telegram
"""
import os, sys, json, re, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER, PROFILES  # noqa: E402  (raiz do ledger + redes que usamos)

PP_KEY   = os.environ.get("POSTPROXY_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
OUT      = os.path.join(os.path.dirname(LEDGER), "metrics.json")
API      = "https://api.postproxy.dev/api/posts/stats"


def log(*a): print(*a, flush=True)


def eh_hashid(pid):
    """True se parece um hashid do PostProxy (6-9 alfanumérico). Descarta legado e ids nativos."""
    if not pid or pid.startswith("metricool-"):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9]{6,9}", pid)) and not (pid.isdigit() and len(pid) > 12)


def coletar_ids(led):
    """{hashid: (vid, net)} de todos os posts com hashid do PostProxy."""
    idx = {}
    for vid, v in led["videos"].items():
        for net in PROFILES:
            p = v["posted"].get(net, {})
            pid = p.get("post_id")
            if p.get("done") and eh_hashid(pid):
                idx[pid] = (vid, net)
    return idx


def _stats_do_post(obj):
    """Extrai o snapshot mais recente por plataforma de um objeto de post do /stats.
    Tolerante ao shape: obj pode ter 'platforms':[{platform, records:[{stats, recorded_at}]}]."""
    saida = {}
    plats = obj.get("platforms") if isinstance(obj, dict) else None
    for pl in (plats or []):
        rede = (pl.get("platform") or "").lower()
        recs = pl.get("records") or []
        if not recs:
            continue
        # snapshot mais recente (records vêm ascendentes por recorded_at)
        ultimo = sorted(recs, key=lambda r: r.get("recorded_at") or "")[-1]
        st = dict(ultimo.get("stats") or {})
        st["recorded_at"] = ultimo.get("recorded_at")
        saida[rede] = st
    return saida


def buscar(ids):
    """Chama o /stats em lotes de 50 e devolve {hashid: {rede_plataforma: stats}}."""
    if not PP_KEY:
        log("metrics: sem POSTPROXY_KEY (rode com o secret)."); return {}
    todos = {}
    lote = list(ids)
    for i in range(0, len(lote), 50):
        q = urllib.parse.urlencode({"post_ids": ",".join(lote[i:i + 50])})
        req = urllib.request.Request(f"{API}?{q}", headers={"Authorization": f"Bearer {PP_KEY}"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
        except Exception as e:
            log(f"metrics: lote {i//50} falhou: {e}"); continue
        data = d.get("data", d)            # aceita {"data": {...}} ou {...}
        if isinstance(data, list):         # ou [{"id"/"post_id":..., "platforms":...}]
            data = {(x.get("id") or x.get("post_id")): x for x in data}
        for hid, obj in (data or {}).items():
            s = _stats_do_post(obj)
            if s:
                todos[hid] = s
    return todos


# nome da plataforma no /stats -> nossa chave de rede
PLAT2NET = {"tiktok": "tiktok", "instagram": "instagram", "facebook": "facebook"}


def montar(led, idx, stats):
    """Cruza stats (por hashid) de volta pro vídeo. Grava metrics.json."""
    out = {}
    for hid, por_plat in stats.items():
        vid, net = idx.get(hid, (None, None))
        if not vid:
            continue
        v = led["videos"].get(vid, {})
        row = out.setdefault(vid, {"title": v.get("title", ""), "yt_views": v.get("views", 0)})
        for plat, st in por_plat.items():
            row[PLAT2NET.get(plat, plat)] = st
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    return out


def views_da_rede(row, net):
    """Métrica de alcance por rede (impressions), com fallbacks."""
    st = row.get(net) or {}
    for k in ("impressions", "reach", "video_views", "views"):
        if isinstance(st.get(k), (int, float)):
            return int(st[k])
    return 0


def relatorio(out):
    linhas = ["📊 *Desempenho real (PostProxy)*"]
    for net, rot in (("tiktok", "TikTok"), ("instagram", "Instagram"), ("facebook", "Facebook")):
        rank = sorted(((views_da_rede(r, net), r) for r in out.values() if net in r), reverse=True)
        rank = [x for x in rank if x[0] > 0][:5]
        if not rank:
            continue
        linhas.append(f"\n*{rot}* (top {len(rank)} por impressões)")
        for imp, r in rank:
            st = r[net]
            eng = int(st.get("likes", 0)) + int(st.get("comments", 0)) + int(st.get("shares", 0))
            linhas.append(f"  {imp:,} imp · {eng} eng — {r['title'][:40]}".replace(",", "."))
    msg = "\n".join(linhas)
    if TG_TOKEN and TG_CHAT:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        except Exception as e:
            log("metrics: telegram falhou:", e)
    return msg


def main():
    led = json.load(open(LEDGER))
    idx = coletar_ids(led)
    log(f"metrics: {len(idx)} posts com hashid PostProxy no ledger.")
    stats = buscar(idx)
    out = montar(led, idx, stats)
    log(f"metrics: {len(out)} vídeos com métricas -> {OUT}")
    if "--report" in sys.argv:
        print(relatorio(out))


if __name__ == "__main__":
    main()
