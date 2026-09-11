#!/usr/bin/env python3
"""Gera roteiros_videos.json a partir do frontmatter dos roteiros do cérebro.

É o fio entre as duas pontas do ciclo: o roteiro (cérebro, markdown) e o vídeo
publicado (YouTube, performance_videos). O painel lê este JSON via
raw.githubusercontent e cruza por video_id em /api/dashboard/safra.

Quando rodar: no MESMO passo em que um vídeo sobe e o video_id é anotado no
frontmatter do roteiro (regra: quem sobe o vídeo anota e roda isto).
  python3 scripts/indice_roteiros.py && git add roteiros_videos.json && git commit -m "indice roteiros" && git push
"""
import json, os, re, glob, datetime

CEREBRO = os.path.expanduser("~/claude-projects/cerebro/projetos/canal-agente/roteiros")
SAIDA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roteiros_videos.json")

def frontmatter(texto):
    if not texto.startswith("---"): return {}
    fim = texto.find("\n---", 3)
    fm = {}
    for linha in texto[3:fim].splitlines():
        m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", linha)
        if m: fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm

itens = []
for arq in sorted(glob.glob(os.path.join(CEREBRO, "*.md"))):
    t = open(arq, encoding="utf-8").read()
    fm = frontmatter(t)
    if fm.get("tipo", "roteiro") not in ("roteiro", ""): continue
    titulo = next((l[2:].strip() for l in t.splitlines() if l.startswith("# ")), fm.get("name", ""))
    itens.append({
        "arquivo": os.path.basename(arq),
        "name": fm.get("name", ""),
        "titulo_roteiro": titulo,
        "description": fm.get("description", "")[:220],
        "status": fm.get("status", ""),
        "gate": fm.get("gate", ""),
        "video_id": fm.get("video_id") or None,
        "publicado_em": fm.get("publicado_em") or None,
        "formato": fm.get("formato") or None,
        "motor": fm.get("motor") or None,
    })

json.dump({"gerado_em": datetime.datetime.utcnow().isoformat() + "Z", "roteiros": itens},
          open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
com = sum(1 for i in itens if i["video_id"])
print(f"{len(itens)} roteiros, {com} com video_id -> {SAIDA}")
