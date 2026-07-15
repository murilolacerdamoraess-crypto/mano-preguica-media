#!/bin/bash
# Uso: cleanup_video.sh <youtube_video_id>  -> apaga o asset/tag do GitHub + temp local
set -euo pipefail
VID="$1"; REPO="murilolacerdamoraess-crypto/mano-preguica-media"
gh release delete "$VID" --repo "$REPO" --yes --cleanup-tag 2>/dev/null || true
rm -f "$HOME/canal_agente/crosspost/tmp/$VID.mp4"
echo "limpo: $VID"
