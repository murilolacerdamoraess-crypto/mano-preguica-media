#!/usr/bin/env python3
"""
PAINEL DO CANAL AGENTE — central visual (o "VidaOS do conteúdo").

Site estático multi-página com SIDEBAR de navegação e THUMBNAILS do YouTube. Zero dependência
externa (ícones SVG inline; as thumbs vêm do CDN público img.youtube.com). Sem API paga.
  - index.html  : HOME. Hero do dia + Precisa de você (com thumbnail e contexto) + cards de rede.
  - <rede>.html : panorama da rede (performance com thumbnail + próximos + ANÁLISE do Claude).
Lê só o que a esteira gera (ledger/metrics/schedule/operacao/producao/analises).
"""
import os, sys, json, datetime, html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER, queue_curada  # noqa: E402
RAIZ  = os.path.dirname(LEDGER)
SCHED = os.path.join(RAIZ, "schedule.json")
MET   = os.path.join(RAIZ, "metrics.json")
OPER  = os.path.join(HERE, "operacao.json")
PROD  = os.path.join(HERE, "producao.json")
SHORTS= os.path.join(RAIZ, "shorts_feitos.json")
ANALI = os.path.join(RAIZ, "dashboard-analises.json")
PERF  = os.path.join(RAIZ, "dashboard-performance.json")
ROTE  = os.path.join(RAIZ, "dashboard-roteiros.json")
APREN = os.path.join(RAIZ, "dashboard-aprendizados.json")
DOSSIE_URL = "../ROTEIROS - DOSSIÊS/"   # relativo à pasta do painel no Drive
OUTDIR= os.path.join(RAIZ, "dashboard")
BRT   = datetime.timezone(datetime.timedelta(hours=-3))


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def esc(s): return html.escape(str(s))

def thumb(vid):
    return f"https://img.youtube.com/vi/{esc(vid)}/mqdefault.jpg"

_I = {
 "target":'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
 "check":'<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>',
 "alert":'<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
 "x":'<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
 "pause":'<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
 "calendar":'<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>',
 "film":'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
 "home":'<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/>',
 "poll":'<path d="M3 3v18h18"/><rect x="7" y="10" width="3" height="7"/><rect x="12" y="6" width="3" height="11"/><rect x="17" y="13" width="3" height="4"/>',
 "scissors":'<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 12.5 20 20M8.1 8.1 12 12"/>',
 "chat":'<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-4-.9L3 21l1.9-4.5A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z"/>',
 "radar":'<path d="M19.07 4.93A10 10 0 1 0 21 12"/><path d="M12 12 8 8M12 2v4"/>',
 "search":'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
 "arrow":'<path d="M5 12h14M13 6l6 6-6 6"/>',
 "spark":'<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
 "youtube":'<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3Z"/>',
 "tiktok":'<path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/>',
 "doc":'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h6"/>',
 "bulb":'<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.5.5 1 1.2 1 2.5h6c0-1.3.5-2 1-2.5A6 6 0 0 0 12 3Z"/>',
 "instagram":'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17" cy="7" r="1"/>',
 "facebook":'<path d="M15 3h-2a4 4 0 0 0-4 4v3H7v4h2v7h4v-7h3l1-4h-4V7a1 1 0 0 1 1-1h2Z"/>',
}
_FILLED = {"tiktok"}   # ícones de marca (path fechado, fill em vez de stroke)
def icon(n, cls="ic"):
    if n in _FILLED:
        return f'<svg class="{cls}" viewBox="0 0 24 24" fill="currentColor" stroke="none">{_I.get(n,"")}</svg>'
    return f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_I.get(n,"")}</svg>'

NETS = [("youtube", "YouTube"), ("tiktok", "TikTok"), ("instagram", "Instagram"), ("facebook", "Facebook")]

CSS = """
:root{--bg:#f4f4f2;--card:#fff;--ink:#161616;--sub:#6b6b6b;--line:#e7e4df;--accent:#0f6e5a;--acc-bg:rgba(15,110,90,.09);
--ok:#1a8f6b;--warn:#c07d17;--bad:#c0392b;--yt:#e0402b;--tt:#111;--ig:#c8398f;--fb:#2a6fd6;
--shadow:0 1px 2px rgba(0,0,0,.04),0 6px 20px rgba(0,0,0,.05)}
@media(prefers-color-scheme:dark){:root{--bg:#0e0e0e;--card:#1a1a1a;--ink:#eee;--sub:#9a9a9a;--line:#282828;--accent:#3fbfa3;--acc-bg:rgba(63,191,163,.13);
--ok:#43c99a;--warn:#e0a24a;--bad:#ef7361;--yt:#f0684f;--tt:#e6e6e6;--ig:#e968b0;--fb:#5b93ea;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35)}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif}
.app{display:flex;max-width:1120px;margin:0 auto;min-height:100vh}
.side{width:216px;flex:none;padding:22px 14px;position:sticky;top:0;height:100vh;border-right:1px solid var(--line)}
.side .brand{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700;text-decoration:none;color:var(--ink);padding:6px 10px;margin-bottom:18px}
.side .brand .logo{width:30px;height:30px;border-radius:8px;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center}
.side .brand .logo svg{width:18px;height:18px}
.nav a{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:9px;text-decoration:none;color:var(--sub);font-size:14px;font-weight:500;margin-bottom:2px}
.nav a .ic{width:18px;height:18px}
.nav a:hover{background:var(--acc-bg);color:var(--ink)}
.nav a.on{background:var(--acc-bg);color:var(--accent);font-weight:700}
.nav .sep{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--sub);padding:14px 11px 6px;font-weight:700}
.main{flex:1;min-width:0;padding:26px 30px 80px}
@media(max-width:720px){.app{flex-direction:column}.side{width:auto;height:auto;position:static;border-right:none;border-bottom:1px solid var(--line);padding:14px}
.nav{display:flex;gap:4px;overflow-x:auto}.nav .sep{display:none}.nav a{white-space:nowrap;margin:0}.main{padding:20px 16px 70px}}
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.head h1{font-size:20px;margin:0}.date{color:var(--sub);font-size:13px}
.ic{width:18px;height:18px;flex:none}
.hero{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:20px;box-shadow:var(--shadow)}
.hero .lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--sub);font-weight:700;margin-bottom:5px}
.hero .big{font-size:19px;font-weight:700}.hero .big.calm{color:var(--ok)}
h2{display:flex;align-items:center;gap:8px;font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--sub);font-weight:700;margin:24px 0 11px}
h2 .ic{width:15px;height:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
.item{display:flex;align-items:center;gap:13px;padding:12px 14px;border-bottom:1px solid var(--line)}.item:last-child{border-bottom:none}
.thumb{width:76px;height:43px;border-radius:7px;object-fit:cover;background:var(--line);flex:none}
.thumb.sm{width:64px;height:36px}
.ph{width:76px;height:43px;border-radius:7px;background:var(--acc-bg);color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}
.item .bd{flex:1;min-width:0}
.item .tt{font-weight:600;font-size:14px;line-height:1.3}
.item .ds{font-size:12.5px;color:var(--sub);margin-top:3px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:5px;background:var(--acc-bg);color:var(--accent);border-radius:6px;padding:2px 8px;font-size:11.5px;font-weight:600}
.pill .ic{width:12px;height:12px}
.empty{padding:16px;color:var(--sub);font-size:13.5px}
.nets{display:grid;grid-template-columns:1fr 1fr;gap:13px}
@media(max-width:560px){.nets{grid-template-columns:1fr}}
.ncard{display:flex;align-items:center;gap:13px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:var(--shadow);text-decoration:none;color:var(--ink)}
.ncard:hover{border-color:var(--accent)}
.ncard .nic{width:40px;height:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;color:#fff;flex:none}
.ncard .nic .ic{width:22px;height:22px}
.yt-bg{background:var(--yt)}.tt-bg{background:var(--tt)}.ig-bg{background:var(--ig)}.fb-bg{background:var(--fb)}
.ncard .nm{flex:1;min-width:0}.ncard .nm b{font-size:15px}.ncard .nm .st{font-size:12.5px;color:var(--sub);margin-top:2px;display:flex;align-items:center;gap:6px}
.dot{width:8px;height:8px;border-radius:50%;flex:none}.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.muted{background:var(--sub)}
.ncard .go{color:var(--sub);flex:none}.ncard .go .ic{width:18px;height:18px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:7px 13px;font-size:12.5px;box-shadow:var(--shadow)}
.chip .ic{width:14px;height:14px;color:var(--accent)}.chip code{color:var(--accent);font:12px ui-monospace,Menlo,monospace}
.subhead{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.subhead .nic{width:40px;height:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;color:#fff;flex:none}
.subhead .nic .ic{width:22px;height:22px}.subhead h1{font-size:21px;margin:0}
.pf{display:flex;align-items:center;gap:12px;padding:11px 14px;border-bottom:1px solid var(--line)}.pf:last-child{border-bottom:none}
.pf .bd{flex:1;min-width:0}
.pf .l1{display:flex;justify-content:space-between;gap:8px;font-size:13px;margin-bottom:5px}
.pf .l1 .n{color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pf .l1 .v{font-weight:700;flex:none}
.pf .track{height:7px;background:var(--line);border-radius:99px;overflow:hidden}.pf .fill{height:100%;border-radius:99px}
.analise{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow);line-height:1.65}
.analise .r{font-weight:600;margin-bottom:8px}.analise p{margin:0;color:var(--sub)}.analise .up{font-size:11px;color:var(--sub);margin-top:12px}
.prow{display:flex;align-items:center;gap:12px;padding:11px 14px;border-bottom:1px solid var(--line)}.prow:last-child{border-bottom:none}
.prow .d{font-size:12px;font-weight:700;width:48px;flex:none;text-align:center;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:5px 0;line-height:1.1}
.prow .d small{display:block;font-size:9px;color:var(--sub);text-transform:uppercase}
.prow .t{font-size:13.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.learn{display:flex;gap:12px;padding:13px 15px;border-bottom:1px solid var(--line)}.learn:last-child{border-bottom:none}
.learn .li{width:30px;height:30px;border-radius:8px;background:var(--acc-bg);color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}.learn .li .ic{width:16px;height:16px}
.learn .lt{font-weight:600;font-size:14px}.learn .lx{font-size:13px;color:var(--sub);margin-top:3px;line-height:1.5}.learn .lf{font-size:11px;color:var(--sub);margin-top:5px;opacity:.8}
.rt{display:flex;align-items:center;gap:13px;padding:13px 15px;border-bottom:1px solid var(--line);text-decoration:none;color:var(--ink)}.rt:last-child{border-bottom:none}.rt:hover{background:var(--acc-bg)}
.rt .ri{width:46px;height:46px;border-radius:10px;background:var(--acc-bg);color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}.rt .ri .ic{width:22px;height:22px}
.rt .rb{flex:1;min-width:0}.rt .rname{display:block;font-weight:600;font-size:14.5px}.rt .rmeta{display:block;font-size:12.5px;color:var(--sub);margin-top:3px}
.rt .rs{font-size:11px;font-weight:700;color:var(--ok);border:1px solid var(--ok);border-radius:999px;padding:2px 9px;flex:none}
.bignada{text-align:center;padding:40px 20px;color:var(--sub)}.bignada .bi{width:46px;height:46px;color:var(--line);margin-bottom:10px}.bignada b{color:var(--ink);display:block;margin-bottom:4px}.bignada code{color:var(--accent);font:12.5px ui-monospace,Menlo,monospace}
footer{color:var(--sub);font-size:12px;margin-top:32px}
"""

COMANDOS = [
    ("radar", "roda o radar de hype"), ("film", "me dá um roteiro"),
    ("scissors", "faz o short desse longo"), ("chat", "responde os comentários"),
    ("poll", "me dá N enquetes"), ("search", "analisa as redes"),
]

def sidebar(ativa):
    S = [f'<a class="brand" href="index.html"><span class="logo">{icon("film")}</span>Canal Agente</a><nav class="nav">']
    S.append(f'<a href="index.html" class="{"on" if ativa=="home" else ""}">{icon("home")} Visão geral</a>')
    S.append(f'<a href="roteiros.html" class="{"on" if ativa=="roteiros" else ""}">{icon("doc")} Roteiros</a>')
    S.append(f'<a href="aprendizados.html" class="{"on" if ativa=="aprendizados" else ""}">{icon("bulb")} Aprendizados</a>')
    S.append('<div class="sep">Redes</div>')
    for net, nome in NETS:
        S.append(f'<a href="{net}.html" class="{"on" if ativa==net else ""}">{icon(net)} {nome}</a>')
    S.append('</nav>')
    return '<aside class="side">' + "".join(S) + '</aside>'

def shell(title, ativa, body):
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head><body><div class="app">'
            + sidebar(ativa) + '<main class="main">' + body
            + '<footer>Painel do Canal Agente · dados vivos da esteira · sem API paga</footer>'
            '</main></div></body></html>')


def net_status(hoje, net, oper, led, prod):
    if net == "youtube":
        fut = sorted(d["data"] for d in oper.get("youtube_videos", {}).get("agendados", []) if d["data"] >= str(hoje))
        if not fut: return ("bad", "nada agendado")
        ate = datetime.date.fromisoformat(fut[-1]); dias = (ate - hoje).days
        return ("ok" if dias >= 7 else "warn", f"{len(fut)} agendados · até {ate.strftime('%d/%m')}")
    if net in ("tiktok", "instagram"):
        n = len(queue_curada(net, led["videos"]))
        return ("ok" if n >= 7 else "warn", f"{n} no backlog curado")
    if net == "facebook":
        return ("muted", "baixa prioridade · 1x/semana")
    return ("muted", "")

def proximos_net(hoje, net, oper, sched):
    itens = []
    if net == "youtube":
        for it in oper.get("youtube_videos", {}).get("agendados", []):
            if it["data"] >= str(hoje): itens.append((it["data"], it["titulo"]))
        for it in oper.get("enquetes", {}).get("agendados", []):
            if it["data"] >= str(hoje): itens.append((it["data"], "Enquete: " + it["titulo"]))
    else:
        agora = datetime.datetime.now(BRT)
        for s in sched:
            if s.get("net") != net: continue
            try: dt = datetime.datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00")).astimezone(BRT)
            except Exception: continue
            if dt > agora: itens.append((dt.date().isoformat(), s.get("title", "")))
    itens.sort()
    return itens[:8]

def perf_net(met, net, perf_real):
    """Prioriza a performance REAL (Metricool, em dashboard-performance.json). Cai pro PostProxy
    (metrics.json) nas redes que ainda não têm fonte melhor. Devolve (itens, unidade, fonte)."""
    reais = perf_real.get(net)
    if reais:
        itens = [(int(x["views"]), x.get("vid"), x.get("titulo", "")) for x in reais if x.get("views")]
        itens.sort(reverse=True)
        return itens[:8], "views", "Metricool"
    rank = []
    for vid, r in met.items():
        stt = r.get(net)
        if not stt: continue
        imp = 0
        for k in ("impressions", "reach", "video_views", "views"):
            if isinstance(stt.get(k), (int, float)): imp = int(stt[k]); break
        if imp > 0: rank.append((imp, vid, r.get("title", "")))
    rank.sort(reverse=True)
    return rank[:6], "impressões", "PostProxy"

JANELA_SHORT = int(os.environ.get("JANELA_SHORT", "75"))  # longo até X dias ainda vale um short-isca
def shorts_pendentes(hoje, led):
    """TODO longo recente (até JANELA_SHORT dias) que ainda não virou short. SEM piso de views
    (o short é isca pra puxar view; longo de poucas views é justamente quem mais precisa).
    Marcados em shorts_feitos.json (o Murilo fala 'já fiz o short do X') não aparecem."""
    feitos = set(load(SHORTS, []))
    cand = []
    for vid, v in led["videos"].items():
        if v.get("type") != "long" or vid in feitos: continue
        try: idade = (hoje - datetime.date.fromisoformat(v["published"][:10])).days
        except Exception: continue
        if 0 <= idade <= JANELA_SHORT:
            cand.append((idade, v.get("views", 0), v.get("title", ""), vid))
    cand.sort()
    return cand


def home(hoje, oper, led, prod, met):
    pend = shorts_pendentes(hoje, led)
    gaps = []
    for key, nome, cad in (("mp1_shorts", "MP1 Shorts", "3x/sem"), ("mp2", "MP2 (IA)", "2x/sem")):
        if not [a for a in prod.get(key, {}).get("agendados", []) if a["data"] >= str(hoje)]:
            gaps.append((nome, cad))
    B = []
    B.append(f'<div class="head"><h1>Visão geral</h1><span class="date">{hoje.strftime("%d/%m/%Y")} · Mano Preguiça</span></div>')
    if not pend and not gaps:
        B.append('<div class="hero"><div class="lbl">Hoje</div><div class="big calm">Tudo em dia. Nada te esperando.</div></div>')
    else:
        partes = []
        if pend: partes.append(f'{len(pend)} short(s) pra fazer')
        if gaps: partes.append(f'{len(gaps)} frente(s) pra produzir')
        B.append(f'<div class="hero"><div class="lbl">Hoje precisa de você</div><div class="big">{esc(" · ".join(partes))}</div></div>')

    if pend or gaps:
        B.append(f'<h2>{icon("spark")} Precisa de você</h2><div class="card">')
        for idade, views, titulo, vid in pend:
            quando = "postado hoje" if idade == 0 else f"há {idade} dias"
            B.append(f'<div class="item"><img class="thumb" loading="lazy" src="{thumb(vid)}" alt="">'
                     f'<div class="bd"><div class="tt">{esc(titulo)}</div>'
                     f'<div class="ds"><span class="pill">{icon("youtube")} Vídeo longo do YouTube</span>'
                     f'vira um Short · {quando} · {views:,} views</div></div>'.replace(",", ".")
                     + '</div>')
        for nome, cad in gaps:
            B.append(f'<div class="item"><span class="ph">{icon("film")}</span>'
                     f'<div class="bd"><div class="tt">Produzir {esc(nome)}</div>'
                     f'<div class="ds"><span class="pill">{icon("youtube")} Você produz</span>{esc(cad)} · nada agendado</div></div></div>')
        B.append('</div>')

    B.append(f'<h2>{icon("target")} Suas redes</h2><div class="nets">')
    for net, nome in NETS:
        cor, stat = net_status(hoje, net, oper, led, prod)
        B.append(f'<a class="ncard" href="{net}.html"><span class="nic {net[:2]}-bg">{icon(net)}</span>'
                 f'<span class="nm"><b>{nome}</b><span class="st"><span class="dot {cor}"></span>{esc(stat)}</span></span>'
                 f'<span class="go">{icon("arrow")}</span></a>')
    B.append('</div>')
    B.append(f'<h2>{icon("chat")} Atalhos (peça pro Claude)</h2><div class="chips">')
    for ic, say in COMANDOS:
        B.append(f'<span class="chip">{icon(ic)}<code>{esc(say)}</code></span>')
    B.append('</div>')
    return shell("Canal Agente", "home", "".join(B))


def page_net(hoje, net, nome, oper, led, prod, met, sched, analises, perf_real, aprendizados):
    prox = proximos_net(hoje, net, oper, sched)
    perf, unidade, fonte = perf_net(met, net, perf_real)
    an = analises.get(net, {})
    learns = [a for a in aprendizados if net in a.get("redes", [])]
    cor, stat = net_status(hoje, net, oper, led, prod)
    B = []
    B.append(f'<div class="subhead"><span class="nic {net[:2]}-bg">{icon(net)}</span><h1>{nome}</h1></div>')
    B.append(f'<p style="color:var(--sub);margin:0 0 4px"><span class="dot {cor}"></span> {esc(stat)}</p>')

    B.append(f'<h2>{icon("spark")} Minha análise</h2>')
    if an:
        B.append(f'<div class="analise"><div class="r">{esc(an.get("resumo",""))}</div>'
                 f'<p>{esc(an.get("texto",""))}</p><div class="up">Escrita pelo Claude · peça "analisa as redes" pra atualizar</div></div>')
    else:
        B.append(f'<div class="analise"><p>Ainda não analisei essa rede. Peça: <code>analisa o {esc(nome)}</code>.</p></div>')

    if learns:
        B.append(f'<h2>{icon("bulb")} O que já aprendi aqui</h2><div class="card">')
        for a in learns:
            B.append(f'<div class="learn"><span class="li">{icon("bulb")}</span><div>'
                     f'<div class="lt">{esc(a.get("titulo",""))}</div><div class="lx">{esc(a.get("texto",""))}</div></div></div>')
        B.append('</div>')

    if net in ("tiktok", "instagram", "facebook"):
        B.append(f'<h2>{icon("poll")} Performance · {esc(unidade)} <span style="color:var(--sub);font-weight:600;text-transform:none;letter-spacing:0">(fonte: {esc(fonte)})</span></h2><div class="card">')
        if perf:
            mx = max(v for v, _, _ in perf) or 1
            for v, vid, t in perf:
                pct = max(4, round(v / mx * 100))
                th = f'<img class="thumb sm" loading="lazy" src="{thumb(vid)}" alt="">' if vid else '<span class="ph" style="width:64px;height:36px"></span>'
                B.append(f'<div class="pf">{th}'
                         f'<div class="bd"><div class="l1"><span class="n">{esc(t)}</span><span class="v">{v:,}</span></div>'.replace(",", ".")
                         + f'<div class="track"><div class="fill" style="width:{pct}%;background:var(--{net[:2]})"></div></div></div></div>')
        else:
            B.append('<div class="empty">Sem dados dessa rede ainda.</div>')
        B.append('</div>')

    B.append(f'<h2>{icon("calendar")} Próximos {"vídeos e enquetes" if net=="youtube" else "posts"}</h2><div class="card">')
    if not prox:
        B.append('<div class="empty">Nada agendado à frente.</div>')
    for data, titulo in prox:
        dt = datetime.date.fromisoformat(data)
        B.append(f'<div class="prow"><div class="d">{dt.strftime("%d")}<small>{dt.strftime("%b").lower()}</small></div>'
                 f'<div class="t">{esc(titulo)}</div></div>')
    B.append('</div>')
    return shell(f"{nome} · Canal Agente", net, "".join(B))


def page_roteiros(hoje, roteiros):
    B = [f'<div class="head"><h1>Roteiros prontos</h1><span class="date">{hoje.strftime("%d/%m/%Y")}</span></div>']
    if not roteiros:
        B.append(f'<div class="card"><div class="bignada">{icon("doc","bi")}'
                 f'<b>Nenhum roteiro pronto agora.</b>Peça ao Claude: <code>me dá um roteiro</code> '
                 f'(ele acha o tema e entrega o dossiê pronto pra gravar).</div></div>')
    else:
        B.append('<div class="card">')
        for r in roteiros:
            meta = f'{esc(r.get("jogo",""))} · motor {esc(r.get("motor",""))} · {esc(r.get("data",""))}'
            arq = esc(DOSSIE_URL + r.get("arquivo", "")) if r.get("arquivo") else "#"
            B.append(f'<a class="rt" href="{arq}"><span class="ri">{icon("doc")}</span>'
                     f'<span class="rb"><span class="rname">{esc(r.get("titulo",""))}</span>'
                     f'<span class="rmeta">{meta}</span></span>'
                     f'<span class="rs">{esc(r.get("status","pronto")).upper()}</span></a>')
        B.append('</div>')
        B.append(f'<p style="color:var(--sub);font-size:13px;margin-top:14px">Os dossiês ficam em '
                 f'<b>Mano Preguica / ROTEIROS - DOSSIÊS</b>. Pra um novo, peça <code>me dá um roteiro</code>.</p>')
    return shell("Roteiros · Canal Agente", "roteiros", "".join(B))


def page_aprendizados(hoje, aprendizados):
    B = [f'<div class="head"><h1>Aprendizados</h1><span class="date">o que o Claude estudou do canal e dos concorrentes</span></div>']
    B.append('<div class="card">')
    for a in aprendizados:
        redes = " · ".join(dict(NETS).get(n, n) for n in a.get("redes", []))
        B.append(f'<div class="learn"><span class="li">{icon("bulb")}</span><div>'
                 f'<div class="lt">{esc(a.get("titulo",""))}</div><div class="lx">{esc(a.get("texto",""))}</div>'
                 f'<div class="lf">{esc(redes)}  ·  fonte: {esc(a.get("fonte",""))}</div></div></div>')
    B.append('</div>')
    B.append(f'<p style="color:var(--sub);font-size:13px;margin-top:14px">Isto cresce conforme eu estudo o que é postado. '
             f'Pra eu revisar e adicionar, peça <code>atualiza os aprendizados</code>.</p>')
    return shell("Aprendizados · Canal Agente", "aprendizados", "".join(B))


def main():
    hoje = datetime.datetime.now(BRT).date()
    led  = load(LEDGER, {"videos": {}})
    oper = load(OPER, {}); prod = load(PROD, {}); met = load(MET, {}); sched = load(SCHED, [])
    analises = load(ANALI, {})
    perf_real = load(PERF, {})
    roteiros = load(ROTE, {}).get("roteiros", [])
    aprend = load(APREN, {}).get("aprendizados", [])
    os.makedirs(OUTDIR, exist_ok=True)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(home(hoje, oper, led, prod, met))
    open(os.path.join(OUTDIR, "roteiros.html"), "w", encoding="utf-8").write(page_roteiros(hoje, roteiros))
    open(os.path.join(OUTDIR, "aprendizados.html"), "w", encoding="utf-8").write(page_aprendizados(hoje, aprend))
    for net, nome in NETS:
        open(os.path.join(OUTDIR, f"{net}.html"), "w", encoding="utf-8").write(
            page_net(hoje, net, nome, oper, led, prod, met, sched, analises, perf_real, aprend))
    print(f"painel gerado: index + roteiros + aprendizados + {len(NETS)} redes")


if __name__ == "__main__":
    main()
