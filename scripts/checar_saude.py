#!/usr/bin/env python3
"""Checa a saúde dos canais de publicação e avisa no BotPreguiça quando algo quebra.

Nasceu de 11-12/09/2026, quando duas coisas falharam em SILÊNCIO:
  1. Três agendamentos de TikTok no Metricool entraram em ERROR (faltava
     privacyOption) e ninguém soube. É receita: o TikTok é monetizado.
  2. O PostProxy passou a devolver 403 no Instagram.

Env: POSTPROXY_KEY, METRICOOL_TOKEN, METRICOOL_USER_ID, METRICOOL_BLOG_ID,
     TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DRY_RUN.
"""
import json, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
DRY = os.environ.get("DRY_RUN", "0") == "1"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTADO = os.path.join(RAIZ, "saude_state.json")


def http(url, data=None, headers=None, metodo=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)[:200]


def tg(texto):
    if DRY:
        print("[DRY] TELEGRAM:\n" + texto + "\n" + "-" * 50); return
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("(sem credencial de telegram)"); return
    body = urllib.parse.urlencode({"chat_id": chat, "text": texto[:3900],
                                   "disable_web_page_preview": "true"}).encode()
    http(f"https://api.telegram.org/bot{tok}/sendMessage", body,
         {"Content-Type": "application/x-www-form-urlencoded"})


def estado():
    try:
        return json.load(open(ESTADO))
    except Exception:
        return {"avisados": []}


def checar_postproxy(avisos):
    """403 aqui = Instagram e Facebook param de sair. Aconteceu em 12/09."""
    key = os.environ.get("POSTPROXY_KEY", "")
    if not key:
        return
    status, corpo = http("https://api.postproxy.dev/api/posts?limit=1",
                         headers={"Authorization": f"Bearer {key}"})
    if status == 200:
        print("postproxy ok")
        return
    # Quando cai, vale saber SE a conta ainda existe e em que plano está: o
    # PostProxy tem plano Free com 10 posts/mês, e a dúvida prática é se dá pra
    # voltar pra ele sem reassinar o pago.
    extra = []
    for caminho in ("/api/me", "/api/account", "/api/subscription", "/api/usage", "/api/profiles"):
        st2, corpo2 = http("https://api.postproxy.dev" + caminho,
                           headers={"Authorization": f"Bearer {key}"})
        extra.append(f"   {caminho} → {st2}: {corpo2[:90]}")
    avisos.append(
        f"🔴 PostProxy respondendo {status}.\n"
        f"Instagram e Facebook não vão publicar enquanto isso durar.\n"
        f"Resposta: {corpo[:160]}\n"
        + "\n".join(extra) + "\n"
        f"Conferir a assinatura e a chave em postproxy.dev; se a chave mudou, "
        f"atualizar o secret POSTPROXY_KEY."
    )


def checar_metricool(avisos):
    """TikTok mora aqui. Agendamento que entra em ERROR não avisa ninguém."""
    tok = os.environ.get("METRICOOL_TOKEN", "")
    blog = os.environ.get("METRICOOL_BLOG_ID", "6553996")
    if not tok:
        return
    agora = datetime.now(BRT)
    ini = (agora - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
    fim = (agora + timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    url = (f"https://app.metricool.com/api/v2/scheduler/posts?blogId={blog}"
           f"&start={ini}&end={fim}")
    status, corpo = http(url, headers={"X-Mc-Auth": tok, "Accept": "application/json"})
    if status != 200:
        avisos.append(f"🟠 Não consegui ler o Metricool ({status}). O token pode ter expirado; "
                      f"sem ele eu não vejo se um TikTok falhou.")
        return
    try:
        posts = json.loads(corpo).get("data", [])
    except Exception:
        return

    st = estado()
    novos = []
    for p in posts:
        pid = str(p.get("id"))
        provs = p.get("providers") or []
        falhou = [x for x in provs if x.get("status") == "ERROR"]
        if not falhou or f"err_{pid}" in st["avisados"]:
            continue
        st["avisados"].append(f"err_{pid}")
        quando = (p.get("publicationDate") or {}).get("dateTime", "")[:16].replace("T", " ")
        motivo = falhou[0].get("detailedStatus", "sem detalhe")
        rede = falhou[0].get("network", "?")
        novos.append(f"   {quando} · {rede} · {(p.get('text') or '')[:45]}\n      motivo: {motivo[:110]}")

    # Post futuro sem privacidade declarada = vai falhar igual aos de 07 e 09/09.
    risco = []
    for p in posts:
        provs = p.get("providers") or []
        if not any(x.get("status") == "PENDING" and x.get("network") == "tiktok" for x in provs):
            continue
        if not (p.get("tiktokData") or {}).get("privacyOption"):
            quando = (p.get("publicationDate") or {}).get("dateTime", "")[:16].replace("T", " ")
            risco.append(f"   {quando} · {(p.get('text') or '')[:45]}")

    if novos:
        avisos.append("🔴 TikTok NÃO publicou (agendamento com erro no Metricool):\n" + "\n".join(novos)
                      + "\n   Isso é Creator Rewards perdido. Reagendar com privacyOption.")
    if risco:
        avisos.append("🟠 TikTok agendado SEM opção de privacidade, vai falhar igual:\n" + "\n".join(risco))
    json.dump(st, open(ESTADO, "w"), ensure_ascii=False, indent=1)


def main():
    avisos = []
    checar_postproxy(avisos)
    checar_metricool(avisos)
    if avisos:
        tg("🩺 Saúde da distribuição\n\n" + "\n\n".join(avisos))
        print(f"{len(avisos)} aviso(s) enviado(s)")
    else:
        print("tudo saudável, nada enviado")


if __name__ == "__main__":
    main()
