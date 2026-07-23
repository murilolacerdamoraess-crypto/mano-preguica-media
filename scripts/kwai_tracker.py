#!/usr/bin/env python3
"""
RASTREADOR DO KWAI — fecha o loop "postei ou não".

Cada "Kwai de hoje" vai com um botão ✅ Postei no Kwai. Enquanto o Murilo NÃO
aperta, o vídeo fica em `pending` (assume não postado) e este rastreador cutuca.

Por rodada (launchd a cada ~30min):
  1. getUpdates no BotPreguiça -> captura toques no botão (callback kposted:<vid>):
     marca como postado (tira do pending), responde o toque e troca o botão por
     "✅ Postado" na mensagem que ele clicou.
  2. Pros pendentes que já passaram do prazo, manda LEMBRETE (com o botão de novo).
     Escalada: 4h, 24h, 48h após o envio; depois de 3 lembretes, para de cutucar.

Estado em ~/.canal/kwai_status.json (offset + pending). Só faz getUpdates se o bot
ativo for o BotPreguiça (não rouba updates do RotinaOS no modo fallback).
"""
import os, sys, json, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.expanduser("~/.canal/kwai_status.json")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
BOT = os.environ.get("BOT_ORIGEM", "")
API = f"https://api.telegram.org/bot{TG_TOKEN}"
LEMBRETES_H = [4, 24, 48]   # horas após o envio pro 1º/2º/3º lembrete


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def api(method, **fields):
    args = ["curl", "-sS"]
    for k, v in fields.items():
        args += ["-F", f"{k}={v}"]
    args.append(f"{API}/{method}")
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def botao(vid):
    return json.dumps({"inline_keyboard": [[
        {"text": "✅ Postei", "callback_data": f"kposted:{vid}"},
        {"text": "⏭️ Pular", "callback_data": f"kskip:{vid}"}]]})


def botao_feito(texto):
    return json.dumps({"inline_keyboard": [[{"text": texto, "callback_data": "noop"}]]})


def horas_desde(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return 0.0
    return (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600.0


def capturar_toques(status):
    """Lê getUpdates e processa os botões apertados. Só se for o BotPreguiça."""
    if not BOT.startswith("BotPreguica"):
        return 0
    resp = api("getUpdates", offset=status.get("offset", 0), timeout=0)
    if not resp.get("ok"):
        return 0
    marcados = 0
    for up in resp.get("result", []):
        status["offset"] = up["update_id"] + 1
        cq = up.get("callback_query")
        if not cq:
            continue
        data = cq.get("data", "")
        postei = data.startswith("kposted:")
        pular = data.startswith("kskip:")
        toast = "✅ Marcado como postado!" if postei else ("⏭️ Pulado" if pular else "")
        api("answerCallbackQuery", callback_query_id=cq["id"], text=toast)
        if not (postei or pular):
            continue
        vid = data.split(":", 1)[1]
        msg = cq.get("message", {})
        if msg.get("message_id"):   # troca o botão da msg clicada pelo estado final
            api("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                reply_markup=botao_feito("✅ Postado ✓" if postei else "⏭️ Pulado ✓"))
        if vid in status["pending"]:
            del status["pending"][vid]
            marcados += 1
    return marcados


def cutucar_pendentes(status):
    """Manda lembrete dos que ainda não foram marcados como postados."""
    lembrados = 0
    for vid, p in list(status["pending"].items()):
        r = p.get("reminders", 0)
        if r >= len(LEMBRETES_H):
            continue
        if horas_desde(p.get("sent_at", "")) < LEMBRETES_H[r]:
            continue
        titulo = p.get("title", "?")[:70]
        fields = dict(chat_id=TG_CHAT,
                      text=f"⏰ Ainda não marcou como postado no Kwai:\n{titulo}\n\nJá foi pro ar? (toque aqui pra ir no vídeo)",
                      reply_markup=botao(vid))
        if p.get("anchor"):   # responde no vídeo -> tocar no lembrete pula pra ele na conversa
            fields["reply_to_message_id"] = p["anchor"]
            fields["allow_sending_without_reply"] = "true"
        api("sendMessage", **fields)
        p["reminders"] = r + 1
        lembrados += 1
    return lembrados


def main():
    if not (TG_TOKEN and TG_CHAT):
        print("Kwai tracker: sem credenciais (rode via kwai_tracker.sh)."); sys.exit(1)
    status = load(STATUS, {"offset": 0, "pending": {}})
    status.setdefault("pending", {})
    status.setdefault("offset", 0)
    marcados = capturar_toques(status)
    lembrados = cutucar_pendentes(status)
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    json.dump(status, open(STATUS, "w"), ensure_ascii=False, indent=1)
    print(f"Kwai tracker: {marcados} marcado(s) postado(s), {lembrados} lembrete(s), "
          f"{len(status['pending'])} pendente(s).")


if __name__ == "__main__":
    main()
