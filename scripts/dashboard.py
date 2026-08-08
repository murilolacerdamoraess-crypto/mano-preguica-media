#!/usr/bin/env python3
"""
PAINEL DO CANAL AGENTE — central de comando visual (o "VidaOS do conteúdo").

Gera um HTML autossuficiente (ícones SVG + gráficos, zero dependência externa) que o Murilo
abre TODO DIA. Sem API paga: só lê os dados que a esteira já gera.
  1. Alerta do dia + Operação (o que cobre / o que seca) com ícones de status.
  2. Próximos posts (o que está agendado, em ordem).
  3. Performance por rede (gráfico de barras: TikTok / Instagram / Facebook).
  4. Precisa de você (INTELIGÊNCIA): quais longos pedem short, buracos de produção.
  5. Central de comandos: o que pedir pro Claude e quando.
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
SHORTS= os.path.join(RAIZ, "shorts_feitos.json")   # vids de longo que já viraram short (marca manual/futura)
OUT   = os.path.join(RAIZ, "dashboard", "index.html")
BRT   = datetime.timezone(datetime.timedelta(hours=-3))


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def esc(s): return html.escape(str(s))

# --- ícones lucide (stroke currentColor), inline pra ficar self-contained ---
_I = {
 "target":'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
 "check":'<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>',
 "alert":'<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
 "x":'<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
 "pause":'<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
 "calendar":'<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>',
 "film":'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
 "poll":'<path d="M3 3v18h18"/><rect x="7" y="10" width="3" height="7"/><rect x="12" y="6" width="3" height="11"/><rect x="17" y="13" width="3" height="4"/>',
 "scissors":'<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 12.5 20 20M8.1 8.1 12 12"/>',
 "chat":'<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-4-.9L3 21l1.9-4.5A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z"/>',
 "radar":'<path d="M19.07 4.93A10 10 0 1 0 21 12"/><path d="M12 12 8 8M12 2v4M12 12l6-3"/>',
 "search":'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
 "bolt":'<path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z"/>',
 "clock":'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "spark":'<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
 "youtube":'<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3Z"/>',
 "tiktok":'<path d="M9 5v9a3 3 0 1 1-3-3"/><path d="M14 5a5 5 0 0 0 5 5V7a3 3 0 0 1-2-3Z"/>',
 "instagram":'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17" cy="7" r="1"/>',
 "facebook":'<path d="M15 3h-2a4 4 0 0 0-4 4v3H7v4h2v7h4v-7h3l1-4h-4V7a1 1 0 0 1 1-1h2Z"/>',
}
def icon(n, cls="ic"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_I.get(n,"")}</svg>'

NET_ICON = {"tiktok": "tiktok", "instagram": "instagram", "facebook": "facebook",
            "youtube": "youtube", "enquete": "poll"}
STATUS_ICON = {"ok": "check", "warn": "alert", "bad": "x", "muted": "pause"}


def frentes(hoje, oper, led, prod):
    out = []
    def st(dias):
        if dias is None: return ("bad",)
        if dias >= 7: return ("ok",)
        if dias >= 3: return ("warn",)
        return ("bad",)
    for chave, nome, ic in (("youtube_videos", "YouTube", "youtube"), ("enquetes", "Enquetes", "poll")):
        bl = oper.get(chave, {})
        fut = sorted(d["data"] for d in bl.get("agendados", []) if d["data"] >= str(hoje))
        ate = datetime.date.fromisoformat(fut[-1]) if fut else None
        dias = (ate - hoje).days if ate else None
        det = (f"{len(fut)} agendados · cobre até {ate.strftime('%d/%m')}" if ate else "nada agendado")
        out.append((st(dias)[0], ic, nome, det, dias))
    tt = len(queue_curada("tiktok", led["videos"]))
    out.append(("ok" if tt >= 7 else "warn", "tiktok", "TikTok", f"automático · {tt} no backlog", tt))
    ig = len(queue_curada("instagram", led["videos"]))
    out.append(("ok" if ig >= 7 else "warn", "instagram", "Instagram", f"automático · {ig} no backlog", ig))
    out.append(("muted", "facebook", "Facebook", "baixa prioridade · 1x/semana", 99))
    for key, nome, cad in (("mp1_shorts", "MP1 Shorts", "3x/sem"), ("mp2", "MP2 (IA)", "2x/sem")):
        bl = prod.get(key, {})
        ags = sorted(a["data"] for a in bl.get("agendados", []) if a["data"] >= str(hoje))
        ate = datetime.date.fromisoformat(ags[-1]) if ags else None
        dias = (ate - hoje).days if ate else None
        det = (f"{cad} · cobre até {ate.strftime('%d/%m')}" if ate else f"{cad} · nada agendado · você produz")
        out.append((st(dias)[0], "film", nome, det, dias))
    return out


def proximos(hoje, oper, sched):
    itens = []
    for chave, tag in (("youtube_videos", "youtube"), ("enquetes", "enquete")):
        for it in oper.get(chave, {}).get("agendados", []):
            if it["data"] >= str(hoje):
                itens.append((it["data"], tag, it["titulo"]))
    agora = datetime.datetime.now(BRT)
    for s in sched:
        try:
            dt = datetime.datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00")).astimezone(BRT)
        except Exception:
            continue
        if dt > agora:
            itens.append((dt.date().isoformat(), s.get("net", "?"), s.get("title", "")))
    itens.sort()
    return itens[:9]


def perf_por_rede(met):
    saida = []
    for net in ("tiktok", "instagram", "facebook"):
        rank = []
        for r in met.values():
            stt = r.get(net)
            if not stt: continue
            imp = 0
            for k in ("impressions", "reach", "video_views", "views"):
                if isinstance(stt.get(k), (int, float)): imp = int(stt[k]); break
            if imp > 0: rank.append((imp, r.get("title", "")))
        rank.sort(reverse=True)
        if rank: saida.append((net, rank[:5]))
    return saida


def shorts_pendentes(hoje, led):
    """INTELIGÊNCIA: longos recentes que ainda pedem um short (o Murilo não precisa lembrar)."""
    feitos = set(load(SHORTS, []))
    cand = []
    for vid, v in led["videos"].items():
        if v.get("type") != "long": continue
        if vid in feitos: continue
        try:
            idade = (hoje - datetime.date.fromisoformat(v["published"][:10])).days
        except Exception:
            continue
        if 0 <= idade <= 60 and v.get("views", 0) >= 5000:   # longo recente e que rendeu
            cand.append((idade, v.get("views", 0), v.get("title", ""), vid))
    cand.sort()   # mais recente primeiro
    return cand[:4]


CSS = """
:root{--bg:#f6f6f4;--card:#fff;--ink:#161616;--sub:#6b6b6b;--line:#e7e4df;--accent:#0f6e5a;
--ok:#1a8f6b;--warn:#c07d17;--bad:#c0392b;--tt:#111;--ig:#c8398f;--fb:#2a6fd6;
--shadow:0 1px 2px rgba(0,0,0,.04),0 6px 20px rgba(0,0,0,.05)}
@media(prefers-color-scheme:dark){:root{--bg:#111;--card:#1a1a1a;--ink:#eee;--sub:#9a9a9a;--line:#2a2a2a;
--accent:#3fbfa3;--ok:#43c99a;--warn:#e0a24a;--bad:#ef7361;--tt:#e6e6e6;--ig:#e968b0;--fb:#5b93ea;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35)}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;padding:26px 16px 80px;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif}
.wrap{max-width:1040px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.brand{display:flex;align-items:center;gap:10px;font-size:20px;font-weight:700}
.brand .logo{width:34px;height:34px;border-radius:9px;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center}
.brand .logo svg{width:20px;height:20px}
.date{color:var(--sub);font-size:13px}
.ic{width:18px;height:18px;flex:none}
.alert{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:12px;padding:13px 16px;margin-bottom:22px;box-shadow:var(--shadow)}
.alert.warn{border-left-color:var(--warn)} .alert.bad{border-left-color:var(--bad)}
.alert .ic{color:var(--accent)} .alert.warn .ic{color:var(--warn)} .alert.bad .ic{color:var(--bad)}
h2{display:flex;align-items:center;gap:8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
color:var(--sub);font-weight:700;margin:28px 0 12px}
h2 .ic{width:15px;height:15px}
.cols{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 4px;box-shadow:var(--shadow)}
.row{display:flex;align-items:center;gap:11px;padding:11px 14px;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:none}
.row .st{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex:none}
.row .st .ic{width:17px;height:17px}
.st.ok{background:rgba(26,143,107,.12);color:var(--ok)} .st.warn{background:rgba(192,125,23,.14);color:var(--warn)}
.st.bad{background:rgba(192,57,43,.13);color:var(--bad)} .st.muted{background:var(--line);color:var(--sub)}
.row .tx{flex:1;min-width:0}
.row .tt{font-weight:600;font-size:14px}
.row .ds{font-size:12.5px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .badge{font-size:11px;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:2px 9px;flex:none}
.px{display:flex;align-items:center;gap:11px;padding:10px 14px;border-bottom:1px solid var(--line)}
.px:last-child{border-bottom:none}
.px .d{font-size:12px;font-weight:700;color:var(--ink);width:52px;flex:none;text-align:center;
background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:5px 0;line-height:1.15}
.px .d small{display:block;font-size:9px;color:var(--sub);font-weight:600;text-transform:uppercase}
.px .netic{width:26px;height:26px;color:var(--sub);display:flex;align-items:center;justify-content:center;flex:none}
.px .netic .ic{width:17px;height:17px}
.px .t{font-size:13.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.perf{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.pcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:var(--shadow)}
.phead{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;margin-bottom:12px}
.phead .netic{width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;color:#fff}
.phead .netic .ic{width:16px;height:16px}
.tt-bg{background:var(--tt)} .ig-bg{background:var(--ig)} .fb-bg{background:var(--fb)}
.bar{margin:9px 0}
.bar .lbl{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;gap:8px}
.bar .lbl .n{color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .lbl .v{font-weight:700;flex:none}
.bar .track{height:7px;background:var(--line);border-radius:99px;overflow:hidden}
.bar .fill{height:100%;border-radius:99px}
.tt-f{background:var(--tt)} .ig-f{background:var(--ig)} .fb-f{background:var(--fb)}
.todo .row .st{background:rgba(15,110,90,.12);color:var(--accent)}
.todo .row .ds{white-space:normal}
.cmds{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.cmd{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px 16px;box-shadow:var(--shadow)}
.cmd .h{display:flex;align-items:center;gap:9px;margin-bottom:8px}
.cmd .h .ci{width:30px;height:30px;border-radius:8px;background:rgba(15,110,90,.1);color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}
.cmd .h b{font-size:14px} .cmd .h .when{margin-left:auto;font-size:10.5px;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:2px 8px}
.cmd code{display:inline-block;color:var(--accent);font:12.5px ui-monospace,Menlo,monospace;background:rgba(15,110,90,.08);border-radius:6px;padding:3px 8px;margin-bottom:6px}
.cmd .ds{font-size:12.5px;color:var(--sub)}
.empty{padding:16px;color:var(--sub);font-size:13px}
footer{text-align:center;color:var(--sub);font-size:12px;margin-top:34px}
"""


def render(hoje, fr, prox, perf, todos, secar):
    P = []
    P.append('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">')
    P.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    P.append('<title>Canal Agente</title><style>' + CSS + '</style></head><body><div class="wrap">')
    P.append(f'<div class="top"><div class="brand"><span class="logo">{icon("film")}</span>Canal Agente</div>'
             f'<div class="date">{hoje.strftime("%d/%m/%Y")} · Mano Preguiça</div></div>')

    # alerta
    if not secar:
        P.append(f'<div class="alert">{icon("target")}<div>Tudo coberto por uma boa margem.</div></div>')
    else:
        d1, n1 = secar
        cls = "" if d1 >= 7 else ("warn" if d1 >= 3 else "bad")
        msg = "está tranquilo" if d1 >= 7 else "bora reabastecer"
        P.append(f'<div class="alert {cls}">{icon("target")}<div><b>{esc(n1)}</b> é o próximo a secar, '
                 f'em {d1} dia(s). {msg}.</div></div>')

    P.append('<div class="cols"><div>')
    # operação
    P.append(f'<h2>{icon("bolt")} Operação</h2><div class="card">')
    for cor, ic, nome, det, dias in fr:
        P.append(f'<div class="row"><div class="st {cor}">{icon(STATUS_ICON[cor])}</div>'
                 f'<div class="tx"><div class="tt">{esc(nome)}</div><div class="ds">{esc(det)}</div></div>'
                 f'<span class="badge">{icon(ic)}</span></div>')
    P.append('</div>')
    # precisa de você
    P.append(f'<h2>{icon("spark")} Precisa de você</h2><div class="card todo">')
    if not todos:
        P.append('<div class="empty">Nada pendente. Bom trabalho.</div>')
    for tt, ds in todos:
        P.append(f'<div class="row"><div class="st">{icon("scissors")}</div>'
                 f'<div class="tx"><div class="tt">{esc(tt)}</div><div class="ds">{esc(ds)}</div></div></div>')
    P.append('</div></div><div>')
    # próximos
    P.append(f'<h2>{icon("calendar")} Próximos posts</h2><div class="card">')
    if not prox:
        P.append('<div class="empty">Nada agendado à frente.</div>')
    for data, tag, titulo in prox:
        dt = datetime.date.fromisoformat(data)
        dia = "hoje" if dt == hoje else ("amanhã" if (dt - hoje).days == 1 else dt.strftime("%d/%m"))
        mes = dt.strftime("%b").lower()
        di = NET_ICON.get(tag, "film")
        P.append(f'<div class="px"><div class="d">{dt.strftime("%d")}<small>{mes}</small></div>'
                 f'<div class="netic">{icon(di)}</div><div class="t">{esc(titulo)}</div></div>')
    P.append('</div></div></div>')

    # performance
    P.append(f'<h2>{icon("poll")} Performance real (PostProxy)</h2>')
    if not perf:
        P.append('<div class="card"><div class="empty">Ainda juntando dados do PostProxy. Enche em alguns dias.</div></div>')
    else:
        P.append('<div class="perf">')
        for net, rank in perf:
            mx = max(v for v, _ in rank) or 1
            P.append(f'<div class="pcard"><div class="phead"><span class="netic {net[:2]}-bg">{icon(NET_ICON[net])}</span>{net.title()}</div>')
            for v, t in rank:
                pct = max(4, round(v / mx * 100))
                P.append(f'<div class="bar"><div class="lbl"><span class="n">{esc(t[:46])}</span>'
                         f'<span class="v">{v:,}</span></div>'.replace(",", ".")
                         + f'<div class="track"><div class="fill {net[:2]}-f" style="width:{pct}%"></div></div></div>')
            P.append('</div>')
        P.append('</div>')

    # comandos
    P.append(f'<h2>{icon("chat")} O que pedir pro Claude</h2><div class="cmds">')
    for ic, t, w, say, d in COMANDOS:
        P.append(f'<div class="cmd"><div class="h"><span class="ci">{icon(ic)}</span><b>{esc(t)}</b>'
                 f'<span class="when">{esc(w)}</span></div><code>{esc(say)}</code><div class="ds">{esc(d)}</div></div>')
    P.append('</div>')

    P.append('<footer>Painel do Canal Agente · lê os dados vivos da esteira · sem API paga</footer>')
    P.append('</div></body></html>')
    return "".join(P)


COMANDOS = [
    ("radar", "Radar de hype", "Toda segunda", "roda o radar de hype",
     "Varre Steam, filmes e trends e traz os jogos quentes com a janela de cada um."),
    ("film", "Gerar roteiro", "Quando quiser", "me dá um roteiro (acha o tema você)",
     "A máquina acha o achado na fonte real do jogo e entrega o dossiê pronto pra gravar."),
    ("scissors", "Short do longo", "Ver 'precisa de você'", "faz o short desse longo",
     "O painel já te diz qual longo está pedindo short. É só apontar."),
    ("chat", "Responder comentários", "Quando acumular", "gera as respostas dos comentários",
     "Escreve na sua voz; você aprova no Telegram."),
    ("poll", "Enquetes", "Quando a fila baixar", "me dá N enquetes",
     "Lote pronto com capas, monta e agenda no Studio."),
    ("search", "Re-scan do Studio", "Se o painel avisar", "re-scan do Studio",
     "Atualiza os vídeos e enquetes agendados."),
]


def main():
    hoje = datetime.datetime.now(BRT).date()
    led  = load(LEDGER, {"videos": {}})
    oper = load(OPER, {}); prod = load(PROD, {}); met = load(MET, {}); sched = load(SCHED, [])

    fr = frentes(hoje, oper, led, prod)
    riscos = sorted((dias, nome) for cor, ic, nome, det, dias in fr if dias is not None and cor != "muted")
    secar = (riscos[0][0], riscos[0][1]) if riscos else None

    prox = proximos(hoje, oper, sched)
    perf = perf_por_rede(met)

    todos = []
    for idade, views, titulo, vid in shorts_pendentes(hoje, led):
        quando = "postado hoje" if idade == 0 else f"há {idade} dias"
        todos.append((f"Fazer short: {titulo[:50]}", f"Longo {quando} · {views:,} views. Peça: 'faz o short desse longo'".replace(",", ".")))
    for cor, ic, nome, det, dias in fr:
        if ic == "film" and dias is None:   # produção seca (MP1/MP2)
            todos.append((f"Produzir {nome}", det))

    out_html = render(hoje, fr, prox, perf, todos, secar)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(out_html)
    print(f"dashboard gerado: {OUT} ({len(out_html)} bytes)")


if __name__ == "__main__":
    main()
