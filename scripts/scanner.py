#!/usr/bin/env python3
"""
SCANNER DA OPERAÇÃO -> Telegram.
Responde a pergunta do Murilo: "estou coberto até quando? quando preciso me preocupar?"

Para CADA frente calcula a AUTONOMIA (até que dia tem coisa agendada) e destaca
a que vai secar primeiro. Não é previsão: lê o que está de fato agendado.

Fontes:
  - schedule.json    (TikTok/FB agendados de verdade — PostProxy/Metricool)  [vivo]
  - tiktok_plan.json (fila curada pronta pra agendar)                        [vivo]
  - ledger.json      (backlog do Facebook)                                   [vivo]
  - operacao.json    (YouTube vídeos + enquetes — snapshot do Studio)        [atualizado quando escaneio]
"""
import os, sys, json, datetime, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER   # noqa: E402
RAIZ  = os.path.dirname(LEDGER)
SCHED = os.path.join(RAIZ, "schedule.json")
PLAN  = os.path.join(HERE, "tiktok_plan.json")
OPER  = os.path.join(HERE, "operacao.json")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
BRT = datetime.timezone(datetime.timedelta(hours=-3))
ALERTA_DIAS = 7   # abaixo disso, vira alerta

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def brt(iso_utc):
    """'2026-07-22T00:00:00Z' (UTC) -> datetime no fuso BRT. 21h BRT NÃO pode virar o dia seguinte."""
    try: return datetime.datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(BRT)
    except Exception: return None

def dias(ate, hoje):
    return (ate - hoje).days

def bloco(nome, ate, hoje, detalhe, extra=""):
    """Monta a linha de uma frente com ícone conforme a folga."""
    if ate is None:
        return f"❌ *{nome}*\n   nada agendado{(' · ' + extra) if extra else ''}"
    d = dias(ate, hoje)
    ic = "✅" if d >= ALERTA_DIAS else ("⚠️" if d >= 3 else "🔴")
    txt = f"{ic} *{nome}*\n   {detalhe} · coberto até *{ate.strftime('%d/%m')}* ({d}d)"
    if extra: txt += f"\n   {extra}"
    return txt

def main():
    hoje = datetime.datetime.now(BRT).date()
    oper = load(OPER, {})
    sched = load(SCHED, [])
    plan = load(PLAN, [])
    led = load(LEDGER, {"videos": {}})
    frentes, riscos = [], []

    # --- YouTube vídeos + Enquetes (snapshot do Studio) ---
    for chave, nome in (("youtube_videos", "YouTube (vídeos)"), ("enquetes", "Enquetes")):
        bl = oper.get(chave, {})
        fut = sorted(d["data"] for d in bl.get("agendados", []) if d["data"] >= str(hoje))
        ate = datetime.date.fromisoformat(fut[-1]) if fut else None
        idade = (hoje - datetime.date.fromisoformat(bl["atualizado_em"])).days if bl.get("atualizado_em") else 99
        extra = f"⏳ dado de {idade}d atrás (pedir re-scan)" if idade > 10 else ""
        frentes.append(bloco(nome, ate, hoje, f"{len(fut)} agendados", extra))
        if ate: riscos.append((ate, nome))

    # --- TikTok (agendado de verdade) + fila pronta ---
    agora = datetime.datetime.now(BRT)
    tt = sorted(d.date() for d in (brt(s["scheduled_at"]) for s in sched
                if s.get("net") == "tiktok") if d and d > agora)   # só o que ainda NÃO foi ao ar
    ate_tt = tt[-1] if tt else None
    fila = len([p for p in plan if not p.get("scheduled")])
    frentes.append(bloco("TikTok", ate_tt, hoje, f"{len(tt)} agendados",
                         f"📦 +{fila} na fila curada (pronta pra agendar)"))
    if ate_tt: riscos.append((ate_tt, "TikTok"))

    # --- Facebook (automático + backlog) ---
    fb_back = sum(1 for v in led["videos"].values()
                  if v.get("postable") and not v["posted"]["facebook"]["done"])
    frentes.append(f"✅ *Facebook*\n   automático seg/qua/sex · 📦 {fb_back} no backlog")
    frentes.append("🔕 *Instagram* — desligado (não paga)")

    # --- o que seca primeiro ---
    riscos.sort()
    if riscos:
        d1, n1 = riscos[0]
        dd = dias(d1, hoje)
        alerta = (f"🎯 *Primeira a secar: {n1}* em {d1.strftime('%d/%m')} ({dd}d)\n"
                  f"   {'Tá tranquilo, te aviso quando chegar perto.' if dd >= ALERTA_DIAS else 'Bora reabastecer essa.'}")
    else:
        alerta = "🎯 Nada agendado em lugar nenhum — precisa reabastecer."

    # --- próximos concretos (o que vai ao ar, em ordem) ---
    prox = []
    for chave, tag in (("youtube_videos", "YouTube"), ("enquetes", "Enquete")):
        for it in oper.get(chave, {}).get("agendados", []):
            if it["data"] >= str(hoje): prox.append((it["data"], tag, it["titulo"]))
    for s in sched:
        d = brt(s["scheduled_at"])
        if d and d > agora:
            prox.append((d.date().isoformat(), s.get("net", "?").title(), s.get("title", "?")))
    prox.sort()
    if prox:
        linhas = []
        for d, tag, t in prox[:4]:
            dt = datetime.date.fromisoformat(d)
            quando = "hoje" if dt == hoje else ("amanhã" if (dt - hoje).days == 1 else dt.strftime("%d/%m"))
            linhas.append(f"   *{quando}* · {tag} — {t[:44]}")
        bloco_prox = "🗓️ *Próximos*\n" + "\n".join(linhas)
    else:
        bloco_prox = ""

    msg = (f"📡 *Scanner da Operação* — {hoje.strftime('%d/%m')}\n\n"
           + "\n\n".join(frentes) + "\n\n" + (bloco_prox + "\n\n" if bloco_prox else "") + alerta)

    if TG_TOKEN and TG_CHAT:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        print("scanner enviado.")
    else:
        print("(sem TG creds) preview:\n" + msg)

if __name__ == "__main__":
    main()
