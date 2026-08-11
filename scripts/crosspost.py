#!/usr/bin/env python3
"""
Robô de crosspost — roda no GitHub Actions (ou local).
Fluxo por execução (MODE=post, cron DIÁRIO):
  1. atualiza o ledger (detecta vídeo novo no YouTube — canal principal + MP2 — preserva status)
  2. monta UMA FILA POR REDE (Facebook / TikTok / Instagram), com dedup e curadoria
  3. agenda a COTA DIÁRIA de cada rede (padrão FB 2, TikTok 1, IG 1) via PostProxy,
     em horários espalhados à noite (BRT), respeitando o teto mensal do plano
  4. marca no ledger + limpa o asset + avisa no Telegram

Migração 2026-07-27: PostProxy pago (Build, 120 posts/mês). TUDO passa a sair pelo
PostProxy REST (TikTok e IG saíram do Metricool). Cadência definida pelo Murilo:
FB 2/dia, TikTok 1/dia, IG 1/dia.

Dedup / segurança (medo de duplicar):
  - Facebook: backlog provado por views (você postou pouco lá -> dup-safe).
  - TikTok/Instagram: FILA CURADA — vertical (TikTok exige 1min+), no nicho (blacklist),
    >= MIN_VIEWS, e NÃO postado NAQUELA rede nos últimos 2 meses (data decodificada do
    post_id). Reposta campeão antigo, nunca o recente. Vídeo NOVO (>= START_DATE) entra
    nas 3 redes que couberem.
Config por variável de ambiente (secrets no Actions).
"""
import os, sys, json, re, subprocess, urllib.request, urllib.error, urllib.parse, datetime, time

DRY        = os.environ.get("DRY_RUN", "1") == "1"
PP_KEY     = os.environ.get("POSTPROXY_KEY", "")
YT_KEY     = os.environ.get("YOUTUBE_API_KEY", "")
TG_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.environ.get("TELEGRAM_CHAT_ID", "")
REPO       = os.environ.get("MEDIA_REPO", "murilolacerdamoraess-crypto/mano-preguica-media")
START_DATE = os.environ.get("START_DATE", "2026-07-15")   # vídeo >= isto = "novo" (entra nas 3 redes)
MONTH_CAP  = int(os.environ.get("MONTH_CAP", "118"))  # teto/mês do plano PostProxy Build (120) c/ folga
MODE       = os.environ.get("MODE", "post")          # "post" (nuvem) ou "prehost" (Mac: baixa+hospeda)
BUFFER_DAYS= int(os.environ.get("BUFFER_DAYS", "3")) # prehost mantém DAILY[net]*BUFFER_DAYS por rede
ONLY_VIDEO = os.environ.get("ONLY_VIDEO", "").strip() # override manual: posta SÓ este vídeo
ONLY_NET   = os.environ.get("ONLY_NET", "").strip()   # ...nesta rede
SCHEDULE_AT= os.environ.get("SCHEDULE_AT", "").strip() # ...opcional: agenda p/ ISO8601 UTC
MIN_VIEWS  = int(os.environ.get("MIN_VIEWS", "10000"))  # piso subido 1000->10000 (análise 02/08):
# TODO flop no TikTok tinha YouTube fraco (Lethal 1140->152 TT, pirâmides 2273->143, história 2182->119).
# Os que renderam no TikTok tinham YT >=15k (Reaper 15.5k->15k TT, Void 25.7k->11k). Piso corta o lixo.

# Cota DIÁRIA por rede (o cron roda 1x/dia e agenda a cota do dia)
DAILY = {"facebook":   int(os.environ.get("DAILY_FB", "2")),
         "tiktok":     int(os.environ.get("DAILY_TT", "1")),
         "instagram":  int(os.environ.get("DAILY_IG", "1"))}
# Data de ATIVAÇÃO por rede (o robô só posta a rede a partir daqui). Deixa o Metricool
# escoar os pendentes antes: TikTok até 01/08, IG até 16/08 -> PostProxy assume no dia seguinte.
# Vazio = já ativo (Facebook começa logo, Metricool não posta FB).
ACTIVATE = {"tiktok":    os.environ.get("TT_START", ""),
            "instagram": os.environ.get("IG_START", "")}
# Cadência SEMANAL opcional por rede (weekday Seg=0..Dom=6): a rede só posta NESSE dia.
# Usado pra manter o Facebook vivo (é monetizado) numa frequência baixa, ~1x/semana, sem gastar cota.
WEEKLY = {}
if os.environ.get("FB_WEEKDAY", "") != "":
    WEEKLY["facebook"] = int(os.environ["FB_WEEKDAY"])
# Horários (hora, minuto) BRT por rede — espalhados p/ não sair tudo junto
HOURS = {"facebook":  [(20, 0), (22, 0)],
         "tiktok":    [(21, 0)],
         "instagram": [(21, 30)]}

FB_PAGE    = "606193705900753"
PROFILES   = {"tiktok": "knUlkm", "instagram": "oJUZQL", "facebook": "L2ULXV"}
# Fonte principal = uploads playlist inteira do Mano Preguiça (UU + resto do channel id).
SOURCES    = {"mp": "UURKX-GV-beUtYs2IQD-f6jg"}
# MP2: NÃO a playlist toda (o MP2 tem games variados que não devem ir pros perfis do principal).
# Só os faceless de IA que a gente PRODUZ aqui, por ALLOWLIST explícita de video IDs.
# Adicionar o ID de cada novo vídeo de IA conforme for feito. Usam os perfis do Mano Preguiça.
MP2_ALLOW  = ["Stm2pYvz-yE",   # E se o RAGNARÖK fosse real?
              "6CCN3fHFPGc"]   # Filmaram ISSO no Rio Amazonas (Jacaré)
HERE       = os.path.dirname(os.path.abspath(__file__))
def _find_ledger():
    for p in (os.environ.get("LEDGER_PATH"), os.path.join(HERE, "ledger.json"),
              os.path.join(HERE, "..", "ledger.json"), "ledger.json"):
        if p and os.path.exists(p): return os.path.abspath(p)
    return os.path.join(HERE, "ledger.json")
LEDGER     = _find_ledger()
TMP        = os.environ.get("TMP_DIR", os.path.join(HERE, "tmp")); os.makedirs(TMP, exist_ok=True)
UA         = {"User-Agent": "crosspost-bot"}

def log(*a): print(*a, flush=True)

BRT    = datetime.timezone(datetime.timedelta(hours=-3))   # Brasil sem horário de verão
DIA_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
NET_PT = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram"}
def fmt_when(iso):
    """'2026-07-18T00:00:00Z' -> 'hoje 21h' / 'amanhã 21h' / 'Sex 21h' (BRT)."""
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BRT)
    except Exception:
        return iso
    d = (dt.date() - datetime.datetime.now(BRT).date()).days
    dia = "hoje" if d == 0 else "amanhã" if d == 1 else DIA_PT[dt.weekday()]
    hhmm = f"{dt.hour}h" if dt.minute == 0 else f"{dt.hour}h{dt.minute:02d}"
    return f"{dia} {hhmm}"

def slot_utc(hour, minute):
    """Hoje às hour:minute BRT em ISO UTC. Se já passou, '' (posta imediato: fallback raro)."""
    agora = datetime.datetime.now(BRT)
    alvo = agora.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if agora >= alvo: return ""
    return alvo.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------- curadoria de repost (TikTok/IG) — regras do Murilo ----------
BLACK = ["arcane","league","jinx","zaun","riot"," tft","anime","série","serie","series","novela",
         "vikings","valhalla","marvel","netflix","filmes","lobisomem","werewolf","uefa","champions",
         "futebol","gta","the last of us","fortnite","valorant","hamburgueria","arcade","orlando"]
IG_AL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
def off_nicho(t):
    tl = t.lower(); return any(k in tl for k in BLACK)

# --- peso de TEMA p/ feed frio (TikTok/IG) — descoberto na análise 05/08 ---
# O nº de views no YouTube é o PISO (MIN_VIEWS já corta o lixo), mas NÃO é o teto no TikTok:
# hits gigantes de YT sobre CONSTRUÇÃO/VEÍCULO morreram no feed frio (Archon 170k YT -> 876 TT,
# bases 484k -> 555), enquanto CRIATURA + medo/escala explodiu (Reaper -> 42k TT, FNAF -> 3.3k).
# Então, entre os elegíveis, priorizamos monstro/medo e afundamos construção/veículo/notícia.
BOOST_KW = ["leviat","reaper","gargantuan","shiver","elusive","ghost","dragon","dragão","warper",
            "crabsquid","serpente","kraken","monstro","criatura","bicho","tubarão","medo","terror",
            "assombr","barulho"," som ","escondid","esconde","void","abismo","fundo do mar","profund",
            "perigos","mortal","matar","mata ","ataca","ataque","sobreviv","fnaf","segredo","nunca",
            "jamais","gigante","maior","tamanho","o que é","que faz","por que","porque não"]
DRAG_KW  = ["base","construir","construç","submarino","veículo","veiculo","cyclops","seamoth","prawn",
            "archon","luxo","tour","mansão","decor","upgrade","módulo","modulo","anunci","lançad",
            "lançament","trailer","mobile","celular","atualizaç","update","patch"]
def tema_score(title):
    """+1 por gatilho de criatura/medo/escala, -1 por construção/veículo/notícia. Reordena a fila."""
    tl = title.lower()
    return sum(1 for k in BOOST_KW if k in tl) - sum(1 for k in DRAG_KW if k in tl)
THEME_CUT = int(os.environ.get("THEME_CUT", "-2"))  # backlog TT/IG com score <= isto: corta (construção pura)

# --- trava de NOTÍCIA VELHA (05/08: "NOVO MONSTRO SUBNAUTICA 2" ia sair com 302 dias) ---
# Título com moldura de novidade ("novo", "anunciado", "vazou", "chegando"...) num vídeo já
# envelhecido = notícia datada. Num jogo em desenvolvimento, "novo" de 10 meses atrás mente.
# NÃO uso "revelou/segredo" (ex.: "segredo de 12 anos" é atemporal, não datado).
NOVELTY_KW = ["novo ", "nova ", "anunci", "lançad", "lançament", "chegando", "vazou", "vazad",
              "acaba de", "breaking", "confirmad", "trailer", "data de lançament", "saiu o"]
FRESH_DAYS = int(os.environ.get("FRESH_DAYS", "120"))  # acima disso, moldura de novidade = velha
def noticia_velha(v):
    tl = v.get("title", "").lower()
    if not any(k in tl for k in NOVELTY_KW):
        return False
    try:
        idade = (datetime.date.today() - datetime.date.fromisoformat(v["published"][:10])).days
    except Exception:
        return False
    return idade > FRESH_DAYS
def tiktok_date(pid):
    try: return datetime.datetime.utcfromtimestamp(int(pid) >> 32).date()
    except Exception: return None
def instagram_date(sc):
    try:
        mid = 0
        for c in sc: mid = mid * 64 + IG_AL.index(c)
        return datetime.datetime.utcfromtimestamp(((mid >> 23) + 1314220021721) / 1000).date()
    except Exception: return None
def parse_date(s):
    try: return datetime.date.fromisoformat(str(s)[:10])
    except Exception: return None
def ultima_vez(net, p):
    pid = p.get("post_id", "") or ""
    dec = instagram_date(pid) if net == "instagram" else tiktok_date(pid) if net == "tiktok" else None
    return dec or parse_date(p.get("date"))

# ---------- YouTube: atualizar ledger ----------
def yt_get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA)))
def dur2s(du):
    m = re.match(r'^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', du)
    if not m: return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups()); return dd*86400 + h*3600 + mi*60 + s

def _playlist_ids(pl):
    ids, token = [], ""
    while True:
        u = (f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=50"
             f"&playlistId={pl}&key={YT_KEY}") + (f"&pageToken={token}" if token else "")
        d = yt_get(u); ids += [it["contentDetails"]["videoId"] for it in d["items"]]; token = d.get("nextPageToken")
        if not token: break
    return ids

def update_ledger():
    led = json.load(open(LEDGER))
    new = 0
    for source, pl in SOURCES.items():
        try:
            ids = _playlist_ids(pl)
        except Exception as e:
            log(f"aviso: fonte {source} ({pl}) falhou: {e}"); continue
        for i in range(0, len(ids), 50):
            d = yt_get(f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails,snippet,statistics&id={','.join(ids[i:i+50])}&key={YT_KEY}")
            for it in d["items"]:
                vid = it["id"]; t = dur2s(it["contentDetails"]["duration"])
                meta = {"title": it["snippet"]["title"], "seconds": t,
                        "type": "vertical" if 0 < t <= 185 else ("long" if t > 185 else "unknown"),
                        "published": it["snippet"]["publishedAt"][:10],
                        "views": int(it["statistics"].get("viewCount", 0)), "source": source}
                if vid not in led["videos"]:
                    new += 1
                    led["videos"][vid] = {**meta, "posted": {n: {"done": False, "date": None, "post_id": None} for n in PROFILES}}
                else:
                    led["videos"][vid].update(meta)
                v = led["videos"][vid]
                v["eligible"] = v["type"] in ("vertical", "long") and v["published"] >= "2025-01-01"
                v["postable"] = bool(v["eligible"] and v["views"] >= 500)
    json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
    return led, new

# ---------- decidir o que postar (fila por rede) ----------
def fits(net, v):
    if net == "tiktok":    return v["type"] == "vertical" and v["seconds"] >= 60   # só 1min+ monetiza
    if net == "instagram": return v["type"] == "vertical"
    if net == "facebook":  return True
    return False

def queue_facebook(vids):
    """Novos + backlog, por views desc, dup-safe (você postou pouco no FB)."""
    out = []
    for vid, v in sorted(vids.items(), key=lambda kv: -kv[1]["views"]):
        if not v["postable"] or v["posted"]["facebook"]["done"]: continue
        if noticia_velha(v): continue   # não repostar notícia datada nem no FB
        out.append(vid)
    return out

def queue_curada(net, vids):
    """TikTok/IG: vertical (TT 1min+), no nicho, >=MIN_VIEWS, não postado nessa rede há 2 meses.
    Novos primeiro (>= START_DATE, por views), depois backlog ANTIGO->NOVO (varredura única)."""
    min_secs = 60 if net == "tiktok" else 0
    novos, backlog = [], []
    for vid, v in vids.items():
        if not v["postable"] or v["type"] != "vertical": continue
        if v["seconds"] < min_secs: continue
        if v["views"] < MIN_VIEWS: continue
        if off_nicho(v["title"]): continue
        if noticia_velha(v): continue   # moldura de novidade + vídeo velho = notícia datada
        novo = v["published"] >= START_DATE
        sc = tema_score(v["title"])
        p = v["posted"][net]
        # NUNCA reposta o que já foi postado nessa rede. Antes reciclava "campeão" após 60 dias —
        # foi isso que repostou o hit "PORQUE NÃO TEM NINGUÉM VIVO" no TikTok (10/08). Regra do
        # Murilo: sem repost automático de campeão em rede nenhuma. Uma vez postado, acabou.
        if p["done"]: continue
        # teto-baixo no feed frio (construção/veículo/notícia pura): corta do BACKLOG.
        # Vídeo NOVO sempre entra (queremos conteúdo fresco nas 3 redes, independente do tema).
        if not novo and sc <= THEME_CUT: continue
        if novo:
            novos.append((-sc, -v["views"], vid))       # novos: melhor tema, depois mais views
        else:
            backlog.append((-sc, v["published"][:10], vid))  # backlog: melhor tema, depois mais antigo
    novos.sort(); backlog.sort()
    return [vid for *_, vid in novos] + [vid for *_, vid in backlog]

# Força H.264/avc1 no download (o [ext=mp4] antigo deixava passar AV1, que quebra em player/ingestão).
YTDLP_H264 = "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/b"

# ---------- hospedar / postar / limpar ----------
def host(vid, title):
    f = os.path.join(TMP, vid + ".mp4")
    subprocess.run(["yt-dlp", "-f", YTDLP_H264,
                    "-o", f, f"https://www.youtube.com/watch?v={vid}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["gh", "release", "create", vid, "--repo", REPO, "--title", title[:90],
                    "--notes", "efemero", f], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["gh", "release", "upload", vid, "--repo", REPO, f, "--clobber"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"https://github.com/{REPO}/releases/download/{vid}/{vid}.mp4"

def hosted_url(vid):
    url = f"https://github.com/{REPO}/releases/download/{vid}/{vid}.mp4"
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=25)
        return url
    except urllib.error.HTTPError as e:
        return url if e.code in (200, 302, 403) else None
    except Exception:
        return None

def cleanup(vid):
    subprocess.run(["gh", "release", "delete", vid, "--repo", REPO, "--yes", "--cleanup-tag"],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try: os.remove(os.path.join(TMP, vid + ".mp4"))
    except OSError: pass

def caption(v):
    # MP2 = faceless variado (não é Subnautica) -> hashtags genéricas de alcance
    if v.get("source") == "mp2":
        return f"{v['title']}\n\n#shorts #fyp #viral"
    return f"{v['title']}\n\n#Subnautica #games #gameplay #jogos"

# FB Reel exige VERTICAL (9:16) e tem limite de duração; horizontal/longo fica como "post" comum.
# Vertical vira Reel pra ganhar o alcance orgânico que o "post" não tem (análise 08/08: FB ~280 imp/post).
FB_REEL_MAXSEC = int(os.environ.get("FB_REEL_MAXSEC", "90"))
def platforms_block(net, v=None):
    if net == "facebook":
        vertical = bool(v) and v.get("type") == "vertical" and v.get("seconds", 0) <= FB_REEL_MAXSEC
        return {"facebook": {"format": "reel" if vertical else "post", "page_id": FB_PAGE}}
    if net == "tiktok":    return {"tiktok": {"privacy_status": "PUBLIC_TO_EVERYONE"}}
    if net == "instagram": return {"instagram": {"format": "reel"}}

def pp_post(net, url, text, scheduled_at="", v=None):
    post = {"body": text}
    if scheduled_at: post["scheduled_at"] = scheduled_at
    body = json.dumps({"post": post, "profiles": [PROFILES[net]],
                       "media": [url], "platforms": platforms_block(net, v)}).encode()
    req = urllib.request.Request("https://api.postproxy.dev/api/posts", data=body,
            headers={"Authorization": f"Bearer {PP_KEY}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def pp_wait_ingest(pid, tries=20):
    for _ in range(tries):
        req = urllib.request.Request(f"https://api.postproxy.dev/api/posts/{pid}",
                headers={"Authorization": f"Bearer {PP_KEY}"})
        d = json.load(urllib.request.urlopen(req))
        m = (d.get("media") or [{}])[0].get("status")
        if m in ("processed", "ready"): return True
        if m == "failed": return False
        time.sleep(15)
    return True

def pp_link(pid, net, tries=5):
    for _ in range(tries):
        try:
            req = urllib.request.Request(f"https://api.postproxy.dev/api/posts/{pid}",
                    headers={"Authorization": f"Bearer {PP_KEY}"})
            p = (json.load(urllib.request.urlopen(req)).get("platforms") or [{}])[0]
            link = p.get("permalink")
            if link:
                if net == "facebook":
                    m = re.search(r'/(\d{6,})', link)
                    if m: return f"https://facebook.com/watch/?v={m.group(1)}"
                return link
        except Exception: pass
        time.sleep(10)
    return None

def telegram(msg):
    if not (TG_TOKEN and TG_CHAT): return
    try:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
    except Exception as e: log("telegram err", e)

# ---------- main ----------
def record_schedule(vid, net, title, scheduled_at):
    path = os.path.join(os.path.dirname(LEDGER), "schedule.json")
    try: sched = json.load(open(path))
    except Exception: sched = []
    sched = [s for s in sched if not (s.get("vid") == vid and s.get("net") == net)]
    sched.append({"vid": vid, "net": net, "title": title, "scheduled_at": scheduled_at})
    json.dump(sched, open(path, "w"), ensure_ascii=False, indent=1)

def post_one(led, vid, net, scheduled_at="", tag="MANUAL"):
    v = led["videos"][vid]
    url = hosted_url(vid)
    if not url:
        log(f"{tag} {vid}: ainda não hospedado (rodar prehost no Mac antes)"); return False
    if DRY:
        log(f"[DRY] {tag} {net:9} <- {vid} | {v['title'][:46]} | quando={scheduled_at or 'agora'}"); return True
    r = pp_post(net, url, caption(v), scheduled_at, v=v); pid = r.get("id")
    pp_wait_ingest(pid); cleanup(vid)
    v["posted"][net] = {"done": True, "date": datetime.date.today().isoformat(), "post_id": pid, "link": ""}
    json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
    if scheduled_at:
        record_schedule(vid, net, v["title"], scheduled_at)
        telegram(f"🗓️ Agendado: {v['title'][:70]}\n→ {NET_PT.get(net, net)}, {fmt_when(scheduled_at)}")
        log(f"OK {tag} AGENDADO {net} <- {vid} (post {pid}) @ {scheduled_at}")
    else:
        link = pp_link(pid, net) or ""
        v["posted"][net]["link"] = link
        json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
        telegram(f"✅ Postei no {net}: {v['title'][:60]}\n{link}".strip())
        log(f"OK {tag} {net} <- {vid} (post {pid}) {link}")
    return True

def month_posted(led):
    month = datetime.date.today().strftime("%Y-%m")
    return sum(1 for v in led["videos"].values() for n in PROFILES
               if v["posted"][n]["done"] and (v["posted"][n]["date"] or "").startswith(month))

def build_queues(led):
    vids = led["videos"]
    return {"facebook":  queue_facebook(vids),
            "tiktok":    queue_curada("tiktok", vids),
            "instagram": queue_curada("instagram", vids)}

def main():
    led, new = update_ledger()

    if ONLY_VIDEO and ONLY_NET:          # botão manual: 1 vídeo -> 1 rede
        log(f"[MANUAL] {ONLY_NET} <- {ONLY_VIDEO} | quando={SCHEDULE_AT or 'agora'}")
        post_one(led, ONLY_VIDEO, ONLY_NET, SCHEDULE_AT); return

    queues = build_queues(led)

    if MODE == "prehost":   # roda no Mac (IP residencial): mantém a prateleira
        want = []
        for net in ("facebook", "tiktok", "instagram"):
            want += queues[net][: DAILY[net] * BUFFER_DAYS]   # buffer proporcional à cota
        log(f"[PREHOST] novos: {new} | filas FB {len(queues['facebook'])} / TT {len(queues['tiktok'])} / IG {len(queues['instagram'])} | buffer {BUFFER_DAYS}d")
        seen, on_shelf, added = set(), 0, 0
        for vid in want:
            if vid in seen: continue
            seen.add(vid)
            if hosted_url(vid): on_shelf += 1; continue
            try:
                host(vid, led["videos"][vid]["title"]); on_shelf += 1; added += 1
                log(f"   ✔ hospedado: {vid} | {led['videos'][vid]['title'][:45]}")
            except Exception as e:
                log(f"   ✗ erro host {vid}: {e}")
        log(f"prehost feito: {on_shelf} hospedados (novos: {added}).")
        return

    posted = month_posted(led); room = max(0, MONTH_CAP - posted)
    log(f"[{'DRY-RUN' if DRY else 'LIVE'}] novos: {new} | mês: {posted}/{MONTH_CAP} (folga {room}) | "
        f"cotas/dia FB {DAILY['facebook']} TT {DAILY['tiktok']} IG {DAILY['instagram']}")
    for net in ("facebook", "tiktok", "instagram"):
        log(f"  fila {net}: {len(queues[net])} candidatos")

    today = datetime.date.today().isoformat()
    done_total, done_vids = 0, set()   # não postar o MESMO vídeo em 2 redes no mesmo run
    for net in ("facebook", "tiktok", "instagram"):
        start = ACTIVATE.get(net, "")
        if start and today < start:
            log(f"  {net}: aguardando ativação ({start}) — Metricool ainda escoando"); continue
        wd = WEEKLY.get(net)
        if wd is not None and datetime.date.today().weekday() != wd:
            log(f"  {net}: cadência semanal ({DIA_PT[wd]}), hoje não é dia — pula"); continue
        slots = HOURS[net][:DAILY[net]]
        taken = 0
        for vid in queues[net]:
            if taken >= DAILY[net] or done_total >= room: break
            if vid in done_vids: continue
            h, m = slots[taken]
            at = slot_utc(h, m)
            try:
                if post_one(led, vid, net, at, tag="AUTO"):
                    taken += 1; done_total += 1; done_vids.add(vid)
            except Exception as e:
                log(f"ERRO {net} {vid}: {e}")
                telegram(f"⚠️ Falha ao postar {led['videos'][vid]['title'][:40]} no {net}: {e}")
        log(f"  {net}: {taken}/{DAILY[net]} agendado(s)")
    log(f"feito: {done_total} post(s) nesta execução (mês agora {posted + (0 if DRY else done_total)}/{MONTH_CAP}).")

if __name__ == "__main__":
    main()
