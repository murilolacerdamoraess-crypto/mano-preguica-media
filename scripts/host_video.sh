#!/bin/bash
# Uso: host_video.sh <youtube_video_id> [titulo]  -> imprime URL publica do mp4
set -euo pipefail
VID="$1"; TITLE="${2:-$VID}"
REPO="murilolacerdamoraess-crypto/mano-preguica-media"
TMP="$HOME/canal_agente/crosspost/tmp"; mkdir -p "$TMP"; F="$TMP/$VID.mp4"
yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" -o "$F" "https://www.youtube.com/watch?v=$VID" >&2
gh release create "$VID" --repo "$REPO" --title "$TITLE" --notes "efemero" "$F" >&2 2>/dev/null \
  || gh release upload "$VID" --repo "$REPO" "$F" --clobber >&2
echo "https://github.com/$REPO/releases/download/$VID/$VID.mp4"
