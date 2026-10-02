#!/usr/bin/env python3
"""Publica o estado da operação Maestri e a biblioteca de referência pro painel.

Gera dois arquivos na raiz deste repo (público), que o painel lê via raw.githubusercontent:
  painel_operacao.json   quadros do Maestri (Backlog de pautas, Em produção, Fila do navegador)
                         + a equipe de agentes, já parseados em itens
  painel_biblioteca.json outliers da biblioteca de referência (sem caminhos locais)

Fonte dos quadros: o CLI `maestri` (só existe dentro de um terminal do Maestri). Quando roda
lá, também grava uma cópia em markdown no cérebro (operacao-maestri/quadro/), que vira a fonte
quando o script roda fora do Maestri (outro PC, terminal comum). Assim o painel nunca depende
de alguém lembrar de copiar.

Quem roda: o hook Stop do cérebro, a cada turno, e só commita se o conteúdo mudou.
  python3 scripts/indice_operacao.py
Publica só DADO e só o essencial (título, status, por que agora, etapa). Premissa e fontes
ficam no cérebro, que é privado.
"""
import json, os, re, subprocess, unicodedata, datetime as dt

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEREBRO = os.path.join(HOME, "claude-projects", "cerebro", "projetos", "canal-agente")
QUADRO_DIR = os.path.join(CEREBRO, "operacao-maestri", "quadro")
BIB_JSON = os.path.join(CEREBRO, "conhecimentos", "dados", "biblioteca-referencia.json")
NOTAS = {"backlog": "Backlog de pautas", "producao": "Em produção", "navegador": "Fila do navegador"}
M = os.environ.get("MAESTRI_CLI") or "maestri"


def maestri(*args):
    if not os.environ.get("MAESTRI_SOCKET"):
        return None
    try:
        r = subprocess.run([M, *args], capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def ler_nota(nome):
    """Lê do Maestri (e salva no cérebro); fora dele, usa a última cópia do cérebro."""
    slug = unicodedata.normalize("NFKD", nome.lower()).encode("ascii", "ignore").decode()
    arq = os.path.join(QUADRO_DIR, re.sub(r"[^a-z0-9]+", "-", slug).strip("-") + ".md")
    bruto = maestri("note", "read", nome)
    if bruto:
        # a saída vem numerada ("12\ttexto") e com um cabeçalho "[N lines total]"
        linhas = []
        for l in bruto.splitlines():
            if l.startswith("[") and "lines total" in l:
                continue
            linhas.append(re.sub(r"^\s*\d+\t", "", l))
        texto = "\n".join(linhas).strip() + "\n"
        os.makedirs(QUADRO_DIR, exist_ok=True)
        antigo = open(arq, encoding="utf-8").read() if os.path.exists(arq) else ""
        if antigo != texto:
            open(arq, "w", encoding="utf-8").write(texto)
        return texto, "maestri"
    if os.path.exists(arq):
        return open(arq, encoding="utf-8").read(), "copia-cerebro"
    return "", "vazio"


def campos(bullet):
    """'- Formato: Short · Concorrência BR: LIVRE · Status: livre' -> dict."""
    out = {}
    for parte in re.split(r"\s+·\s+", bullet.lstrip("- ").strip()):
        m = re.match(r"^([^:]{2,40}):\s*(.+)$", parte)
        if m:
            out[m.group(1).strip().lower()] = m.group(2).strip()
    return out


def itens_backlog(texto):
    itens, cur, rodada = [], None, None
    for l in texto.splitlines():
        if l.startswith("## "):
            rodada = l[3:].strip()
        elif l.startswith("### "):
            if cur:
                itens.append(cur)
            t = l[4:].strip()
            m = re.match(r"^(P\d+)\.\s*(.+)$", t)
            cur = {"id": m.group(1) if m else None, "titulo": m.group(2) if m else t, "rodada": rodada, "campos": {}}
        elif cur and l.startswith("- "):
            cur["campos"].update(campos(l))
    if cur:
        itens.append(cur)
    itens = [it for it in itens if it["id"]]  # só pauta numerada (Pn); "Reservas"/"Descartados" ficam fora
    for it in itens:
        c = it.pop("campos")
        it.update({
            "gancho": c.get("gancho de título", "").strip('"“”'),
            "por_que_agora": c.get("por que agora", ""),
            "formato": c.get("formato", ""),
            "concorrencia": c.get("concorrência br", ""),
            "status": c.get("status", "livre"),
            "frente": c.get("frente", ""),
            "pendente": c.get("pendente antes do roteiro", ""),
        })
    return itens


def itens_linhas(texto):
    """Em produção / Fila: uma linha '- ...' por peça, campos separados por ' · '.
    Formato combinado: - [Short] Título · etapa: X · responsável: Y · falta do Murilo: Z"""
    itens = []
    for l in texto.splitlines():
        if not l.startswith("- "):
            continue
        partes = re.split(r"\s+·\s+", l[2:].strip())
        cab = partes[0]
        m = re.match(r"^\[([^\]]+)\]\s*(.+)$", cab)
        c = {}
        for p in partes[1:]:
            mm = re.match(r"^([^:]{2,40}):\s*(.+)$", p)
            if mm:
                c[mm.group(1).strip().lower()] = mm.group(2).strip()
        if (m.group(2) if m else cab).strip() in ("Título", "Titulo"):
            continue  # linha de exemplo do formato
        falta = c.get("falta do murilo") or c.get("falta") or ""
        itens.append({
            "tipo": m.group(1) if m else "",
            "titulo": m.group(2) if m else cab,
            "etapa": c.get("etapa", ""),
            "responsavel": c.get("responsável", c.get("responsavel", "")),
            "falta_murilo": "" if falta.lower() in ("nada", "-", "nenhum", "não") else falta,
        })
    return itens


def equipe(anterior):
    """Só o terminal Maestro enxerga a equipe inteira; nos agentes, mantém a última lista
    (senão cada terminal publica uma equipe diferente e vira commit a cada turno)."""
    bruto = maestri("list")
    if not bruto or "maestro: true" not in bruto:
        return anterior
    ag = []
    for l in bruto.splitlines():
        m = re.search(r'name: "([^"]+)", role: "([^"]+)"', l)
        if m and not l.strip().startswith("⎿"):
            ag.append({"nome": m.group(1), "funcao": m.group(2)})
    return ag


def main():
    agora = dt.datetime.now().astimezone().isoformat(timespec="minutes")
    notas, fonte = {}, set()
    for chave, nome in NOTAS.items():
        texto, f = ler_nota(nome)
        fonte.add(f)
        notas[chave] = itens_backlog(texto) if chave == "backlog" else itens_linhas(texto)
    saida = os.path.join(REPO, "painel_operacao.json")
    anterior = json.load(open(saida, encoding="utf-8")).get("equipe", []) if os.path.exists(saida) else []
    op = {
        "_doc": "Gerado por scripts/indice_operacao.py a partir dos quadros do Maestri. Não editar.",
        "equipe": equipe(anterior),
        **notas,
    }
    escreve(saida, op, agora)

    if os.path.exists(BIB_JSON):
        b = json.load(open(BIB_JSON, encoding="utf-8"))
        outl = []
        for c in b["canais"]:
            for fmt, f in c["formatos"].items():
                for v in f["top"]:
                    outl.append({"canal": c["titulo"], "handle": c["handle"], "grupo": c["grupo"], "formato": fmt,
                                 "id": v["id"], "titulo": v["titulo"], "views": v["views"], "outlier": v["outlier"],
                                 "publicado": v["publicado"], "thumb": v["thumb_url"], "mediana_canal": f["mediana_views"]})
        outl.sort(key=lambda x: -x["outlier"])
        escreve(os.path.join(REPO, "painel_biblioteca.json"),
                {"_doc": "Biblioteca de referência (biblioteca_referencia.py, repo canal-agente). Não editar.",
                 "atualizado": b["atualizado"], "metodo": b["metodo"], "outliers": outl}, agora)


def copiar_decisoes():
    """Copia o registro único de decisões (painel + Telegram) pro cérebro, onde os agentes leem.
    Fonte: GET /api/decidir/lista do painel. Só reescreve se mudou."""
    import urllib.request
    try:
        bruto = urllib.request.urlopen("https://canal-agente-geer.vercel.app/api/decidir/lista", timeout=20).read()
        dec = json.loads(bruto).get("decisoes") or []
    except Exception:
        return
    if not dec:
        return
    nomes = {"ideia": "pauta", "roteiro": "roteiro", "peca": "peça", "regra": "regra", "titulo": "título"}
    linhas = ["# Decisões do Murilo (registro único: painel + Telegram)", "",
              "Gerado pelo hook do cérebro a partir de /api/decidir/lista. NÃO editar. Mais recente primeiro.",
              "Agentes: antes de pegar trabalho, confiram aqui o que foi aprovado e o MOTIVO do que foi reprovado.", ""]
    for d in dec:
        marca = "APROVADO" if d["decisao"] == "aprovado" else "REPROVADO"
        linha = f"- {d['criado_em'][:16].replace('T', ' ')} · {marca} · {nomes.get(d['tipo'], d['tipo'])} · {d.get('titulo') or d['chave']} · via {d.get('origem', '')}"
        if d.get("motivo"):
            linha += f" · motivo: {d['motivo']}"
        linha += f" · `{d['chave']}`"
        linhas.append(linha)
    texto = "\n".join(linhas) + "\n"
    arq = os.path.join(CEREBRO, "operacao-maestri", "decisoes.md")
    if not os.path.exists(arq) or open(arq, encoding="utf-8").read() != texto:
        open(arq, "w", encoding="utf-8").write(texto)


def escreve(caminho, dado, agora):
    """Só reescreve se o conteúdo (sem o carimbo) mudou, pra não gerar commit vazio."""
    novo = json.dumps(dado, ensure_ascii=False, sort_keys=True)
    if os.path.exists(caminho):
        velho = json.load(open(caminho, encoding="utf-8"))
        velho.pop("gerado_em", None)
        if json.dumps(velho, ensure_ascii=False, sort_keys=True) == novo:
            return
    dado["gerado_em"] = agora
    json.dump(dado, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
    copiar_decisoes()
