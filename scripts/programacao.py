#!/usr/bin/env python3
"""
Programação do crosspost -> manda no Telegram (RotinaOS) o que está pela frente.
Ex.:  "Hoje 21h - VIDEO X no TikTok | Seg 21h - VIDEO Y no Facebook"

Fontes:
  - schedule.json : posts AGENDADOS explicitamente (one-off, com horário exato) -> mostrados no horário
  - ledger.json + build_todo : previsão do automático (cron Seg/Qua/Sex 21h posta o topo da fila)

Roda no Mac (RotinaOS). Não posta nada, só informa. Sem rede além do Telegram.
"""
import os, sys, json, datetime, urllib.parse, urllib.request

HERE   = os.path.dirname(os.path.abspath(__file__))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
BRT = datetime.timezone(datetime.timedelta(hours=-3))   # Brasil não tem mais horário de verão
CRON_DAYS = {0, 2, 4}   # Seg/Qua/Sex (weekday: Seg=0)
CRON_HOUR = 21          # 21h BRT (= o cron 17 0 * * 2,4,6 UTC)
N_AHEAD = 5             # quantos posts adiante mostrar
NET_PT = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram"}
DIA_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# build_todo + resolvedor do ledger moram no crosspost.py. Importa sem rodar main.
sys.path.insert(0, HERE)
from crosspost import build_todo, LEDGER, PROFILES   # noqa: E402
SCHED = os.path.join(os.path.dirname(LEDGER), "schedule.json")
PP_LIMIT  = 10   # PostProxy grátis: 10 posts/mês
MET_LIMIT = 20   # Metricool grátis: 20 agendados/mês (reserva, ainda não usamos p/ postar)

def cota_postproxy(led):
    """Quantos posts já foram pela PostProxy este mês (1 post = 1 vídeo x 1 rede)."""
    mes = datetime.datetime.now(BRT).strftime("%Y-%m")
    return sum(1 for v in led["videos"].values() for n in PROFILES
               if v["posted"][n]["done"] and (v["posted"][n]["date"] or "").startswith(mes))

def carrega(path, default):
    try: return json.load(open(path))
    except Exception: return default

def rotulo_dia(dt, hoje):
    d = (dt.date() - hoje).days
    if d == 0: return "Hoje"
    if d == 1: return "Amanhã"
    return DIA_PT[dt.weekday()]

def proximos_slots(agora, n):
    """Próximos n horários de cron (Seg/Qua/Sex 21h BRT) a partir de agora."""
    slots, d = [], agora.date()
    # se hoje é dia de cron e ainda não passou das 21h, hoje conta
    for i in range(0, 21):
        dia = d + datetime.timedelta(days=i)
        if dia.weekday() in CRON_DAYS:
            slot = datetime.datetime(dia.year, dia.month, dia.day, CRON_HOUR, 0, tzinfo=BRT)
            if slot >= agora - datetime.timedelta(minutes=30):
                slots.append(slot)
        if len(slots) >= n: break
    return slots

def main():
    agora = datetime.datetime.now(BRT)
    hoje = agora.date()
    led = carrega(LEDGER, {"videos": {}})
    sched = carrega(SCHED, [])
    itens = []   # (datetime_brt, vid, net, title, tipo)

    # 1) agendados explícitos, ainda no futuro
    vids_agendados = set()
    for s in sched:
        try:
            dt = datetime.datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00")).astimezone(BRT)
        except Exception:
            continue
        if dt >= agora - datetime.timedelta(hours=1):
            itens.append((dt, s["vid"], s["net"], s.get("title", "?"), "agendado"))
            vids_agendados.add((s["vid"], s["net"]))

    # 2) previsão do automático: topo da fila -> próximos slots de cron
    todo = [t for t in build_todo(led) if (t[2], t[3]) not in vids_agendados]
    slots = proximos_slots(agora, N_AHEAD)
    for slot, (prio, negv, vid, net) in zip(slots, todo):
        title = led["videos"].get(vid, {}).get("title", vid)
        itens.append((slot, vid, net, title, "auto"))

    itens.sort(key=lambda x: x[0])
    itens = itens[:N_AHEAD]

    # cota do mês
    pp_usado = cota_postproxy(led)
    pp_rest = max(0, PP_LIMIT - pp_usado)
    bloco_cota = ("📊 *Cota do mês*\n"
                  f"   PostProxy: *{pp_rest}* restantes ({pp_usado}/{PP_LIMIT})\n"
                  f"   Metricool: *{MET_LIMIT}* livres (reserva)")

    if not itens:
        corpo = "Nada na fila agora. Sobe vídeo novo no YouTube que eu reabasteço. 👊"
    else:
        blocos = []
        for dt, vid, net, title, tipo in itens:
            tag = "  ·  agendado" if tipo == "agendado" else ""
            blocos.append(f"*{rotulo_dia(dt, hoje)} {dt.hour}h* → {NET_PT.get(net, net)}{tag}\n{title[:70]}")
        corpo = "\n\n".join(blocos)

    msg = f"🗓️ *Programação Mano Preguiça*\n\n{corpo}\n\n{bloco_cota}\n\n_Trocar ou tirar algo? é só falar._"

    if TG_TOKEN and TG_CHAT:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        print("programação enviada.")
    else:
        print("(sem TG creds) preview:\n" + msg)

if __name__ == "__main__":
    main()
