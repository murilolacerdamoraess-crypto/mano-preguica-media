#!/usr/bin/env python3
"""Publica programacao.json: o que o crosspost VAI postar, por rede, com data.

Pedido do Murilo (10/09): "quero ver tiktok, facebook, instagram, pra saber se tem
coisa agendada, se eu preciso agendar mais". Essas redes não expõem post agendado
por API, mas quem agenda é este robô, então ele mesmo publica a agenda:

  agendados = schedule.json (o que já foi submetido ao PostProxy/Metricool, futuro)
  previstos = simulação da regra do próprio robô (mesmas filas, cotas, horários,
              cadência semanal e teto do mês de crosspost.py) para os próximos dias

Roda no workflow do crosspost logo depois do robô, com o MESMO env (DAILY_*,
FB_WEEKDAY, START_DATE, MONTH_CAP...). O painel lê via raw.githubusercontent.
"""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("DRY_RUN", "1")
from crosspost import (build_queues, LEDGER, DAILY, WEEKLY, HOURS, ACTIVATE, MONTH_CAP,  # noqa: E402
                       month_posted)

BRT = datetime.timezone(datetime.timedelta(hours=-3))
DIAS_ADIANTE = 14
SAIDA = os.path.join(os.path.dirname(LEDGER), "programacao.json")
SCHED = os.path.join(os.path.dirname(LEDGER), "schedule.json")
# Agenda manual do Metricool (TikTok): quem agenda grava aqui, porque o robô não vê o Metricool.
AGENDA_MANUAL = os.path.join(os.path.dirname(LEDGER), "tiktok_agenda.json")
TOLERANCIA = {"tiktok": 3, "instagram": 3, "facebook": 8}
# Redes agendadas à mão no Metricool. IG/FB com cota 0 estão DESLIGADOS, não manuais.
MANUAIS = {"tiktok"}
DIA_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def carrega(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def cadencia(net):
    if DAILY.get(net, 0) <= 0:
        return "manual (Metricool)" if net in MANUAIS else "desligado (sem PostProxy)"
    h, m = HOURS[net][0]
    hora = f"{h}h{m:02d}" if m else f"{h}h"
    if net in WEEKLY:
        return f"toda {DIA_PT[WEEKLY[net]]} {hora}"
    return f"todo dia {hora}" + (f" (+{DAILY[net]-1})" if DAILY[net] > 1 else "")


def main():
    agora = datetime.datetime.now(BRT)
    led = carrega(LEDGER, {"videos": {}})
    vids = led.get("videos", {})
    sched = carrega(SCHED, [])
    queues = build_queues(led)

    # agendados reais (futuros), por rede; e quais dias já têm post real
    agendados = {n: [] for n in DAILY}
    dias_reais = set()
    for s in sched:
        try:
            dt = datetime.datetime.fromisoformat(s["scheduled_at"].replace("Z", "+00:00")).astimezone(BRT)
        except Exception:
            continue
        if dt < agora - datetime.timedelta(minutes=30):
            continue
        n = s.get("net")
        if n not in agendados:
            continue
        agendados[n].append({
            "video_id": s["vid"], "titulo": s.get("title") or vids.get(s["vid"], {}).get("title", s["vid"]),
            "quando": dt.isoformat(), "fonte": "metricool" if str(s.get("post_id", "")).startswith("metricool") else "postproxy",
        })
        dias_reais.add((n, dt.date()))

    # agenda manual (Metricool): sem isto o painel dizia "TikTok 0" com 5 agendados (12/09)
    publicados_manual = {n: [] for n in DAILY}
    for p in carrega(AGENDA_MANUAL, {}).get("posts", []):
        n = p.get("net", "tiktok")
        try:
            dt = datetime.datetime.fromisoformat(p["quando"]).astimezone(BRT)
        except Exception:
            continue
        if n not in agendados:
            continue
        if dt < agora - datetime.timedelta(minutes=30):
            publicados_manual[n].append(dt.date().isoformat())
            continue
        agendados[n].append({"video_id": p["video_id"], "titulo": p.get("titulo") or vids.get(p["video_id"], {}).get("title", p["video_id"]),
                             "quando": dt.isoformat(), "fonte": "metricool"})
        dias_reais.add((n, dt.date()))

    # previsão: mesma regra do main() do crosspost, dia a dia
    postados_mes = month_posted(led)
    folga = max(0, MONTH_CAP - postados_mes)
    previstos = {n: [] for n in DAILY}
    usados = {n: set() for n in DAILY}
    consumo = 0
    for off in range(0, DIAS_ADIANTE):
        dia = agora.date() + datetime.timedelta(days=off)
        ja_no_dia = set()
        for net in ("facebook", "tiktok", "instagram"):
            if DAILY.get(net, 0) <= 0:
                continue
            start = ACTIVATE.get(net, "")
            if start and dia.isoformat() < start:
                continue
            wd = WEEKLY.get(net)
            if wd is not None and dia.weekday() != wd:
                continue
            if (net, dia) in dias_reais:
                continue  # o robô já agendou de verdade neste dia
            slots = HOURS[net][: DAILY[net]]
            for h, m in slots:
                slot = datetime.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=BRT)
                if slot <= agora:
                    continue
                if consumo >= folga:
                    break
                vid = next((v for v in queues[net] if v not in usados[net] and v not in ja_no_dia), None)
                if not vid:
                    break
                usados[net].add(vid); ja_no_dia.add(vid); consumo += 1
                previstos[net].append({"video_id": vid, "titulo": vids.get(vid, {}).get("title", vid),
                                       "quando": slot.isoformat()})

    redes = {}
    for net in ("tiktok", "instagram", "facebook"):
        feitos = [v["posted"][net].get("date") for v in vids.values()
                  if v.get("posted", {}).get(net, {}).get("done") and v["posted"][net].get("date")]
        feitos += publicados_manual[net]
        ultimo = max(feitos) if feitos else None
        dias = (agora.date() - datetime.date.fromisoformat(ultimo)).days if ultimo else None
        ativo = DAILY.get(net, 0) > 0
        redes[net] = {
            "ativo": ativo,
            "manual": net in MANUAIS,
            "cadencia": cadencia(net),
            "na_fila": len(queues[net]),
            "ultimo_post": ultimo,
            "dias_parado": dias,
            # parado = passou da cadência esperada. Em rede manual (TikTok) o alerta é
            # "ninguém agendou", não "robô quebrou".
            "parado": dias is not None and dias > TOLERANCIA.get(net, 3),
            "agendados": sorted(agendados[net], key=lambda x: x["quando"]),
            "previstos": previstos[net],
            "proximos_da_fila": [{"video_id": v, "titulo": vids.get(v, {}).get("title", v)} for v in queues[net][:3]],
        }

    out = {"gerado_em": agora.isoformat(), "mes": {"postados": postados_mes, "teto": MONTH_CAP, "folga": folga},
           "redes": redes}
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for n, r in redes.items():
        print(f"{n:<10} ativo={r['ativo']!s:<5} {r['cadencia']:<24} agendados={len(r['agendados'])} previstos={len(r['previstos'])} fila={r['na_fila']} ultimo={r['ultimo_post']}")
    print("->", SAIDA)


if __name__ == "__main__":
    main()
