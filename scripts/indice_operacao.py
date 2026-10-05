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
            "prazo": c.get("prazo", ""),
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
    regras = []
    arq_r = os.path.join(CEREBRO, "conhecimentos", "propostas-de-regra.md")
    if os.path.exists(arq_r):
        for b in re.split(r"\n(?=### )", open(arq_r, encoding="utf-8").read()):
            m = re.match(r"### (R\d+)\.\s*(.+)", b)
            if not m:
                continue
            c = {}
            for l in b.splitlines()[1:]:
                mm = re.match(r"^- ([^:]{2,30}):\s*(.+)$", l.strip())
                if mm:
                    c[mm.group(1).strip().lower()] = mm.group(2).strip()
            regras.append({"id": m.group(1), "titulo": m.group(2).strip(), "onde": c.get("onde entra", ""),
                           "confianca": c.get("confiança", c.get("confianca", "")), "status": c.get("status", "aguardando"),
                           "simples": c.get("em palavras simples", "")})
    op = {
        "_doc": "Gerado por scripts/indice_operacao.py a partir dos quadros do Maestri. Não editar.",
        "regras": regras,
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
        bruto = urllib.request.urlopen(f"https://canal-agente-geer.vercel.app/api/decidir/lista?t={TOKEN_DECIDIR}", timeout=20).read()
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


PAINEL = "https://canal-agente-geer.vercel.app"
# A chave dos robôs NUNCA fica neste repositório (ele é público): mora em ~/.canal-agente/painel-token
# no Mac e no secret PAINEL_TOKEN do GitHub. Trocada em 05/10/2026 depois que a antiga ficou exposta aqui.
def _token():
    try:
        return open(os.path.expanduser("~/.canal-agente/painel-token")).read().strip()
    except OSError:
        return os.environ.get("PAINEL_TOKEN", "")
TOKEN_DECIDIR = os.environ.get("PAINEL_TOKEN") or _token()
AVISADOS = os.path.join(HOME, ".canal-agente", "telegram-avisados.json")


def avisar_telegram(seco=False):
    """Espelho do Decidir no Telegram (tese do painel, premissa 4). Manda UMA mensagem com o que
    ficou pendente desde o último aviso, com botões de aprovar/reprovar por item. Os botões abrem
    /api/decidir, que grava no mesmo registro do painel. Bot: @RotinaOS_bot (só sendMessage, não
    briga com o webhook do RotinaOS). Credenciais em ~/.rotina-os/rotina-os.env (cópia no cérebro:
    projetos/rotina-os/acessos/credenciais.md)."""
    import urllib.request, urllib.parse
    env = {}
    try:
        for l in open(os.path.join(HOME, ".rotina-os", "rotina-os.env"), encoding="utf-8"):
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.strip().split("=", 1)
                env[k] = v.strip().strip('"').strip("'")
    except Exception:
        return
    bot, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("CHAT_ID")
    if not bot or not chat:
        return
    try:
        d = json.loads(urllib.request.urlopen(f"{PAINEL}/api/decidir/pendentes?t={TOKEN_DECIDIR}", timeout=25).read())
    except Exception:
        return
    if d.get("tabela_ausente") and not seco:
        return  # sem a tabela os botões não gravariam
    ja = set(json.load(open(AVISADOS))) if os.path.exists(AVISADOS) else set()
    novos = [p for p in d.get("pendentes", []) if p["chave"] not in ja][:12]
    if not novos:
        return
    linhas = [f"🧭 {len(novos)} decisão(ões) nova(s) esperando você", ""]
    teclado = []
    for i, p in enumerate(novos, 1):
        linhas.append(f"{i}. [{p['portao']}] {p['titulo']}")
        base = {"chave": p["chave"], "tipo": p["tipo"], "titulo": p["titulo"][:120], "t": TOKEN_DECIDIR}
        ok = f"{PAINEL}/api/decidir?" + urllib.parse.urlencode({**base, "r": "aprovado"})
        no = f"{PAINEL}/api/decidir?" + urllib.parse.urlencode({**base, "r": "reprovado"})
        linha = [{"text": f"✅ {i}", "url": ok}, {"text": f"❌ {i}", "url": no}]
        if p.get("link"):
            link = p["link"] if p["link"].startswith("http") else PAINEL + p["link"]
            linha.append({"text": f"📄 ler {i}", "url": link})
        teclado.append(linha)
    teclado.append([{"text": "Abrir o Decidir no painel", "url": f"{PAINEL}/decidir"}])
    corpo = {"chat_id": chat, "text": "\n".join(linhas), "disable_web_page_preview": True,
             "reply_markup": {"inline_keyboard": teclado}}
    if seco:
        print(corpo["text"]); print(f"[{len(teclado)} linhas de botão] ex.: {teclado[0][0]['url'][:150]}")
        return
    req = urllib.request.Request(f"https://api.telegram.org/bot{bot}/sendMessage",
                                 data=json.dumps(corpo).encode(), headers={"content-type": "application/json"})
    try:
        if json.loads(urllib.request.urlopen(req, timeout=20).read()).get("ok"):
            os.makedirs(os.path.dirname(AVISADOS), exist_ok=True)
            json.dump(sorted(ja | {p["chave"] for p in novos}), open(AVISADOS, "w"))
    except Exception:
        pass


DOC_HASH = os.path.join(HOME, ".canal-agente", "documentos-hash.json")


def enviar_documentos():
    """Manda pro painel o TEXTO do cérebro que o Murilo lê lá (roteiros, quadros, jornadas, regras),
    pra o leitor /ler desenhar, em vez de abrir o .md cru no GitHub (pedido de 03/10/2026).
    Só envia o que mudou (hash local). Token = o mesmo do Decidir."""
    import hashlib, urllib.request
    alvos = []
    for arq in sorted(glob_md(os.path.join(CEREBRO, "roteiros"))):
        alvos.append(("roteiro:" + os.path.basename(arq), "roteiro", arq))
    for arq in sorted(glob_md(QUADRO_DIR)):
        alvos.append(("quadro:" + os.path.basename(arq)[:-3], "quadro", arq))
    for nome, tipo in (("conhecimentos/propostas-de-regra.md", "regra"), ("conhecimentos/livro-de-licoes.md", "regra"),
                       ("conhecimentos/rematch-24h.md", "jornada"), ("tese-do-painel.md", "regra"),
                       ("conhecimentos/cartilha-anzol.md", "regra"), ("producao/FILA.md", "quadro")):
        arq = os.path.join(CEREBRO, nome)
        if os.path.exists(arq):
            alvos.append((tipo + ":" + os.path.basename(arq)[:-3], tipo, arq))
    velho = json.load(open(DOC_HASH)) if os.path.exists(DOC_HASH) else {}
    novo, docs = dict(velho), []
    for chave, tipo, arq in alvos:
        md = open(arq, encoding="utf-8").read()
        h = hashlib.sha1(md.encode()).hexdigest()
        if velho.get(chave) == h:
            continue
        titulo = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), os.path.basename(arq))
        docs.append({"chave": chave, "tipo": tipo, "titulo": titulo, "markdown": md})
        novo[chave] = h
    if not docs:
        return
    for i in range(0, len(docs), 20):
        corpo = json.dumps({"t": TOKEN_DECIDIR, "docs": docs[i:i + 20]}).encode()
        req = urllib.request.Request(f"{PAINEL}/api/documentos", data=corpo, headers={"content-type": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=40).read())
            if not r.get("ok"):
                return
        except Exception:
            return
    os.makedirs(os.path.dirname(DOC_HASH), exist_ok=True)
    json.dump(novo, open(DOC_HASH, "w"))


def glob_md(pasta):
    import glob
    return [a for a in glob.glob(os.path.join(pasta, "*.md")) if not os.path.basename(a).startswith("_")]


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


# ---------- vídeos prontos pra assistir no painel (pedido do Murilo, 05/10/2026) ----------
# "seria legal ter uma parte no canal onde eu pudesse assistir os vídeos que vão ficando prontos,
# porque procurar esses arquivos nas pastas no Drive dá muito trabalho". O Drive do Mac guarda o
# id de cada arquivo no atributo com.google.drivefs.item-id; com ele o painel toca o vídeo pelo
# player do próprio Drive (drive.google.com/file/d/<id>/preview, ele está logado na conta).
DRIVE = os.path.expanduser("~/Library/CloudStorage/GoogleDrive-manopreguicacontato@gmail.com/Meu Drive")
PASTAS_VIDEO = [   # (pasta, canal, seção, quantos no máximo; 0 = todos)
    ("VIDEOS/00 - PRONTOS PRA PUBLICAR", "Canal principal", "pra-publicar", 0),
    ("Mano Preguica/MP2 - PRONTOS PRA SUBIR", "Mano Preguiça 2", "pra-publicar", 0),
    ("Mano Preguica/MP2 - PRONTOS PRA SUBIR/versao 72s (TikTok, nao subir no YouTube)", "TikTok (versão 72 s)", "outras-versoes", 0),
    ("VIDEOS/3 - Videos Curtos", "Canal principal", "publicados", 8),
    ("VIDEOS/2 - Editados", "Canal principal", "publicados", 4),
    ("Mano Preguica/MP2 - PRONTOS PRA SUBIR/publicados", "Mano Preguiça 2", "publicados", 6),
    # 05/10: o Windows fez 3 vídeos novos da corrida de dados e eles ficaram aqui, invisíveis pro Murilo
    ("VIDEOS/PROJETOS CLAUDE (saidas)", "Feito pelo Windows", "previas", 12),
    ("VIDEOS/6 - Edicao IA (bastidores)/testes", "Teste do Windows", "previas", 6),
]


def drive_id(caminho):
    try:
        out = subprocess.run(["xattr", "-p", "com.google.drivefs.item-id#S", caminho],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except Exception:
        return None


def telegram_simples(texto):
    import urllib.request, urllib.parse
    env = {}
    try:
        for l in open(os.path.join(os.path.expanduser("~"), ".rotina-os", "rotina-os.env"), encoding="utf-8"):
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("CHAT_ID"):
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                                   data=urllib.parse.urlencode({"chat_id": env["CHAT_ID"], "text": texto[:3500]}).encode(), timeout=20)
        except Exception:
            pass


def videos_prontos():
    import hashlib, urllib.request
    itens = []
    for rel, canal, secao, maximo in PASTAS_VIDEO:
        pasta = os.path.join(DRIVE, rel)
        if not os.path.isdir(pasta):
            continue
        if secao == "previas":   # pastas de trabalho têm subpastas por projeto
            arqs = [os.path.relpath(os.path.join(r, f), pasta) for r, _, fs in os.walk(pasta) for f in fs
                    if f.lower().endswith((".mp4", ".mov", ".webm")) and "_partes" not in r]
        else:
            arqs = [f for f in os.listdir(pasta) if f.lower().endswith((".mp4", ".mov", ".webm"))]
        arqs.sort(key=lambda f: os.path.getmtime(os.path.join(pasta, f)), reverse=True)
        if maximo:
            arqs = arqs[:maximo]
        for f in arqs:
            cam = os.path.join(pasta, f)
            fid = drive_id(cam)
            if not fid:
                continue
            nome = os.path.splitext(os.path.basename(f))[0]
            aviso = ""
            m = re.search(r"\(ANTES DE POSTAR,?\s*([^)]*)\)", nome, re.I)
            if m:
                aviso = m.group(1).strip(); nome = nome.replace(m.group(0), "").strip()
            fmt = "Longo" if re.match(r"^LONGO\b", nome, re.I) else "Short"
            titulo = re.sub(r"^(SHORT|LONGO)\s*-\s*", "", nome, flags=re.I)
            itens.append({"id": fid, "titulo": titulo, "formato": fmt, "canal": canal, "secao": secao,
                          "aviso": aviso, "pasta": rel,
                          "data": dt.datetime.fromtimestamp(os.path.getmtime(cam)).strftime("%Y-%m-%d %H:%M"),
                          "mb": round(os.path.getsize(cam) / 1e6, 1)})
    corpo_meta = {"itens": itens}
    h = hashlib.sha1(json.dumps(corpo_meta, sort_keys=True).encode()).hexdigest()
    estado = os.path.expanduser("~/.canal-agente/videos-hash.txt")
    try:
        if open(estado).read().strip() == h:
            return
    except OSError:
        pass
    corpo = json.dumps({"t": TOKEN_DECIDIR, "docs": [{"chave": "videos:prontos", "tipo": "videos",
                        "titulo": "Vídeos prontos", "markdown": "", "meta": corpo_meta}]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"{PAINEL}/api/documentos", data=corpo,
                               headers={"content-type": "application/json"}), timeout=30)
        os.makedirs(os.path.dirname(estado), exist_ok=True)
        open(estado, "w").write(h)
        print(f"vídeos prontos: {len(itens)} enviados ao painel")
        # Aviso no Telegram quando aparece vídeo NOVO (o Murilo: "eu nunca sei se o Windows criou vídeos")
        vistos_arq = os.path.expanduser("~/.canal-agente/videos-vistos.json")
        try:
            vistos = set(json.load(open(vistos_arq)))
        except Exception:
            vistos = None   # primeira rodada: só registra, não avisa tudo de uma vez
        novos = [i for i in itens if vistos is not None and i["id"] not in vistos and i["secao"] in ("pra-publicar", "previas")]
        json.dump([i["id"] for i in itens] + list(vistos or []), open(vistos_arq, "w"))
        if novos:
            linhas = [f"• {i['formato']} · {i['titulo'][:70]} ({i['canal']})" for i in novos[:8]]
            telegram_simples("🎬 Vídeo novo pra assistir no painel:\n" + "\n".join(linhas) + "\nhttps://canal-agente-geer.vercel.app/assistir")
    except Exception as e:
        print("vídeos prontos: falhou o envio", e)


if __name__ == "__main__":
    import sys
    main()
    copiar_decisoes()
    enviar_documentos()
    videos_prontos()
    avisar_telegram(seco="--seco" in sys.argv)
