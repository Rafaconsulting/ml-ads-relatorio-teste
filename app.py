import streamlit as st
import pandas as pd
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
        "faturamento",
        "vendas (r$)",
    ]
    return any(k in c for k in money_keys)


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


# -------------------------
# ACOS objetivo -> ROAS objetivo
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

    acos_frac = v / 100 if v > 2 else v
    if acos_frac <= 0:
        return pd.NA

    return 1 / acos_frac


def replace_acos_obj_with_roas_obj(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df2 = df.copy()

    for col in df2.columns:
        lc = str(col).strip().lower()
        if "acos" in lc and "objetivo" in lc:
            ser = pd.to_numeric(df2[col], errors="coerce")
            df2[col] = ser.map(_acos_value_to_roas)
            df2 = df2.rename(columns={col: "ROAS objetivo"})
            break

    return df2


# -------------------------
# Formatacao (Painel Geral e Matriz CPI)
# -------------------------
def format_table_br(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regras:
    - preserva colunas de texto (Nome da campanha, Acao_recomendada, etc)
    - dinheiro: R$ com separador BR
    - percentuais: % com separador BR (e escala corrigida se vier 0-1)
    - numeros gerais: 2 casas e separador BR
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df_fmt = df.copy()

    for col in df_fmt.columns:
        lc = str(col).strip().lower()

        # preserva texto por nome (mais seguro que heuristica)
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

        # tenta converter para numero
        serie_num = pd.to_numeric(df_fmt[col], errors="coerce")
        non_null = df_fmt[col].notna().sum()
        num_ok = serie_num.notna().sum()

        # se nao for numerica de verdade, preserva como texto
        if non_null == 0 or (num_ok / max(non_null, 1)) < 0.60:
            df_fmt[col] = df_fmt[col].astype(str).replace({"nan": ""})
            continue

        # numerica
        if _is_money_col(col):
            df_fmt[col] = serie_num.map(fmt_money_br)

        elif _is_percent_col(col):
            vmax = serie_num.max(skipna=True)
            if pd.notna(vmax) and vmax <= 2:
                serie_num = serie_num * 100
            df_fmt[col] = serie_num.map(fmt_percent_br)

        else:
            df_fmt[col] = serie_num.map(lambda x: fmt_number_br(x, 2))

    return df_fmt


# -------------------------
# Exibição padrão (tabelas auxiliares)
# -------------------------
def show_df(df, **kwargs):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        st.dataframe(df, **kwargs)
        return

    _df = df.copy()

    # corrige escala de percentuais quando vier 0-1
    for col in _df.columns:
        if _is_percent_col(col):
            ser = pd.to_numeric(_df[col], errors="coerce")
            vmax = ser.max(skipna=True)
            if pd.notna(vmax) and vmax <= 2:
                _df[col] = ser * 100

    st.dataframe(_df, **kwargs)


# -------------------------
# App
# -------------------------
def main():
    st.set_page_config(page_title="Mercado Livre Ads", layout="wide")
    st.title("Mercado Livre Ads - Dashboard e Relatório")

    with st.sidebar:
        st.caption(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        st.divider()

        st.subheader("Arquivos")
        organico_file = st.file_uploader("Relatório de Desempenho de Vendas (Excel)", type=["xlsx"])
        patrocinados_file = st.file_uploader("Relatório Anúncios Patrocinados (Excel)", type=["xlsx"])
        campanhas_file = st.file_uploader("Relatório de Campanha (Excel)", type=["xlsx"])

        st.divider()
        st.subheader("Filtros de regra")

        enter_visitas_min = st.number_input("Entrar em Ads: visitas mín", min_value=0, value=50, step=10)

        enter_conv_min_pct = st.number_input(
            "Entrar em Ads: conversão mín (%)",
            min_value=0.0,
            value=5.0,
            step=0.5,
            format="%.2f",
        )

        pause_invest_min = st.number_input(
            "Pausar: investimento mín (R$)",
            min_value=0.0,
            value=100.0,
            step=50.0,
            format="%.2f",
        )

        pause_cvr_max_pct = st.number_input(
            "Pausar: CVR máx (%)",
            min_value=0.0,
            value=1.0,
            step=0.5,
            format="%.2f",
        )

        enter_conv_min = enter_conv_min_pct / 100
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
    st.subheader("KPIs")
    cols = st.columns(4)

    cols[0].metric("Investimento Ads", fmt_money_br(float(kpis.get("Investimento Ads (R$)", 0))))
    cols[1].metric("Receita Ads", fmt_money_br(float(kpis.get("Receita Ads (R$)", 0))))
    cols[2].metric("ROAS", fmt_number_br(float(kpis.get("ROAS", 0)), 2))

    tacos_val = float(kpis.get("TACOS", 0))
    tacos_pct = tacos_val * 100 if tacos_val <= 2 else tacos_val
    cols[3].metric("TACOS", fmt_percent_br(tacos_pct))

    st.divider()

    # -------------------------
    # Painel geral
    # Importante: ml_report espera "ACOS Objetivo" dentro do camp_strat
    # -------------------------
    st.subheader("Painel geral")
    panel_raw = ml.build_control_panel(camp_strat)
    panel_raw = replace_acos_obj_with_roas_obj(panel_raw)
    panel_fmt = format_table_br(panel_raw)
    st.dataframe(panel_fmt, use_container_width=True)

    st.divider()

    # -------------------------
    # Matriz CPI com os mesmos ajustes do Painel Geral
    # -------------------------
    st.subheader("Matriz CPI")

    cpi_raw = replace_acos_obj_with_roas_obj(camp_strat)
    cpi_fmt = format_table_br(cpi_raw)

    st.dataframe(cpi_fmt, use_container_width=True)

    st.divider()

    # -------------------------
    # Outras tabelas (mantem estilo atual, mas com ROAS objetivo)
    # Se quiser, podemos aplicar format_table_br nelas tambem
    # -------------------------
    pause_view = replace_acos_obj_with_roas_obj(pause)
    enter_view = replace_acos_obj_with_roas_obj(enter)
    scale_view = replace_acos_obj_with_roas_obj(scale)
    acos_view = replace_acos_obj_with_roas_obj(acos)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pausar ou revisar")
        show_df(pause_view, use_container_width=True)
    with c2:
        st.subheader("Entrar em Ads")
        show_df(enter_view, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Escalar orçamento")
        show_df(scale_view, use_container_width=True)
    with c4:
        st.subheader("Subir ROAS objetivo")
        show_df(acos_view, use_container_width=True)

    st.subheader("Download Excel")
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


if __name__ == "__main__":
    main()
