#!/usr/bin/env python3
"""MVP preliminar do DetectaFIDC para a Sprint 3."""

from __future__ import annotations

import csv
import html
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = ROOT / "Massa_Dados_Challgenge_Nuclea_v1.zip"
OUTPUT_DIR = ROOT / "output"


@dataclass
class RiskResult:
    id_boleto: str
    risk_score: float
    risk_level: str
    reasons: list[str]
    delay_days: int | None
    amount: float
    payer_id: str
    beneficiary_id: str
    payer_uf: str
    beneficiary_uf: str
    especie: str
    baixa_missing: bool
    materiality_score: float | None
    quantity_score: float | None


def parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    year, month, day = value.split("-")
    return date(int(year), int(month), int(day))


def percentile(values: list[float], target: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = 0
    for index, value in enumerate(ordered):
        if target <= value:
            break
    else:
        index = len(ordered) - 1
    return round((index + 1) / len(ordered), 4)


def normalize(value: float | None, min_value: float, max_value: float) -> float:
    if value is None or max_value == min_value:
        return 0.0
    return max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))


def risk_level(score: float) -> str:
    if score >= 75:
        return "critico"
    if score >= 50:
        return "alto"
    if score >= 30:
        return "medio"
    return "baixo"


def read_csv_from_zip(zip_file: ZipFile, filename: str) -> list[dict[str, str]]:
    raw = zip_file.read(filename).decode("utf-8", "ignore")
    return list(csv.DictReader(raw.splitlines()))


def build_reference_maps(aux_rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, float]]:
    aux_by_cnpj = {row["id_cnpj"]: row for row in aux_rows}
    aux_scores = [
        parse_float(row["score_materialidade_v2"])
        for row in aux_rows
        if parse_float(row["score_materialidade_v2"]) is not None
    ]
    aux_delay = [
        parse_float(row["media_atraso_dias"])
        for row in aux_rows
        if parse_float(row["media_atraso_dias"]) is not None
    ]
    ranges = {
        "mat_min": min(aux_scores) if aux_scores else 0.0,
        "mat_max": max(aux_scores) if aux_scores else 1.0,
        "delay_min": min(aux_delay) if aux_delay else 0.0,
        "delay_max": max(aux_delay) if aux_delay else 1.0,
    }
    return aux_by_cnpj, ranges


def analyze() -> tuple[list[RiskResult], dict[str, object]]:
    with ZipFile(ZIP_PATH) as zip_file:
        boletos = read_csv_from_zip(zip_file, "base_boletos_fiap.csv")
        aux_rows = read_csv_from_zip(zip_file, "base_auxiliar_fiap.csv")

    aux_by_cnpj, ranges = build_reference_maps(aux_rows)

    payer_counts = Counter(row["id_pagador"] for row in boletos)
    beneficiary_counts = Counter(row["id_beneficiario"] for row in boletos)
    amounts = [parse_float(row["vlr_nominal"]) or 0.0 for row in boletos]
    non_zero_amounts = [value for value in amounts if value > 0]

    results: list[RiskResult] = []
    low_liquidity_count = 0
    missing_baixa_count = 0
    delayed_count = 0
    uf_counter: Counter[str] = Counter()

    for row in boletos:
        payer = aux_by_cnpj.get(row["id_pagador"], {})
        beneficiary = aux_by_cnpj.get(row["id_beneficiario"], {})

        nominal = parse_float(row["vlr_nominal"]) or 0.0
        baixa = parse_float(row["vlr_baixa"])
        dt_vencimento = parse_date(row["dt_vencimento"])
        dt_pagamento = parse_date(row["dt_pagamento"])
        delay_days = None
        if dt_vencimento and dt_pagamento:
            delay_days = (dt_pagamento - dt_vencimento).days

        payer_liquidity = parse_float(payer.get("sacado_indice_liquidez_1m"))
        beneficiary_liquidity = parse_float(beneficiary.get("cedente_indice_liquidez_1m"))
        payer_materiality = parse_float(payer.get("score_materialidade_v2"))
        payer_quantity = parse_float(payer.get("score_quantidade_v2"))
        payer_avg_delay = parse_float(payer.get("media_atraso_dias"))
        payer_inad = parse_float(payer.get("share_vl_inad_pag_bol_6_a_15d"))

        score = 0.0
        reasons: list[str] = []

        if baixa is None:
            score += 18
            reasons.append("boleto sem valor de baixa")
            missing_baixa_count += 1

        if delay_days is not None and delay_days > 0:
            delayed_count += 1
            delay_component = min(20.0, delay_days / 3)
            score += delay_component
            reasons.append(f"pagamento com atraso de {delay_days} dias")

        amount_pct = percentile(non_zero_amounts, nominal) if nominal else 0.0
        if amount_pct >= 0.95:
            score += 14
            reasons.append("valor nominal entre os 5% maiores da base")
        elif amount_pct >= 0.85:
            score += 8
            reasons.append("valor nominal elevado")

        payer_volume = payer_counts[row["id_pagador"]]
        if payer_volume >= 8:
            score += 8
            reasons.append("pagador com alta recorrencia de boletos")
        elif payer_volume >= 5:
            score += 4
            reasons.append("pagador com recorrencia relevante")

        beneficiary_volume = beneficiary_counts[row["id_beneficiario"]]
        if beneficiary_volume >= 8:
            score += 6
            reasons.append("beneficiario com alta concentracao operacional")

        if payer_liquidity is not None and payer_liquidity < 0.45:
            score += 10
            reasons.append("pagador com baixa liquidez")
            low_liquidity_count += 1
        elif payer_liquidity is not None and payer_liquidity < 0.65:
            score += 4
            reasons.append("pagador com liquidez moderada")

        if beneficiary_liquidity is not None and beneficiary_liquidity < 0.45:
            score += 6
            reasons.append("beneficiario com baixa liquidez")

        if payer_materiality is not None:
            materiality_risk = 1.0 - normalize(payer_materiality, ranges["mat_min"], ranges["mat_max"])
            if materiality_risk > 0.7:
                score += 10
                reasons.append("score de materialidade desfavoravel")
            elif materiality_risk > 0.45:
                score += 5
                reasons.append("score de materialidade intermediario")

        if payer_quantity is not None and payer_quantity < 200:
            score += 8
            reasons.append("score de quantidade baixo")
        elif payer_quantity is not None and payer_quantity < 500:
            score += 4
            reasons.append("score de quantidade intermediario")

        if payer_avg_delay is not None:
            delay_norm = normalize(payer_avg_delay, ranges["delay_min"], ranges["delay_max"])
            if delay_norm > 0.7:
                score += 10
                reasons.append("historico de atraso elevado")
            elif delay_norm > 0.45:
                score += 5
                reasons.append("historico de atraso moderado")

        if payer_inad is not None and payer_inad > 0.20:
            score += 10
            reasons.append("indicador de inadimplencia elevado")
        elif payer_inad is not None and payer_inad > 0.08:
            score += 5
            reasons.append("indicador de inadimplencia moderado")

        uf = payer.get("uf") or beneficiary.get("uf") or "NA"
        uf_counter[uf] += 1

        results.append(
            RiskResult(
                id_boleto=row["id_boleto"],
                risk_score=round(min(score, 100.0), 2),
                risk_level=risk_level(score),
                reasons=reasons[:5],
                delay_days=delay_days,
                amount=round(nominal, 2),
                payer_id=row["id_pagador"],
                beneficiary_id=row["id_beneficiario"],
                payer_uf=payer.get("uf", "NA"),
                beneficiary_uf=beneficiary.get("uf", "NA"),
                especie=row["tipo_especie"],
                baixa_missing=baixa is None,
                materiality_score=payer_materiality,
                quantity_score=payer_quantity,
            )
        )

    results.sort(key=lambda item: item.risk_score, reverse=True)
    levels = Counter(result.risk_level for result in results)
    top_ufs = uf_counter.most_common(5)
    avg_score = round(mean(result.risk_score for result in results), 2) if results else 0.0

    reason_counter = Counter(reason for result in results for reason in result.reasons)
    summary: dict[str, object] = {
        "project": "DetectaFIDC MVP Preliminar",
        "analysis_date": date.today().isoformat(),
        "source_zip": ZIP_PATH.name,
        "totals": {
            "boletos": len(results),
            "cnpjs_auxiliares": len(aux_rows),
            "alertas_criticos": levels.get("critico", 0),
            "alertas_altos": levels.get("alto", 0),
            "alertas_medios": levels.get("medio", 0),
            "alertas_baixos": levels.get("baixo", 0),
        },
        "quality": {
            "percentual_sem_vlr_baixa": round((missing_baixa_count / len(results)) * 100, 2),
            "percentual_com_atraso": round((delayed_count / len(results)) * 100, 2),
            "score_medio_geral": avg_score,
            "regioes_mais_frequentes": [{"uf": uf, "qtd": count} for uf, count in top_ufs],
        },
        "risk_distribution": [
            {
                "level": level,
                "count": levels.get(level, 0),
                "percent": round((levels.get(level, 0) / len(results)) * 100, 2),
            }
            for level in ["critico", "alto", "medio", "baixo"]
        ],
        "top_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reason_counter.most_common(8)
        ],
        "business_rules": [
            "atraso no pagamento",
            "ausencia de valor de baixa",
            "valor nominal elevado",
            "baixa liquidez",
            "historico de atraso e inadimplencia",
            "concentracao operacional por pagador e beneficiario",
        ],
        "observations": [
            "Motor de risco inicial baseado em regras explicaveis.",
            "Pode ser evoluido para Autoencoder ou modelo supervisionado em sprint futura.",
            "Adequado como evidencia de construcao do MVP preliminar.",
        ],
        "top_alerts": [
            {
                "id_boleto": item.id_boleto,
                "risk_score": item.risk_score,
                "risk_level": item.risk_level,
                "amount": item.amount,
                "reasons": item.reasons,
            }
            for item in results[:10]
        ],
        "operational_signals": {
            "low_liquidity_hits": low_liquidity_count,
            "missing_baixa_hits": missing_baixa_count,
            "delayed_hits": delayed_count,
            "top_especies": Counter(item.especie for item in results).most_common(5),
        },
    }

    return results, summary


def write_csv(results: list[RiskResult]) -> Path:
    output_path = OUTPUT_DIR / "alertas_priorizados.csv"
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "rank",
                "id_boleto",
                "risk_score",
                "risk_level",
                "amount",
                "delay_days",
                "payer_uf",
                "beneficiary_uf",
                "tipo_especie",
                "baixa_missing",
                "materiality_score",
                "quantity_score",
                "reasons",
            ]
        )
        for index, item in enumerate(results, start=1):
            writer.writerow(
                [
                    index,
                    item.id_boleto,
                    item.risk_score,
                    item.risk_level,
                    f"{item.amount:.2f}",
                    item.delay_days if item.delay_days is not None else "",
                    item.payer_uf,
                    item.beneficiary_uf,
                    item.especie,
                    "sim" if item.baixa_missing else "nao",
                    item.materiality_score if item.materiality_score is not None else "",
                    item.quantity_score if item.quantity_score is not None else "",
                    "; ".join(item.reasons),
                ]
            )
    return output_path


def write_json(summary: dict[str, object]) -> Path:
    output_path = OUTPUT_DIR / "resumo_mvp.json"
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def html_badge(level: str) -> str:
    colors = {
        "critico": "#8b0000",
        "alto": "#c46a00",
        "medio": "#336699",
        "baixo": "#1d6b3b",
    }
    return f"<span class='badge' style='background:{colors[level]}'>{html.escape(level.upper())}</span>"






def write_html(results: list[RiskResult], summary: dict[str, object]) -> Path:
    totals = summary["totals"]
    quality = summary["quality"]
    risk_distribution = summary["risk_distribution"]
    top_reasons = summary["top_reasons"]
    operational = summary["operational_signals"]

    priority_count = totals["alertas_criticos"] + totals["alertas_altos"]
    priority_percent = round((priority_count / totals["boletos"]) * 100, 2) if totals["boletos"] else 0.0
    top_region = quality["regioes_mais_frequentes"][0] if quality["regioes_mais_frequentes"] else {"uf": "NA", "qtd": 0}
    dominant_reason = top_reasons[0] if top_reasons else {"reason": "sem dados", "count": 0}

    attention_cards = []
    for index, item in enumerate(results[:3], start=1):
        reasons = ''.join(f"<span class='reason-chip'>" + html.escape(reason) + "</span>" for reason in item.reasons[:4])
        attention_cards.append(
            "<article class='attention-card'>"
            f"<div class='attention-top'><span class='attention-rank'>Caso prioritário {index}</span>{html_badge(item.risk_level)}</div>"
            f"<h3>{html.escape(item.id_boleto[:18])}...</h3>"
            f"<div class='attention-metrics'><div><strong>{item.risk_score:.2f}</strong><span>Score</span></div><div><strong>R$ {item.amount:,.2f}</strong><span>Valor</span></div><div><strong>{'' if item.delay_days is None else item.delay_days}</strong><span>Atraso</span></div></div>"
            f"<div class='chip-wrap'>{reasons}</div>"
            "</article>"
        )

    max_distribution = max(item["count"] for item in risk_distribution) or 1
    level_labels = {"critico": "Crítico", "alto": "Alto", "medio": "Médio", "baixo": "Baixo"}
    level_colors = {"critico": "var(--critical)", "alto": "var(--high)", "medio": "var(--medium)", "baixo": "var(--low)"}
    distribution_cards = []
    for item in risk_distribution:
        width = max(8, round((item["count"] / max_distribution) * 100))
        distribution_cards.append(
            "<div class='dist-card'>"
            f"<div class='dist-top'><span>{level_labels[item['level']]}</span><strong>{item['count']}</strong></div>"
            f"<div class='bar'><span style='width:{width}%; background:{level_colors[item['level']]}'></span></div>"
            f"<small>{item['percent']}% da base</small>"
            "</div>"
        )

    max_reason = max(item["count"] for item in top_reasons) if top_reasons else 1
    reasons_html = []
    for item in top_reasons:
        width = max(12, round((item["count"] / max_reason) * 100))
        reasons_html.append(
            "<div class='reason-row'>"
            f"<div class='reason-label'>{html.escape(item['reason'])}</div>"
            f"<div class='reason-bar'><span style='width:{width}%'></span></div>"
            f"<div class='reason-count'>{item['count']}</div>"
            "</div>"
        )

    top_rows = []
    for item in results[:40]:
        reason_chips = "".join(f"<span class='reason-chip'>" + html.escape(reason) + "</span>" for reason in item.reasons)
        top_rows.append(
            "<tr "
            f"data-level='{html.escape(item.risk_level)}' "
            f"data-text='{html.escape((item.id_boleto + ' ' + item.payer_uf + ' ' + item.beneficiary_uf + ' ' + ' '.join(item.reasons)).lower())}'>"
            f"<td class='mono'>{html.escape(item.id_boleto[:18])}...</td>"
            f"<td><strong>{item.risk_score:.2f}</strong></td>"
            f"<td>{html_badge(item.risk_level)}</td>"
            f"<td>R$ {item.amount:,.2f}</td>"
            f"<td>{'' if item.delay_days is None else item.delay_days}</td>"
            f"<td>{html.escape(item.payer_uf or 'NA')}</td>"
            f"<td>{reason_chips}</td>"
            "</tr>"
        )

    uf_html = "".join(f"<span class='mini-pill'>{html.escape(region['uf'])}: {region['qtd']}</span>" for region in quality["regioes_mais_frequentes"])
    especies_html = "".join(f"<span class='mini-pill'>{html.escape(especie)}: {count}</span>" for especie, count in operational["top_especies"])

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DetectaFIDC MVP</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #060b15;
      --panel: rgba(16, 24, 42, 0.82);
      --panel-strong: rgba(10, 14, 24, 0.94);
      --panel-soft: rgba(20, 30, 52, 0.68);
      --line: rgba(193, 168, 122, 0.16);
      --line-soft: rgba(255,255,255,0.08);
      --text: #f4efe7;
      --muted: #b5ac9f;
      --accent: #d6b57a;
      --accent-2: #6cd2d7;
      --critical: #db5f66;
      --high: #d89a36;
      --medium: #58afd7;
      --low: #41b97d;
      --shadow: 0 28px 90px rgba(0, 0, 0, 0.42);
      --glow: radial-gradient(circle at top, rgba(214,181,122,0.12), transparent 40%);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'IBM Plex Sans', Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(214,181,122,0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(108,210,215,0.10), transparent 24%),
        linear-gradient(180deg, #060b15 0%, #09111d 52%, #050912 100%);
      color: var(--text);
    }}
    .wrap {{ max-width: 1420px; margin: 0 auto; padding: 30px 22px 60px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.45fr 0.9fr;
      gap: 18px;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 32px;
      background:
        linear-gradient(135deg, rgba(10,14,24,0.98), rgba(13,19,32,0.94)),
        var(--glow);
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .hero::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(120deg, transparent 35%, rgba(255,255,255,0.03) 50%, transparent 65%);
      pointer-events: none;
    }}
    .eyebrow, .meta, .section-kicker {{ color: var(--accent); text-transform: uppercase; letter-spacing: 0.18em; font-size: 11px; font-weight: 700; }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-family: 'Playfair Display', serif; font-size: 52px; line-height: 1.12; letter-spacing: -0.02em; max-width: 900px; margin-top: 10px; padding-bottom: 4px; }}
    h2 {{ font-family: 'Playfair Display', serif; font-size: 28px; line-height: 1.18; margin-bottom: 14px; padding-bottom: 2px; }}
    h3 {{ font-family: 'Playfair Display', serif; font-size: 22px; line-height: 1.18; margin: 12px 0 8px; padding-bottom: 2px; }}
    p {{ margin: 0; }}
    .lead {{ max-width: 780px; color: var(--muted); line-height: 1.72; font-size: 17px; margin-top: 14px; }}
    .hero-copy {{ padding-right: 10px; }}
    .tag-row, .toolbar, .pill-row, .chip-wrap {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .tag, .filter-btn, .mini-pill {{
      border: 1px solid var(--line-soft);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      backdrop-filter: blur(8px);
    }}
    .hero-side {{ display: grid; gap: 14px; }}
    .premium-card, .status-card {{
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 22px;
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }}
    .premium-card strong, .status-card strong {{ display: block; margin-top: 8px; font-size: 30px; }}
    .premium-card {{ background: linear-gradient(135deg, rgba(214,181,122,0.10), rgba(108,210,215,0.08)); }}
    .focus-value {{ display: flex; gap: 12px; align-items: center; margin: 14px 0 12px; flex-wrap: wrap; }}
    .focus-value strong {{ font-size: 56px; line-height: 1.2; color: #fff5df; padding-bottom: 4px; }}
    .focus-value span {{ color: var(--muted); font-size: 14px; }}
    .focus-note, .footer-note {{ color: var(--muted); line-height: 1.65; font-size: 14px; }}
    .section {{ margin-top: 22px; }}
    .grid-kpi {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }}
    .card {{
      background: linear-gradient(180deg, rgba(18,26,44,0.90), rgba(10,14,24,0.92));
      border: 1px solid var(--line-soft);
      border-radius: 26px;
      padding: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .kpi-card {{ position: relative; overflow: hidden; }}
    .kpi-card::before {{ content: ""; position: absolute; inset: 0 0 auto 0; height: 3px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }}
    .kpi-card.attention::before {{ background: linear-gradient(90deg, var(--critical), var(--high)); }}
    .kpi-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.10em; }}
    .kpi-value {{ font-size: 36px; font-weight: 700; line-height: 1.15; margin: 12px 0 8px; padding-bottom: 2px; }}
    .kpi-note {{ color: var(--muted); font-size: 14px; line-height: 1.55; }}
    .main-grid {{ display: grid; grid-template-columns: 1.18fr 0.82fr; gap: 16px; }}
    .attention-stack {{ display: grid; gap: 12px; }}
    .attention-card {{
      padding: 20px;
      border-radius: 22px;
      border: 1px solid var(--line-soft);
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
    }}
    .attention-top {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
    .attention-rank {{ color: var(--accent); font-family: 'IBM Plex Mono', monospace; font-size: 12px; letter-spacing: 0.05em; text-transform: uppercase; }}
    .attention-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
    .attention-metrics div {{ padding: 12px 14px; border-radius: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); }}
    .attention-metrics strong {{ font-size: 22px; line-height: 1.15; display: block; margin-bottom: 6px; padding-bottom: 2px; }}
    .attention-metrics span {{ color: var(--muted); font-size: 12px; }}
    .right-stack {{ display: grid; gap: 16px; }}
    .dist-card {{ margin-bottom: 14px; }}
    .dist-top {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-weight: 700; }}
    .bar, .reason-bar {{ width: 100%; height: 12px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }}
    .bar span, .reason-bar span {{ display: block; height: 100%; border-radius: inherit; }}
    .reason-row {{ display: grid; grid-template-columns: 1.45fr 1fr 56px; gap: 12px; align-items: center; margin-bottom: 12px; }}
    .reason-label, .reason-count, .mono {{ font-family: 'IBM Plex Mono', monospace; }}
    .reason-label {{ font-size: 13px; color: var(--text); }}
    .reason-count {{ text-align: right; color: var(--muted); font-size: 13px; }}
    .reason-bar span {{ background: linear-gradient(90deg, var(--accent), var(--accent-2)); }}
    .grid-3 {{ display: grid; grid-template-columns: 1.06fr 1fr 0.9fr; gap: 16px; }}
    .insight-list {{ display: grid; gap: 12px; }}
    .insight {{ padding: 16px 18px; border-radius: 18px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); line-height: 1.62; color: var(--muted); }}
    .controls {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 18px 0 14px; flex-wrap: wrap; }}
    .filter-btn {{ cursor: pointer; transition: 0.2s ease; }}
    .filter-btn.active, .filter-btn:hover {{ background: rgba(214,181,122,0.16); border-color: rgba(214,181,122,0.34); }}
    .search {{ min-width: 280px; background: rgba(255,255,255,0.05); border: 1px solid var(--line-soft); border-radius: 14px; padding: 12px 14px; color: var(--text); outline: none; }}
    .table-shell {{ border: 1px solid var(--line); border-radius: 26px; overflow: hidden; background: linear-gradient(180deg, rgba(12,18,31,0.92), rgba(8,12,22,0.96)); }}
    table {{ width: 100%; border-collapse: collapse; }}
    thead th {{ position: sticky; top: 0; background: rgba(10, 14, 24, 0.98); z-index: 1; text-align: left; padding: 14px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); border-bottom: 1px solid var(--line-soft); }}
    tbody td {{ padding: 14px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: top; font-size: 14px; }}
    tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
    .table-wrap {{ max-height: 720px; overflow: auto; }}
    .badge {{ color: #fff; padding: 6px 10px; border-radius: 999px; font-size: 11px; letter-spacing: 0.08em; font-weight: 700; display: inline-flex; }}
    .reason-chip {{ display: inline-flex; margin: 0 6px 6px 0; padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.06); font-size: 12px; color: var(--text); }}
    .signature {{ margin-top: 16px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.14em; }}
    @media (max-width: 1180px) {{
      .hero, .grid-kpi, .main-grid, .grid-3 {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow">Challenge FIAP + Núclea • Sprint 3</div>
        <h1>DetectaFIDC em versão premium: uma leitura institucional do MVP para demonstrar valor, risco e maturidade</h1>
        <p class="lead">Esta versão reorganiza o MVP como um produto com linguagem mais institucional. A proposta não é apenas exibir indicadores, mas sustentar uma narrativa de confiança: volume processado, fila prioritária, sinais dominantes de risco e evidências reais de decisão sobre a base oficial do challenge.</p>
        <div class="tag-row" style="margin-top:20px;">
          <span class="tag">Base oficial processada</span>
          <span class="tag">Lógica explicável</span>
          <span class="tag">Dashboard pronto para banca</span>
          <span class="tag">Visão com acabamento premium</span>
        </div>
        <div class="signature">DetectaFIDC • Data Vision • Sprint 3 MVP</div>
      </div>
      <div class="hero-side">
        <div class="premium-card">
          <div class="meta">Monitoramento prioritário</div>
          <div class="focus-value"><strong>{priority_count}</strong><span>alertas altos + críticos</span></div>
          <p class="focus-note">{priority_percent}% da base entrou na fila de atenção imediata. O principal gatilho recorrente é <strong>{html.escape(dominant_reason['reason'])}</strong>, reforçando a necessidade de monitoramento concentrado e justificável.</p>
        </div>
        <div class="status-card">
          <div class="meta">Status institucional</div>
          <strong>MVP funcional, demonstrável e defensável</strong>
          <p class="footer-note">Geração em {summary['analysis_date']} a partir de {summary['source_zip']}. A leitura desta tela foi pensada para screenshot, apresentação executiva e demonstração guiada.</p>
        </div>
      </div>
    </section>

    <section class="section grid-kpi">
      <div class="card kpi-card"><div class="kpi-label">Boletos processados</div><div class="kpi-value">{totals['boletos']}</div><div class="kpi-note">Volume total analisado pelo pipeline com a massa oficial do desafio.</div></div>
      <div class="card kpi-card"><div class="kpi-label">CNPJs enriquecidos</div><div class="kpi-value">{totals['cnpjs_auxiliares']}</div><div class="kpi-note">Base auxiliar usada para liquidez, materialidade, histórico e inadimplência.</div></div>
      <div class="card kpi-card attention"><div class="kpi-label">Fila de atenção</div><div class="kpi-value">{priority_count}</div><div class="kpi-note">Casos altos e críticos que devem abrir a demonstração e a fala da banca.</div></div>
      <div class="card kpi-card"><div class="kpi-label">Sem valor de baixa</div><div class="kpi-value">{quality['percentual_sem_vlr_baixa']}%</div><div class="kpi-note">{operational['missing_baixa_hits']} registros indicam sensibilidade operacional imediata.</div></div>
      <div class="card kpi-card"><div class="kpi-label">Concentração regional</div><div class="kpi-value">{top_region['uf']}</div><div class="kpi-note">{top_region['qtd']} ocorrências na região líder da execução atual.</div></div>
    </section>

    <section class="section main-grid">
      <div class="card">
        <div class="section-kicker">Fila de demonstração</div>
        <h2>Três casos premium para abrir a narrativa</h2>
        <div class="attention-stack">{''.join(attention_cards)}</div>
        <p class="footer-note">Esses casos concentram o tipo de evidência que a banca espera: score alto, critérios compreensíveis e justificativas diretamente ligadas aos sinais do negócio.</p>
      </div>
      <div class="right-stack">
        <div class="card">
          <div class="section-kicker">Composição da carteira</div>
          <h2>Distribuição do risco</h2>
          {''.join(distribution_cards)}
          <p class="footer-note">O score médio geral foi <strong>{quality['score_medio_geral']}</strong>. A maior parte da carteira permanece em baixa prioridade, enquanto um conjunto menor concentra material de investigação.</p>
        </div>
        <div class="card">
          <div class="section-kicker">Pressões predominantes</div>
          <h2>Motivos mais frequentes</h2>
          {''.join(reasons_html)}
        </div>
      </div>
    </section>

    <section class="section grid-3">
      <div class="card">
        <div class="section-kicker">Capacidades entregues</div>
        <h2>O que o MVP já sustenta hoje</h2>
        <div class="insight-list">
          <div class="insight">Leitura da massa oficial com tratamento de campos críticos, parsing de datas e normalização de valores.</div>
          <div class="insight">Enriquecimento com base auxiliar para compor sinais financeiros e operacionais de risco.</div>
          <div class="insight">Motor com score entre 0 e 100, classificação em níveis e priorização auditável.</div>
          <div class="insight">Saídas em CSV, JSON, HTML e SVG prontas para análise, tela e apresentação formal.</div>
        </div>
      </div>
      <div class="card">
        <div class="section-kicker">Leitura estratégica</div>
        <h2>Recortes úteis para a banca</h2>
        <div class="pill-row">{uf_html}</div>
        <p class="footer-note">As UFs acima concentram o maior volume observado no processamento atual.</p>
        <div class="pill-row" style="margin-top:14px;">{especies_html}</div>
        <p class="footer-note">A base é fortemente dominada por duplicatas mercantis, o que ajuda a contextualizar a massa analisada.</p>
      </div>
      <div class="card">
        <div class="section-kicker">Evolução do produto</div>
        <h2>Próxima etapa natural</h2>
        <div class="insight-list">
          <div class="insight">Substituir ou complementar a heurística com Autoencoder ou modelo estatístico de anomalia.</div>
          <div class="insight">Publicar uma camada visual interativa em Power BI ou Streamlit com uso institucional.</div>
          <div class="insight">Aproximar o fluxo local da arquitetura futura com simulação contínua e integração.</div>
        </div>
      </div>
    </section>

    <section class="section card">
      <div class="section-kicker">Mesa analítica</div>
      <h2>Tabela premium filtrável para demonstração e screenshot</h2>
      <div class="controls">
        <div class="toolbar">
          <button class="filter-btn active" data-filter="todos">Todos</button>
          <button class="filter-btn" data-filter="critico">Crítico</button>
          <button class="filter-btn" data-filter="alto">Alto</button>
          <button class="filter-btn" data-filter="medio">Médio</button>
          <button class="filter-btn" data-filter="baixo">Baixo</button>
        </div>
        <input id="searchInput" class="search" type="search" placeholder="Buscar por ID, UF ou motivo de risco">
      </div>
      <div class="table-shell">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID boleto</th>
                <th>Score</th>
                <th>Nível</th>
                <th>Valor</th>
                <th>Atraso</th>
                <th>UF</th>
                <th>Motivos principais</th>
              </tr>
            </thead>
            <tbody id="alertsTable">
              {''.join(top_rows)}
            </tbody>
          </table>
        </div>
      </div>
      <div class="footer-note">Sugestão de fala: primeiro mostre a fila crítica; depois filtre por um gatilho como <strong>sem valor de baixa</strong> para provar a capacidade explicável do motor.</div>
    </section>
  </div>

  <script>
    const buttons = [...document.querySelectorAll('.filter-btn')];
    const rows = [...document.querySelectorAll('#alertsTable tr')];
    const searchInput = document.getElementById('searchInput');
    let currentFilter = 'todos';

    function applyFilters() {{
      const query = (searchInput.value || '').trim().toLowerCase();
      rows.forEach((row) => {{
        const level = row.dataset.level;
        const text = row.dataset.text || '';
        const levelMatch = currentFilter === 'todos' || level === currentFilter;
        const textMatch = !query || text.includes(query);
        row.style.display = levelMatch && textMatch ? '' : 'none';
      }});
    }}

    buttons.forEach((button) => {{
      button.addEventListener('click', () => {{
        buttons.forEach((btn) => btn.classList.remove('active'));
        button.classList.add('active');
        currentFilter = button.dataset.filter;
        applyFilters();
      }});
    }});

    searchInput.addEventListener('input', applyFilters);
    applyFilters();
  </script>
</body>
</html>
"""
    output_path = OUTPUT_DIR / "evidencias_mvp.html"
    output_path.write_text(html_content, encoding="utf-8")
    return output_path



def write_architecture_svg() -> Path:
    output_path = OUTPUT_DIR / "arquitetura_mvp_detectafidc.svg"
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="980" viewBox="0 0 1680 980">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#060b15"/>
      <stop offset="58%" stop-color="#09111d"/>
      <stop offset="100%" stop-color="#050912"/>
    </linearGradient>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="18" stdDeviation="16" flood-color="#000000" flood-opacity="0.24"/>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M2,2 L10,6 L2,10 Z" fill="#d6b57a"/>
    </marker>
    <style>
      .title{font-family:Georgia,serif;font-size:44px;font-weight:700;fill:#f4efe7}
      .subtitle{font-family:Arial,sans-serif;font-size:20px;fill:#b5ac9f}
      .section-title{font-family:Arial,sans-serif;font-size:22px;font-weight:800;fill:#e0bf84}
      .section-sub{font-family:Arial,sans-serif;font-size:15px;fill:#b5ac9f}
      .lane{fill:rgba(255,255,255,0.025);stroke:rgba(214,181,122,0.16);stroke-width:2;rx:30}
      .box{fill:#121a2a;stroke:#2e2a22;stroke-width:2;rx:24;filter:url(#shadow)}
      .box-title{font-family:Georgia,serif;font-size:24px;font-weight:700;fill:#f4efe7}
      .box-text{font-family:Arial,sans-serif;font-size:17px;fill:#d8c9ad}
      .tag{fill:#172131;stroke:#3a3123;stroke-width:1;rx:14}
      .tag-text{font-family:Arial,sans-serif;font-size:13px;font-weight:800;fill:#e0bf84}
      .arrow{stroke:#d6b57a;stroke-width:4;fill:none;marker-end:url(#arrow)}
      .note{font-family:Arial,sans-serif;font-size:16px;fill:#b5ac9f}
      .callout{fill:#0f1624;stroke:#3a3123;stroke-width:2;rx:20}
      .callout-title{font-family:Arial,sans-serif;font-size:18px;font-weight:800;fill:#f4efe7}
      .callout-text{font-family:Arial,sans-serif;font-size:15px;fill:#d8c9ad}
    </style>
  </defs>
  <rect width="1680" height="980" fill="url(#bg)"/>
  <text x="70" y="82" class="title">DetectaFIDC • arquitetura premium do MVP preliminar</text>
  <text x="72" y="118" class="subtitle">Uma leitura institucional do fluxo atual: o que já existe, como os dados percorrem o motor e qual é a ponte para a evolução da solução</text>

  <rect x="70" y="160" width="1540" height="340" class="lane"/>
  <text x="105" y="206" class="section-title">Camada efetivamente entregue na Sprint 3</text>
  <text x="105" y="234" class="section-sub">A arquitetura abaixo não é apenas conceitual: ela representa o fluxo local já executável sobre dados reais do challenge</text>

  <rect x="90" y="275" width="320" height="175" class="box"/>
  <text x="122" y="322" class="box-title">1. Massa oficial</text>
  <text x="122" y="360" class="box-text">ZIP do desafio contendo</text>
  <text x="122" y="388" class="box-text">boletos e base auxiliar</text>
  <rect x="122" y="404" width="182" height="32" class="tag"/>
  <text x="142" y="425" class="tag-text">Massa_Dados_Challgenge</text>

  <rect x="455" y="275" width="320" height="175" class="box"/>
  <text x="487" y="322" class="box-title">2. Ingestão e preparo</text>
  <text x="487" y="360" class="box-text">Leitura do ZIP, parsing</text>
  <text x="487" y="388" class="box-text">de datas, valores e nulos</text>
  <rect x="487" y="404" width="170" height="32" class="tag"/>
  <text x="507" y="425" class="tag-text">detectafidc_mvp.py</text>

  <rect x="820" y="275" width="320" height="175" class="box"/>
  <text x="852" y="322" class="box-title">3. Enriquecimento</text>
  <text x="852" y="360" class="box-text">Liquidez, materialidade,</text>
  <text x="852" y="388" class="box-text">inadimplência, UF e histórico</text>
  <rect x="852" y="404" width="170" height="32" class="tag"/>
  <text x="872" y="425" class="tag-text">features de risco</text>

  <rect x="1185" y="275" width="320" height="175" class="box"/>
  <text x="1217" y="322" class="box-title">4. Motor de risco</text>
  <text x="1217" y="360" class="box-text">Score 0–100, motivos</text>
  <text x="1217" y="388" class="box-text">explicáveis e níveis de alerta</text>
  <rect x="1217" y="404" width="118" height="32" class="tag"/>
  <text x="1237" y="425" class="tag-text">priorização</text>

  <path d="M410 362 C430 362 438 362 455 362" class="arrow"/>
  <path d="M775 362 C792 362 802 362 820 362" class="arrow"/>
  <path d="M1140 362 C1158 362 1168 362 1185 362" class="arrow"/>

  <rect x="70" y="545" width="1540" height="295" class="lane"/>
  <text x="105" y="590" class="section-title">Saídas visíveis e continuidade estratégica</text>
  <text x="105" y="618" class="section-sub">O MVP já gera evidências formais para banca e estabelece uma base coerente para escalar a solução nas próximas sprints</text>

  <rect x="95" y="655" width="360" height="145" class="box"/>
  <text x="127" y="700" class="box-title">Saídas para banca</text>
  <text x="127" y="736" class="box-text">alertas_priorizados.csv</text>
  <text x="127" y="764" class="box-text">resumo_mvp.json + evidencias_mvp.html</text>

  <rect x="500" y="655" width="360" height="145" class="box"/>
  <text x="532" y="700" class="box-title">Evidência visual</text>
  <text x="532" y="736" class="box-text">tela_aplicacao_operando.svg</text>
  <text x="532" y="764" class="box-text">evidencia_codigo_motor_risco.svg</text>

  <rect x="905" y="655" width="585" height="145" class="box"/>
  <text x="937" y="700" class="box-title">Próxima etapa institucional</text>
  <text x="937" y="736" class="box-text">Autoencoder ou modelo estatístico • camada visual interativa</text>
  <text x="937" y="764" class="box-text">simulação contínua • integração cloud / APIs • evolução para produção</text>

  <rect x="1195" y="470" width="330" height="120" class="callout"/>
  <text x="1220" y="512" class="callout-title">Mensagem-chave</text>
  <text x="1220" y="540" class="callout-text">A Sprint 3 já materializa o fluxo</text>
  <text x="1220" y="564" class="callout-text">central da solução com dados reais,</text>
  <text x="1220" y="588" class="callout-text">score explicável e artefatos defensáveis.</text>

  <text x="72" y="900" class="note">Use este slide para explicar: origem dos dados → preparo → enriquecimento → score → evidências. Isso mostra maturidade do MVP sem prometer produção antes da hora.</text>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")
    return output_path

def write_code_evidence_svg() -> Path:
    output_path = OUTPUT_DIR / "evidencia_codigo_motor_risco.svg"
    snippet = [
        "with ZipFile(ZIP_PATH) as zip_file:",
        "    boletos = read_csv_from_zip(zip_file, 'base_boletos_fiap.csv')",
        "    aux_rows = read_csv_from_zip(zip_file, 'base_auxiliar_fiap.csv')",
        "",
        "payer_liquidity = parse_float(payer.get('sacado_indice_liquidez_1m'))",
        "payer_materiality = parse_float(payer.get('score_materialidade_v2'))",
        "payer_inad = parse_float(payer.get('share_vl_inad_pag_bol_6_a_15d'))",
        "",
        "if baixa is None:",
        "    score += 18",
        "    reasons.append('boleto sem valor de baixa')",
        "",
        "if delay_days is not None and delay_days > 0:",
        "    score += min(20.0, delay_days / 3)",
        "    reasons.append(f'pagamento com atraso de {delay_days} dias')",
        "",
        "if payer_liquidity is not None and payer_liquidity < 0.45:",
        "    score += 10",
        "    reasons.append('pagador com baixa liquidez')",
        "",
        "results.sort(key=lambda item: item.risk_score, reverse=True)",
    ]
    code_lines = []
    y = 170
    for idx, line in enumerate(snippet, start=1):
        safe = html.escape(line)
        code_lines.append(f"<text x='92' y='{y}' class='ln'>{idx:02}</text><text x='140' y='{y}' class='code'>{safe}</text>")
        y += 31

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="930" viewBox="0 0 1500 930">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#081020"/>
      <stop offset="100%" stop-color="#111936"/>
    </linearGradient>
    <style>
      .title{{font-family:Arial,sans-serif;font-size:40px;font-weight:800;fill:#eff6ff}}
      .subtitle{{font-family:Arial,sans-serif;font-size:19px;fill:#9fb3d9}}
      .panel{{fill:#0d1327;stroke:#243457;stroke-width:2;rx:20}}
      .bar{{fill:#111936}}
      .dot1{{fill:#ff5f57}} .dot2{{fill:#ffbd2e}} .dot3{{fill:#28c840}}
      .ln{{font-family:Consolas,monospace;font-size:18px;fill:#6f83aa}}
      .code{{font-family:Consolas,monospace;font-size:18px;fill:#e5eefc}}
      .call{{font-family:Arial,sans-serif;font-size:18px;fill:#d6e3fb}}
      .tag{{fill:#173055;rx:12}}
      .tagText{{font-family:Arial,sans-serif;font-size:15px;font-weight:700;fill:#7dd3fc}}
      .callout{{fill:#101a32;stroke:#243457;stroke-width:2;rx:18}}
      .callTitle{{font-family:Arial,sans-serif;font-size:18px;font-weight:800;fill:#eff6ff}}
      .callText{{font-family:Arial,sans-serif;font-size:15px;fill:#c6d6f4}}
    </style>
  </defs>
  <rect width="1500" height="930" fill="url(#bg)"/>
  <text x="70" y="78" class="title">Evidência real do código-fonte</text>
  <text x="72" y="115" class="subtitle">Trecho do motor de risco em src/detectafidc_mvp.py mostrando ingestão, critérios e priorização</text>
  <rect x="70" y="140" width="980" height="720" class="panel"/>
  <rect x="70" y="140" width="980" height="54" class="bar" rx="20"/>
  <circle cx="105" cy="167" r="8" class="dot1"/><circle cx="130" cy="167" r="8" class="dot2"/><circle cx="155" cy="167" r="8" class="dot3"/>
  <text x="190" y="174" class="call">detectafidc_mvp.py</text>
  {''.join(code_lines)}
  <rect x="1110" y="210" width="320" height="150" class="callout"/>
  <text x="1135" y="248" class="callTitle">1. Ingestão</text>
  <text x="1135" y="276" class="callText">Leitura direta do ZIP oficial.</text>
  <text x="1135" y="300" class="callText">Não é mockup: usa a massa real</text>
  <text x="1135" y="324" class="callText">da Sprint 3.</text>

  <rect x="1110" y="405" width="320" height="150" class="callout"/>
  <text x="1135" y="443" class="callTitle">2. Regras explicáveis</text>
  <text x="1135" y="471" class="callText">Atraso, baixa ausente, liquidez</text>
  <text x="1135" y="495" class="callText">e recorrência justificam o score</text>
  <text x="1135" y="519" class="callText">de forma auditável.</text>

  <rect x="1110" y="600" width="320" height="150" class="callout"/>
  <text x="1135" y="638" class="callTitle">3. Saída priorizada</text>
  <text x="1135" y="666" class="callText">Os resultados são ordenados por</text>
  <text x="1135" y="690" class="callText">score e viram evidências em CSV,</text>
  <text x="1135" y="714" class="callText">JSON, HTML e SVG.</text>

  <rect x="1110" y="790" width="250" height="42" class="tag"/>
  <text x="1132" y="817" class="tagText">Lógica executada e documentada</text>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")
    return output_path







def write_app_screen_svg(summary: dict[str, object]) -> Path:
    output_path = OUTPUT_DIR / "tela_aplicacao_operando.svg"
    totals = summary["totals"]
    quality = summary["quality"]
    priority_count = totals["alertas_criticos"] + totals["alertas_altos"]
    top_reasons = summary["top_reasons"][:3]
    top_region = quality["regioes_mais_frequentes"][0] if quality["regioes_mais_frequentes"] else {"uf": "NA", "qtd": 0}

    rows = []
    y = 605
    for alert in summary["top_alerts"][:4]:
        reasons = " | ".join(alert["reasons"][:2])
        rows.append(
            f"<text x='110' y='{y}' class='row mono'>{html.escape(alert['id_boleto'][:16])}...</text>"
            f"<text x='515' y='{y}' class='row strong'>{alert['risk_score']}</text>"
            f"<text x='650' y='{y}' class='row'>{html.escape(alert['risk_level'].upper())}</text>"
            f"<text x='810' y='{y}' class='row'>R$ {alert['amount']:,.2f}</text>"
            f"<text x='1060' y='{y}' class='row'>{html.escape(reasons[:63])}</text>"
        )
        y += 66

    highlights = []
    hy = 272
    for item in top_reasons:
        highlights.append(f"<text x='1100' y='{hy}' class='mini'>• {html.escape(item['reason'])} ({item['count']})</text>")
        hy += 32

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1650" height="1040" viewBox="0 0 1650 1040">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#060b15"/>
      <stop offset="58%" stop-color="#09111d"/>
      <stop offset="100%" stop-color="#050912"/>
    </linearGradient>
    <style>
      .title{{font-family:Georgia,serif;font-size:44px;font-weight:700;fill:#f4efe7}}
      .sub{{font-family:Arial,sans-serif;font-size:19px;fill:#b5ac9f}}
      .hero{{fill:#0c1321;stroke:#3a3123;stroke-width:2;rx:30}}
      .card{{fill:#121a2a;stroke:#2e2a22;stroke-width:2;rx:24}}
      .table{{fill:#0b111d;stroke:#2e2a22;stroke-width:2;rx:24}}
      .metric{{font-family:Arial,sans-serif;font-size:38px;font-weight:800;fill:#f4efe7}}
      .metricAccent{{font-family:Arial,sans-serif;font-size:58px;font-weight:800;fill:#e0bf84}}
      .label{{font-family:Arial,sans-serif;font-size:15px;fill:#b5ac9f}}
      .small{{font-family:Arial,sans-serif;font-size:13px;fill:#b5ac9f}}
      .head{{font-family:Arial,sans-serif;font-size:15px;font-weight:800;fill:#e0bf84}}
      .row{{font-family:Arial,sans-serif;font-size:14px;fill:#efe8dd}}
      .strong{{font-weight:800}}
      .mono{{font-family:Consolas,monospace}}
      .mini{{font-family:Arial,sans-serif;font-size:14px;fill:#d6c5a6}}
      .pill{{fill:#172131;rx:14}}
      .pillText{{font-family:Arial,sans-serif;font-size:14px;font-weight:800;fill:#e0bf84}}
      .badge{{fill:#111927;stroke:#3a3123;stroke-width:2;rx:20}}
      .badgeTitle{{font-family:Arial,sans-serif;font-size:18px;font-weight:800;fill:#f4efe7}}
      .badgeText{{font-family:Arial,sans-serif;font-size:15px;fill:#d8c9ad}}
    </style>
  </defs>
  <rect width="1650" height="1040" fill="url(#bg)"/>
  <text x="70" y="82" class="title">DetectaFIDC • visão premium do MVP preliminar</text>
  <text x="72" y="118" class="sub">Uma leitura institucional para slide: volume analisado, fila prioritária, sinais dominantes e casos que sustentam a defesa do projeto</text>

  <rect x="70" y="155" width="970" height="215" class="hero"/>
  <text x="108" y="204" class="label">Monitoramento prioritário</text>
  <text x="108" y="282" class="metricAccent">{priority_count}</text>
  <text x="255" y="282" class="label">alertas altos + críticos em destaque</text>
  <text x="108" y="316" class="small">{quality['percentual_com_atraso']}% da base com atraso • {quality['percentual_sem_vlr_baixa']}% sem valor de baixa</text>
  <text x="108" y="342" class="small">Região com maior volume: {top_region['uf']} ({top_region['qtd']} registros) • Score médio geral: {quality['score_medio_geral']}</text>

  <rect x="1075" y="155" width="505" height="240" class="badge"/>
  <text x="1108" y="205" class="badgeTitle">Sinais dominantes da base</text>
  <text x="1108" y="238" class="badgeText">• {totals['boletos']} boletos processados</text>
  <text x="1108" y="268" class="badgeText">• {totals['cnpjs_auxiliares']} CNPJs enriquecidos</text>
  {''.join(highlights)}

  <rect x="70" y="420" width="230" height="145" class="card"/>
  <text x="103" y="480" class="metric">{totals['alertas_criticos']}</text>
  <text x="103" y="516" class="label">Críticos</text>

  <rect x="320" y="420" width="230" height="145" class="card"/>
  <text x="353" y="480" class="metric">{totals['alertas_altos']}</text>
  <text x="353" y="516" class="label">Altos</text>

  <rect x="570" y="420" width="230" height="145" class="card"/>
  <text x="603" y="480" class="metric">{totals['boletos']}</text>
  <text x="603" y="516" class="label">Boletos analisados</text>

  <rect x="820" y="420" width="230" height="145" class="card"/>
  <text x="853" y="480" class="metric">{totals['cnpjs_auxiliares']}</text>
  <text x="853" y="516" class="label">CNPJs auxiliares</text>

  <rect x="1070" y="420" width="510" height="145" class="card"/>
  <text x="1105" y="474" class="badgeTitle">Mensagem para apresentação</text>
  <text x="1105" y="504" class="badgeText">O MVP já demonstra ingestão, enriquecimento e priorização</text>
  <text x="1105" y="530" class="badgeText">de risco em dados reais com evidência visual e narrativa executiva.</text>

  <rect x="70" y="590" width="1510" height="360" class="table"/>
  <text x="105" y="638" class="head">ID boleto</text>
  <text x="515" y="638" class="head">Score</text>
  <text x="650" y="638" class="head">Nível</text>
  <text x="810" y="638" class="head">Valor</text>
  <text x="1060" y="638" class="head">Motivos dominantes</text>
  <line x1="100" y1="664" x2="1535" y2="664" stroke="#2e2a22" stroke-width="2"/>
  {''.join(rows)}

  <rect x="70" y="975" width="720" height="42" class="pill"/>
  <text x="98" y="1002" class="pillText">Saída real gerada a partir de resumo_mvp.json + alertas_priorizados.csv</text>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")
    return output_path

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    results, summary = analyze()
    csv_path = write_csv(results)
    json_path = write_json(summary)
    html_path = write_html(results, summary)
    architecture_path = write_architecture_svg()
    code_evidence_path = write_code_evidence_svg()
    screen_path = write_app_screen_svg(summary)

    print("MVP gerado com sucesso.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")
    print(f"Arquitetura SVG: {architecture_path}")
    print(f"Codigo SVG: {code_evidence_path}")
    print(f"Tela SVG: {screen_path}")
    print(f"Top alerta: {results[0].id_boleto} | score={results[0].risk_score:.2f} | nivel={results[0].risk_level}")


if __name__ == "__main__":
    main()
