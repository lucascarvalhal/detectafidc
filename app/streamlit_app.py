"""DetectaFIDC - Dashboard interativo (Sprint 4).

Le o output do pipeline (alertas_sprint4.csv + resumo_sprint4.json) e expoe
uma interface navegavel: visao geral, fila de alertas, motor heuristico vs
camada estatistica, e divergencias entre as duas leituras de risco.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
CSV_PATH = OUTPUT_DIR / "alertas_sprint4.csv"
JSON_PATH = OUTPUT_DIR / "resumo_sprint4.json"
LEGACY_CSV = OUTPUT_DIR / "alertas_priorizados.csv"

PRIMARY = "#0078D4"
ACCENT = "#D4FC79"
LEVEL_COLORS = {
    "critico": "#FF6B6B",
    "alto": "#FF6F00",
    "medio": "#FFD93D",
    "baixo": "#41B97D",
}

st.set_page_config(
    page_title="DetectaFIDC - Console de Risco",
    page_icon="*",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, dict | None]:
    if CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        summary = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.exists() else None
        return df, summary
    if LEGACY_CSV.exists():
        df = pd.read_csv(LEGACY_CSV)
        df.rename(columns={"risk_score": "risk_score_heuristico"}, inplace=True)
        df["statistical_score"] = 0
        df["statistical_level"] = "sem dados"
        df["score_consolidado"] = df["risk_score_heuristico"]
        df["z_combined"] = 0
        df["motivo_estatistico"] = "execute pipeline_sprint4.py para gerar"
        df["motivos_heuristicos"] = df["reasons"]
        return df, None
    return pd.DataFrame(), None


def render_header() -> None:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            """
            <h1 style='margin-bottom:4px;color:#0078D4;letter-spacing:-0.02em;'>
              DetectaFIDC
            </h1>
            <p style='color:#7a8595;margin-top:0;font-size:18px;'>
              Console de risco em FIDCs - Sprint 4 - Data Vision - FIAP 1TSCO
            </p>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div style='text-align:right;padding-top:18px;color:#7a8595;'>
              <strong style='color:#D4FC79;'>Solucao final</strong><br>
              Enterprise Challenge FIAP + Nuclea
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.divider()


def render_kpis(df: pd.DataFrame, summary: dict | None) -> None:
    total = len(df)
    criticos = (df["risk_level"] == "critico").sum()
    altos = (df["risk_level"] == "alto").sum()
    valor_total = df["amount"].astype(float).sum()
    valor_critico = df.loc[df["risk_level"] == "critico", "amount"].astype(float).sum()

    cols = st.columns(5)
    cols[0].metric("Boletos analisados", f"{total:,}".replace(",", "."))
    cols[1].metric("Alertas criticos", int(criticos))
    cols[2].metric("Alertas altos", int(altos))
    cols[3].metric("Valor total processado", f"R$ {valor_total/1e6:,.1f} mi".replace(",", "."))
    cols[4].metric("Valor em fila critica", f"R$ {valor_critico/1e3:,.0f} mil".replace(",", "."))

    if summary and "divergencias_heuristico_baixo_estatistico_alto" in summary:
        st.info(
            f"**{summary['divergencias_heuristico_baixo_estatistico_alto']}** boletos "
            f"apresentam divergencia entre as duas camadas: pontuacao heuristica baixa, "
            f"mas a camada estatistica Z-score sinaliza anomalia. Sao casos de atencao oculta "
            f"que escapam ao motor heuristico puro."
        )


def render_visao_geral(df: pd.DataFrame, summary: dict | None) -> None:
    st.subheader("Composicao da carteira por nivel de risco")
    col1, col2 = st.columns([1, 1])

    with col1:
        dist = (
            df.groupby("risk_level").size().reset_index(name="qtd").assign(
                ordem=lambda x: x["risk_level"].map({"critico": 0, "alto": 1, "medio": 2, "baixo": 3})
            ).sort_values("ordem")
        )
        fig = px.bar(
            dist,
            x="risk_level",
            y="qtd",
            color="risk_level",
            color_discrete_map=LEVEL_COLORS,
            text="qtd",
            title="Distribuicao heuristica (Sprint 3)",
        )
        fig.update_layout(
            showlegend=False,
            xaxis_title="Nivel",
            yaxis_title="Quantidade",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if "statistical_score" in df.columns and df["statistical_score"].astype(float).sum() > 0:
            fig2 = px.histogram(
                df,
                x="statistical_score",
                nbins=40,
                title="Distribuicao da camada estatistica (Z-score)",
                color_discrete_sequence=[PRIMARY],
            )
            fig2.update_layout(
                xaxis_title="Score estatistico (0-100)",
                yaxis_title="Quantidade",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                bargap=0.02,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Camada estatistica ainda nao calculada. Rode `python src/pipeline_sprint4.py`.")

    st.subheader("Volume por UF do pagador")
    uf_df = df.groupby("payer_uf").size().reset_index(name="qtd").sort_values("qtd", ascending=False).head(15)
    fig3 = px.bar(uf_df, x="payer_uf", y="qtd", title=None, color_discrete_sequence=[ACCENT])
    fig3.update_layout(
        xaxis_title="UF",
        yaxis_title="Boletos",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig3, use_container_width=True)


def render_fila_alertas(df: pd.DataFrame) -> None:
    st.subheader("Fila priorizada de alertas")

    col1, col2, col3 = st.columns(3)
    nivel = col1.multiselect(
        "Nivel de risco",
        ["critico", "alto", "medio", "baixo"],
        default=["critico", "alto"],
    )
    uf_options = sorted([u for u in df["payer_uf"].dropna().unique() if u != "NA"])
    uf_sel = col2.multiselect("UF do pagador", uf_options)
    busca = col3.text_input("Buscar (ID, motivo)", "")

    filtered = df.copy()
    if nivel:
        filtered = filtered[filtered["risk_level"].isin(nivel)]
    if uf_sel:
        filtered = filtered[filtered["payer_uf"].isin(uf_sel)]
    if busca:
        mask = (
            filtered["id_boleto"].astype(str).str.contains(busca, case=False, na=False)
            | filtered.get("motivos_heuristicos", pd.Series("", index=filtered.index)).astype(str).str.contains(busca, case=False, na=False)
        )
        filtered = filtered[mask]

    st.caption(f"{len(filtered):,} boletos no filtro atual".replace(",", "."))

    display_cols = [
        c
        for c in [
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
            "motivos_heuristicos",
        ]
        if c in filtered.columns
    ]
    display = filtered[display_cols].copy()
    if "id_boleto" in display.columns:
        display["id_boleto"] = display["id_boleto"].astype(str).str.slice(0, 16) + "..."
    if "amount" in display.columns:
        display["amount"] = display["amount"].astype(float).map(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.dataframe(display, use_container_width=True, hide_index=True, height=500)


def render_comparativo(df: pd.DataFrame, summary: dict | None) -> None:
    st.subheader("Heuristico vs estatistico")

    if "statistical_score" not in df.columns or df["statistical_score"].astype(float).sum() == 0:
        st.warning("Camada estatistica nao disponivel. Rode o pipeline da Sprint 4.")
        return

    df_plot = df.copy()
    df_plot["risk_score_heuristico"] = df_plot["risk_score_heuristico"].astype(float)
    df_plot["statistical_score"] = df_plot["statistical_score"].astype(float)

    fig = px.scatter(
        df_plot,
        x="risk_score_heuristico",
        y="statistical_score",
        color="risk_level",
        color_discrete_map=LEVEL_COLORS,
        hover_data=["id_boleto", "amount", "payer_uf"],
        opacity=0.6,
        title="Cada ponto e um boleto. Quadrante superior esquerdo: divergencia (heuristico nao viu).",
    )
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100, line=dict(color="gray", dash="dot"))
    fig.add_shape(type="line", x0=0, x1=100, y0=50, y1=50, line=dict(color="gray", dash="dot"))
    fig.update_layout(
        xaxis_title="Score heuristico (Sprint 3)",
        yaxis_title="Score estatistico Z-score (Sprint 4)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Casos com divergencia: heuristico baixo, estatistico alto**")
    divergentes = df_plot[
        (df_plot["risk_score_heuristico"] < 30) & (df_plot["statistical_score"] >= 50)
    ].sort_values("statistical_score", ascending=False).head(20)
    if divergentes.empty:
        st.caption("Nenhuma divergencia significativa no filtro atual.")
    else:
        cols_show = ["id_boleto", "risk_score_heuristico", "statistical_score", "amount", "payer_uf", "motivo_estatistico"]
        display = divergentes[[c for c in cols_show if c in divergentes.columns]].copy()
        if "id_boleto" in display.columns:
            display["id_boleto"] = display["id_boleto"].astype(str).str.slice(0, 18) + "..."
        st.dataframe(display, use_container_width=True, hide_index=True)


def render_metodo(summary: dict | None) -> None:
    st.subheader("Como o motor decide")
    st.markdown(
        """
        O DetectaFIDC combina duas leituras complementares de risco:

        **1. Motor heuristico (Sprint 3)** - regras explicaveis sobre cada boleto
        e seu enriquecimento com a base auxiliar de CNPJs. Pontua atraso, ausencia
        de baixa, valor nominal, recorrencia, liquidez, materialidade,
        inadimplencia e concentracao.

        **2. Camada estatistica Z-score (Sprint 4)** - calcula o desvio do valor
        nominal de cada boleto em relacao ao historico do pagador e do beneficiario.
        Pontua de 0 a 100 conforme o boleto se afasta da media da entidade.

        **Score consolidado** = 0,7 x heuristico + 0,3 x estatistico.

        A divergencia entre as duas camadas e proposital: o heuristico captura
        o conhecido (regras de negocio), o estatistico captura o anomalo
        (comportamento que destoa do historico da propria entidade).
        """
    )
    if summary and "statistical_layer" in summary:
        layer = summary["statistical_layer"]
        st.json(layer)


def main() -> None:
    df, summary = load_data()
    render_header()

    if df.empty:
        st.error("Nenhum CSV de saida encontrado em sprint4/output/. Rode `python src/pipeline_sprint4.py` antes.")
        return

    section = st.sidebar.radio(
        "Navegacao",
        ["Visao geral", "Fila de alertas", "Heuristico vs estatistico", "Metodo"],
        index=0,
    )

    st.sidebar.divider()
    st.sidebar.caption("Equipe Data Vision")
    st.sidebar.markdown(
        """
        - Andreza Dias Almeida Batista
        - Kaue Marcal Pla Gil
        - Lucas Carvalhal Pereira dos Santos
        - Maria Eduarda Carmo da Silva
        """
    )

    render_kpis(df, summary)
    st.divider()

    if section == "Visao geral":
        render_visao_geral(df, summary)
    elif section == "Fila de alertas":
        render_fila_alertas(df)
    elif section == "Heuristico vs estatistico":
        render_comparativo(df, summary)
    elif section == "Metodo":
        render_metodo(summary)


if __name__ == "__main__":
    main()
