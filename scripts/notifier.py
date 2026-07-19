#!/usr/bin/env python3
"""
Vigia de publicação -> avisa no Telegram (BotPreguiça) quando um post AGENDADO vai ao ar.
Fecha o furo: agendados (PostProxy/Metricool) publicam no servidor, sem o robô rodando -> ninguém avisava.

Lê schedule.json (agendados, com scheduled_at). Quando a hora passa, manda "foi ao ar" UMA vez.
Estado de "já avisei" fica LOCAL (~/.canal/announced.json), pra não sujar o git.
Roda no Mac (launchd, a cada 2h).
"""
import os, sys, json, datetime, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER   # noqa: E402  (só p/ achar a raiz do repo)
SCHED = os.path.join(os.path.dirname(LEDGER), "schedule.json")
STATE = os.path.expanduser("~/.canal/announced.json")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
NET_PT = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram"}

def load(path, default):
    try: return json.load(open(path))
    except Exception: return default

def telegram(msg):
    if not (TG_TOKEN and TG_CHAT):
        print("(sem TG creds) " + msg); return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)

def main():
    sched = load(SCHED, [])
    announced = set(load(STATE, []))
    agora = datetime.datetime.now(datetime.timezone.utc)
    novos = 0
    for s in sched:
        key = f"{s.get('vid')}|{s.get('net')}|{s.get('scheduled_at')}"
        if key in announced: continue
        try:
            dt = datetime.datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if dt <= agora:
            net = s.get("net", "?")
            telegram(f"🔔 Foi ao ar: {s.get('title', '?')[:70]}\n→ {NET_PT.get(net, net)}")
            announced.add(key); novos += 1
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(sorted(announced), open(STATE, "w"), ensure_ascii=False, indent=1)
    print(f"avisos enviados: {novos}")

if __name__ == "__main__":
    main()
