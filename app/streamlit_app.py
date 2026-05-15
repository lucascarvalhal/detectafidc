"""DetectaFIDC, dashboard interativo da Sprint 4."""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_option_menu import option_menu


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
CSV_PATH = OUTPUT_DIR / "alertas_sprint4.csv"
JSON_PATH = OUTPUT_DIR / "resumo_sprint4.json"
LEGACY_CSV = OUTPUT_DIR / "alertas_priorizados.csv"

LEVEL_COLORS = {
    "critico": "#DA1E28",
    "alto": "#FF832B",
    "medio": "#F1C21B",
    "baixo": "#24A148",
}
LEVEL_LABEL = {
    "critico": "Crítico",
    "alto": "Alto",
    "medio": "Médio",
    "baixo": "Baixo",
}

PALETTES = {
    "dark": {
        "primary": "#4589FF",
        "accent": "#42BE65",
        "text": "#F4F4F4",
        "muted": "#A8A8A8",
        "bg": "#161616",
        "panel": "#262626",
        "panel_2": "#393939",
        "border": "#393939",
        "border_strong": "#525252",
        "card_bg": "#262626",
        "title_color": "#F4F4F4",
        "plotly_template": "plotly_dark",
    },
    "light": {
        "primary": "#0F62FE",
        "accent": "#198038",
        "text": "#161616",
        "muted": "#525252",
        "bg": "#F4F4F4",
        "panel": "#FFFFFF",
        "panel_2": "#F4F4F4",
        "border": "#E0E0E0",
        "border_strong": "#C6C6C6",
        "card_bg": "#FFFFFF",
        "title_color": "#161616",
        "plotly_template": "plotly_white",
    },
}


st.set_page_config(
    page_title="DetectaFIDC, Console de Risco",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_theme(theme: str) -> dict:
    p = PALETTES[theme]
    css = f"""
    <style>
      .stApp {{ background: {p['bg']} !important; color: {p['text']} !important; }}
      .block-container {{ padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1600px; }}

      section[data-testid="stSidebar"] {{
        background: {p['panel']} !important;
        border-right: 1px solid {p['border']};
      }}
      section[data-testid="stSidebar"] * {{ color: {p['text']} !important; }}

      h1, h2, h3, h4, h5, h6 {{ color: {p['text']} !important; letter-spacing: -0.01em; }}
      p, span, label, div {{ color: {p['text']}; }}
      .stMarkdown, .stCaption {{ color: {p['text']} !important; }}

      [data-testid="stMetricValue"] {{ color: {p['text']} !important; }}
      [data-testid="stMetricLabel"] {{ color: {p['muted']} !important; }}

      .stDataFrame {{ background: {p['panel']} !important; border: 1px solid {p['border']}; }}
      .stDataFrame [role="grid"] {{ color: {p['text']} !important; }}

      .stTextInput input, .stNumberInput input, .stSelectbox > div, .stMultiSelect > div {{
        background: {p['panel']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
      }}

      .stSlider [data-baseweb="slider"] {{ color: {p['text']}; }}
      .stSlider [role="slider"] {{ background: {p['primary']} !important; }}

      .stCheckbox label {{ color: {p['text']} !important; }}

      .js-plotly-plot .gtitle {{ fill: {p['title_color']} !important; }}
      .js-plotly-plot .xtitle, .js-plotly-plot .ytitle {{ fill: {p['muted']} !important; }}
      .js-plotly-plot .xtick text, .js-plotly-plot .ytick text {{ fill: {p['muted']} !important; }}

      .carbon-card {{
        background: {p['card_bg']};
        border: 1px solid {p['border']};
        padding: 20px 22px;
        position: relative;
        min-height: 124px;
        transition: border-color 0.18s ease;
      }}
      .carbon-card:hover {{ border-color: {p['border_strong']}; }}
      .carbon-card .eyebrow {{
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {p['muted']};
        margin-bottom: 6px;
        font-weight: 600;
      }}
      .carbon-card .value {{
        font-size: 38px;
        font-weight: 300;
        color: {p['text']};
        line-height: 1.05;
        font-family: 'IBM Plex Sans', 'Inter', sans-serif;
      }}
      .carbon-card .delta {{
        font-size: 12px;
        color: {p['muted']};
        margin-top: 8px;
      }}
      .carbon-card .accent-bar {{
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: {p['primary']};
      }}
      .carbon-card.attention .accent-bar {{ background: {LEVEL_COLORS['critico']}; }}
      .carbon-card.warning .accent-bar {{ background: {LEVEL_COLORS['alto']}; }}
      .carbon-card.success .accent-bar {{ background: {p['accent']}; }}

      .info-banner {{
        background: {p['panel_2']};
        border-left: 3px solid {p['primary']};
        padding: 14px 18px;
        margin: 18px 0;
        font-size: 14px;
        color: {p['text']};
      }}
      .info-banner strong {{ color: {p['primary']}; }}

      .section-header {{
        margin: 24px 0 14px;
        padding-bottom: 8px;
        border-bottom: 1px solid {p['border']};
      }}
      .section-header .eyebrow {{
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {p['primary']};
        font-weight: 600;
        margin-bottom: 4px;
      }}
      .section-header h2 {{
        font-size: 22px;
        font-weight: 400;
        margin: 0;
        color: {p['text']};
      }}

      .stRadio > label, .stMultiSelect > label, .stTextInput > label,
      .stSelectbox > label, .stSlider > label, .stNumberInput > label,
      .stCheckbox > label {{
        color: {p['text']} !important;
        font-size: 13px !important;
        font-weight: 500 !important;
      }}

      div[data-testid="stMetric"] {{
        background: {p['card_bg']};
        border: 1px solid {p['border']};
        padding: 16px 18px;
      }}

      /* st.json e blocos de código, garantir contraste em ambos os temas */
      [data-testid="stJson"], .stJson, pre, code {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
      }}
      [data-testid="stJson"] *, .stJson *, pre *, code * {{
        color: {p['text']} !important;
      }}
      .stJson .object-key, .stJson .object-key-val span {{
        color: {p['accent']} !important;
      }}
      .stJson .variable-value, .stJson .number {{
        color: {p['primary']} !important;
      }}

      /* Botões, download e ações, sempre com contraste */
      .stButton > button, .stDownloadButton > button {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border_strong']} !important;
        border-radius: 0 !important;
        font-weight: 500 !important;
        transition: background 0.15s ease, border-color 0.15s ease;
      }}
      .stButton > button:hover, .stDownloadButton > button:hover {{
        background: {p['primary']} !important;
        color: #FFFFFF !important;
        border-color: {p['primary']} !important;
      }}
      .stButton > button:focus, .stDownloadButton > button:focus {{
        outline: 2px solid {p['primary']} !important;
        outline-offset: 2px;
        box-shadow: none !important;
      }}
      .stButton > button:active, .stDownloadButton > button:active {{
        background: {p['border_strong']} !important;
      }}

      /* Expander, header e fundo */
      [data-testid="stExpander"] {{
        background: {p['card_bg']} !important;
        border: 1px solid {p['border']} !important;
      }}
      [data-testid="stExpander"] summary {{ color: {p['text']} !important; }}
      [data-testid="stExpander"] summary:hover {{ background: {p['panel_2']} !important; }}
      [data-testid="stExpander"] svg {{ fill: {p['muted']} !important; }}

      /* Banners nativos do Streamlit, info/warning/success/error */
      [data-testid="stNotification"], [data-testid="stAlert"] {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border-left: 3px solid {p['primary']} !important;
      }}
      [data-testid="stNotification"] *, [data-testid="stAlert"] * {{
        color: {p['text']} !important;
      }}

      /* DataFrame headers, sem azul */
      .stDataFrame thead th {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border-bottom: 2px solid {p['border_strong']} !important;
      }}
      .stDataFrame tbody td {{
        background: {p['card_bg']} !important;
        color: {p['text']} !important;
      }}
      .stDataFrame tbody tr:hover td {{
        background: {p['panel_2']} !important;
      }}

      /* Multiselect tags, sem azul nativo */
      [data-baseweb="tag"] {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
      }}
      [data-baseweb="tag"] svg {{ fill: {p['text']} !important; }}

      /* Segmented control, neutralizar azul */
      [data-testid="stSegmentedControl"] button {{
        background: {p['panel_2']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
      }}
      [data-testid="stSegmentedControl"] button[aria-pressed="true"],
      [data-testid="stSegmentedControl"] button[aria-checked="true"] {{
        background: {p['text']} !important;
        color: {p['bg']} !important;
        border-color: {p['text']} !important;
      }}

      /* Foco geral, sem ring azul Streamlit */
      *:focus-visible {{
        outline-color: {p['muted']} !important;
      }}

      /* Limpar qualquer cor azul residual do option_menu */
      section[data-testid="stSidebar"] nav,
      section[data-testid="stSidebar"] nav a,
      section[data-testid="stSidebar"] .nav-link,
      section[data-testid="stSidebar"] .nav-pills,
      section[data-testid="stSidebar"] .nav-pills .nav-link {{
        background-color: transparent !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
      }}
      section[data-testid="stSidebar"] .nav-pills .nav-link.active,
      section[data-testid="stSidebar"] .nav-pills .nav-link:hover {{
        background-color: {p['panel_2']} !important;
        color: {p['text']} !important;
        border: none !important;
        box-shadow: none !important;
      }}
      section[data-testid="stSidebar"] .nav-pills .nav-link:focus {{
        outline: none !important;
        box-shadow: none !important;
      }}

      /* Neutralizar bolinhas azuis dos radio buttons como fallback */
      section[data-testid="stSidebar"] div[role="radiogroup"] label svg {{
        fill: {p['muted']} !important;
      }}
      section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{
        background-color: {p['panel_2']} !important;
        border-color: {p['border']} !important;
      }}
      section[data-testid="stSidebar"] div[role="radiogroup"] input:checked + div {{
        background-color: {p['text']} !important;
        border-color: {p['text']} !important;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    return p


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


def render_header(p: dict) -> None:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            f"""
            <div style='margin-bottom:6px;'>
              <span style='color:{p['primary']};font-size:11px;letter-spacing:0.08em;text-transform:uppercase;font-weight:600;'>
                Enterprise Challenge, FIAP + Núclea
              </span>
            </div>
            <h1 style='margin:0;color:{p['text']};letter-spacing:-0.02em;font-weight:300;font-size:42px;'>
              DetectaFIDC
            </h1>
            <p style='color:{p['muted']};margin:4px 0 0;font-size:15px;'>
              Console de risco em FIDCs, Sprint 4, equipe Data Vision, turma 1TSCO
            </p>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div style='text-align:right;padding-top:8px;'>
              <div style='color:{p['accent']};font-size:11px;letter-spacing:0.08em;text-transform:uppercase;font-weight:600;'>
                Solução final
              </div>
              <div style='color:{p['muted']};font-size:13px;margin-top:6px;'>
                Maio de 2026
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def carbon_card(p: dict, eyebrow: str, value: str, note: str = "", variant: str = "default") -> str:
    variant_class = {"default": "", "attention": "attention", "warning": "warning", "success": "success"}.get(variant, "")
    return f"""
    <div class='carbon-card {variant_class}'>
      <div class='accent-bar'></div>
      <div class='eyebrow'>{eyebrow}</div>
      <div class='value'>{value}</div>
      {'<div class="delta">' + note + '</div>' if note else ''}
    </div>
    """


def section_header(p: dict, eyebrow: str, title: str) -> None:
    st.markdown(
        f"""
        <div class='section-header'>
          <div class='eyebrow'>{eyebrow}</div>
          <h2>{title}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(df: pd.DataFrame, summary: dict | None, p: dict) -> None:
    total = len(df)
    criticos = int((df["risk_level"] == "critico").sum())
    altos = int((df["risk_level"] == "alto").sum())
    valor_total = df["amount"].astype(float).sum()
    valor_critico = df.loc[df["risk_level"] == "critico", "amount"].astype(float).sum()

    cards = [
        carbon_card(p, "Boletos analisados", f"{total:,}".replace(",", "."),
                    "Massa oficial do desafio"),
        carbon_card(p, "Alertas críticos", f"{criticos}",
                    "Score acima de 75", variant="attention"),
        carbon_card(p, "Alertas altos", f"{altos}",
                    "Score entre 50 e 74", variant="warning"),
        carbon_card(p, "Valor total processado", f"R$ {valor_total/1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", "."),
                    "Soma do valor nominal"),
        carbon_card(p, "Valor em fila crítica", f"R$ {valor_critico/1e3:,.0f} mil".replace(",", "X").replace(".", ",").replace("X", "."),
                    "Concentrado nos boletos críticos", variant="attention"),
    ]
    cols = st.columns(5, gap="small")
    for col, html in zip(cols, cards):
        with col:
            st.markdown(html, unsafe_allow_html=True)

    if summary and "divergencias_heuristico_baixo_estatistico_alto" in summary:
        st.markdown(
            f"""
            <div class='info-banner'>
              <strong>{summary['divergencias_heuristico_baixo_estatistico_alto']} boletos</strong> apresentam
              divergência entre as duas camadas. A pontuação heurística é baixa, mas a camada estatística
              Z-score sinaliza anomalia. São casos de atenção oculta que escapariam ao motor heurístico puro.
            </div>
            """,
            unsafe_allow_html=True,
        )


def style_fig(fig, p: dict, *, title: str | None = None) -> None:
    fig.update_layout(
        template=p["plotly_template"],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=p["text"], family="IBM Plex Sans, Inter, sans-serif"),
        title=dict(text=title, font=dict(color=p["title_color"], size=15)) if title else None,
        title_font_color=p["title_color"],
        xaxis=dict(gridcolor=p["border"], zerolinecolor=p["border"], color=p["muted"]),
        yaxis=dict(gridcolor=p["border"], zerolinecolor=p["border"], color=p["muted"]),
        legend=dict(font=dict(color=p["text"])),
        margin=dict(l=20, r=20, t=50, b=40),
    )


def render_visao_geral(df: pd.DataFrame, summary: dict | None, p: dict) -> None:
    section_header(p, "Composição da carteira", "Distribuição por nível de risco")
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        dist = (
            df.groupby("risk_level").size().reset_index(name="qtd")
            .assign(ordem=lambda x: x["risk_level"].map({"critico": 0, "alto": 1, "medio": 2, "baixo": 3}))
            .sort_values("ordem")
        )
        dist["risk_level_label"] = dist["risk_level"].map(LEVEL_LABEL)
        fig = px.bar(
            dist, x="risk_level_label", y="qtd",
            color="risk_level", color_discrete_map=LEVEL_COLORS, text="qtd",
        )
        fig.update_traces(textposition="outside", textfont_color=p["text"])
        style_fig(fig, p, title="Distribuição heurística, motor da Sprint 3")
        fig.update_layout(showlegend=False, xaxis_title="Nível", yaxis_title="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if "statistical_score" in df.columns and df["statistical_score"].astype(float).sum() > 0:
            fig2 = px.histogram(
                df, x="statistical_score", nbins=40,
                color_discrete_sequence=[p["primary"]],
            )
            style_fig(fig2, p, title="Distribuição da camada estatística, Z-score")
            fig2.update_layout(xaxis_title="Score estatístico, 0 a 100", yaxis_title="Quantidade", bargap=0.02)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Camada estatística ainda não calculada. Rode `python src/pipeline_sprint4.py`.")

    section_header(p, "Geografia operacional", "Volume por UF do pagador")
    uf_df = df.groupby("payer_uf").size().reset_index(name="qtd").sort_values("qtd", ascending=False).head(15)
    fig3 = px.bar(uf_df, x="payer_uf", y="qtd", color_discrete_sequence=[p["accent"]])
    style_fig(fig3, p, title="Top 15 UFs por volume de boletos")
    fig3.update_layout(xaxis_title="UF", yaxis_title="Boletos")
    st.plotly_chart(fig3, use_container_width=True)


def render_fila_alertas(df: pd.DataFrame, p: dict) -> None:
    section_header(p, "Operação", "Fila priorizada de alertas")

    col1, col2, col3 = st.columns(3, gap="medium")
    nivel = col1.multiselect(
        "Nível de risco",
        ["critico", "alto", "medio", "baixo"],
        default=["critico", "alto"],
        format_func=lambda x: LEVEL_LABEL[x],
    )
    uf_options = sorted([u for u in df["payer_uf"].dropna().unique() if u != "NA"])
    uf_sel = col2.multiselect("UF do pagador", uf_options)
    busca = col3.text_input("Buscar por ID ou motivo", "")

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

    st.caption(f"{len(filtered):,} boletos no filtro atual.".replace(",", "."))

    display_cols = [
        c for c in [
            "rank", "id_boleto", "risk_score_heuristico", "risk_level",
            "statistical_score", "statistical_level", "score_consolidado",
            "amount", "delay_days", "payer_uf", "motivos_heuristicos",
        ] if c in filtered.columns
    ]
    display = filtered[display_cols].copy()
    if "id_boleto" in display.columns:
        display["id_boleto"] = display["id_boleto"].astype(str).str.slice(0, 16) + "..."
    if "amount" in display.columns:
        display["amount"] = display["amount"].astype(float).map(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
    if "risk_level" in display.columns:
        display["risk_level"] = display["risk_level"].map(LEVEL_LABEL)

    st.dataframe(display, use_container_width=True, hide_index=True, height=520)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Exportar fila filtrada em CSV",
        data=csv_bytes,
        file_name="detectafidc_fila_filtrada.csv",
        mime="text/csv",
    )


def render_comparativo(df: pd.DataFrame, summary: dict | None, p: dict) -> None:
    section_header(p, "Inteligência cruzada", "Heurístico contra estatístico")

    if "statistical_score" not in df.columns or df["statistical_score"].astype(float).sum() == 0:
        st.warning("Camada estatística não disponível. Rode o pipeline da Sprint 4.")
        return

    df_plot = df.copy()
    df_plot["risk_score_heuristico"] = df_plot["risk_score_heuristico"].astype(float)
    df_plot["statistical_score"] = df_plot["statistical_score"].astype(float)
    df_plot["risk_level_label"] = df_plot["risk_level"].map(LEVEL_LABEL)

    fig = px.scatter(
        df_plot,
        x="risk_score_heuristico",
        y="statistical_score",
        color="risk_level",
        color_discrete_map=LEVEL_COLORS,
        hover_data=["id_boleto", "amount", "payer_uf"],
        opacity=0.7,
    )
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100, line=dict(color=p["border_strong"], dash="dot"))
    fig.add_shape(type="line", x0=0, x1=100, y0=50, y1=50, line=dict(color=p["border_strong"], dash="dot"))
    style_fig(fig, p, title="Cada ponto é um boleto. Quadrante superior esquerdo indica divergência, ou seja, o heurístico não viu")
    fig.update_layout(
        xaxis_title="Score heurístico, Sprint 3",
        yaxis_title="Score estatístico Z-score, Sprint 4",
    )
    st.plotly_chart(fig, use_container_width=True)

    section_header(p, "Atenção oculta", "Casos com divergência, heurístico baixo, estatístico alto")
    divergentes = df_plot[
        (df_plot["risk_score_heuristico"] < 30) & (df_plot["statistical_score"] >= 50)
    ].sort_values("statistical_score", ascending=False).head(20)
    if divergentes.empty:
        st.caption("Nenhuma divergência significativa no filtro atual.")
    else:
        cols_show = ["id_boleto", "risk_score_heuristico", "statistical_score", "amount", "payer_uf", "motivo_estatistico"]
        display = divergentes[[c for c in cols_show if c in divergentes.columns]].copy()
        if "id_boleto" in display.columns:
            display["id_boleto"] = display["id_boleto"].astype(str).str.slice(0, 18) + "..."
        st.dataframe(display, use_container_width=True, hide_index=True)


def simular_boleto(
    valor_nominal: float,
    delay_days: int,
    baixa_missing: bool,
    payer_volume: int,
    beneficiary_volume: int,
    payer_liquidity: float,
    payer_inadimplencia: float,
    valor_percentil: float,
    z_combined: float,
) -> dict:
    score = 0.0
    reasons: list[str] = []

    if baixa_missing:
        score += 18
        reasons.append("boleto sem valor de baixa")

    if delay_days > 0:
        score += min(20.0, delay_days / 3)
        reasons.append(f"pagamento com atraso de {delay_days} dias")

    if valor_percentil >= 0.95:
        score += 14
        reasons.append("valor nominal entre os 5% maiores da base")
    elif valor_percentil >= 0.85:
        score += 8
        reasons.append("valor nominal elevado")

    if payer_volume >= 8:
        score += 8
        reasons.append("pagador com alta recorrência de boletos")
    elif payer_volume >= 5:
        score += 4
        reasons.append("pagador com recorrência relevante")

    if beneficiary_volume >= 8:
        score += 6
        reasons.append("beneficiário com alta concentração operacional")

    if payer_liquidity < 0.45:
        score += 10
        reasons.append("pagador com baixa liquidez")
    elif payer_liquidity < 0.65:
        score += 4
        reasons.append("pagador com liquidez moderada")

    if payer_inadimplencia > 0.20:
        score += 10
        reasons.append("indicador de inadimplência elevado")
    elif payer_inadimplencia > 0.08:
        score += 5
        reasons.append("indicador de inadimplência moderado")

    heuristico = round(min(score, 100.0), 2)
    nivel_heur = ("critico" if heuristico >= 75 else "alto" if heuristico >= 50 else "medio" if heuristico >= 30 else "baixo")

    estatistico = round(min(100.0, abs(z_combined) * 25.0), 2)
    consolidado = round(0.7 * heuristico + 0.3 * estatistico, 2)
    nivel_cons = ("critico" if consolidado >= 75 else "alto" if consolidado >= 50 else "medio" if consolidado >= 30 else "baixo")

    return {
        "heuristico": heuristico,
        "nivel_heuristico": nivel_heur,
        "estatistico": estatistico,
        "consolidado": consolidado,
        "nivel_consolidado": nivel_cons,
        "reasons": reasons,
    }


def render_simulador(df: pd.DataFrame, p: dict) -> None:
    section_header(p, "Sandbox", "Simulador de risco de boleto")
    st.caption("Preencha os campos do boleto e veja o score dos dois motores em tempo real, com os motivos legíveis.")

    col_left, col_right = st.columns([1.05, 1], gap="large")

    with col_left:
        st.markdown("**Dados do boleto**")
        valor_nominal = st.number_input("Valor nominal em R$", min_value=0.0, value=25000.0, step=1000.0, format="%.2f")
        delay_days = st.slider("Dias de atraso no pagamento", min_value=0, max_value=365, value=60)
        baixa_missing = st.checkbox("Boleto sem valor de baixa", value=False)

        st.markdown("**Perfil do pagador, sacado**")
        payer_volume = st.slider("Recorrência, quantos boletos esse pagador tem no histórico", 1, 50, 6)
        payer_liquidity = st.slider("Índice de liquidez de 1 mês do pagador", 0.0, 1.0, 0.55, step=0.05)
        payer_inadimplencia = st.slider("Share de inadimplência de 6 a 15 dias, pagador", 0.0, 1.0, 0.10, step=0.01)

        st.markdown("**Perfil do beneficiário, cedente**")
        beneficiary_volume = st.slider("Recorrência do beneficiário", 1, 50, 10)

        st.markdown("**Camada estatística, Z-score**")
        z_combined = st.slider("Z-score combinado, desvio do valor contra histórico", 0.0, 6.0, 1.0, step=0.1)

    valores = df["amount"].astype(float).sort_values().values
    if len(valores) > 0 and valor_nominal > 0:
        idx = bisect.bisect_left(valores, valor_nominal)
        valor_percentil = idx / len(valores)
    else:
        valor_percentil = 0.0

    r = simular_boleto(
        valor_nominal=valor_nominal,
        delay_days=delay_days,
        baixa_missing=baixa_missing,
        payer_volume=payer_volume,
        beneficiary_volume=beneficiary_volume,
        payer_liquidity=payer_liquidity,
        payer_inadimplencia=payer_inadimplencia,
        valor_percentil=valor_percentil,
        z_combined=z_combined,
    )

    with col_right:
        st.markdown("**Resultado da simulação**")
        cor_heur = LEVEL_COLORS.get(r["nivel_heuristico"], p["muted"])
        cor_cons = LEVEL_COLORS.get(r["nivel_consolidado"], p["muted"])

        cards = st.columns(3, gap="small")
        with cards[0]:
            st.markdown(
                f"""
                <div class='carbon-card'>
                  <div class='accent-bar' style='background:{p['primary']};'></div>
                  <div class='eyebrow'>Heurístico</div>
                  <div class='value'>{r['heuristico']}</div>
                  <div class='delta' style='color:{cor_heur};font-weight:600;'>{LEVEL_LABEL[r['nivel_heuristico']]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cards[1]:
            st.markdown(
                f"""
                <div class='carbon-card'>
                  <div class='accent-bar' style='background:{p['accent']};'></div>
                  <div class='eyebrow'>Estatístico</div>
                  <div class='value'>{r['estatistico']}</div>
                  <div class='delta'>Z = {z_combined:.2f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cards[2]:
            st.markdown(
                f"""
                <div class='carbon-card'>
                  <div class='accent-bar' style='background:{cor_cons};'></div>
                  <div class='eyebrow'>Consolidado</div>
                  <div class='value'>{r['consolidado']}</div>
                  <div class='delta' style='color:{cor_cons};font-weight:600;'>{LEVEL_LABEL[r['nivel_consolidado']]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption(f"Percentil do valor nominal na base atual, {valor_percentil*100:.1f}%.")

        st.markdown("**Motivos detectados**")
        if r["reasons"]:
            for txt in r["reasons"]:
                st.markdown(f"- {txt}")
        else:
            st.info("Nenhum gatilho de risco acionado para esse perfil.")

    with st.expander("Como o simulador calcula"):
        st.markdown(
            """
            O simulador aplica a mesma lógica do motor heurístico da Sprint 3 sobre os
            valores informados. Atraso, valor nominal, ausência de baixa, liquidez,
            recorrência e inadimplência geram pontos no score de 0 a 100.

            A camada estatística usa o Z-score combinado ajustado no slider, que na
            execução real é calculado automaticamente por pagador e por cedente.

            O score consolidado segue a fórmula `0,7 × heurístico + 0,3 × estatístico`.
            """
        )


def render_metodo(summary: dict | None, p: dict) -> None:
    section_header(p, "Documentação", "Como o motor decide")
    st.markdown(
        """
        O DetectaFIDC combina duas leituras complementares de risco.

        **1. Motor heurístico, da Sprint 3.** Regras explicáveis sobre cada boleto
        e seu enriquecimento com a base auxiliar de CNPJs. Pontua atraso, ausência
        de baixa, valor nominal, recorrência, liquidez, materialidade, inadimplência
        e concentração.

        **2. Camada estatística Z-score, da Sprint 4.** Calcula o desvio do valor
        nominal de cada boleto em relação ao histórico do pagador e do beneficiário.
        Pontua de 0 a 100 conforme o boleto se afasta da média da entidade.

        **Score consolidado** = 0,7 × heurístico + 0,3 × estatístico.

        A divergência entre as duas camadas é proposital. O heurístico captura o
        conhecido, ou seja, regras de negócio. O estatístico captura o anômalo,
        ou seja, comportamento que destoa do histórico da própria entidade.
        """
    )
    if summary and "statistical_layer" in summary:
        st.markdown("**Estatísticas da camada Z-score**")
        st.json(summary["statistical_layer"])


def main() -> None:
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"

    # Sidebar fixo: header + toggle de tema + menu visual
    with st.sidebar:
        st.markdown(
            f"""
            <div style='padding:8px 4px 18px;'>
              <div style='font-size:11px;letter-spacing:0.08em;text-transform:uppercase;
                          color:{PALETTES[st.session_state["theme"]]["primary"]};
                          font-weight:600;margin-bottom:4px;'>
                Data Vision
              </div>
              <div style='font-size:22px;font-weight:300;color:{PALETTES[st.session_state["theme"]]["text"]};
                          letter-spacing:-0.01em;'>
                DetectaFIDC
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        try:
            theme_label = st.segmented_control(
                "Tema",
                options=["🌙 Dark", "☀ Light"],
                default="🌙 Dark" if st.session_state["theme"] == "dark" else "☀ Light",
                label_visibility="collapsed",
            )
        except AttributeError:
            theme_label = st.radio(
                "Tema",
                ["🌙 Dark", "☀ Light"],
                index=0 if st.session_state["theme"] == "dark" else 1,
                horizontal=True,
                label_visibility="collapsed",
            )
        if theme_label:
            st.session_state["theme"] = "dark" if theme_label.startswith("🌙") else "light"

    p = inject_theme(st.session_state["theme"])

    with st.sidebar:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        secao = option_menu(
            menu_title=None,
            options=["Visão geral", "Fila de alertas", "Heurístico × estatístico", "Simulador", "Método"],
            icons=["grid", "list-task", "graph-up", "calculator", "book"],
            default_index=0,
            styles={
                "container": {
                    "padding": "0",
                    "background-color": "transparent",
                    "border": "none",
                    "box-shadow": "none",
                },
                "icon": {"color": p["muted"], "font-size": "16px"},
                "nav-link": {
                    "font-size": "14px",
                    "text-align": "left",
                    "margin": "2px 0",
                    "padding": "10px 14px",
                    "color": p["text"],
                    "border-radius": "0",
                    "background-color": "transparent",
                    "border": "none",
                    "--hover-color": p["panel_2"],
                },
                "nav-link-selected": {
                    "background-color": p["panel_2"],
                    "color": p["text"],
                    "font-weight": "500",
                    "border": "none",
                    "box-shadow": "none",
                },
            },
        )

        st.divider()
        st.caption("Equipe Data Vision")
        st.markdown(
            """
            <div style='font-size:12px;line-height:1.7;'>
              Andreza Dias Almeida Batista<br>
              Kauê Marçal Pla Gil<br>
              Lucas Carvalhal Pereira dos Santos<br>
              Maria Eduarda Carmo da Silva
            </div>
            """,
            unsafe_allow_html=True,
        )

    df, summary = load_data()
    render_header(p)

    if df.empty:
        st.error("Nenhum CSV de saída encontrado em `output/`. Rode `python src/pipeline_sprint4.py` antes.")
        return

    render_kpis(df, summary, p)

    if secao == "Visão geral":
        render_visao_geral(df, summary, p)
    elif secao == "Fila de alertas":
        render_fila_alertas(df, p)
    elif secao == "Heurístico × estatístico":
        render_comparativo(df, summary, p)
    elif secao == "Simulador":
        render_simulador(df, p)
    elif secao == "Método":
        render_metodo(summary, p)


if __name__ == "__main__":
    main()
