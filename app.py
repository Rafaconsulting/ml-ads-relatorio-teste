import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

import ml_report as ml


# -------------------------
# Formatadores BR
# -------------------------
def fmt_money_br(x):
    if pd.isna(x):
        return ""
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_percent_br(x):
    if pd.isna(x):
        return ""
    return f"{x:.2f}%".replace(".", ",")


def fmt_number_br(x, decimals=2):
    if pd.isna(x):
        return ""
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int_br(x):
    if pd.isna(x):
        return ""
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return ""


# -------------------------
# Limpeza e ordenacao das tabelas (APENAS VISUAL)
# -------------------------

def _norm_col(col: str) -> str:
    return str(col).strip().lower().replace(' ', '_').replace('__', '_')


def _drop_cols_by_norm(df: pd.DataFrame, targets_norm: set[str]) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    drop_cols = [c for c in df.columns if _norm_col(c) in targets_norm]
    return df.drop(columns=drop_cols, errors='ignore')


def _keep_first_by_prefix(df: pd.DataFrame, prefixes_norm: tuple[str, ...]) -> pd.DataFrame:
    """Mantem apenas a primeira coluna cujo nome normalizado inicia com algum prefixo informado."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    cols = list(df.columns)
    hits = [c for c in cols if any(_norm_col(c).startswith(p) for p in prefixes_norm)]
    if len(hits) <= 1:
        return df
    # mantem a primeira na ordem atual
    for col in hits[1:]:
        df = df.drop(columns=[col], errors='ignore')
    return df


def _reorder_next_to(df: pd.DataFrame, left_col: str, right_col: str) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if left_col not in df.columns or right_col not in df.columns:
        return df
    cols = list(df.columns)
    cols.remove(right_col)
    try:
        idx = cols.index(left_col) + 1
    except ValueError:
        return df
    cols.insert(idx, right_col)
    return df[cols]


def _enforce_action_block(df: pd.DataFrame) -> pd.DataFrame:
    """Garante Acao_Recomendada antes de Confianca_Dado e Motivo, sem baguncar o resto."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    ordered = []
    for col in ["Acao_Recomendada", "Confianca_Dado", "Motivo"]:
        if col in df.columns:
            ordered.append(col)
    if not ordered:
        return df
    rest = [c for c in df.columns if c not in ordered]
    # insere o bloco no fim do rest, mas mantendo a ordem do bloco
    return df[rest + ordered]


def _reorder_roas_acos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regras visuais:
    - manter apenas 1 ROAS objetivo (quando houver duplicatas)
    - colar ROAS_Real ao lado do ROAS objetivo
    - colar ACOS_Real ao lado do ROAS_Real (logo depois)
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    # 1) manter apenas o primeiro ROAS objetivo (variações)
    df = _keep_first_by_prefix(df, prefixes_norm=("roas_objetivo", "roas_objetivo_n", "roas_objetivo"))

    # detectar a coluna de ROAS objetivo que sobrou
    roas_obj_cols = [c for c in df.columns if _norm_col(c).startswith('roas_objetivo')]
    roas_obj_col = roas_obj_cols[0] if roas_obj_cols else None

    # detectar ROAS real e ACOS real (variações)
    roas_real_cols = [c for c in df.columns if _norm_col(c) == 'roas_real']
    roas_real_col = roas_real_cols[0] if roas_real_cols else None

    acos_real_cols = [c for c in df.columns if _norm_col(c) == 'acos_real']
    acos_real_col = acos_real_cols[0] if acos_real_cols else None

    # 2) posicionar ROAS_Real logo após ROAS objetivo (se existir)
    if roas_obj_col and roas_real_col:
        df = _reorder_next_to(df, roas_obj_col, roas_real_col)

    # 3) posicionar ACOS_Real logo após ROAS_Real
    if roas_real_col and acos_real_col:
        df = _reorder_next_to(df, roas_real_col, acos_real_col)

    return df


def prepare_df_for_view(df: pd.DataFrame, *, drop_cpi_cols: bool = True, drop_roas_generic: bool = False) -> pd.DataFrame:
    """
    Aplica padroes de visualizacao sem alterar calculos:
    - (opcional) remove CPI_Share, CPI_Cum, CPI_80
    - (opcional) remove ROAS generico (coluna 'ROAS')
    - remove duplicatas de ROAS objetivo, cola ROAS_Real e ACOS_Real
    - garante Acao_Recomendada antes de Confianca_Dado e Motivo
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    out = df.copy()

    if drop_cpi_cols:
        out = _drop_cols_by_norm(out, targets_norm={"cpi_share", "cpi_cum", "cpi_80"})

    if drop_roas_generic:
        out = _drop_cols_by_norm(out, targets_norm={"roas"})

    out = _reorder_roas_acos(out)
    out = _enforce_action_block(out)
    return out
# -------------------------
# Detectores de colunas
# -------------------------
def _is_money_col(col_name: str) -> bool:
    c = str(col_name).strip().lower()
    money_keys = [
        "orcamento",
        "orçamento",
        "investimento",
        "receita",
        "vendas_brutas",
        "potencial_receita",
        "potencial receita",
        "impacto_estimado",
        "impacto estimado",
        "faturamento",
        "vendas (r$)",
    ]
    return any(k in c for k in money_keys)


def _is_id_col(col_name: str) -> bool:
    """
    IDs sao identificadores, nao devem receber formatacao numerica.
    Mantem como texto puro (ex: 6086561266).
    """
    c = str(col_name).strip().lower().replace("__", "_")
    return (
        c == "id"
        or c == "id_anuncio"
        or c == "id_anúncio"
        or c == "id campanha"
        or c == "id_campanha"
        or c.endswith("_id")
        or c.startswith("id_")
        or "id anuncio" in c
        or "id anúncio" in c
        or "id do anuncio" in c
        or "id do anúncio" in c
        or "id campanha" in c
    )


# IMPORTANTE
# Tiramos ACOS objetivo e ACOS_Objetivo_N daqui, porque agora viram ROAS (numero)
_PERCENT_COLS = {
    "acos real",
    "acos_real",
    "cpi_share",
    "cpi share",
    "cpi_cum",
    "cpi cum",
    "con_visitas_vendas",
    "con visitas vendas",
    "conv_visitas_vendas",
    "conv visitas vendas",
    "conv_visitas_compradores",
    "conv visitas compradores",
    "perdidas_orc",
    "perdidas_class",
    "cvr",
    "cvr\n(conversion rate)",
}


def _is_percent_col(col_name: str) -> bool:
    c = str(col_name).strip().lower().replace("__", "_")
    return c in _PERCENT_COLS


def _is_count_col(col_name: str) -> bool:
    """
    Apenas colunas de volume/contagem, para remover decimais.
    Evita capturar colunas de conversao/taxa (Conv_Visitas_Vendas etc).
    """
    c = str(col_name).strip().lower().replace("__", "_")

    # nunca formatar como inteiro se for conversao/taxa
    if (
        "conv_" in c
        or c.startswith("con_")
        or "convers" in c
        or "cvr" in c
        or "taxa" in c
    ):
        return False

    targets = {
        "impressoes",
        "impressões",
        "impressions",
        "cliques",
        "clicks",
        "visitas",
        "visits",
        "qtd_vendas",
        "qtd vendas",
        "quantidade_vendas",
        "quantidade vendas",
        "orders",
        "pedidos",
    }

    if c in targets:
        return True

    # casos com sufixo
    if c.endswith("_impressoes") or c.endswith("_impressões") or c.endswith("_impressions"):
        return True
    if c.endswith("_cliques") or c.endswith("_clicks"):
        return True
    if c.endswith("_visitas") or c.endswith("_visits"):
        return True
    if "qtd_vendas" in c or "quantidade_vendas" in c:
        return True

    return False


# -------------------------
# ACOS objetivo -> ROAS objetivo (inclui ACOS_Objetivo_N)
# -------------------------
def _acos_value_to_roas(ac):
    if pd.isna(ac):
        return pd.NA
    try:
        v = float(ac)
    except Exception:
        return pd.NA

    if v == 0:
        return pd.NA

    # se vier como percentual (25, 30, 50), converte para fracao
    acos_frac = v / 100 if v > 2 else v
    if acos_frac <= 0:
        return pd.NA

    return 1 / acos_frac


def _roas_col_name_from_acos_col(col_name: str) -> str:
    lc = str(col_name).strip().lower().replace("__", "_")
    if lc.endswith("_n") or "objetivo_n" in lc or "objetivo n" in lc:
        return "ROAS objetivo N"
    return "ROAS objetivo"


def replace_acos_obj_with_roas_obj(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte TODAS as colunas que tenham "acos" e "objetivo":
    - ACOS Objetivo -> ROAS objetivo
    - ACOS_Objetivo_N -> ROAS objetivo N
    Mantem ambas se existirem no dataframe.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df2 = df.copy()
    renames = {}

    for col in list(df2.columns):
        lc = str(col).strip().lower()
        if "acos" in lc and "objetivo" in lc:
            ser = pd.to_numeric(df2[col], errors="coerce")
            df2[col] = ser.map(_acos_value_to_roas)
            renames[col] = _roas_col_name_from_acos_col(col)

    if renames:
        df2 = df2.rename(columns=renames)

    return df2


# -------------------------
# Formatacao unificada (Painel, CPI, Acoes)
# -------------------------
def format_table_br(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regras:
    - preserva colunas de texto (Nome da campanha, Acao_recomendada, etc)
    - IDs: texto puro (somente digitos)
    - dinheiro: R$ com separador BR
    - percentuais: % com separador BR (e escala corrigida se vier 0-1)
    - contagens: inteiros sem decimais (Impressoes, Cliques, Visitas, Qtd_Vendas)
    - numeros gerais: 2 casas e separador BR
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df_fmt = df.copy()

    for col in df_fmt.columns:
        lc = str(col).strip().lower()

        # IDs devem ser texto puro, sem formatacao numerica
        if _is_id_col(col):
            s = df_fmt[col].astype(str).replace({"nan": ""})
            # remove .0, separadores e qualquer caractere nao numerico
            s = s.str.replace(r"\.0$", "", regex=True)
            s = s.str.replace(r"\D", "", regex=True)
            df_fmt[col] = s
            continue

        # preserva texto por nome (blindagem)
        if (
            "nome" in lc
            or "campanha" in lc
            or "acao" in lc
            or "ação" in lc
            or "recomend" in lc
            or "estrateg" in lc
            or "estratég" in lc
        ):
            df_fmt[col] = df_fmt[col].astype(str).replace({"nan": ""})
            continue

        serie_num = pd.to_numeric(df_fmt[col], errors="coerce")
        non_null = df_fmt[col].notna().sum()
        num_ok = serie_num.notna().sum()

        # se nao for numerica, preserva como texto
        if non_null == 0 or (num_ok / max(non_null, 1)) < 0.60:
            df_fmt[col] = df_fmt[col].astype(str).replace({"nan": ""})
            continue

        # ordem importa: percentual antes de contagem
        if _is_money_col(col):
            df_fmt[col] = serie_num.map(fmt_money_br)

        elif _is_percent_col(col):
            vmax = serie_num.max(skipna=True)
            if pd.notna(vmax) and vmax <= 2:
                serie_num = serie_num * 100
            df_fmt[col] = serie_num.map(fmt_percent_br)

        elif _is_count_col(col):
            df_fmt[col] = serie_num.map(fmt_int_br)

        else:
            df_fmt[col] = serie_num.map(lambda x: fmt_number_br(x, 2))

    return df_fmt


# -------------------------
# App
# -------------------------
def render_pareto_chart(df):
    """Gera um gráfico de Pareto para a Receita das Campanhas."""
    if df is None or df.empty or "Receita" not in df.columns:
        return
    
    df_sorted = df.sort_values("Receita", ascending=False).copy()
    df_sorted["Receita_Cum_Pct"] = 100 * df_sorted["Receita"].cumsum() / df_sorted["Receita"].sum()
    
    fig = go.Figure()
    
    # Barras de Receita
    fig.add_trace(go.Bar(
        x=df_sorted["Nome"],
        y=df_sorted["Receita"],
        name="Receita",
        marker_color="#3483fa"
    ))
    
    # Linha de Percentual Acumulado
    fig.add_trace(go.Scatter(
        x=df_sorted["Nome"],
        y=df_sorted["Receita_Cum_Pct"],
        name="% Acumulado",
        yaxis="y2",
        line=dict(color="#ffe600", width=3),
        mode="lines+markers"
    ))
    
    fig.update_layout(
        title="Análise de Pareto: Receita por Campanha",
        xaxis=dict(title="Campanha", showticklabels=False),
        yaxis=dict(title="Receita (R$)"),
        yaxis2=dict(title="% Acumulado", overlaying="y", side="right", range=[0, 110]),
        template="plotly_dark",
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

def render_treemap_chart(df):
    """Gera um Treemap mostrando Investimento por Campanha, agrupado por Quadrante e colorido por ROAS."""
    if df is None or df.empty or "Investimento" not in df.columns:
        return
    
    df_plot = df[df["Investimento"] > 0].copy()
    
    # Preparar dados para o Treemap
    df_plot["ROAS_Real"] = pd.to_numeric(df_plot.get("ROAS_Real", 0), errors="coerce").fillna(0)
    df_plot["Quadrante"] = df_plot.get("Quadrante", "SEM_CLASSIFICACAO")
    
    # Criar figura com Treemap usando path e values
    fig = px.treemap(
        df_plot,
        path=["Quadrante", "Nome"],
        values="Investimento",
        color="ROAS_Real",
        color_continuous_scale="RdYlGn",
        title="Alocacao de Investimento por Campanha (Tamanho = Investimento, Cor = ROAS)",
        template="plotly_dark",
        color_continuous_midpoint=5,
        hover_name="Nome"
    )
    
    fig.update_traces(textposition="middle center", textfont_size=10)
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        coloraxis_colorbar=dict(title="ROAS")
    )
    st.plotly_chart(fig, use_container_width=True)

def main():
    # Carregar CSS customizado
    try:
        with open(".streamlit/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("Arquivo de estilo não encontrado. O dashboard será exibido com o tema padrão.")
    st.set_page_config(page_title="Mercado Livre Ads", layout="wide", initial_sidebar_state="expanded")
    st.title("📊 Mercado Livre Ads - Dashboard e Relatório")

    with st.sidebar:
        st.caption(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        st.divider()

        st.subheader("Arquivos")
        organico_file = st.file_uploader("Relatorio de Desempenho de Vendas (Excel)", type=["xlsx"])
        patrocinados_file = st.file_uploader("Relatorio Anuncios Patrocinados (Excel)", type=["xlsx"])
        campanhas_file = st.file_uploader("Relatorio de Campanha (Excel)", type=["xlsx"])
        
        st.divider()
        st.subheader("Comparativo (Opcional)")
        snapshot_file = st.file_uploader("Snapshot de Referencia (Excel)", type=["xlsx"], help="Arquivo gerado ha 15 dias para comparar evolucao")

        st.divider()
        st.subheader("Filtros de regra")

        enter_visitas_min = st.number_input("Entrar em Ads: visitas mín", min_value=0, value=50, step=10)
        enter_conv_min_pct = st.number_input(
            "Entrar em Ads: conversão mín (%)",
            min_value=0.0,
            value=3.0,
            step=0.5,
            format="%.2f",
        )
        pause_invest_min = st.number_input(
            "Pausar: investimento mín (R$)",
            min_value=0.0,
            value=20.0,
            step=10.0,
            format="%.2f",
        )
        pause_cvr_max_pct = st.number_input(
            "Pausar: CVR máx (%)",
            min_value=0.0,
            value=1.5,
            step=0.5,
            format="%.2f",
        )

        # IMPORTANTE: Conv_Visitas_Vendas e CVR chegam em pontos percentuais (ex.: 1,82 vira 1.82).
        pause_cvr_max = pause_cvr_max_pct
        enter_conv_min = enter_conv_min_pct
        pause_cvr_max = pause_cvr_max_pct / 100

        st.divider()
        executar = st.button("Gerar relatório", use_container_width=True)

    if not (organico_file and patrocinados_file and campanhas_file):
        st.info("Envie os 3 arquivos na barra lateral para liberar o relatório.")
        return

    if not executar:
        st.warning("Quando estiver pronto, clique em Gerar relatório.")
        return

    try:
        org = ml.load_organico(organico_file)
        pat = ml.load_patrocinados(patrocinados_file)

        # Modo unico: consolidado
        camp_raw = ml.load_campanhas_consolidado(campanhas_file)
        camp_agg = ml.build_campaign_agg(camp_raw, modo="consolidado")

        kpis, pause, enter, scale, acos, camp_strat = ml.build_tables(
            org=org,
            camp_agg=camp_agg,
            pat=pat,
            enter_visitas_min=int(enter_visitas_min),
            enter_conv_min=float(enter_conv_min),
            pause_invest_min=float(pause_invest_min),
            pause_cvr_max=float(pause_cvr_max),
        )

        st.success("Relatório gerado com sucesso.")

    except Exception as e:
        st.error("Erro ao processar os arquivos.")
        st.exception(e)
        return

    # -------------------------
    # KPIs
    # -------------------------
    st.header("Indicadores Chave de Performance (KPIs)")
    cols = st.columns(4)

    cols[0].metric("💰 Investimento Ads", fmt_money_br(float(kpis.get("Investimento Ads (R$)", 0))))
    cols[1].metric("📈 Receita Ads", fmt_money_br(float(kpis.get("Receita Ads (R$)", 0))))
    cols[2].metric("🎯 ROAS", fmt_number_br(float(kpis.get("ROAS", 0)), 2))

    tacos_val = float(kpis.get("TACOS", 0))
    tacos_pct = tacos_val * 100 if tacos_val <= 2 else tacos_val
    cols[3].metric("📉 TACOS", fmt_percent_br(tacos_pct), delta_color="inverse")

    st.divider()

    # -------------------------
    # Gráficos de Análise
    # -------------------------
    st.header("Análise Visual de Performance")
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        render_pareto_chart(camp_strat)
    
    with col_g2:
        render_treemap_chart(camp_strat)

    st.divider()

    # -------------------------
    # Painel geral
    # Importante: ml_report espera "ACOS Objetivo" dentro do camp_strat
    # -------------------------
    with st.expander("Painel Geral de Campanhas", expanded=True):
        panel_raw = ml.build_control_panel(camp_strat)
        panel_raw = replace_acos_obj_with_roas_obj(panel_raw)
        panel_view = prepare_df_for_view(panel_raw, drop_cpi_cols=True, drop_roas_generic=False)
        st.dataframe(format_table_br(panel_view), use_container_width=True)

    st.divider()

    # -------------------------
    # Matriz CPI
    # -------------------------
    with st.expander("Matriz CPI (Oportunidades de Otimização)", expanded=False):
        cpi_raw = replace_acos_obj_with_roas_obj(camp_strat)
        # Visao limpa (sem alterar calculos): esconder colunas auxiliares, remover duplicidades e alinhar ROAS/ACOS
        cpi_view = prepare_df_for_view(cpi_raw, drop_cpi_cols=True, drop_roas_generic=True)
        st.dataframe(format_table_br(cpi_view), use_container_width=True)

    st.divider()

    # -------------------------
    # Plano de Ação 15 Dias
    # -------------------------
    st.header("📅 Plano de Ação Estratégico (15 Dias)")
    st.info("Este plano respeita a janela de 7 dias do algoritmo do Mercado Livre. Não faça alterações nas mesmas campanhas em intervalos menores que uma semana.")
    
    plan15 = ml.build_15_day_plan(camp_strat)
    if not plan15.empty:
        # Estilização básica para o plano
        def color_fase(val):
            if "Semana 1" in str(val): return "color: #3483fa; font-weight: bold"
            if "Semana 2" in str(val): return "color: #ffe600; font-weight: bold"
            return ""
        
        st.dataframe(
            plan15.style.applymap(color_fase, subset=["Fase"]),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.write("Nenhuma ação necessária para o período atual.")

    st.divider()

    # -------------------------
    # Restante do dashboard (com os mesmos ajustes)
    # -------------------------
    pause_view = prepare_df_for_view(replace_acos_obj_with_roas_obj(pause), drop_cpi_cols=True, drop_roas_generic=False)
    pause_fmt = format_table_br(pause_view)
    enter_view = prepare_df_for_view(replace_acos_obj_with_roas_obj(enter), drop_cpi_cols=True, drop_roas_generic=False)
    enter_fmt = format_table_br(enter_view)
    scale_view = prepare_df_for_view(replace_acos_obj_with_roas_obj(scale), drop_cpi_cols=True, drop_roas_generic=False)
    scale_fmt = format_table_br(scale_view)
    acos_view = prepare_df_for_view(replace_acos_obj_with_roas_obj(acos), drop_cpi_cols=True, drop_roas_generic=False)
    acos_fmt = format_table_br(acos_view)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛑 Pausar ou revisar")
        st.dataframe(pause_fmt, use_container_width=True)
    with c2:
        st.subheader("✅ Entrar em Ads")
        st.dataframe(enter_fmt, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("🚀 Escalar orçamento")
        st.dataframe(scale_fmt, use_container_width=True)
    with c4:
        st.subheader("⬇️ Baixar ROAS objetivo")
        st.dataframe(acos_fmt, use_container_width=True)

    # -------------------------
    # Download Excel
    # Mantem dataframes originais para nao quebrar o gerar_excel do ml_report
    # -------------------------
    st.header("Download do Relatório Completo")
    try:
        excel_bytes = ml.gerar_excel(
            kpis=kpis,
            camp_agg=camp_agg,
            pause=pause,
            enter=enter,
            scale=scale,
            acos=acos,
            camp_strat=camp_strat,
            daily=None,
        )

        st.download_button(
            "Baixar Excel do relatório",
            data=excel_bytes,
            file_name="relatorio_meli_ads.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        st.error("Não consegui gerar o Excel.")
        st.exception(e)


    st.divider()
    
    # -------------------------
    # Snapshot para Comparativo
    # -------------------------
    st.header("📸 Snapshot para Comparativo")
    st.info("Baixe um snapshot do estado atual das suas campanhas. Daqui a 15 dias, suba este arquivo junto com os novos relatorios para ver a evolucao.")
    
    try:
        snapshot_data = camp_strat[["Nome", "ROAS_Real", "Investimento", "Receita", "Quadrante"]].copy()
        snapshot_data["Data_Snapshot"] = datetime.now().strftime("%d/%m/%Y")
        
        snapshot_excel = ml.gerar_excel(
            kpis=kpis,
            camp_agg=camp_agg,
            pause=pause,
            enter=enter,
            scale=scale,
            acos=acos,
            camp_strat=snapshot_data,
            daily=None,
        )
        
        st.download_button(
            "Baixar Snapshot de Referencia",
            data=snapshot_excel,
            file_name=f"snapshot_referencia_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"Erro ao gerar Snapshot: {e}")
    
    # -------------------------
    # Se snapshot foi enviado, mostrar comparativo
    # -------------------------
    if snapshot_file:
        st.divider()
        st.header("📈 Evolucao e Resultados")
        st.success("Snapshot de referencia detectado! Analisando evolucao das campanhas...")
        
        try:
            # Ler snapshot
            snapshot_df = pd.read_excel(snapshot_file, sheet_name="Campanhas Estrategicas")
            
            # Comparar
            comparison = ml.compare_snapshots(camp_strat, snapshot_df)
            
            if not comparison.empty:
                # Exibir metricas de evolucao
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Campanhas Analisadas", len(comparison))
                with col2:
                    recuperadas = len(comparison[comparison["Evolucao_Status"] == "Recuperado"])
                    st.metric("Recuperadas", recuperadas, delta=f"+{recuperadas}")
                with col3:
                    potencializadas = len(comparison[comparison["Evolucao_Status"] == "Potencializado"])
                    st.metric("Potencializadas", potencializadas, delta=f"+{potencializadas}")
                with col4:
                    delta_roas_medio = comparison["Delta_ROAS"].mean()
                    st.metric("Delta ROAS Medio", f"{delta_roas_medio:.2f}x", delta=f"{delta_roas_medio:+.2f}x")
                
                st.divider()
                st.subheader("Tabela de Evolucao")
                cols_view = ["Nome", "ROAS_Ref", "ROAS_Real", "Delta_ROAS", "Invest_Ref", "Investimento", "Delta_Invest", "Quadrante_Ref", "Quadrante", "Evolucao_Status"]
                comparison_view = comparison[[c for c in cols_view if c in comparison.columns]].copy()
                st.dataframe(format_table_br(comparison_view), use_container_width=True)
            else:
                st.warning("Nenhuma campanha em comum entre o snapshot e os dados atuais.")
        except Exception as e:
            st.error(f"Erro ao processar snapshot: {e}")


if __name__ == "__main__":
    main()
