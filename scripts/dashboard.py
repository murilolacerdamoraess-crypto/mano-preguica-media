#!/usr/bin/env python3
"""
PAINEL DO CANAL AGENTE — central de comando visual (o "VidaOS do conteúdo").

Gera um HTML autossuficiente que o Murilo abre TODO DIA:
  1. Operação — o scanner em versão visual: o que está coberto, o que vai secar, próximos posts.
  2. Performance — métricas REAIS do PostProxy por rede (top posts por impressões).
  3. Central de comandos — O QUE pedir pro Claude e QUANDO (o problema "não sei por onde começar").
  4. Roteiros — a biblioteca de dossiês no Drive.

Sem API paga: só lê os dados que a esteira já gera (ledger/metrics/schedule/operacao/producao).
Roda no mesmo cron do crosspost; o Vercel serve o HTML e atualiza sozinho a cada push.
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
OUT   = os.path.join(RAIZ, "dashboard", "index.html")
BRT   = datetime.timezone(datetime.timedelta(hours=-3))


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def esc(s): return html.escape(str(s))


def frentes(hoje, oper, led, prod):
    """Calcula cada frente: (icone, nome, detalhe, dias_ate, cor). Espelha o scanner."""
    out = []
    def status(dias):
        if dias is None: return ("secou", "🔴", "bad")
        if dias >= 7: return (f"{dias}d", "🟢", "ok")
        if dias >= 3: return (f"{dias}d", "🟡", "warn")
        return (f"{dias}d", "🔴", "bad")

    for chave, nome in (("youtube_videos", "YouTube (vídeos)"), ("enquetes", "Enquetes")):
        bl = oper.get(chave, {})
        fut = sorted(d["data"] for d in bl.get("agendados", []) if d["data"] >= str(hoje))
        ate = datetime.date.fromisoformat(fut[-1]) if fut else None
        dias = (ate - hoje).days if ate else None
        txt, ic, cor = status(dias)
        det = f"{len(fut)} agendados" + (f" · até {ate.strftime('%d/%m')}" if ate else " · nada agendado")
        out.append((ic, nome, det, dias, cor))

    tt = len(queue_curada("tiktok", led["videos"]))
    out.append(("🟢" if tt >= 7 else "🟡", "TikTok", f"automático · {tt} no backlog curado", tt, "ok" if tt >= 7 else "warn"))
    ig = len(queue_curada("instagram", led["videos"]))
    out.append(("🟢" if ig >= 7 else "🟡", "Instagram", f"automático · {ig} no backlog", ig, "ok" if ig >= 7 else "warn"))
    out.append(("🐢", "Facebook", "baixa prioridade · 1x/semana (qua)", 99, "muted"))

    for key, nome, cad in (("mp1_shorts", "MP1 Shorts", "3x/semana"), ("mp2", "MP2 (vídeos IA)", "2x/semana")):
        bl = prod.get(key, {})
        ags = sorted(a["data"] for a in bl.get("agendados", []) if a["data"] >= str(hoje))
        ate = datetime.date.fromisoformat(ags[-1]) if ags else None
        dias = (ate - hoje).days if ate else None
        txt, ic, cor = status(dias)
        det = f"{cad} · você produz · " + (f"até {ate.strftime('%d/%m')}" if ate else "nada agendado")
        out.append((ic, nome, det, dias, cor))
    return out


def top_performance(met):
    redes = []
    for net, rot in (("tiktok", "TikTok"), ("instagram", "Instagram"), ("facebook", "Facebook")):
        rank = []
        for r in met.values():
            st = r.get(net)
            if not st: continue
            imp = 0
            for k in ("impressions", "reach", "video_views", "views"):
                if isinstance(st.get(k), (int, float)): imp = int(st[k]); break
            eng = int(st.get("likes", 0)) + int(st.get("comments", 0)) + int(st.get("shares", 0))
            if imp > 0: rank.append((imp, eng, r.get("title", "")))
        rank.sort(reverse=True)
        if rank: redes.append((rot, rank[:5]))
    return redes


# Central de comandos: o que pedir pro Claude e quando (o problema "não sei por onde começar")
COMANDOS = [
    ("🔥", "Radar de hype", "Toda segunda", "roda o radar de hype",
     "Varre Steam/filmes/trends e traz os jogos quentes com janela. Candidato fura a fila."),
    ("🎬", "Gerar roteiro", "Quando quiser um vídeo", "me dá um roteiro (acha o tema você)",
     "A máquina acha o achado na fonte real do jogo e entrega o dossiê pronto pra gravar."),
    ("✂️", "Short do longo", "A cada vídeo longo novo", "faz o short-isca desse longo",
     "Gera o short que puxa view pro longo (cliffhanger + longo anexado)."),
    ("💬", "Responder comentários", "Quando acumular", "gera as respostas dos comentários",
     "Escreve na sua voz; você aprova no Telegram (skill mano-comentarios)."),
    ("📊", "Enquetes", "Quando a fila baixar", "me dá N enquetes",
     "Lote pronto com capas, monta e agenda no Studio."),
    ("🔭", "Re-scan do Studio", "Quando o painel avisar dado velho", "re-scan do Studio",
     "Atualiza vídeos/enquetes agendados (o painel some com o aviso de dado velho)."),
]

RITMO_AUTO = [
    "Crosspost TikTok/IG roda sozinho todo dia (você não pede nada).",
    "Facebook sai 1x/semana na quarta (baixa prioridade).",
    "A sentinela cancela post ruim antes de publicar, sozinha.",
    "As métricas do PostProxy entram sozinhas no painel.",
]


def render(hoje, fr, perf, secar):
    def card_frente(ic, nome, det, cor):
        return f'<div class="fr {cor}"><div class="fr-h">{ic} {esc(nome)}</div><div class="fr-d">{esc(det)}</div></div>'
    frentes_html = "".join(card_frente(ic, n, d, c) for ic, n, d, _, c in fr)

    perf_html = ""
    if perf:
        for rot, rank in perf:
            linhas = "".join(
                f'<tr><td class="imp">{imp:,}</td><td class="eng">{eng}</td><td>{esc(t[:52])}</td></tr>'.replace(",", ".")
                for imp, eng, t in rank)
            perf_html += f'<div class="perf-net"><h3>{rot}</h3><table><tr><th>impr.</th><th>eng.</th><th>post</th></tr>{linhas}</table></div>'
    else:
        perf_html = '<p class="muted">Ainda juntando dados do PostProxy (poucos posts desde a migração). Enche em alguns dias.</p>'

    cmd_html = "".join(
        f'<div class="cmd"><div class="cmd-t">{ic} <b>{esc(t)}</b><span class="when">{esc(w)}</span></div>'
        f'<div class="cmd-say">Peça ao Claude: <code>{esc(say)}</code></div>'
        f'<div class="cmd-d">{esc(d)}</div></div>'
        for ic, t, w, say, d in COMANDOS)
    auto_html = "".join(f"<li>{esc(x)}</li>" for x in RITMO_AUTO)

    secar_txt = ("Tudo coberto por uma boa margem." if not secar
                 else f'<b>{esc(secar[1])}</b> seca em {secar[0]}d. ' +
                      ("Tá tranquilo." if secar[0] >= 7 else "Bora reabastecer."))

    dossies = ("Meu Drive → Mano Preguica → ROTEIROS - DOSSIÊS "
               "(cada vídeo vira um dossiê HTML com roteiro + fonte + prova anti-alucinação).")

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canal Agente · Central</title>
<style>
:root{{--bg:#faf9f7;--card:#fff;--ink:#1a1a1a;--muted:#6b6b6b;--line:#e6e3de;--accent:#0f6e5a;
--ok:#0f6e5a;--warn:#b26b00;--bad:#b3261e;--shadow:0 1px 2px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.05)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#131313;--card:#1c1c1c;--ink:#ececec;--muted:#9a9a9a;
--line:#2b2b2b;--accent:#3fbfa3;--ok:#3fbfa3;--warn:#e0a24a;--bad:#f0806f;--shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.3)}}}}
*{{box-sizing:border-box}}body{{background:var(--bg);color:var(--ink);margin:0;padding:28px 16px 80px;
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:980px;margin:0 auto}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:6px}}
h1{{font-size:22px;margin:0}}.date{{color:var(--muted);font-size:13px}}
.secar{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:14px 0 22px;box-shadow:var(--shadow)}}
h2{{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:26px 0 12px;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}
.fr{{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--muted);border-radius:10px;padding:12px 14px;box-shadow:var(--shadow)}}
.fr.ok{{border-left-color:var(--ok)}}.fr.warn{{border-left-color:var(--warn)}}.fr.bad{{border-left-color:var(--bad)}}.fr.muted{{border-left-color:var(--line)}}
.fr-h{{font-weight:600;margin-bottom:3px}}.fr-d{{font-size:13px;color:var(--muted)}}
.cmds{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.cmd{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}}
.cmd-t{{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}}.cmd-t .when{{margin-left:auto;font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 9px}}
.cmd-say{{font-size:13px;color:var(--muted);margin:8px 0 6px}}
.cmd-say code{{color:var(--accent);font:13px ui-monospace,Menlo,monospace;background:transparent}}
.cmd-d{{font-size:13px;color:var(--muted)}}
.perf{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}}
.perf-net{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;box-shadow:var(--shadow)}}
.perf-net h3{{font-size:14px;margin:0 0 8px}}table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)}}th{{font-size:10px;text-transform:uppercase;color:var(--muted)}}
.imp{{font-weight:700;white-space:nowrap}}.eng{{color:var(--muted);white-space:nowrap}}
.auto{{font-size:13px;color:var(--muted);padding-left:18px;margin:6px 0}}.muted{{color:var(--muted)}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);font-size:14px}}
footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:30px}}a{{color:var(--accent)}}
</style></head><body><div class="wrap">
<header><h1>🎬 Canal Agente</h1><div class="date">Atualizado {hoje.strftime('%d/%m/%Y')} · Mano Preguiça</div></header>
<div class="secar">🎯 {secar_txt}</div>

<h2>Operação: o que está coberto</h2>
<div class="grid">{frentes_html}</div>

<h2>Central de comandos: o que pedir pro Claude</h2>
<div class="cmds">{cmd_html}</div>
<h2>No automático (você não pede nada)</h2>
<ul class="auto">{auto_html}</ul>

<h2>Performance real (PostProxy)</h2>
<div class="perf">{perf_html}</div>

<h2>Roteiros</h2>
<div class="box">{esc(dossies)}</div>

<footer>Painel do Canal Agente · lê os dados vivos da esteira · sem API paga · a execução é com o Claude</footer>
</div></body></html>"""


def main():
    hoje = datetime.datetime.now(BRT).date()
    led  = load(LEDGER, {"videos": {}})
    oper = load(OPER, {})
    prod = load(PROD, {})
    met  = load(MET, {})

    fr = frentes(hoje, oper, led, prod)
    # próximo a secar (ignora Facebook/muted e o que já secou)
    riscos = sorted((dias, nome) for ic, nome, det, dias, cor in fr if dias is not None and cor != "muted")
    secar = None
    if riscos:
        d1, n1 = riscos[0]; secar = (d1, n1)

    perf = top_performance(met)
    out_html = render(hoje, fr, perf, secar)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(out_html)
    print(f"dashboard gerado: {OUT} ({len(out_html)} bytes)")


if __name__ == "__main__":
    main()
