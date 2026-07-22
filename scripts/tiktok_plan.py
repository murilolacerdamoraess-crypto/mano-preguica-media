#!/usr/bin/env python3
"""
Planeja a fila curada do TikTok (via Metricool) com as regras do Murilo:
  - vertical de 1min+ (o que monetiza)
  - dentro do nicho (exclui Arcane/LoL/animes/séries/lobisomem/futebol/etc)
  - NÃO postado no TikTok nos últimos 2 meses (data recuperada decodificando o post_id do TikTok)
Gera scripts/tiktok_plan.json (vid, title, seconds, views, slot BRT+UTC), ordenado por views.
Slots: Ter/Qui/Sáb 21h BRT (3/semana), começando amanhã.
Uso: `python tiktok_plan.py`  (só planeja)  |  `python tiktok_plan.py host N` (hospeda os N primeiros ainda-não-agendados)
"""
import os, sys, json, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER, REPO, host, hosted_url   # noqa: E402
PLAN = os.path.join(HERE, "tiktok_plan.json")
BRT = datetime.timezone(datetime.timedelta(hours=-3))
POST_DAYS = {1, 3, 5}   # Ter/Qui/Sáb (weekday: Seg=0)
POST_HOUR = 21
BLACK = ["arcane","league","jinx","zaun","riot"," tft","anime","série","serie","series","novela",
         "vikings","valhalla","marvel","netflix","filmes","lobisomem","werewolf","uefa","champions",
         "futebol","gta","the last of us","fortnite","valorant",
         # fora do nicho survival/terror/mistério (decisão Murilo 21/07)
         "hamburgueria","arcade","orlando"]
MIN_VIEWS = 1000   # corta os muito fracos (não vale queimar slot)

def off_nicho(t):
    tl = t.lower(); return any(k in tl for k in BLACK)

def tiktok_date(pid):
    """ID de vídeo do TikTok codifica o timestamp: unix = id >> 32."""
    try: return datetime.datetime.utcfromtimestamp(int(pid) >> 32).date()
    except Exception: return None

def parse_date(s):
    try: return datetime.date.fromisoformat(str(s)[:10])
    except Exception: return None

def eligiveis(led):
    hoje = datetime.datetime.now(BRT).date()
    cutoff = hoje - datetime.timedelta(days=60)
    out = []
    for vid, d in led["videos"].items():
        if d["type"] != "vertical" or not d.get("postable") or d["seconds"] < 60: continue
        if d["views"] < MIN_VIEWS: continue
        if off_nicho(d["title"]): continue
        p = d["posted"]["tiktok"]
        if p["done"]:
            # data do último post no TikTok: decodifica o id do TikTok OU usa o campo date
            # (posts nossos ficam como "metricool-<id>"/PostProxy, que não decodificam).
            dt = tiktok_date(p.get("post_id", "")) or parse_date(p.get("date"))
            if dt is None: continue          # marcado como postado mas sem data -> NÃO arrisca duplicar
            if dt >= cutoff: continue        # postado (ou agendado) nos últimos 2 meses -> ainda não reposta
        out.append((d["published"][:10], d["views"], vid, d["title"], d["seconds"]))
    out.sort()   # por DATA DE PUBLICAÇÃO ascendente (mais antigos primeiro) — varredura única, envelhece os novos
    return out

def slots(n, comeca):
    res, dia = [], comeca
    while len(res) < n:
        if dia.weekday() in POST_DAYS:
            res.append(datetime.datetime(dia.year, dia.month, dia.day, POST_HOUR, 0, tzinfo=BRT))
        dia += datetime.timedelta(days=1)
    return res

def build_plan():
    led = json.load(open(LEDGER))
    elig = eligiveis(led)
    amanha = datetime.datetime.now(BRT).date() + datetime.timedelta(days=1)
    sl = slots(len(elig), amanha)
    plan = []
    for (pub, views, vid, title, secs), s in zip(elig, sl):
        plan.append({"vid": vid, "title": title, "seconds": secs, "views": views, "publicado": pub,
                     "slot_brt": s.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                     "slot_utc": s.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "scheduled": False})
    json.dump(plan, open(PLAN, "w"), ensure_ascii=False, indent=1)
    return plan

def main():
    plan = build_plan()
    print(f"PLANO: {len(plan)} vídeos, Ter/Qui/Sáb 21h. Salvo em {PLAN}")
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
        print("primeiros 6:")
        for p in plan[:6]:
            print(f"  {p['slot_brt'][:10]} 21h | {p['views']:>7}v {p['seconds']:>3}s | {p['vid']} | {p['title'][:40]}")

if __name__ == "__main__":
    main()
