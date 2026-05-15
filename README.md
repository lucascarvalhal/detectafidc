---
title: DetectaFIDC
emoji: "📊"
colorFrom: blue
colorTo: gray
sdk: streamlit
sdk_version: 1.40.0
app_file: app/streamlit_app.py
pinned: false
license: mit
short_description: Console de risco em FIDCs - Sprint 4 FIAP+Nuclea
---

# DetectaFIDC, Sprint 4

Solução final do desafio Enterprise Challenge FIAP + Núclea, turma 1TSCO, equipe Data Vision.

## Conteúdo

- `src/motor_heuristico.py`, motor de risco da Sprint 3 em Python puro.
- `src/motor_estatistico.py`, camada estatística Z-score por sacado e cedente.
- `src/pipeline_sprint4.py`, pipeline que combina as duas camadas.
- `app/streamlit_app.py`, dashboard interativo.
- `output/alertas_sprint4.csv` e `output/resumo_sprint4.json`, evidências pré-geradas.
- `requirements.txt` e `.streamlit/config.toml`, infraestrutura.

## Rodar localmente

```bash
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

O dashboard abre em `http://localhost:8501`.

## Regerar o output a partir da massa oficial

Coloque `Massa_Dados_Challgenge_Nuclea_v1.zip` em `data/` e execute:

```bash
python src/pipeline_sprint4.py
```

Isso reconstrói `output/alertas_sprint4.csv` e `output/resumo_sprint4.json`.

## Estrutura do score

- `risk_score_heuristico`, motor heurístico da Sprint 3, 0 a 100.
- `statistical_score`, camada estatística Z-score por entidade, 0 a 100.
- `score_consolidado = 0,7 * heuristico + 0,3 * estatistico`.
- `motivo_estatistico` documenta o desvio em relação ao sacado e ao cedente.

## Equipe Data Vision

- Andreza Dias Almeida Batista, RM 568336
- Kauê Marçal Pla Gil, RM 567950
- Lucas Carvalhal Pereira dos Santos, RM 567524
- Maria Eduarda Carmo da Silva, RM 568578
