"""Pipeline da Sprint 4: combina motor heuristico (Sprint 3) com camada estatistica Z-score.

Le a massa oficial do challenge (ZIP), reaproveita o motor heuristico do MVP
e adiciona um escore estatistico complementar baseado em Z-score por entidade.
Gera saidas enriquecidas em CSV e JSON consumidas pelo dashboard Streamlit.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import motor_heuristico as heuristico  # noqa: E402
from motor_estatistico import analyze_boletos as analyze_estatistico  # noqa: E402


def read_boletos_from_zip(zip_path: Path) -> list[dict[str, str]]:
    with ZipFile(zip_path) as zip_file:
        raw = zip_file.read("base_boletos_fiap.csv").decode("utf-8", "ignore")
    return list(csv.DictReader(raw.splitlines()))


def find_zip() -> Path:
    candidates = [
        DATA_DIR / "Massa_Dados_Challgenge_Nuclea_v1.zip",
        ROOT.parent.parent / "Massa_Dados_Challgenge_Nuclea_v1.zip",
        Path("/mnt/c/Users/carva/Downloads/faculdade/Massa_Dados_Challgenge_Nuclea_v1.zip"),
        Path("/home/carva/pessoal/fiap/Massa_Dados_Challgenge_Nuclea_v1.zip"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Massa_Dados_Challgenge_Nuclea_v1.zip nao encontrada. "
        "Coloque o arquivo em sprint4/data/ ou ajuste o caminho."
    )


def run() -> dict[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = find_zip()

    heuristico.ZIP_PATH = zip_path
    heuristico.OUTPUT_DIR = OUTPUT_DIR

    print(f"[1/4] Lendo massa: {zip_path.name}")
    boletos = read_boletos_from_zip(zip_path)
    print(f"     {len(boletos)} boletos carregados")

    print("[2/4] Executando motor heuristico (Sprint 3)")
    heuristic_results, heuristic_summary = heuristico.analyze()

    print("[3/4] Aplicando camada estatistica Z-score")
    statistical_results, statistical_summary = analyze_estatistico(boletos)
    stat_by_id = {item.id_boleto: item for item in statistical_results}

    print("[4/4] Consolidando e exportando saidas")
    csv_path = OUTPUT_DIR / "alertas_sprint4.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "rank",
                "id_boleto",
                "risk_score_heuristico",
                "risk_level",
                "statistical_score",
                "statistical_level",
                "score_consolidado",
                "amount",
                "delay_days",
                "payer_uf",
                "beneficiary_uf",
                "tipo_especie",
                "baixa_missing",
                "z_payer",
                "z_beneficiary",
                "z_combined",
                "motivo_estatistico",
                "motivos_heuristicos",
            ]
        )
        consolidated: list[tuple[float, dict]] = []
        for item in heuristic_results:
            stat = stat_by_id.get(item.id_boleto)
            stat_score = stat.statistical_score if stat else 0.0
            stat_level = stat.statistical_level if stat else "sem dados"
            z_p = stat.z_payer if stat else None
            z_b = stat.z_beneficiary if stat else None
            z_c = stat.z_combined if stat else 0.0
            motivo_est = stat.motivo_estatistico if stat else ""
            consolidated_score = round(0.7 * item.risk_score + 0.3 * stat_score, 2)
            consolidated.append(
                (
                    consolidated_score,
                    {
                        "row": [
                            item.id_boleto,
                            item.risk_score,
                            item.risk_level,
                            stat_score,
                            stat_level,
                            consolidated_score,
                            f"{item.amount:.2f}",
                            item.delay_days if item.delay_days is not None else "",
                            item.payer_uf,
                            item.beneficiary_uf,
                            item.especie,
                            "sim" if item.baixa_missing else "nao",
                            z_p if z_p is not None else "",
                            z_b if z_b is not None else "",
                            z_c,
                            motivo_est,
                            "; ".join(item.reasons),
                        ]
                    },
                )
            )
        consolidated.sort(key=lambda x: x[0], reverse=True)
        for rank, (_, payload) in enumerate(consolidated, start=1):
            writer.writerow([rank, *payload["row"]])
    print(f"     CSV: {csv_path.name}")

    divergencias = sum(
        1
        for item in heuristic_results
        if (stat_by_id.get(item.id_boleto) and stat_by_id[item.id_boleto].statistical_score >= 50 and item.risk_level == "baixo")
    )

    consolidado_count = Counter()
    for score_consolidado, _ in consolidated:
        if score_consolidado >= 75:
            consolidado_count["critico"] += 1
        elif score_consolidado >= 50:
            consolidado_count["alto"] += 1
        elif score_consolidado >= 30:
            consolidado_count["medio"] += 1
        else:
            consolidado_count["baixo"] += 1

    full_summary = {
        "project": "DetectaFIDC Sprint 4",
        "version": "1.0",
        "analysis_date": heuristic_summary["analysis_date"],
        "source_zip": zip_path.name,
        "totals": heuristic_summary["totals"],
        "quality": heuristic_summary["quality"],
        "risk_distribution_heuristico": heuristic_summary["risk_distribution"],
        "risk_distribution_consolidado": [
            {
                "level": level,
                "count": consolidado_count.get(level, 0),
                "percent": round((consolidado_count.get(level, 0) / len(heuristic_results)) * 100, 2),
            }
            for level in ["critico", "alto", "medio", "baixo"]
        ],
        "statistical_layer": statistical_summary,
        "divergencias_heuristico_baixo_estatistico_alto": divergencias,
        "top_reasons": heuristic_summary["top_reasons"],
        "operational_signals": heuristic_summary["operational_signals"],
        "observations": [
            "Sprint 4 combina motor heuristico (Sprint 3) com camada estatistica Z-score por entidade.",
            "Score consolidado: 0.7 heuristico + 0.3 estatistico.",
            "Divergencias entre as duas camadas indicam casos de atencao oculta.",
            "Pipeline mantem zero dependencias externas na camada analitica.",
        ],
    }

    json_path = OUTPUT_DIR / "resumo_sprint4.json"
    json_path.write_text(json.dumps(full_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"     JSON: {json_path.name}")
    print(f"\nResumo: {len(heuristic_results)} boletos. {divergencias} casos com divergencia (heuristico baixo, estatistico alto).")

    return {"csv": csv_path, "json": json_path}


if __name__ == "__main__":
    run()
