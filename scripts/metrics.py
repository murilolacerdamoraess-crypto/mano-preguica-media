#!/usr/bin/env python3
"""
MÉTRICAS REAIS do Instagram e do Facebook pela API oficial da Meta (04/10/2026).

Substitui o /stats do PostProxy (assinatura cancelada em 12/09, a API respondia 403 e o
metrics.json ficava vazio). O painel guarda o token da Meta; esta rotina chama
POST /api/meta/publicar {acao: "metricas"} e recebe os posts recentes da conta com os números.

Como casa post com vídeo do YouTube:
  1. pelo post_id gravado no ledger (posts feitos pela API da Meta, desde 04/10);
  2. pela legenda: o crosspost sempre começa a legenda com o título do vídeo (posts antigos,
     feitos pelo PostProxy, cujo id nativo não ficou salvo).

Grava metrics.json {vid: {title, yt_views, instagram: {...}, facebook: {...}}}. A chave
"impressions" guarda as visualizações (plays) de cada rede, que é o que o dashboard e o
scanner leem; "reach" fica ao lado. Se a Meta falhar, NÃO sobrescreve o metrics.json anterior.

Uso:
  PAINEL_TOKEN=... python metrics.py           -> atualiza metrics.json
  PAINEL_TOKEN=... python metrics.py --report   -> + manda ranking no Telegram
"""
import os, sys, json, re, unicodedata, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER  # noqa: E402

PAINEL    = os.environ.get("PAINEL_URL", "https://canal-agente-geer.vercel.app").rstrip("/")
PAINEL_TK = os.environ.get("PAINEL_TOKEN", "")
TG_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
OUT       = os.path.join(os.path.dirname(LEDGER), "metrics.json")


def log(*a): print(*a, flush=True)


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"#\w+", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def buscar():
    if not PAINEL_TK:
        log("metrics: sem PAINEL_TOKEN (rode com o secret)."); return None
    body = json.dumps({"t": PAINEL_TK, "acao": "metricas", "limite": 100}).encode()
    req = urllib.request.Request(f"{PAINEL}/api/meta/publicar", data=body,
            headers={"Content-Type": "application/json", "User-Agent": "crosspost-bot"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=90))
    except Exception as e:
        log(f"metrics: painel falhou: {e}"); return None
    if d.get("erro"):
        log(f"metrics: painel respondeu erro: {d['erro']}"); return None
    return d


def casar(led, post, net, por_id, titulos, por_data=None):
    vid = por_id.get((net, str(post["id"])))
    if vid: return vid
    leg = norm(post.get("legenda", ""))
    if not leg:
        # Reels do FB feitos pelo PostProxy voltam sem legenda: casa pela data, se o robô postou
        # um só vídeo na rede naquele dia (data UTC da Meta ou a do dia anterior, fuso BRT).
        dia = (post.get("data") or "")[:10]
        cands = (por_data or {}).get((net, dia), [])
        return cands[0] if len(cands) == 1 else None
    for t, v in titulos:                    # título mais longo primeiro (evita casar um prefixo curto)
        if t and leg.startswith(t): return v
    return None


def montar(led, d):
    vids = led["videos"]
    por_id = {(n, str(v["posted"][n].get("post_id"))): k for k, v in vids.items()
              for n in ("instagram", "facebook") if v["posted"].get(n, {}).get("post_id")}
    titulos = sorted(((norm(v.get("title", "")), k) for k, v in vids.items()), key=lambda x: -len(x[0]))
    import datetime
    por_data = {}
    for k, v in vids.items():
        for n in ("instagram", "facebook"):
            pd = v["posted"].get(n, {})
            if pd.get("done") and pd.get("date"):
                d0 = datetime.date.fromisoformat(pd["date"][:10])
                for dd in (d0, d0 + datetime.timedelta(days=1)):   # agendado à noite BRT = dia seguinte UTC
                    por_data.setdefault((n, dd.isoformat()), []).append(k)
    out, sem = {}, 0
    for net, chave in (("instagram", "ig"), ("facebook", "fb")):
        for p in d.get(chave, []):
            vid = casar(led, p, net, por_id, titulos, por_data)
            if not vid: sem += 1; continue
            v = vids[vid]
            row = out.setdefault(vid, {"title": v.get("title", ""), "yt_views": v.get("views", 0)})
            st = {"impressions": int(p.get("views") or 0), "link": p.get("link", ""), "data": p.get("data", "")}
            if net == "instagram":
                st.update({k: int(p.get(k) or 0) for k in ("reach", "likes", "comments", "shares", "saved")})
            else:
                st["reach"] = int(p.get("impressions") or 0)
            # o mesmo vídeo postado 2x na rede: fica o de mais views
            if st["impressions"] >= (row.get(net) or {}).get("impressions", -1):
                row[net] = st
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    log(f"metrics: {len(out)} vídeos com métricas; {sem} posts sem vídeo correspondente no ledger.")
    return out


def relatorio(out):
    linhas = ["📊 *Desempenho real (Meta)*"]
    for net, rot in (("instagram", "Instagram"), ("facebook", "Facebook")):
        rank = sorted(((r[net]["impressions"], r) for r in out.values() if net in r), key=lambda x: -x[0])
        rank = [x for x in rank if x[0] > 0][:5]
        if not rank: continue
        linhas.append(f"\n*{rot}* (top {len(rank)} por views)")
        for imp, r in rank:
            st = r[net]
            eng = st.get("likes", 0) + st.get("comments", 0) + st.get("shares", 0)
            linhas.append(f"  {imp:,} views · {eng} eng · {r['title'][:40]}".replace(",", "."))
    msg = "\n".join(linhas)
    if TG_TOKEN and TG_CHAT:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}).encode()
        try: urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        except Exception as e: log("metrics: telegram falhou:", e)
    return msg


def main():
    d = buscar()
    if d is None:
        log("metrics: mantendo o metrics.json anterior."); return
    log(f"metrics: Meta devolveu {len(d.get('ig', []))} posts do IG e {len(d.get('fb', []))} vídeos do FB.")
    out = montar(json.load(open(LEDGER)), d)
    if "--report" in sys.argv:
        print(relatorio(out))


if __name__ == "__main__":
    main()
