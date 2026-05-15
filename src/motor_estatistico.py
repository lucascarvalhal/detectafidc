"""Camada estatistica complementar ao motor heuristico da Sprint 3.

Calcula um escore de anomalia por boleto a partir do desvio do valor nominal
em relacao ao historico do sacado (pagador) e do cedente (beneficiario). Usa
apenas biblioteca padrao do Python para manter a mesma filosofia da Sprint 3
(zero dependencias externas no pipeline analitico).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable


@dataclass
class EntityStats:
    n: int
    mean: float
    std: float


@dataclass
class StatisticalResult:
    id_boleto: str
    z_payer: float | None
    z_beneficiary: float | None
    z_combined: float
    statistical_score: float
    statistical_level: str
    motivo_estatistico: str


def build_entity_stats(rows: Iterable[dict[str, str]], key: str, value_key: str = "vlr_nominal") -> dict[str, EntityStats]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        try:
            value = float(str(row.get(value_key, "0")).replace(",", "."))
        except ValueError:
            continue
        if value <= 0:
            continue
        grouped[row.get(key, "")].append(value)
    stats: dict[str, EntityStats] = {}
    for entity, values in grouped.items():
        if len(values) >= 2:
            stats[entity] = EntityStats(n=len(values), mean=mean(values), std=pstdev(values))
        elif values:
            stats[entity] = EntityStats(n=1, mean=values[0], std=0.0)
    return stats


def z_score(value: float, stats: EntityStats | None) -> float | None:
    if stats is None or stats.std <= 0:
        return None
    return (value - stats.mean) / stats.std


def map_z_to_score(z_combined: float) -> float:
    """Z=0 -> 0, Z=4 -> 100, saturando entre 0 e 100."""
    return round(min(100.0, max(0.0, abs(z_combined) * 25.0)), 2)


def statistical_level(score: float) -> str:
    if score >= 75:
        return "anomalia forte"
    if score >= 50:
        return "anomalia moderada"
    if score >= 25:
        return "desvio leve"
    return "comportamento normal"


def describe(z_payer: float | None, z_beneficiary: float | None) -> str:
    partes: list[str] = []
    if z_payer is not None:
        sinal = "acima" if z_payer > 0 else "abaixo"
        partes.append(f"valor {abs(z_payer):.2f} desvios {sinal} da media do pagador")
    if z_beneficiary is not None:
        sinal = "acima" if z_beneficiary > 0 else "abaixo"
        partes.append(f"valor {abs(z_beneficiary):.2f} desvios {sinal} da media do beneficiario")
    if not partes:
        return "historico insuficiente para teste estatistico"
    return "; ".join(partes)


def analyze_boletos(
    boletos: list[dict[str, str]],
) -> tuple[list[StatisticalResult], dict[str, object]]:
    payer_stats = build_entity_stats(boletos, "id_pagador")
    beneficiary_stats = build_entity_stats(boletos, "id_beneficiario")

    results: list[StatisticalResult] = []
    z_combined_values: list[float] = []

    for row in boletos:
        try:
            value = float(str(row.get("vlr_nominal", "0")).replace(",", "."))
        except ValueError:
            value = 0.0

        z_p = z_score(value, payer_stats.get(row.get("id_pagador", "")))
        z_b = z_score(value, beneficiary_stats.get(row.get("id_beneficiario", "")))

        candidates = [z for z in (z_p, z_b) if z is not None]
        z_combined = max((abs(z) for z in candidates), default=0.0)
        score = map_z_to_score(z_combined)

        results.append(
            StatisticalResult(
                id_boleto=row.get("id_boleto", ""),
                z_payer=round(z_p, 4) if z_p is not None else None,
                z_beneficiary=round(z_b, 4) if z_b is not None else None,
                z_combined=round(z_combined, 4),
                statistical_score=score,
                statistical_level=statistical_level(score),
                motivo_estatistico=describe(z_p, z_b),
            )
        )
        z_combined_values.append(z_combined)

    summary = {
        "method": "Z-score por entidade (sacado e cedente)",
        "n_pagadores_modelados": len(payer_stats),
        "n_beneficiarios_modelados": len(beneficiary_stats),
        "z_medio": round(mean(z_combined_values), 4) if z_combined_values else 0.0,
        "z_p90": round(sorted(z_combined_values)[int(0.9 * len(z_combined_values))], 4) if z_combined_values else 0.0,
        "z_p99": round(sorted(z_combined_values)[int(0.99 * len(z_combined_values))], 4) if z_combined_values else 0.0,
        "distribuicao_estatistica": {
            "anomalia_forte": sum(1 for r in results if r.statistical_score >= 75),
            "anomalia_moderada": sum(1 for r in results if 50 <= r.statistical_score < 75),
            "desvio_leve": sum(1 for r in results if 25 <= r.statistical_score < 50),
            "normal": sum(1 for r in results if r.statistical_score < 25),
        },
    }
    return results, summary
