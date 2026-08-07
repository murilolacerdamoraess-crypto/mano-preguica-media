#!/usr/bin/env python3
"""
SENTINELA — rede de segurança ANTES de publicar (roda ~18h BRT, cron próprio).

Por que existe: as travas (notícia velha, fora de nicho) impedem AGENDAR conteúdo ruim,
mas NÃO matam o que já está na fila do PostProxy de antes da trava existir. Foi assim que o
"NOVO MONSTRO SUBNAUTICA 2" (302 dias) escapou: já estava agendado, e do Mac não dá pra cancelar
(a chave só vive na nuvem). A sentinela roda NA NUVEM, revarre tudo que ainda está AGENDADO e
CANCELA sozinha (DELETE /api/posts/{id}) o que viola as regras ATUAIS. Assim, qualquer trava nova
protege até o que já estava na fila — sem depender de ninguém no painel.

Regras que cancelam (as "nunca deveria postar", não as de mera otimização):
  - notícia velha (moldura de novidade + vídeo > FRESH_DAYS)
  - fora de nicho (BLACK)
DELETE só é seguro antes de publicar: só mexo em post com scheduled_at no FUTURO e status não-publicado.

Uso:
  POSTPROXY_KEY=... python sentinela.py           -> cancela de verdade
  DRY_RUN=1 POSTPROXY_KEY=... python sentinela.py  -> só mostra o que cancelaria
"""
import os, sys, json, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER, noticia_velha, off_nicho, BRT  # noqa: E402
from metrics import eh_hashid                                # noqa: E402  (só hashid dá pra cancelar)

PP_KEY   = os.environ.get("POSTPROXY_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
SCHED    = os.path.join(os.path.dirname(LEDGER), "schedule.json")
DRY      = os.environ.get("DRY_RUN", "0") == "1"
API      = "https://api.postproxy.dev/api/posts"
PUBLICADO = {"published", "posted", "sent", "live", "complete", "completed", "success"}


def log(*a): print(*a, flush=True)


def telegram(msg):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                               data=urllib.parse.urlencode({"chat_id": TG_CHAT, "text": msg,
                                                            "parse_mode": "Markdown"}).encode())
    except Exception as e:
        log("tg err", e)


def pp_status(pid):
    try:
        req = urllib.request.Request(f"{API}/{pid}", headers={"Authorization": f"Bearer {PP_KEY}"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        return (d.get("status") or d.get("state") or "").lower()
    except Exception as e:
        log("status err", pid, e)
        return ""   # sem status = trato como agendado (scheduled_at futuro já garante que não publicou)


def pp_delete(pid):
    req = urllib.request.Request(f"{API}/{pid}", method="DELETE",
                                 headers={"Authorization": f"Bearer {PP_KEY}"})
    try:
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception as e:
        log("delete err", pid, e)
        return False


def motivo(v):
    """Por que este vídeo NÃO deveria ir ao ar (None = está ok)."""
    if noticia_velha(v):
        return "notícia velha (novidade + vídeo antigo)"
    if off_nicho(v.get("title", "")):
        return "fora de nicho"
    return None


def main():
    if not PP_KEY:
        log("sentinela: sem POSTPROXY_KEY — abortando."); return
    led = json.load(open(LEDGER))
    try:
        sched = json.load(open(SCHED))
    except Exception:
        sched = []
    agora = datetime.datetime.now(BRT)

    alvos = []
    for p in sched:
        try:
            dt = datetime.datetime.fromisoformat(p["scheduled_at"].replace("Z", "+00:00")).astimezone(BRT)
        except Exception:
            continue
        if dt <= agora:                      # já publicou (ou passou) — não mexo
            continue
        vid, net = p.get("vid"), p.get("net")
        v = led["videos"].get(vid, {})
        m = motivo(v)
        if not m:
            continue
        pid = v.get("posted", {}).get(net, {}).get("post_id")
        alvos.append((vid, net, pid, dt, v, m))

    if not alvos:
        log("sentinela: fila limpa, nada a cancelar."); return

    cancelados, manuais = [], []
    for vid, net, pid, dt, v, m in alvos:
        titulo = v.get("title", "")[:44]
        if not eh_hashid(pid):               # leftover Metricool / id nativo: não dá pra cancelar via PP
            manuais.append((net, dt, titulo, m, pid))
            log(f"sentinela: {vid}/{net} viola ({m}) mas id '{pid}' não é PostProxy — avisar manual.")
            continue
        if DRY:
            log(f"[DRY] cancelaria {net} {vid} pp={pid} ({m})"); continue
        if pp_status(pid) in PUBLICADO:
            log(f"sentinela: {pid} já publicado, não mexo."); continue
        if pp_delete(pid):
            v["posted"][net]["cancelled"] = True
            cancelados.append((net, dt, titulo, m))
            log(f"sentinela: CANCELADO {net} {vid} pp={pid} ({m})")

    if cancelados and not DRY:
        json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
        linhas = [f"🛡️ *Sentinela cancelou {len(cancelados)} post(s) ruim(ns) antes de ir ao ar:*"]
        for net, dt, t, m in cancelados:
            linhas.append(f"  ❌ {net} {dt.strftime('%d/%m %Hh')} — {t} ({m})")
        telegram("\n".join(linhas))
    if manuais:
        linhas = [f"⚠️ *Sentinela: {len(manuais)} post ruim que NÃO consigo cancelar (cancele no painel):*"]
        for net, dt, t, m, pid in manuais:
            linhas.append(f"  {net} {dt.strftime('%d/%m %Hh')} — {t} ({m})")
        telegram("\n".join(linhas))
    log(f"sentinela: {len(cancelados)} cancelado(s), {len(manuais)} manual(is).")


if __name__ == "__main__":
    main()
