#!/usr/bin/env python3
"""
Robô de crosspost — roda no GitHub Actions (ou local).
Fluxo por execução:
  1. atualiza o ledger (detecta vídeo novo no YouTube, preserva status)
  2. monta a lista do que falta postar (por rede, sem duplicar)
  3. posta os N do topo via PostProxy (hospeda no GitHub Releases antes)
  4. marca no ledger + limpa o asset + avisa no Telegram

Segurança (medo de duplicar):
  - TikTok/Instagram: só postam vídeo NOVO (published >= START_DATE). Backlog velho NÃO,
    porque essas redes já têm quase tudo (236/215 mapeados).
  - Facebook: pode postar o backlog provado (você postou pouco lá), do maior view p/ o menor.
Config por variável de ambiente (secrets no Actions).
"""
import os, sys, json, re, subprocess, urllib.request, urllib.error, urllib.parse, datetime, time

DRY        = os.environ.get("DRY_RUN", "1") == "1"
PP_KEY     = os.environ.get("POSTPROXY_KEY", "")
YT_KEY     = os.environ.get("YOUTUBE_API_KEY", "")
TG_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.environ.get("TELEGRAM_CHAT_ID", "")
REPO       = os.environ.get("MEDIA_REPO", "murilolacerdamoraess-crypto/mano-preguica-media")
START_DATE = os.environ.get("START_DATE", "2026-07-15")   # TikTok/IG só postam >= isto
MAX_RUN    = int(os.environ.get("MAX_PER_RUN", "1"))
MONTH_CAP  = int(os.environ.get("MONTH_CAP", "9"))   # teto p/ não estourar os 10/mês do PostProxy grátis
MODE       = os.environ.get("MODE", "post")          # "post" (nuvem) ou "prehost" (Mac: baixa+hospeda)
PREHOST_N  = int(os.environ.get("PREHOST_N", "5"))
FB_PAGE    = "606193705900753"
PROFILES   = {"tiktok": "knUlkm", "instagram": "oJUZQL", "facebook": "L2ULXV"}
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

# ---------- YouTube: atualizar ledger com vídeos novos ----------
def yt_get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA)))
def dur2s(du):
    m = re.match(r'^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', du)
    if not m: return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups()); return dd*86400 + h*3600 + mi*60 + s

def update_ledger():
    led = json.load(open(LEDGER))
    PL = "UURKX-GV-beUtYs2IQD-f6jg"
    ids, token = [], ""
    while True:
        u = f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=50&playlistId={PL}&key={YT_KEY}" + (f"&pageToken={token}" if token else "")
        d = yt_get(u); ids += [it["contentDetails"]["videoId"] for it in d["items"]]; token = d.get("nextPageToken")
        if not token: break
    new = 0
    for i in range(0, len(ids), 50):
        d = yt_get(f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails,snippet,statistics&id={','.join(ids[i:i+50])}&key={YT_KEY}")
        for it in d["items"]:
            vid = it["id"]; t = dur2s(it["contentDetails"]["duration"])
            meta = {"title": it["snippet"]["title"], "seconds": t,
                    "type": "vertical" if 0 < t <= 185 else ("long" if t > 185 else "unknown"),
                    "published": it["snippet"]["publishedAt"][:10],
                    "views": int(it["statistics"].get("viewCount", 0))}
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

# ---------- decidir o que postar ----------
def fits(net, v):
    if net == "tiktok":    return v["type"] == "vertical" or (v["type"] == "long" and v["seconds"] <= 600)
    if net == "instagram": return v["type"] == "vertical"           # IG = vertical (Reel)
    if net == "facebook":  return True
    return False

def build_todo(led):
    todo = []
    vids = led["videos"]
    # 1) vídeos NOVOS -> todas as redes que couberem
    for vid, v in vids.items():
        if not v["postable"] or v["published"] < START_DATE: continue
        for net in ("tiktok", "instagram", "facebook"):
            if fits(net, v) and not v["posted"][net]["done"]:
                todo.append((0, -v["views"], vid, net))   # prio 0 = novo
    # 2) backlog do FACEBOOK (dup-safe) por views
    for vid, v in sorted(vids.items(), key=lambda kv: -kv[1]["views"]):
        if not v["postable"] or v["published"] >= START_DATE: continue
        if fits("facebook", v) and not v["posted"]["facebook"]["done"]:
            todo.append((1, -v["views"], vid, "facebook"))  # prio 1 = backlog FB
    todo.sort()
    return todo

# ---------- hospedar / postar / limpar ----------
def host(vid, title):
    f = os.path.join(TMP, vid + ".mp4")
    subprocess.run(["yt-dlp", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                    "-o", f, f"https://www.youtube.com/watch?v={vid}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["gh", "release", "create", vid, "--repo", REPO, "--title", title[:90],
                    "--notes", "efemero", f], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["gh", "release", "upload", vid, "--repo", REPO, f, "--clobber"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"https://github.com/{REPO}/releases/download/{vid}/{vid}.mp4"

def hosted_url(vid):
    """Retorna a URL pública se o vídeo JÁ está hospedado no GitHub Releases, senão None."""
    url = f"https://github.com/{REPO}/releases/download/{vid}/{vid}.mp4"
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=25)
        return url
    except urllib.error.HTTPError as e:
        return url if e.code in (200, 302, 403) else None   # 403 = asset existe mas exige range; ok
    except Exception:
        return None

def cleanup(vid):
    subprocess.run(["gh", "release", "delete", vid, "--repo", REPO, "--yes", "--cleanup-tag"],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try: os.remove(os.path.join(TMP, vid + ".mp4"))
    except OSError: pass

def caption(v):
    return f"{v['title']}\n\n#Subnautica #games #gameplay #jogos"

def platforms_block(net):
    if net == "facebook":  return {"facebook": {"format": "post", "page_id": FB_PAGE}}
    if net == "tiktok":    return {"tiktok": {"privacy_status": "PUBLIC_TO_EVERYONE"}}
    if net == "instagram": return {"instagram": {"format": "reel"}}

def pp_post(net, url, text):
    body = json.dumps({"post": {"body": text}, "profiles": [PROFILES[net]],
                       "media": [url], "platforms": platforms_block(net)}).encode()
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
    return True  # segue mesmo assim; PostProxy costuma ter a cópia

def pp_link(pid, net, tries=5):
    """Pega o link publicado; converte FB reel->watch (que funciona p/ vídeo longo)."""
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
def main():
    led, new = update_ledger()
    todo = build_todo(led)

    if MODE == "prehost":   # roda no Mac (IP residencial): baixa+hospeda o próximo lote
        log(f"[PREHOST] novos: {new} | fila: {len(todo)} | hospedar até {PREHOST_N} não-hospedados")
        seen, hosted = set(), 0
        for prio, negv, vid, net in todo:
            if hosted >= PREHOST_N: break
            if vid in seen: continue
            seen.add(vid)
            if hosted_url(vid): log(f"   já hospedado: {vid}"); continue
            try:
                host(vid, led["videos"][vid]["title"])
                log(f"   ✔ hospedado: {vid} | {led['videos'][vid]['title'][:45]}"); hosted += 1
            except Exception as e:
                log(f"   ✗ erro host {vid}: {e}")
        log(f"prehost feito: {hosted} vídeo(s) na prateleira.")
        return

    month = datetime.date.today().strftime("%Y-%m")
    posted_month = sum(1 for v in led["videos"].values() for n in PROFILES
                       if v["posted"][n]["done"] and (v["posted"][n]["date"] or "").startswith(month))
    room = max(0, MONTH_CAP - posted_month)
    limit = min(MAX_RUN, room)
    log(f"[{'DRY-RUN' if DRY else 'LIVE'}] novos: {new} | fila: {len(todo)} | postados este mês: {posted_month}/{MONTH_CAP} | vou postar até {limit}")
    for prio, negv, vid, net in todo[:12]:
        tag = "NOVO" if prio == 0 else "backlog-FB"
        log(f"   [{tag}] {net:9} | {-negv:>7} views | {led['videos'][vid]['title'][:48]}")
    if DRY:
        log("modo seco: nada foi postado."); return
    if limit <= 0:
        log("teto mensal atingido; nada a postar."); return
    done = 0
    for prio, negv, vid, net in todo:
        if done >= limit: break
        v = led["videos"][vid]
        url = hosted_url(vid)
        if not url:
            log(f"pular {vid}: ainda não hospedado (rodar prehost no Mac)"); continue
        try:
            r = pp_post(net, url, caption(v))
            pid = r.get("id")
            pp_wait_ingest(pid)
            cleanup(vid)
            link = pp_link(pid, net) or ""
            v["posted"][net] = {"done": True, "date": datetime.date.today().isoformat(), "post_id": pid, "link": link}
            json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
            telegram(f"✅ Postei no {net}: {v['title'][:60]}\n{link}".strip())
            log(f"OK {net} <- {vid} (post {pid}) {link}")
            done += 1
        except Exception as e:
            log(f"ERRO {net} {vid}: {e}"); telegram(f"⚠️ Falha ao postar {v['title'][:40]} no {net}: {e}")
    log(f"feito: {done} post(s) nesta execução.")

if __name__ == "__main__":
    main()
