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


def fmt_int_br(x):
    if pd.isna(x):
        return ""
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return ""


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
    st.dataframe(format_table_br(panel_raw), use_container_width=True)

    st.divider()

    # -------------------------
    # Matriz CPI
    # -------------------------
    st.subheader("Matriz CPI")
    cpi_raw = replace_acos_obj_with_roas_obj(camp_strat)
    st.dataframe(format_table_br(cpi_raw), use_container_width=True)

    st.divider()

    # -------------------------
    # Restante do dashboard (com os mesmos ajustes)
    # -------------------------
    pause_fmt = format_table_br(replace_acos_obj_with_roas_obj(pause))
    enter_fmt = format_table_br(replace_acos_obj_with_roas_obj(enter))
    scale_fmt = format_table_br(replace_acos_obj_with_roas_obj(scale))
    acos_fmt = format_table_br(replace_acos_obj_with_roas_obj(acos))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pausar ou revisar")
        st.dataframe(pause_fmt, use_container_width=True)
    with c2:
        st.subheader("Entrar em Ads")
        st.dataframe(enter_fmt, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Escalar orçamento")
        st.dataframe(scale_fmt, use_container_width=True)
    with c4:
        st.subheader("Baixar ROAS objetivo")
        st.dataframe(acos_fmt, use_container_width=True)

    # -------------------------
    # Download Excel
    # Mantem dataframes originais para nao quebrar o gerar_excel do ml_report
    # -------------------------
    st.subheader("Download Excel")
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


if __name__ == "__main__":
    main()
