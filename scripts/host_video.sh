#!/bin/bash
# Uso: host_video.sh <youtube_video_id> [titulo]  -> imprime URL publica do mp4
#
# PREHOST: baixa o video do YouTube e hospeda como release asset, pra o robo da
# nuvem (crosspost.py -> PostProxy) ter uma URL publica pra passar como midia.
# O Actions NAO faz esse passo: ele nao passa no anti-bot do YouTube. Enquanto
# ninguem roda isto, o robo roda todo dia "com sucesso" e posta ZERO.
# (Foi assim que o Instagram ficou 13 dias parado, 24/08 a 06/09/2026.)
#
# Roda em Mac e Windows (Git Bash). Precisa de yt-dlp, ffmpeg, gh e node.
set -euo pipefail
VID="$1"; TITLE="${2:-$VID}"
REPO="murilolacerdamoraess-crypto/mano-preguica-media"
TMP="${PREHOST_TMP:-$HOME/canal_agente/crosspost/tmp}"; mkdir -p "$TMP"; F="$TMP/$VID.mp4"

# Ja hospedado? nao refaz.
if gh release view "$VID" --repo "$REPO" >/dev/null 2>&1; then
  echo "https://github.com/$REPO/releases/download/$VID/$VID.mp4"
  exit 0
fi

# FLAGS OBRIGATORIAS (validado 06-07/09/2026, yt-dlp + Chrome 152):
#   --js-runtimes node --remote-components ejs  -> resolve o desafio "n" do
#     YouTube. Sem isso o download sai truncado ou falha.
#   --no-plugin-dirs -> evita o timeout de 15s do bgutil-pot tentando falar com
#     127.0.0.1:4416 quando aquele servidor nao esta de pe.
# NAO usar --cookies-from-browser chrome: morreu no Chrome 152 (app-bound
# encryption). Video PUBLICO nao precisa de cookie. Pra video privado, extrair
# os cookies via CDP (Network.getAllCookies) e passar --cookies <arquivo>.
yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" \
  --js-runtimes node --remote-components ejs --no-plugin-dirs \
  -o "$F" "https://www.youtube.com/watch?v=$VID" >&2

[ -f "$F" ] || { echo "FALHOU: $VID nao baixou" >&2; exit 1; }

gh release create "$VID" --repo "$REPO" --title "$TITLE" --notes "efemero" "$F" >&2 2>/dev/null \
  || gh release upload "$VID" --repo "$REPO" "$F" --clobber >&2

echo "https://github.com/$REPO/releases/download/$VID/$VID.mp4"

# ATENCAO: NAO rodar cleanup_video.sh depois de agendar no Metricool.
# Desde 06/09/2026 o Metricool NAO re-hospeda mais a midia: o post fica
# apontando pro proprio GitHub. Apagar o asset QUEBRA o post agendado.
