#!/usr/bin/env python3
"""
KIT DE POSTAGEM DO KWAI (semi-manual).

Por que semi-manual: o Kwai NÃO tem API de post, NÃO tem upload web e NENHUM
agendador (PostProxy/Metricool/Postiz/etc) suporta. O único jeito 100% auto seria
emular um celular (frágil + só com o Mac ligado). Então a última etapa é o Murilo:
o robô prepara TUDO e entrega no BotPreguiça; ele só salva na galeria e posta (~30s).

O que este script faz por rodada:
  1. escolhe o próximo vertical elegível (nicho, >= MIN_VIEWS, CAMPEÕES primeiro,
     nunca enviado antes) — Kwai é audiência nova, então manda os bangers na frente;
  2. baixa via yt-dlp (IP residencial do Mac);
  3. manda no Telegram (BotPreguiça): o VÍDEO (pra salvar na galeria) + a LEGENDA
     pronta numa mensagem separada (copiar limpo);
  4. marca em kwai_sent.json pra nunca repetir.

Uso:
  python kwai_kit.py            -> manda 1 (o próximo campeão)
  python kwai_kit.py 3          -> manda 3
  KWAI_DRY=1 python kwai_kit.py -> mostra o que mandaria, sem baixar/enviar
"""
import os, sys, json, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crosspost import LEDGER            # noqa: E402  (raiz do repo + estrutura do ledger)
from tiktok_plan import off_nicho, MIN_VIEWS  # noqa: E402  (mesma curadoria de nicho/views)

SENT   = os.path.expanduser("~/.canal/kwai_sent.json")    # dedup: nunca reenvia (LOCAL, fora do git)
STATUS = os.path.expanduser("~/.canal/kwai_status.json")  # botão "postei?": pendentes + offset do getUpdates
TMP    = os.path.join(os.path.dirname(HERE), "tmp")
DRY    = os.environ.get("KWAI_DRY", "") not in ("", "0")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
# Força H.264/avc1 (iPhone Fotos e Telegram engolem sempre; AV1 do YouTube CONGELA e não salva).
# 720p de propósito: arquivo pequeno (<50MB, limite do bot) e o Kwai re-encoda no upload mesmo.
YTDLP_FMT = "bv*[vcodec^=avc1][height<=1280]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/b"
HASHTAGS = "#subnautica #games #gameplay #kwai #fyp"
MAX_PENDING = 2   # teto de pendentes: o automático segura o próximo até o Murilo limpar (não empilha)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def elegiveis(led, ja_enviados):
    """Verticais no nicho, >= MIN_VIEWS, nunca enviados. Ordena por VIEWS desc (campeão primeiro)."""
    out = []
    for vid, d in led["videos"].items():
        if vid in ja_enviados:
            continue
        if d.get("type") != "vertical" or not d.get("postable"):
            continue
        if d.get("views", 0) < MIN_VIEWS:
            continue
        if off_nicho(d.get("title", "")):
            continue
        out.append((d["views"], vid, d["title"], d["seconds"], d["published"][:10]))
    out.sort(reverse=True)   # CAMPEÃO primeiro
    return out


def legenda(title):
    return f"{title}\n\n{HASHTAGS}"


def vcodec(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=codec_name", "-of",
                        "default=noprint_wrappers=1:nokey=1", f],
                       capture_output=True, text=True)
    return r.stdout.strip()


def baixar(vid):
    os.makedirs(TMP, exist_ok=True)
    f = os.path.join(TMP, f"{vid}.mp4")
    if not os.path.exists(f):
        subprocess.run(["yt-dlp", "-f", YTDLP_FMT, "-o", f,
                        f"https://www.youtube.com/watch?v={vid}"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Rede de segurança: se ainda não for H.264 (vídeo raro só em AV1/VP9), re-encoda.
    if vcodec(f) != "h264":
        g = os.path.join(TMP, f"{vid}_h264.mp4")
        subprocess.run(["ffmpeg", "-y", "-i", f, "-c:v", "libx264", "-c:a", "aac",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", g],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(g, f)
    return f


def dimensoes(arquivo):
    """(width, height, duration_seg) do vídeo — pro Telegram NÃO chutar o aspecto (senão estica)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", arquivo], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        st = j["streams"][0]
        return st.get("width"), st.get("height"), int(float(j["format"]["duration"]))
    except Exception:
        return None, None, None


def tg_video(arquivo, caption):
    """Manda o vídeo com dimensões + miniatura explícitas; devolve o message_id (âncora do lembrete)."""
    w, h, dur = dimensoes(arquivo)
    thumb = arquivo.rsplit(".", 1)[0] + "_thumb.jpg"   # miniatura 9:16 correta (evita poster esticado)
    subprocess.run(["ffmpeg", "-y", "-i", arquivo, "-vf", "scale=-2:320", "-frames:v", "1", thumb],
                   capture_output=True)
    args = ["curl", "-sS", "-F", f"chat_id={TG_CHAT}", "-F", f"caption={caption}",
            "-F", "supports_streaming=true", "-F", f"video=@{arquivo}"]
    if w:   args += ["-F", f"width={w}"]
    if h:   args += ["-F", f"height={h}"]
    if dur: args += ["-F", f"duration={dur}"]
    if os.path.exists(thumb): args += ["-F", f"thumbnail=@{thumb}"]
    args.append(f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo")
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        os.remove(thumb)
    except OSError:
        pass
    try:
        return json.loads(r.stdout).get("result", {}).get("message_id")
    except Exception:
        return None


def tg_msg(texto, reply_markup=None):
    """Manda mensagem; devolve o message_id (pra ancorar o botão 'Postei?')."""
    args = ["curl", "-sS", "-F", f"chat_id={TG_CHAT}", "-F", f"text={texto}"]
    if reply_markup:
        args += ["-F", f"reply_markup={reply_markup}"]
    args.append(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage")
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("result", {}).get("message_id")
    except Exception:
        return None


def botao_postei(vid):
    return json.dumps({"inline_keyboard": [[
        {"text": "✅ Postei", "callback_data": f"kposted:{vid}"},
        {"text": "⏭️ Pular", "callback_data": f"kskip:{vid}"}]]})


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enviar(vid, title, views, status, enviados):
    """Baixa e manda 1 vídeo (vídeo + legenda + botões) e registra como pendente."""
    arq = baixar(vid)
    cap = f"🎬 Kwai de hoje — salve na galeria e poste ({views:,} views no YT)".replace(",", ".")
    anchor = tg_video(arq, cap)
    tg_msg(legenda(title), reply_markup=botao_postei(vid))   # legenda + botões Postei/Pular
    try:
        os.remove(arq)
    except OSError:
        pass
    if vid not in enviados:
        enviados.append(vid)
    status["pending"][vid] = {"title": title, "sent_at": agora_utc(),
                              "anchor": anchor, "reminders": 0}   # anchor = msg do vídeo


def salvar(status, enviados):
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    json.dump(enviados, open(SENT, "w"), ensure_ascii=False, indent=1)
    json.dump(status, open(STATUS, "w"), ensure_ascii=False, indent=1)


def main():
    args = sys.argv[1:]
    led = load(LEDGER, {"videos": {}})
    enviados = load(SENT, [])
    status = load(STATUS, {"offset": 0, "pending": {}})
    status.setdefault("pending", {})

    # send-by-vid: reenvia um vídeo específico (fix/teste), ignorando o dedup
    if len(args) >= 2 and args[0] == "send":
        vid = args[1]
        d = led["videos"].get(vid)
        if not d:
            print(f"Kwai: vídeo {vid} não existe no ledger."); return
        if not (TG_TOKEN and TG_CHAT):
            print("Kwai: sem credenciais (rode via kwai_kit.sh)."); sys.exit(1)
        enviar(vid, d["title"], d["views"], status, enviados)
        salvar(status, enviados)
        print(f"  ✔ reenviado: {vid} | {d['title'][:50]}")
        return

    n = int(args[0]) if args and args[0].isdigit() else 1
    # teto de pendentes: não empilha vídeo pra postar enquanto o Murilo não limpa os que já foram
    pend = len(status["pending"])
    if not DRY and pend >= MAX_PENDING:
        print(f"Kwai: segurando — já tem {pend} pendente(s) (teto {MAX_PENDING}). "
              f"Marque Postei/Pular pra liberar o próximo.")
        return
    fila = elegiveis(led, set(enviados))
    if not fila:
        print("Kwai: fila vazia (nada novo elegível).")
        return
    if not DRY and not (TG_TOKEN and TG_CHAT):
        print("Kwai: sem credenciais do Telegram (rode via kwai_kit.sh)."); sys.exit(1)

    feitos = 0
    for views, vid, title, secs, pub in fila:
        if feitos >= n:
            break
        if DRY:
            print(f"[DRY] {views:>7}v {secs:>3}s | {vid} | {title[:50]}")
            feitos += 1
            continue
        try:
            enviar(vid, title, views, status, enviados)
        except Exception as e:
            print(f"  ✗ download {vid}: {e}")
            continue
        feitos += 1
        print(f"  ✔ enviado: {vid} | {title[:50]}")

    if not DRY:
        salvar(status, enviados)
    print(f"Kwai: {feitos} enviado(s). Fila restante: {max(0, len(fila) - feitos)}.")


if __name__ == "__main__":
    main()
