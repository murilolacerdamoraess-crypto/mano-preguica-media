#!/usr/bin/env python3
# Uso: match_network.py <arquivo_posts> <rede>  -> atualiza ledger.json posted[rede]
import json,re,unicodedata,sys,datetime
POSTS,NET=sys.argv[1],sys.argv[2]
raw=open(POSTS).read().strip()
try: s=json.loads(raw)
except: s=raw.replace('\\t','\t').replace('\\n','\n').strip('"')
pairs=[l.split("\t",1) for l in s.split("\n") if "\t" in l]
def base(t):
    t=''.join(c for c in unicodedata.normalize('NFD',t.upper()) if unicodedata.category(c)!='Mn')
    t=re.sub(r'#\w+',' ',t); t=re.sub(r'CRIADO POR MANO PREGUICA.*$',' ',t)
    t=re.sub(r'(VIDEO|ACABOU DE SAIR|LINK NA BIO|LINK NO|ASSISTA|COMPLETO NO).*$',' ',t)
    return re.sub(r'[^A-Z0-9 ]',' ',t)
STOP={"NAO","QUE","COM","UMA","MEU","MINHA","VOCE","ESSE","ESSA","DOS","DAS","PRA","POR","MAIS","SEU","SUA","VAI","FOI","NUM","ATE","SER","SE","EU","UM","OU"}
def words(t): return [w for w in base(t).split() if len(w)>=2 and w not in STOP]
def sstr(t): return re.sub(r'\s+',' ',base(t)).strip()
cw=[(v,set(words(c))) for v,c in pairs]; cs=[(v,sstr(c)) for v,c in pairs]
def match(title):
    yt=set(words(title)); ys=sstr(title)
    if len(ys)>=12:
        for v,x in cs:
            if ys in x: return v
    if len(yt)<2: return "SHORT_UNCERTAIN"
    best=0;bid=None
    for v,x in cw:
        if not x:continue
        o=len(yt&x)/len(yt)
        if o>best:best=o;bid=v
    return bid if best>=0.6 else None
led=json.load(open("ledger.json")); m=0;u=0
for vid,v in led["videos"].items():
    r=match(v["title"])
    if r=="SHORT_UNCERTAIN": v["posted"][NET]={"done":True,"date":None,"post_id":"short-uncertain"};u+=1;m+=1
    else:
        d=bool(r); v["posted"][NET]={"done":d,"date":None,"post_id":r}
        if d:m+=1
led["updated"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
json.dump(led,open("ledger.json","w"),ensure_ascii=False,indent=1)
V=led["videos"].values()
cand=[v for v in V if v["postable"] and not v["posted"][NET]["done"]]
print(f"[{NET}] posts lidos: {len(pairs)} | casados como JA postados: {m} (curto-conservador {u}) | POSTAVEIS faltando: {len(cand)}")
