#!/usr/bin/env python3
"""
vigia.py: o carinha que fica olhando a analytics do canal e avisa no BotPreguica.

O que ele faz a cada rodada (cron ~30min):
  1. Acha os videos publicados nas ultimas 96h (Data API, via API key).
  2. Views quase em tempo real: marcos (500, 1k, 5k...) e mudanca de ritmo (views/hora).
  3. Quando a Analytics API fecha um dia de dados (ela atrasa 1 a 2 dias), manda o
     raio-x do dia: CTR, impressoes, % media assistida, inscritos ganhos, fontes de trafego.
  4. Guarda estado em vigia_state.json (commitado pelo workflow) pra nao repetir aviso.

Env: YOUTUBE_API_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN,
     TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DRY_RUN (1 = so imprime).
Regua de CTR do canal (thumb-receita-validada, ago/2026): forte >6%, normal 4 a 6, fraco <3.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
CANAL = "UCRKX-GV-beUtYs2IQD-f6jg"
UPLOADS = "UURKX-GV-beUtYs2IQD-f6jg"
JANELA_H = 96
MARCOS = [500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 250000, 500000, 1000000]
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(RAIZ, "vigia_state.json")
DRY = os.environ.get("DRY_RUN", "0") == "1"


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()[:300]
        raise RuntimeError(f"HTTP {e.code} em {url.split('?')[0]}: {corpo}")


def tg(texto):
    if DRY:
        print("[DRY] TELEGRAM:\n" + texto + "\n" + "-" * 40)
        return
    body = urllib.parse.urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": texto[:3900],
        "disable_web_page_preview": "true",
    }).encode()
    http(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
         body, {"Content-Type": "application/x-www-form-urlencoded"})


def access_token():
    body = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    return http("https://oauth2.googleapis.com/token", body,
                {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]


_TOK = None
def yt_token():
    global _TOK
    if _TOK is None: _TOK = access_token()
    return _TOK


def data_api(path, **params):
    # Usa o mesmo OAuth da Analytics (youtube.readonly); API key vira opcional.
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if key:
        params["key"] = key
        return http(f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(params))
    return http(f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(params),
                headers={"Authorization": f"Bearer {yt_token()}"})


def analytics(tok, video_id, start, end, metrics, dims=None, sort=None):
    p = {"ids": "channel==MINE", "startDate": start, "endDate": end,
         "metrics": metrics, "filters": f"video=={video_id}"}
    if dims: p["dimensions"] = dims
    if sort: p["sort"] = sort
    return http("https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(p),
                headers={"Authorization": f"Bearer {tok}"})


def eh_short(dur_iso):
    # PT1M13S etc; short = ate 3 minutos
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur_iso or "")
    if not m: return False
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h == 0 and (mi * 60 + s) <= 180


def carregar_estado():
    try:
        with open(STATE_PATH) as f: return json.load(f)
    except Exception:
        return {"videos": {}}


def salvar_estado(st):
    with open(STATE_PATH, "w") as f: json.dump(st, f, ensure_ascii=False, indent=1)


def fontes_bonitas(rows):
    NOMES = {"NO_LINK_OTHER": "direto/outros", "SUBSCRIBER": "inscritos/feed", "BROWSE": "navegacao",
             "RELATED_VIDEO": "sugeridos", "YT_SEARCH": "busca", "SHORTS": "feed de Shorts",
             "EXT_URL": "links externos", "NOTIFICATION": "notificacao", "PLAYLIST": "playlist",
             "YT_CHANNEL": "pagina do canal", "YT_OTHER_PAGE": "outras paginas", "VIDEO_REMIXES": "remix"}
    tot = sum(r[1] for r in rows) or 1
    top = sorted(rows, key=lambda r: -r[1])[:3]
    return ", ".join(f"{NOMES.get(r[0], r[0])} {round(100*r[1]/tot)}%" for r in top)


def main():
    agora = datetime.now(timezone.utc)
    st = carregar_estado()
    avisos = []

    # 1) uploads recentes
    itens = data_api("playlistItems", part="contentDetails", playlistId=UPLOADS, maxResults=15)
    ids = [i["contentDetails"]["videoId"] for i in itens.get("items", [])]
    if not ids:
        print("sem uploads"); return
    vids = data_api("videos", part="snippet,statistics,contentDetails,status", id=",".join(ids))

    vigiados = []
    for v in vids.get("items", []):
        if v.get("status", {}).get("privacyStatus") != "public":
            continue  # agendado/privado nao entra no radar ate ir ao ar
        pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
        if (agora - pub) <= timedelta(hours=JANELA_H):
            vigiados.append(v)

    tok = None
    for v in vigiados:
        vid = v["id"]
        titulo = v["snippet"]["title"][:55]
        tipo = "Short" if eh_short(v["contentDetails"].get("duration")) else "video longo"
        pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
        views = int(v["statistics"].get("viewCount", 0))
        s = st["videos"].setdefault(vid, {"titulo": titulo, "avisos": [], "hist": [], "dias_reportados": []})

        # radar: primeira vez que vemos o video
        if "radar" not in s["avisos"]:
            s["avisos"].append("radar")
            avisos.append(f"🔭 No radar: {tipo} «{titulo}» (publicado {pub.astimezone(BRT).strftime('%d/%m %H:%M')}). "
                          f"Aviso nos marcos de views e quando a analytics fechar cada dia.")

        # historico de views pra velocidade
        s["hist"].append([agora.isoformat(), views])
        s["hist"] = s["hist"][-48:]
        if len(s["hist"]) >= 3:
            t0, v0 = s["hist"][-3]
            t1, v1 = s["hist"][-1]
            horas = max((datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds() / 3600, 0.1)
            vph = (v1 - v0) / horas
            ultimo_vph = s.get("vph", 0)
            s["vph"] = round(vph, 1)
            chave6h = "vel_" + agora.strftime("%d%H")[:3]
            if vph >= 200 and vph >= 2 * max(ultimo_vph, 50) and chave6h not in s["avisos"]:
                s["avisos"].append(chave6h)
                avisos.append(f"🚀 «{titulo}» acelerou: {round(vph)} views/hora agora (antes ~{round(ultimo_vph)}). Total {views:,}.".replace(",", "."))

        # marcos
        for m in MARCOS:
            k = f"marco_{m}"
            if views >= m and k not in s["avisos"]:
                s["avisos"].append(k)
                avisos.append(f"🎯 «{titulo}» passou de {m:,} views (agora {views:,}).".replace(",", "."))

        # analytics por dia (chega com 1 a 2 dias de atraso)
        try:
            if tok is None: tok = yt_token()
            ini = pub.astimezone(BRT).strftime("%Y-%m-%d")
            fim = agora.astimezone(BRT).strftime("%Y-%m-%d")
            met = "views,averageViewDuration,averageViewPercentage,subscribersGained,videoThumbnailImpressions,videoThumbnailImpressionsClickRate"
            try:
                rep = analytics(tok, vid, ini, fim, met, dims="day")
            except RuntimeError:
                met = "views,averageViewDuration,averageViewPercentage,subscribersGained"
                rep = analytics(tok, vid, ini, fim, met, dims="day")
            cols = [c["name"] for c in rep.get("columnHeaders", [])]
            for row in rep.get("rows", []):
                d = dict(zip(cols, row))
                dia = d.get("day")
                if not dia or dia in s["dias_reportados"] or int(d.get("views", 0)) == 0:
                    continue
                s["dias_reportados"].append(dia)
                partes = [f"📊 «{titulo}», dia {datetime.strptime(dia, '%Y-%m-%d').strftime('%d/%m')} fechado:"]
                if "videoThumbnailImpressionsClickRate" in d and d.get("videoThumbnailImpressions"):
                    ctr = float(d["videoThumbnailImpressionsClickRate"])
                    imp = int(d["videoThumbnailImpressions"])
                    partes.append(f"CTR {ctr:.1f}% em {imp:,} impressoes".replace(",", "."))
                partes.append(f"{int(d.get('views', 0))} views, {float(d.get('averageViewPercentage', 0)):.0f}% assistido em media, "
                              f"{int(d.get('subscribersGained', 0))} inscritos ganhos.")
                try:
                    tr = analytics(tok, vid, dia, dia, "views", dims="insightTrafficSourceType", sort="-views")
                    linhas = [(r[0], int(r[1])) for r in tr.get("rows", [])]
                    if linhas: partes.append("Fontes: " + fontes_bonitas(linhas) + ".")
                except Exception:
                    pass
                partes.append("Regua do canal: CTR forte acima de 6, normal 4 a 6, fraco abaixo de 3.")
                avisos.append(" ".join(partes))
        except Exception as e:
            print(f"analytics falhou p/ {vid}: {e}")

    # limpa videos que sairam da janela
    for vid in list(st["videos"].keys()):
        if vid not in [v["id"] for v in vigiados]:
            st["videos"][vid]["fora_da_janela"] = True

    salvar_estado(st)

    if avisos:
        tg("\n\n".join(avisos))
        print(f"{len(avisos)} aviso(s) enviado(s).")
    else:
        print("rodada sem novidade, nada enviado.")


if __name__ == "__main__":
    main()
