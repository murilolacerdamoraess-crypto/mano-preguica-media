#!/usr/bin/env python3
"""
Planeja a fila curada de repost (TikTok e Instagram) com as regras do Murilo:
  - dentro do nicho (exclui Arcane/LoL/animes/séries/lobisomem/futebol/hambúrguer/arcade/etc)
  - >= MIN_VIEWS (não queima slot com vídeo fraco)
  - NÃO postado NAQUELA rede nos últimos 2 meses (data recuperada decodificando o post_id)
  - ordem MAIS ANTIGO -> MAIS NOVO (varredura única; os "novos" envelhecem sozinhos)
Regras por rede:
  - tiktok    : vertical de 1min+ (só isso monetiza). 3x/semana (Ter/Qui/Sáb 21h).
  - instagram : vertical de qualquer duração (não monetiza; é presença). 1x/semana (Dom 21h).
Uso:
  python tiktok_plan.py                 -> planeja TikTok
  PLAN_NET=instagram python tiktok_plan.py
  python tiktok_plan.py host 5          -> hospeda os N primeiros do plano
"""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER, host, hosted_url   # noqa: E402
BRT = datetime.timezone(datetime.timedelta(hours=-3))
NET = os.environ.get("PLAN_NET", "tiktok")
CFG = {
    "tiktok":    {"min_secs": 60, "days": {1, 3, 5}, "arq": "tiktok_plan.json"},  # Ter/Qui/Sáb
    "instagram": {"min_secs": 0,  "days": {6},       "arq": "ig_plan.json"},      # Domingo
}[NET]
PLAN = os.path.join(HERE, CFG["arq"])
POST_HOUR = 21
MIN_VIEWS = 1000
BLACK = ["arcane","league","jinx","zaun","riot"," tft","anime","série","serie","series","novela",
         "vikings","valhalla","marvel","netflix","filmes","lobisomem","werewolf","uefa","champions",
         "futebol","gta","the last of us","fortnite","valorant","hamburgueria","arcade","orlando"]
IG_AL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

def off_nicho(t):
    tl = t.lower(); return any(k in tl for k in BLACK)

def tiktok_date(pid):
    """ID de vídeo do TikTok codifica o timestamp: unix = id >> 32."""
    try: return datetime.datetime.utcfromtimestamp(int(pid) >> 32).date()
    except Exception: return None

def instagram_date(sc):
    """Shortcode do IG -> media id (base64) -> timestamp: ms = (id >> 23) + epoch do Instagram."""
    try:
        mid = 0
        for c in sc: mid = mid * 64 + IG_AL.index(c)
        return datetime.datetime.utcfromtimestamp(((mid >> 23) + 1314220021721) / 1000).date()
    except Exception: return None

def parse_date(s):
    try: return datetime.date.fromisoformat(str(s)[:10])
    except Exception: return None

def ultima_vez(p):
    """Quando esse vídeo foi pra essa rede pela última vez (None = não dá pra saber)."""
    pid = p.get("post_id", "") or ""
    dec = instagram_date(pid) if NET == "instagram" else tiktok_date(pid)
    return dec or parse_date(p.get("date"))

def eligiveis(led):
    hoje = datetime.datetime.now(BRT).date()
    cutoff = hoje - datetime.timedelta(days=60)
    out = []
    for vid, d in led["videos"].items():
        if d["type"] != "vertical" or not d.get("postable"): continue
        if d["seconds"] < CFG["min_secs"]: continue
        if d["views"] < MIN_VIEWS: continue
        if off_nicho(d["title"]): continue
        p = d["posted"][NET]
        if p["done"]:
            dt = ultima_vez(p)
            if dt is None: continue        # postado mas sem data -> não arrisca duplicar
            if dt >= cutoff: continue      # foi/vai nos últimos 2 meses -> ainda não reposta
        out.append((d["published"][:10], d["views"], vid, d["title"], d["seconds"]))
    out.sort()   # MAIS ANTIGO primeiro
    return out

def slots(n, comeca):
    res, dia = [], comeca
    while len(res) < n:
        if dia.weekday() in CFG["days"]:
            res.append(datetime.datetime(dia.year, dia.month, dia.day, POST_HOUR, 0, tzinfo=BRT))
        dia += datetime.timedelta(days=1)
    return res

def build_plan():
    led = json.load(open(LEDGER))
    elig = eligiveis(led)
    amanha = datetime.datetime.now(BRT).date() + datetime.timedelta(days=1)
    plan = []
    for (pub, views, vid, title, secs), s in zip(elig, slots(len(elig), amanha)):
        plan.append({"vid": vid, "title": title, "seconds": secs, "views": views, "publicado": pub,
                     "slot_brt": s.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                     "slot_utc": s.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "scheduled": False})
    json.dump(plan, open(PLAN, "w"), ensure_ascii=False, indent=1)
    return plan

def main():
    plan = build_plan()
    print(f"PLANO [{NET}]: {len(plan)} vídeos. Salvo em {PLAN}")
    if len(sys.argv) >= 3 and sys.argv[1] == "host":
        n = int(sys.argv[2]); feitos = 0
        led = json.load(open(LEDGER))
        for item in plan:
            if feitos >= n: break
            vid = item["vid"]
            if hosted_url(vid):
                print(f"  já hospedado: {vid} | {item['title'][:40]}"); feitos += 1; continue
            try:
                host(vid, led["videos"][vid]["title"]); feitos += 1
                print(f"  ✔ hospedado: {vid} | {item['title'][:40]}")
            except Exception as e:
                print(f"  ✗ erro {vid}: {e}")
    else:
        for p in plan[:6]:
            print(f"  {p['slot_brt'][:10]} | {p['publicado']} | {p['views']:>6}v {p['seconds']:>3}s | {p['vid']} | {p['title'][:38]}")

if __name__ == "__main__":
    main()
