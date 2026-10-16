#!/usr/bin/env python3
"""
Placar do experimento "furar a bolha" no TikTok do canal principal (Sextante, 14/10/2026).

O Murilo (14/10): "estamos na busca de conteúdos que performam tão bem quanto Subnautica... meu
algoritmo está focado nisso mas precisamos furar essa bolha de alguma forma". Regras aprovadas: 2 dos
4 TikToks da semana fora do Subnautica, jogo em alta + gancho de monstro/medo/escala/segredo, 3
tentativas por tema antes de descartar, mais uma chance pros rankings com gancho.

O que este script faz, a cada rodada:
  1. lê o perfil público do TikTok com yt-dlp (sem login) e grava uma FOTO das views de todo post com
     menos de 8 dias em bolha_tiktok_fotos.json. O TikTok não guarda a curva, então o número de 48 h
     e de 7 dias só existe se a gente fotografar perto da hora (entre duas fotos, interpola);
  2. acha os testes de bolha_tiktok_testes.json no perfil (tiktok_id ou palavras do título);
  3. calcula a régua do canal (mediana dos 12 últimos TikToks que NÃO são teste) no mesmo prazo:
     48 h e 7 dias. Enquanto não houver 6 posts fotografados no prazo, a régua é provisória: views
     totais dos 12 últimos com 7 dias ou mais (mais dura com o teste de 48 h, avisado no painel);
  4. dá a faixa de cada teste (abaixo da régua = não pegou; acima = promissor; 5 mil ou mais = furou)
     e o veredito do tema depois da última tentativa fechar 7 dias;
  5. escreve bolha_tiktok.json, que o painel mostra (tela Resultado e /bolha).

Roda sozinho pelo bin/atualizar_painel.sh (launchd, a cada 10 min); só lê o TikTok se a última foto
tem mais de 2 h (--forcar ignora). Uso: python3 scripts/bolha_tiktok.py [--forcar]
"""
import json, os, re, statistics, subprocess, sys, unicodedata
import datetime as dt

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTES = os.path.join(RAIZ, "bolha_tiktok_testes.json")
FOTOS = os.path.join(RAIZ, "bolha_tiktok_fotos.json")
SAIDA = os.path.join(RAIZ, "bolha_tiktok.json")
# 12/10: "@manopreguica" passou a dar erro no yt-dlp ("Unable to extract secondary user ID"); pelo id funciona.
PERFIL = "tiktokuser:MS4wLjABAAAALaAIS7xTvWi4UpXfnEMxpaiGNw4gJYI5qK4Hf8KK8a2U5TUInmcUUrh3dz79X22q"
BRT = dt.timezone(dt.timedelta(hours=-3))
H = 3600
MARCOS = {"48h": 48 * H, "7d": 7 * 24 * H}
INTERVALO = 2 * H          # só lê o perfil de novo depois de 2 h
SEGUIR = 8.5 * 24 * H      # fotografa post até 8,5 dias (passa do marco de 7 dias)
N_REGUA, MIN_REGUA = 12, 6


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def ler_perfil(n=40):
    r = subprocess.run(["yt-dlp", "--no-update", "--flat-playlist", "-J", "--playlist-end", str(n), PERFIL],
                       capture_output=True, text=True, timeout=300)
    d = json.loads(r.stdout or "{}")
    posts = []
    for e in d.get("entries") or []:
        if not e.get("timestamp"):
            continue
        posts.append({"id": str(e["id"]), "ts": int(e["timestamp"]), "titulo": (e.get("title") or "").strip(),
                      "views": (int(e["view_count"]) if e.get("view_count") is not None else None), "likes": int(e.get("like_count") or 0),
                      "comentarios": int(e.get("comment_count") or 0), "salvos": int(e.get("save_count") or 0),
                      "compart": int(e.get("repost_count") or 0)})
    return posts


def carregar(p, padrao):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def no_marco(post, fotos, seg):
    """Views no marco (seg depois de publicar). Foto a até 1 h do marco vale direto; entre duas fotos,
    interpola; só fotos depois do marco, vale a primeira se veio até 12 h depois. Senão, None."""
    alvo = post["ts"] + seg
    fs = sorted(fotos, key=lambda f: f["t"])
    if not fs or fs[-1]["t"] < alvo - H:
        return None, "ainda não chegou"
    perto = min(fs, key=lambda f: abs(f["t"] - alvo))
    if abs(perto["t"] - alvo) <= H:
        return perto["v"], "lido na hora"
    antes = [f for f in fs if f["t"] < alvo]
    depois = [f for f in fs if f["t"] > alvo]
    if antes and depois:
        a, b = antes[-1], depois[0]
        if b["t"] - a["t"] <= 24 * H:
            return round(a["v"] + (b["v"] - a["v"]) * (alvo - a["t"]) / (b["t"] - a["t"])), "estimado entre duas leituras"
    if depois and depois[0]["t"] - alvo <= 12 * H:
        return depois[0]["v"], f"lido {round((depois[0]['t'] - alvo) / H)} h depois"
    return None, "sem leitura no prazo"


def casar(tent, posts, desde):
    if tent.get("tiktok_id"):
        return next((p for p in posts if p["id"] == str(tent["tiktok_id"])), None)
    for p in sorted(posts, key=lambda p: p["ts"]):
        if p["ts"] < desde:
            continue
        t = norm(p["titulo"])
        if any(all(w in t for w in grupo) for grupo in tent.get("palavras", [])):
            return p
    return None


def faixa(v, regua, furou):
    if v is None or regua is None:
        return None
    if v >= furou:
        return "furou"
    return "promissor" if v >= regua else "não pegou"


def main():
    forcar = "--forcar" in sys.argv
    cfg = carregar(TESTES, None)
    if not cfg:
        print("sem bolha_tiktok_testes.json"); return
    banco = carregar(FOTOS, {"_leia": "Fotos das views dos TikToks (scripts/bolha_tiktok.py). t = unix, v = views.", "posts": {}})
    agora = int(dt.datetime.now(dt.timezone.utc).timestamp())
    ultima = max((f["t"] for p in banco["posts"].values() for f in p["fotos"]), default=0)
    if not forcar and agora - ultima < INTERVALO:
        print("última foto há menos de 2 h; nada a fazer"); return
    posts = ler_perfil()
    if not posts:
        print("não consegui ler o perfil do TikTok"); return

    for p in posts:
        reg = banco["posts"].setdefault(p["id"], {"titulo": p["titulo"], "ts": p["ts"], "fotos": []})
        # Leitura falha (16/10/2026): o yt-dlp às vezes devolve o post sem view_count, ou com 0 num post que já tinha
        # milhares (a lava foi de 35.500 a 0). Isso derrubou a régua de 702 pra 133. Leitura sem número, ou 0 depois de
        # um valor positivo, não vira foto: o post fica com o último número bom.
        if p["views"] is None or (p["views"] == 0 and reg.get("views", 0) > 0):
            p["views"] = reg.get("views") or 0
            continue
        reg["views"] = p["views"]
        if agora - p["ts"] <= SEGUIR or p["id"] in {str(t.get("tiktok_id")) for te in cfg["temas"] for t in te["tentativas"]}:
            if not reg["fotos"] or reg["fotos"][-1]["v"] != p["views"] or agora - reg["fotos"][-1]["t"] > 6 * H:
                reg["fotos"].append({"t": agora, "v": p["views"]})
    json.dump(banco, open(FOTOS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    desde = int(dt.datetime.fromisoformat(cfg["desde"]).replace(tzinfo=BRT).timestamp())
    furou = int(cfg.get("furou", 5000))
    teste_ids = set()
    achados = {}
    for te in cfg["temas"]:
        for t in te["tentativas"]:
            p = casar(t, posts, desde)
            if p:
                achados[id(t)] = p
                teste_ids.add(p["id"])

    # Régua do canal: os 12 últimos posts que não são teste, no mesmo prazo.
    base = sorted([p for p in posts if p["id"] not in teste_ids], key=lambda p: -p["ts"])
    regua = {}
    for nome, seg in MARCOS.items():
        vals = []
        for p in base:
            v, _ = no_marco(p, banco["posts"].get(p["id"], {}).get("fotos", []), seg)
            if v is not None:
                vals.append(v)
        if len(vals) >= MIN_REGUA:
            regua[nome] = {"valor": int(statistics.median(vals[:N_REGUA])), "n": min(len(vals), N_REGUA), "provisoria": False,
                           "como": f"mediana dos {min(len(vals), N_REGUA)} últimos TikToks fora do teste, em views com {nome}"}
        else:
            maduros = [p["views"] for p in base if agora - p["ts"] >= MARCOS["7d"]][:N_REGUA]
            regua[nome] = {"valor": int(statistics.median(maduros)) if maduros else None, "n": len(maduros), "provisoria": True,
                           "como": f"provisória: views totais dos {len(maduros)} últimos TikToks fora do teste com 7 dias ou mais "
                                   f"(vira a mediana com {nome} quando houver {MIN_REGUA} posts fotografados nesse prazo)"}

    temas_out = []
    for te in cfg["temas"]:
        linhas = []
        for i, t in enumerate(te["tentativas"], 1):
            p = achados.get(id(t))
            l = {"n": i, "pauta": t.get("pauta"), "titulo": t["titulo"], "status": "esperando publicar"}
            if p:
                fotos = banco["posts"].get(p["id"], {}).get("fotos", [])
                horas = round((agora - p["ts"]) / H)
                l.update({"status": "no ar", "tiktok_id": p["id"], "link": f"https://www.tiktok.com/@manopreguica/video/{p['id']}",
                          "publicado": dt.datetime.fromtimestamp(p["ts"], BRT).strftime("%d/%m %H:%M"), "horas_no_ar": horas,
                          "titulo_tiktok": p["titulo"][:120], "agora": {"views": p["views"], "likes": p["likes"],
                          "comentarios": p["comentarios"], "salvos": p["salvos"], "compart": p["compart"]}})
                for nome, seg in MARCOS.items():
                    v, como = no_marco(p, fotos, seg)
                    l[nome] = {"views": v, "como": como, "regua": regua[nome]["valor"],
                               "x": round(v / regua[nome]["valor"], 2) if v is not None and regua[nome]["valor"] else None,
                               "faixa": faixa(v, regua[nome]["valor"], furou)}
                if l["7d"]["views"] is not None:
                    l["status"] = "fechado (7 dias)"
            linhas.append(l)
        fechadas = [l for l in linhas if l.get("7d", {}).get("views") is not None]
        total = len(linhas)
        if len(fechadas) < total:
            parcial = [l["7d"]["faixa"] for l in fechadas]
            veredito = {"fechado": False, "texto": f"em teste: {len(fechadas)} de {total} tentativas fecharam 7 dias"
                        + (f" ({', '.join(parcial)})" if parcial else "")}
        else:
            fx = [l["7d"]["faixa"] for l in fechadas]
            acima = sum(f in ("promissor", "furou") for f in fx)
            if "furou" in fx:
                txt, cod = "furou a bolha: pelo menos uma tentativa passou de 5 mil", "furou"
            elif acima * 2 >= total:   # metade ou mais acima da régua (2 de 3; nos rankings, 1 de 2)
                txt, cod = "promissor: metade ou mais passou da régua do canal, mas nenhuma de 5 mil", "promissor"
            else:
                txt, cod = "não pegou: a maioria ficou abaixo da régua do canal; tema descartado", "não pegou"
            veredito = {"fechado": True, "codigo": cod, "texto": txt}
        temas_out.append({"tema": te["tema"], "por_que": te.get("por_que"), "tentativas": linhas, "veredito": veredito})

    out = {
        "_leia": "Gerado por scripts/bolha_tiktok.py (Sextante). O painel mostra na tela Resultado e em /bolha.",
        "gerado_em": dt.datetime.now(BRT).isoformat(timespec="minutes"),
        "pedido": "Furar a bolha no TikTok: achar fora do Subnautica o que performa tão bem quanto ele (Murilo, 14/10/2026).",
        "como_ler": [
            "Cada teste é medido no mesmo prazo: 48 horas e 7 dias depois de publicar. O que vale pro veredito é o de 7 dias.",
            "Régua = mediana do canal no TikTok, recalculada a cada leitura, sem contar os próprios testes.",
            f"Abaixo da régua: não pegou. Acima da régua: promissor. {furou:,} views ou mais: furou.".replace(",", "."),
            "Cada tema tem 3 tentativas (os rankings, 2). Quando a última fecha 7 dias, o tema ganha o veredito: furou (alguma passou de 5 mil), promissor (metade ou mais passou da régua) ou não pegou (descarta).",
        ],
        "furou": furou,
        "regua": regua,
        "subnautica_referencia": "Subnautica criatura no TikTok: 308 mil (Reaper maior), 139 mil (pior susto), 83 mil (Gargantuan), 32 mil (buraco da lava).",
        "temas": temas_out,
    }
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for te in temas_out:
        print(te["tema"], "·", te["veredito"]["texto"])
        for l in te["tentativas"]:
            if l["status"] != "esperando publicar":
                print("  ", l["pauta"], l["agora"]["views"], "views,", l["horas_no_ar"], "h ·", "48h:", l["48h"]["views"], l["48h"]["faixa"], "· 7d:", l["7d"]["views"], l["7d"]["faixa"])
    print("régua:", {k: (v["valor"], "provisória" if v["provisoria"] else "") for k, v in regua.items()})


if __name__ == "__main__":
    main()
