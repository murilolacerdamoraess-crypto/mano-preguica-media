#!/usr/bin/env python3
# Constroi/atualiza o ledger de crosspost: todos os videos do YT + status por rede.
# Preserva status existente e adiciona videos novos. Nao apaga nada.
import os, re, json, sys, urllib.request, datetime
KEY=open(os.path.expanduser("~/.rotina-os/rotina-os.env")).read()
KEY=re.search(r'YOUTUBE_API_KEY=["\']?([^"\'\n]+)', KEY).group(1)
PL="UURKX-GV-beUtYs2IQD-f6jg"
LEDGER=os.path.expanduser("~/canal_agente/crosspost/ledger.json")

def get(u): return json.load(urllib.request.urlopen(u))
def dur2s(du):
    m=re.match(r'^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$',du)
    if not m: return 0
    dd,h,mi,s=(int(x or 0) for x in m.groups()); return dd*86400+h*3600+mi*60+s

# 1) puxa todos os uploads
ids=[]; token=""
while True:
    u=f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=50&playlistId={PL}&key={KEY}"+(f"&pageToken={token}" if token else "")
    d=get(u); ids+=[it["contentDetails"]["videoId"] for it in d["items"]]; token=d.get("nextPageToken")
    if not token: break
meta={}
for i in range(0,len(ids),50):
    d=get(f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails,snippet,statistics&id={','.join(ids[i:i+50])}&key={KEY}")
    for it in d["items"]:
        t=dur2s(it["contentDetails"]["duration"])
        meta[it["id"]]={"title":it["snippet"]["title"],"seconds":t,
            "type":"vertical" if 0<t<=185 else ("long" if t>185 else "unknown"),
            "published":it["snippet"]["publishedAt"][:10],
            "views":int(it["statistics"].get("viewCount",0))}

# 2) posts JA no TikTok (capturados 2026-07-15). Titulo p/ casar.
TIKTOK_DONE=[
"PORQUE NAO TEM NINGUEM VIVO EM SUBNAUTICA","QUE CRIATURA FAZ ESSE BARULHO NA VOID",
"O REAPER VIROU PARTE DE UM PLANO MALIGNO","E SE O SENNA TIVESSE UM FILME DE LEGO",
"O MELHOR MOD DE SUBNAUTICA VOLTOU","COLOCARAM O REAPER LEVIATHAN NO SUBNAUTICA 2",
"ESSE E O MELHOR MOD DE SUBNAUTICA","PASSEI O LIMITE DO MAPA DE SUBNAUTICA 2",
"EXISTE UM NOVO LEVIATHAN CHEGANDO NO SUBNAUTICA","COMO E A PRIMEIRA MEIA HORA DE SUBNAUTICA 2",
"SUBNAUTICA 2 REVELOU UM SEGREDO DE 12 ANOS","JA ASSISTIRAM OS PRIMEIROS 30 MINUTOS",
"VOCE CONHECE O NOME DE CADA REAPER NO SUBNAUTICA","ESSE E O MONSTRO DA VOID DE SUBNAUTICA 2",
"NINGUEM PERCEBEU ISSO EM SUBNAUTICA 2","SUBNAUTICA DE GRACA",
]
def norm(s):
    s=s.upper()
    s=re.sub(r'#\w+','',s)
    s=re.sub(r'[^A-Z0-9 ]',' ',s)  # tira acento? nao, mas alpha basico
    import unicodedata
    s=''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn')
    return re.sub(r'\s+',' ',s).strip()
tt_norm=[norm(x) for x in TIKTOK_DONE]
def on_tiktok(title):
    n=norm(title)
    for t in tt_norm:
        key=n[:22]
        if key and (key in t or t[:22] in n): return True
    return False

# 3) carrega ledger existente (preserva status) e faz merge
led={"videos":{}}
if os.path.exists(LEDGER):
    led=json.load(open(LEDGER))
new_count=0
for vid,m in meta.items():
    if vid not in led["videos"]:
        new_count+=1
        led["videos"][vid]={**m,"posted":{
            "tiktok":{"done":on_tiktok(m["title"]),"date":None,"post_id":None},
            "facebook":{"done":False,"date":None,"post_id":None},
            "instagram":{"done":False,"date":None,"post_id":None},
        }}
    else:
        led["videos"][vid].update({k:m[k] for k in ("title","seconds","type","published","views")})
led["updated"]="pending-stamp"
json.dump(led,open(LEDGER,"w"),ensure_ascii=False,indent=1)

# resumo
vids=led["videos"].values()
vert=[v for v in vids if v["type"]=="vertical"]
lon=[v for v in vids if v["type"]=="long"]
tt=sum(1 for v in vids if v["posted"]["tiktok"]["done"])
print(f"LEDGER: {len(led['videos'])} videos ({len(vert)} verticais, {len(lon)} longos) | novos nesta rodada: {new_count}")
print(f"Marcados como JA no TikTok: {tt}")
print(f"Verticais AINDA fora do TikTok (candidatos): {sum(1 for v in vert if not v['posted']['tiktok']['done'])}")
print(f"Arquivo: {LEDGER}")
