#!/usr/bin/env python3
"""
TikTok da semana (05/10/2026). O Murilo: "garantir que esses vídeos do YouTube que estão sendo
publicados vão pro TikTok, sempre respeitando as regras... o TikTok vai se tornar uma grande fonte
de renda". Decisões dele: piso de 10 mil views no YouTube e Metricool grátis (20 posts/mês; o IG e
o FB saíram do Metricool em 04/10, então os 20 são do TikTok).

Regras (do cérebro: crosspost-pipeline, padrao-desempenho-yt-tiktok, tiktok_plan):
  1. vertical de 61 s a 600 s (TikTok só paga 1 min+; o Metricool trava acima de 10 min)
  2. 2 mil views no YouTube é PRIORIDADE, não corte (05/11/2026, Murilo: o TikTok ficou parado de 30/10 a 05/11). Primeiro
     os de 2 mil ou mais; quando acabarem, os de baixo do piso, na ordem do tema que funciona no TikTok (tema_score:
     criatura e medo primeiro, Reaper e Gargantuan na frente, regra de 04/10), não pelas views do YouTube
  3. maturado: 7+ dias no ar (o número do YouTube já diz alguma coisa)
  4. conteúdo novo (>= START_DATE; decisão de 24/08: sem ressuscitar backlog antigo)
  5. dentro do nicho (off_nicho) e sem notícia velha (moldura de "novo" em vídeo envelhecido)
  6. canal principal e canal 2 (MP2, só os verticais; desde 04/11/2026, Murilo: "os videos do canal secundario vão
     pro tiktok tmb"; antes era só a allowlist de faceless de IA). Narrado com voz clonada sai com o selo de IA
     (isAigc) no Metricool: o plano marca "conferir_voz" nos do MP2 e o Leme confere quem narra antes de agendar
  7. nunca postado nem agendado no TikTok (lê o perfil público com yt-dlp a cada rodada + ledger + tiktok_agenda.json)
  8. ordem: acerto cedo; depois os de 2 mil+ por views no YouTube (escala log) + bônus de tema; depois os de baixo do
     piso por tema e só então views
  9. sempre PUBLIC_TO_EVERYONE (o não público perde a monetização)
 10. nunca Ranking da Steam nem outro vídeo do formato bar race (corrida de dados) e nada abaixo de 1x a régua do canal
     de origem (06/11/2026, Murilo vendo o painel: "tem um vídeo de números no tiktok, não vamos postar isso né? foi um
     fracasso"; os rankings fecharam 0,58x e no máximo 0,5x a régua no YouTube). Régua: a da ficha do vídeo (Sextante,
     mesma idade) quando tem; senão as views contra a mediana dos 10 verticais anteriores do mesmo canal

Saída: tiktok_semana.json com os escolhidos, horário (desde 05/11/2026 TODO DIA às 18h BRT, os 7 dias a partir de
amanhã, sem buraco; antes era ter/qui/sáb/dom e até 4 por semana), legenda e URL pública do vídeo (hospedado no release do GitHub pelo Mac,
igual ao crosspost). Quem agenda no Metricool é o Leme (MCP do Metricool), na rotina de segunda.

Acerto cedo (Murilo, 23/10/2026: "podemos adotar essa parada de passar a regua"): Short que passou de 2x a régua
com 24 h ou 3 dias (campo acerto_cedo da ficha do vídeo, que o ficha_video.py grava no cérebro) não espera os 7 dias
e vai na frente da fila. As outras regras continuam (o piso virou prioridade em 05/11). Com "acertos", o script planeja só esses, e o horário
das 18h do próprio dia também conta se ainda for antes das 16h (rotina diária "TikTok: acerto cedo" do Leme).

Uso (no Mac):
  python3 scripts/tiktok_semana.py          -> planeja e mostra (não hospeda)
  python3 scripts/tiktok_semana.py hospedar -> planeja, hospeda os escolhidos e grava o json
  python3 scripts/tiktok_semana.py hospedar acertos -> só os acertos cedo, no próximo horário livre
"""
import os, re, sys, json, statistics, datetime as dt

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
POR_SEMANA = int(os.environ.get("TT_POR_SEMANA", "7"))
TETO_MES = int(os.environ.get("TT_TETO_MES", "31"))   # 05/11: 1 por dia; o teto de 20 do Metricool grátis deixou de valer aqui
# 05/11 (Maestro): o Metricool grátis aceita 20 posts por mês. Com METRICOOL_LIMITE no mês, os próximos daquele mês vão pelo
# agendamento do próprio TikTok na web (Periscópio, navegador) e entram no tiktok_agenda.json com agendado_por "tiktok-web".
METRICOOL_TETO = 20
METRICOOL_LIMITE = int(os.environ.get("TT_METRICOOL_LIMITE", "18"))   # 2 de folga
DIAS = [0, 1, 2, 3, 4, 5, 6]   # 05/11/2026 (Murilo): 1 TikTok por dia, todo dia, 18h
HORA = 18
FICHAS = os.path.expanduser("~/claude-projects/cerebro/projetos/canal-agente/producao/fichas-video")


def acerto_cedo(vid):
    """A marca do ficha_video.py: passou de 2x a régua com 24 h ou 3 dias (None se não passou ou não tem ficha)."""
    try:
        return json.load(open(os.path.join(FICHAS, f"{vid}.json"), encoding="utf-8")).get("acerto_cedo")
    except (OSError, ValueError):
        return None


# 06/11/2026: os 13 Rankings da Steam (bar race) que saíram no canal 2 casam todos com isto, e nenhum outro vertical casa
BAR_RACE = re.compile(r"mais jogad[oa]s? d[ae] steam|ranking d[oa]s?|mais vendid[oa]s? d[ae] hist|você acha que (é|vale|vendeu)|"
                      r"mais valios[oa]s? d[oa]", re.I)
# status que não ocupa horário nem aparece como agendado (06/11: o Maestro passou os 3 rankings pra rascunho no Metricool)
FORA_DA_AGENDA = ("cancelado", "rascunho")


def vezes_regua(vid, led):
    """Quantas vezes a régua do canal de origem o vídeo fez (06/11). A ficha do Sextante compara na mesma idade; sem
    ficha, views de agora contra a mediana dos 10 verticais anteriores do mesmo canal. None se não dá pra medir."""
    try:
        x = json.load(open(os.path.join(FICHAS, f"{vid}.json"), encoding="utf-8")).get("porque", {}).get("vezes")
        if x is not None:
            return x
    except (OSError, ValueError):
        pass
    v = led["videos"][vid]
    ant = sorted(((w.get("published", ""), w.get("views", 0)) for k, w in led["videos"].items()
                  if k != vid and w.get("type") == "vertical" and w.get("source") == v.get("source")
                  and w.get("published", "") < v.get("published", "")), reverse=True)[:10]
    r = statistics.median([b for _, b in ant]) if ant else 0
    return v.get("views", 0) / r if r else None


def agenda():
    try:
        return json.load(open(AGENDA, encoding="utf-8"))
    except OSError:
        return {"posts": []}


def _norm(t):
    import re, unicodedata
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"#\w+", " ", t)
    genericas = {"subnautica", "games", "game", "jogos", "jogo", "gameplay", "curiosidades", "curiosidade", "shorts",
                 "short", "sobre", "esse", "essa", "isso", "voce", "para", "mais", "muito", "quando", "como"}
    return set(w for w in re.sub(r"[^a-z0-9 ]+", " ", t).split() if len(w) >= 4 and w not in genericas)


def sincronizar_perfil(led):
    """Lê o perfil público do TikTok (yt-dlp, sem navegador) e marca no ledger o que JÁ saiu lá.
    05/10: o seletor escolheu 6 vídeos que já tinham sido postados por sessões manuais no Metricool,
    que nunca anotavam no ledger. Casa por título: 3+ palavras de 4+ letras em comum (sem as genéricas) e, além disso, 5+ ou 60% do menor.
    04/11: um post vale pra um vídeo só (o do ledger ou o do agendamento daquele dia no tiktok_agenda.json), e o título
    inteiro também casa."""
    import subprocess
    # 12/10: o yt-dlp passou a dar erro com a URL do @; pelo id do perfil (secUid) funciona. Tenta os dois.
    posts = []
    for url in ("https://www.tiktok.com/@manopreguica",
                "tiktokuser:MS4wLjABAAAALaAIS7xTvWi4UpXfnEMxpaiGNw4gJYI5qK4Hf8KK8a2U5TUInmcUUrh3dz79X22q"):
        r = subprocess.run(["yt-dlp", "--no-update", "--flat-playlist", "--print", "%(id)s|%(timestamp)s|%(view_count)s|%(title)s",
                            url], capture_output=True, text=True, timeout=240)
        posts = [l.split("|", 3) for l in r.stdout.splitlines() if l.count("|") >= 3]
        if posts:
            break
    if not posts:
        print("  ⚠ não consegui ler o perfil do TikTok; sigo só com o ledger e a agenda")
        return 0
    marcados = 0
    # 04/11: o oxigênio (C6wqfeLVQ1s) foi dado como postado com o post da Pokédex do canal 2 (só "cara" e "tentando"
    # em comum, saiu 8 dias depois). Agora um post do TikTok vale pra um vídeo só: o post que já está no ledger, ou
    # que caiu no dia de um agendamento do tiktok_agenda.json, é daquele vídeo e não casa com outro; e o título
    # inteiro (a legenda começa com o título do YouTube) casa antes da regra das palavras.
    dono = {}
    for x, w in led["videos"].items():
        if w["posted"]["tiktok"].get("post_id"):
            dono[w["posted"]["tiktok"]["post_id"]] = x
    por_dia = {}
    for p in agenda().get("posts", []):
        if p.get("video_id") and p.get("quando"):
            por_dia.setdefault(p["quando"][:10], set()).add(p["video_id"])
    for pid, ts, views, titulo in posts:
        try:
            dia = por_dia.get(dt.datetime.fromtimestamp(int(ts), BRT).date().isoformat(), set())
        except Exception:
            dia = set()
        if pid not in dono and len(dia) == 1:
            dono[pid] = next(iter(dia))
    # Cada par (vídeo, post) que casa ganha uma nota; os pares vão do mais certo pro menos certo, e cada post e
    # cada vídeo só entram uma vez (antes um post do Shiver marcava 3 vídeos de uma vez).
    pares = []
    for vid, v in led["videos"].items():
        if v["posted"]["tiktok"]["done"]:
            continue
        inteiro = cp._norm_titulo(v.get("title", ""))
        a = _norm(v.get("title", ""))
        for pid, ts, views, titulo in posts:
            if dono.get(pid, vid) != vid:
                continue
            b = _norm(titulo)
            comum = len(a & b)
            perto, dias = False, 999   # título reescrito pro TikTok: 2 palavras bastam se saiu até 45 dias depois do YouTube
            try:
                d_tt = dt.datetime.fromtimestamp(int(ts), BRT).date()
                dias = (d_tt - dt.date.fromisoformat(v["published"][:10])).days
                perto = -10 <= dias <= 45   # às vezes sai no TikTok antes
            except Exception:
                pass
            if dono.get(pid) == vid or (inteiro and cp._norm_titulo(titulo).startswith(inteiro)):
                nota = 2.0
            elif (comum >= 3 and (comum >= 5 or comum >= 0.6 * min(len(a), len(b)))) or (perto and comum >= 2):
                nota = comum / max(1, min(len(a), len(b)))
            else:
                continue
            pares.append((nota, -abs(dias), vid, pid, ts, views))
    feitos = set()
    for nota, _, vid, pid, ts, views in sorted(pares, reverse=True):
        if vid in feitos or dono.get(pid, vid) != vid:
            continue
        data = dt.datetime.fromtimestamp(int(ts or 0), BRT).date().isoformat() if ts and ts != "NA" else None
        led["videos"][vid]["posted"]["tiktok"] = {"done": True, "date": data, "post_id": pid,
                                                  "link": f"https://www.tiktok.com/@manopreguica/video/{pid}",
                                                  "views_tiktok": int(views) if views and views.isdigit() else None}
        dono[pid] = vid
        feitos.add(vid)
        marcados += 1
    if marcados:
        json.dump(led, open(cp.LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  perfil do TikTok: {len(posts)} posts lidos, {marcados} vídeos marcados como já postados no ledger")
    return marcados


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
        if not v.get("eligible"):
            motivo = "não elegível"
        elif v["posted"]["tiktok"]["done"] or vid in ja:
            continue
        elif idade + 7 < MATURA and not acerto_cedo(vid):   # 12/10: conta até o dia do post (o slot mais longe é daqui a 7 dias), não até hoje
            motivo = f"ainda maturando ({idade} dias no ar, não chega a {MATURA} até o último horário da semana)"
        elif BAR_RACE.search(v["title"]):
            motivo = "Ranking da Steam / bar race (fracasso no YouTube, Murilo 06/11)"
        elif cp.off_nicho(v["title"]):
            motivo = "fora do nicho"
        elif cp.noticia_velha(v):
            motivo = "notícia velha"
        elif not acerto_cedo(vid) and (vezes_regua(vid, led) or 0) < 1:
            motivo = f"abaixo de 1x a régua do canal ({vezes_regua(vid, led) or 0:.2f}x)".replace(".", ",")
        if motivo:
            fora.append((vid, v["title"], motivo))
        else:
            out.append((cp.tema_score(v["title"]), v.get("views", 0), vid, v))   # abaixo do piso entra no fim (05/11)
    # Views mandam (escala log: 10x mais views = +1 ponto) e o tema dá bônus de 0,25 por gatilho.
    # Antes era tema primeiro e um Short de 4,5 mil passava na frente de um de 542 mil (05/10).
    import math
    # 23/10: acerto cedo vai na frente
    # 05/11: o piso virou prioridade; abaixo dele, o tema manda e as views só desempatam
    out.sort(key=lambda x: (bool(acerto_cedo(x[2])), x[1] >= PISO,
                            math.log10(max(x[1], 1)) + 0.25 * x[0] if x[1] >= PISO else (x[0], x[1])), reverse=True)
    return out, fora


def horarios(ag, n, hoje_tambem=False):
    """Próximos slots livres (18h de cada dia em DIAS) dos 7 dias a partir de amanhã, sem passar do teto do mês.
    hoje_tambem: o das 18h de hoje também, se ainda for antes das 16h (acerto cedo)."""
    ocupados = {p["quando"][:16] for p in ag["posts"] if p.get("status") not in FORA_DA_AGENDA}
    agora = dt.datetime.now(BRT)
    hoje = agora.date()
    slots = []
    for d in range(0 if hoje_tambem and agora.hour < 16 else 1, 8):
        dia = hoje + dt.timedelta(days=d)
        if dia.weekday() not in DIAS:
            continue
        no_mes = sum(1 for p in ag["posts"] if p["quando"][:7] == dia.strftime("%Y-%m") and p.get("status") not in FORA_DA_AGENDA)
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


def main(hospedar, so_acertos=False):
    led = json.load(open(cp.LEDGER, encoding="utf-8"))
    sincronizar_perfil(led)
    ag = agenda()
    ja = {p.get("video_id") for p in ag["posts"]}
    cand, fora = candidatos(led, ja)
    if so_acertos:
        cand = [c for c in cand if acerto_cedo(c[2])]
    slots = horarios(ag, POR_SEMANA, hoje_tambem=so_acertos)   # 19/10: pede todos os horários; com 1 apto ainda maturando, len(cand) só testava o 1º
    # 12/10/2026 (Murilo, saída "a" do buraco de 15 a 27/10): os 7 dias contam até o DIA DO POST, não até a
    # segunda da rotina. Cada horário, em ordem, leva o melhor candidato que já vai ter MATURA dias naquela data.
    pares, livres = [], list(cand)
    for quando in slots:
        dia = dt.date.fromisoformat(quando[:10])
        escolhido = next((c for c in livres if acerto_cedo(c[2]) or (dia - dt.date.fromisoformat(c[3]["published"][:10])).days >= MATURA), None)
        if escolhido:
            livres.remove(escolhido)
            pares.append((escolhido, quando))
    cand = [c for c, _ in pares] + livres
    plano = []
    for (score, views, vid, v), quando in pares:
        url = cp.hosted_url(vid)
        if not url and hospedar:
            try:
                url = cp.host(vid, v["title"])
            except Exception as e:
                print(f"  ✗ não hospedou {vid}: {e}")
                continue
        mes = quando[:7]
        no_metricool = sum(1 for p in ag["posts"] if p["quando"][:7] == mes and p.get("status") not in FORA_DA_AGENDA
                           and p.get("agendado_por", "metricool") == "metricool") + sum(1 for p in plano if p["quando"][:7] == mes and p["agendar_por"] == "metricool")
        plano.append({"video_id": vid, "titulo": v["title"], "views_youtube": views, "tema_score": score,
                      "agendar_por": "metricool" if no_metricool < METRICOOL_LIMITE else "tiktok-web",
                      "quando": quando, "legenda": legenda(v), "video_url": url,
                      "privacidade": "PUBLIC_TO_EVERYONE", "canal": v.get("source", "mp"),
                      **({"conferir_voz": "voz clonada = isAigc true no Metricool"} if v.get("source") == "mp2" else {})})
    sobra = cand[len(plano):]
    print(f"TikTok da semana · piso {PISO:,} views".replace(",", ".") + f" · {len(cand)} aptos · {len(plano)} no plano")
    for p in plano:
        ac = acerto_cedo(p["video_id"])
        print(f"  ✔ {p['quando'][:16]} · {p['views_youtube']:>7,} · tema {p['tema_score']} · {p['titulo'][:60]} {'' if p['video_url'] else '(SEM HOSPEDAGEM)'}".replace(",", ".")
              + (" · abaixo do piso" if p["views_youtube"] < PISO else "") + (" · PELO TIKTOK WEB (Periscópio)" if p["agendar_por"] == "tiktok-web" else "")
              + (f" · acerto cedo: {ac['vezes']}x a régua com {ac['marco_nome']}".replace(".", ",") if ac else ""))
    for s in sobra:
        print(f"  … fica pra próxima: {s[3]['title'][:60]}")
    print(f"Fora ({len(fora)}):")
    for vid, t, m in fora[:15]:
        print(f"  ✗ {t[:55]} · {m}")
    if hospedar:
        json.dump({"_leia": "Gerado por tiktok_semana.py. O Leme agenda estes no Metricool (MCP), sempre PUBLIC_TO_EVERYONE, "
                            "e grava cada um em tiktok_agenda.json com o metricool_id e agendado_por. Os de agendar_por tiktok-web "
                            "(Metricool perto de 20 no mês) vão pro Periscópio agendar no TikTok web.",
                   "gerado_em": dt.datetime.now(BRT).isoformat(), "plano": plano},
                  open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"-> {SAIDA}")


if __name__ == "__main__":
    main("hospedar" in sys.argv, "acertos" in sys.argv)
