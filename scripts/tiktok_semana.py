#!/usr/bin/env python3
"""
TikTok da semana (05/10/2026). O Murilo: "garantir que esses vídeos do YouTube que estão sendo
publicados vão pro TikTok, sempre respeitando as regras... o TikTok vai se tornar uma grande fonte
de renda". Decisões dele: piso de 10 mil views no YouTube e Metricool grátis (20 posts/mês; o IG e
o FB saíram do Metricool em 04/10, então os 20 são do TikTok).

Regras (do cérebro: crosspost-pipeline, padrao-desempenho-yt-tiktok, tiktok_plan):
  1. vertical de 61 s a 600 s (TikTok só paga 1 min+; o Metricool trava acima de 10 min)
  2. 2 mil views ou mais no YouTube (piso baixado de 10 mil em 05/10: corta só o fracasso ridículo; sobe quando o Sextante mostrar que dá)
  3. maturado: 7+ dias no ar (o número do YouTube já diz alguma coisa)
  4. conteúdo novo (>= START_DATE; decisão de 24/08: sem ressuscitar backlog antigo)
  5. dentro do nicho (off_nicho) e sem notícia velha (moldura de "novo" em vídeo envelhecido)
  6. canal principal; do MP2 só o que está na allowlist de faceless de IA (postable)
  7. nunca postado nem agendado no TikTok (ledger + tiktok_agenda.json)
  8. ordem: views no YouTube (escala log) + bônus de tema (criatura/medo/escala sobem, construção/veículo descem)
  9. sempre PUBLIC_TO_EVERYONE (o não público perde a monetização)

Saída: tiktok_semana.json com os escolhidos, horário (Ter/Qui/Sáb/Dom 18h BRT, até 4 por semana e
sem passar de 20 no mês), legenda e URL pública do vídeo (hospedado no release do GitHub pelo Mac,
igual ao crosspost). Quem agenda no Metricool é o Leme (MCP do Metricool), na rotina de segunda.

Uso (no Mac):
  python3 scripts/tiktok_semana.py          -> planeja e mostra (não hospeda)
  python3 scripts/tiktok_semana.py hospedar -> planeja, hospeda os escolhidos e grava o json
"""
import os, sys, json, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("DRY_RUN", "1")
import crosspost as cp  # noqa: E402

BRT = dt.timezone(dt.timedelta(hours=-3))
RAIZ = os.path.dirname(cp.LEDGER)
AGENDA = os.path.join(RAIZ, "tiktok_agenda.json")
SAIDA = os.path.join(RAIZ, "tiktok_semana.json")
PISO = int(os.environ.get("TT_PISO", "2000"))   # 05/10: 10 mil travava a fila; o Murilo pediu cortar só os fracassos ridículos
MATURA = int(os.environ.get("TT_MATURA", "7"))
POR_SEMANA = int(os.environ.get("TT_POR_SEMANA", "4"))
TETO_MES = int(os.environ.get("TT_TETO_MES", "20"))
DIAS = [1, 3, 5, 6]          # ter, qui, sáb, dom
HORA = 18


def agenda():
    try:
        return json.load(open(AGENDA, encoding="utf-8"))
    except OSError:
        return {"posts": []}


def candidatos(led, ja):
    hoje = dt.date.today()
    out, fora = [], []
    for vid, v in led["videos"].items():
        if v.get("type") != "vertical" or not (61 <= v.get("seconds", 0) <= 600):
            continue
        if v.get("published", "") < cp.START_DATE:
            continue
        motivo = None
        idade = (hoje - dt.date.fromisoformat(v["published"][:10])).days
        if not v.get("postable"):
            motivo = "fora da allowlist (MP2/IA)"
        elif v["posted"]["tiktok"]["done"] or vid in ja:
            continue
        elif v.get("views", 0) < PISO:
            motivo = f"abaixo do piso ({v.get('views', 0):,} views)".replace(",", ".")
        elif idade < MATURA:
            motivo = f"ainda maturando ({idade} dias no ar)"
        elif cp.off_nicho(v["title"]):
            motivo = "fora do nicho"
        elif cp.noticia_velha(v):
            motivo = "notícia velha"
        if motivo:
            fora.append((vid, v["title"], motivo))
        else:
            out.append((cp.tema_score(v["title"]), v.get("views", 0), vid, v))
    # Views mandam (escala log: 10x mais views = +1 ponto) e o tema dá bônus de 0,25 por gatilho.
    # Antes era tema primeiro e um Short de 4,5 mil passava na frente de um de 542 mil (05/10).
    import math
    out.sort(key=lambda x: math.log10(max(x[1], 1)) + 0.25 * x[0], reverse=True)
    return out, fora


def horarios(ag, n):
    """Próximos slots livres (ter/qui/sáb/dom 18h) dos 7 dias a partir de amanhã, sem passar do teto do mês."""
    ocupados = {p["quando"][:16] for p in ag["posts"] if p.get("status") != "cancelado"}
    hoje = dt.datetime.now(BRT).date()
    slots = []
    for d in range(1, 8):
        dia = hoje + dt.timedelta(days=d)
        if dia.weekday() not in DIAS:
            continue
        no_mes = sum(1 for p in ag["posts"] if p["quando"][:7] == dia.strftime("%Y-%m") and p.get("status") != "cancelado")
        no_mes += sum(1 for s in slots if s[:7] == dia.strftime("%Y-%m"))
        if no_mes >= TETO_MES:
            continue
        q = dt.datetime(dia.year, dia.month, dia.day, HORA, 0, tzinfo=BRT).isoformat()
        if q[:16] not in ocupados:
            slots.append(q)
    return slots[:min(n, POR_SEMANA)]


def legenda(v):
    t = v["title"].replace("#shorts", "").replace("#Shorts", "").strip()
    return f"{t}\n\n#subnautica #games #jogos #curiosidades" if "subnautica" in t.lower() else f"{t}\n\n#games #jogos #curiosidades"


def main(hospedar):
    led = json.load(open(cp.LEDGER, encoding="utf-8"))
    ag = agenda()
    ja = {p.get("video_id") for p in ag["posts"]}
    cand, fora = candidatos(led, ja)
    slots = horarios(ag, len(cand))
    plano = []
    for (score, views, vid, v), quando in zip(cand, slots):
        url = cp.hosted_url(vid)
        if not url and hospedar:
            try:
                url = cp.host(vid, v["title"])
            except Exception as e:
                print(f"  ✗ não hospedou {vid}: {e}")
                continue
        plano.append({"video_id": vid, "titulo": v["title"], "views_youtube": views, "tema_score": score,
                      "quando": quando, "legenda": legenda(v), "video_url": url,
                      "privacidade": "PUBLIC_TO_EVERYONE"})
    sobra = cand[len(plano):]
    print(f"TikTok da semana · piso {PISO:,} views".replace(",", ".") + f" · {len(cand)} aptos · {len(plano)} no plano")
    for p in plano:
        print(f"  ✔ {p['quando'][:16]} · {p['views_youtube']:>7,} · {p['titulo'][:60]} {'' if p['video_url'] else '(SEM HOSPEDAGEM)'}".replace(",", "."))
    for s in sobra:
        print(f"  … fica pra próxima: {s[3]['title'][:60]}")
    print(f"Fora ({len(fora)}):")
    for vid, t, m in fora[:15]:
        print(f"  ✗ {t[:55]} · {m}")
    if hospedar:
        json.dump({"_leia": "Gerado por tiktok_semana.py. O Leme agenda estes no Metricool (MCP), sempre PUBLIC_TO_EVERYONE, "
                            "e grava cada um em tiktok_agenda.json com o metricool_id.",
                   "gerado_em": dt.datetime.now(BRT).isoformat(), "plano": plano},
                  open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"-> {SAIDA}")


if __name__ == "__main__":
    main("hospedar" in sys.argv)
