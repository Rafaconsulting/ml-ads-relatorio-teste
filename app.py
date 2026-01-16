import streamlit as st
import pandas as pd
import inspect
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


# IMPORTANTE:
# Removi ACOS objetivo daqui, porque ele vai virar ROAS objetivo (numero, nao percentual)
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


def _dataframe_accepts_column_config() -> bool:
    try:
        sig = inspect.signature(st.dataframe)
        return "column_config" in sig.parameters
    except Exception:
        return False


# -------------------------
# Conversao ACOS objetivo -> ROAS objetivo
# -------------------------
def _acos_value_to_roas(ac):
    """
    Converte um ACOS objetivo para ROAS objetivo.
    Aceita ACOS como:
      - fracao (0.25)
      - percentual (25)
    Retorna ROAS como numero (ex: 4.0).
    """
    if pd.isna(ac):
        return pd.NA

    try:
        v = float(ac)
    except Exception:
        return pd.NA

    if v == 0:
        return pd.NA

    # se vier como percentual (25, 30, 50...), converte para fracao
    acos_frac = v / 100.0 if v > 2 else v

    if acos_frac <= 0:
        return pd.NA

    return 1.0 / acos_frac


def replace_acos_obj_with_roas_obj(df: pd.DataFrame) -> pd.DataFrame:
    """
    Procura colunas de ACOS objetivo e:
      - substitui os valores por ROAS objetivo
      - renomeia a coluna para "ROAS objetivo"
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df2 = df.copy()

    # candidatos mais comuns, mantendo compatibilidade com o que aparece no seu app
    candidates = [
        "ACOS Objetivo",
        "ACOS objetivo",
        "ACOS_Objetivo",
        "ACOS_Objetivo_N",
        "acos_objetivo_n",
        "acos objetivo n",
        "ACOS Objetivo N",
    ]

    found_col = None
    for c in df2.columns:
        if c in candidates:
            found_col = c
            break

    # fallback: busca por texto parecido
    if found_col is None:
        for c in df2.columns:
            lc = str(c).strip().lower()
            if "acos" in lc and "objetivo" in lc:
                found_col = c
                break

    if found_col is None:
        return df2

    ser = pd.to_numeric(df2[found_col], errors="coerce")
    df2[found_col] = ser.map(_acos_value_to_roas)

    # renomeia
    df2 = df2.rename(columns={found_col: "ROAS objetivo"})

    return df2


# -------------------------
# Formatacao exclusiva do Painel Geral
# -------------------------
def format_panel_geral_br(df: pd.DataFrame) -> pd.DataFrame:
    df_fmt = df.copy()

    for col in df_fmt.columns:
        # preserva texto (ex: Nome da campanha, Acao_recomendada)
        serie_num = pd.to_numeric(df_fmt[col], errors="coerce")
        non_null = df_fmt[col].notna().sum()
        num_ok = serie_num.notna().sum()

        if non_null > 0 and (num_ok / non_null) < 0.60:
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
# Exibicao padronizada (geral)
# -------------------------
def show_df(df, **kwargs):
    kwargs.pop("column_config", None)

    if df is None:
        st.info("Sem dados para exibir.")
        return

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.dataframe(df, **kwargs)
        return

    _df = df.copy()

    money_cols = [c for c in _df.columns if _is_money_col(c)]
    percent_cols = [c for c in _df.columns if _is_percent_col(c)]

    for c in percent_cols:
        ser = pd.to_numeric(_df[c], errors="coerce")
        vmax = ser.max(skipna=True)
        if pd.notna(vmax) and vmax <= 2:
            _df[c] = ser * 100
        else:
            _df[c] = ser

    n_rows, n_cols = _df.shape

    if n_rows <= 1500 and n_cols <= 50:
        fmt = {}
        for c in money_cols:
            fmt[c] = fmt_money_br
        for c in percent_cols:
            fmt[c] = fmt_percent_br

        try:
            st.dataframe(_df.style.format(fmt), **kwargs)
            return
        except Exception:
            pass

    for c in money_cols:
        _df[c] = pd.to_numeric(_df[c], errors="coerce").map(fmt_money_br)
    for c in percent_cols:
        _df[c] = pd.to_numeric(_df[c], errors="coerce").map(fmt_percent_br)

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
        st.subheader("Modo Campanhas")
        modo = st.radio("Como ler o relatório de campanha", ["diario", "consolidado"], horizontal=True)

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

        if modo == "diario":
            camp_raw = ml.load_campanhas_diario(campanhas_file)
            daily = ml.build_daily_from_diario(camp_raw)
            camp_agg = ml.build_campaign_agg(camp_raw, modo="diario")
        else:
            camp_raw = ml.load_campanhas_consolidado(campanhas_file)
            daily = None
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

        # Converte ACOS objetivo -> ROAS objetivo nos dataframes que costumam ter a coluna
        camp_strat = replace_acos_obj_with_roas_obj(camp_strat)
        scale = replace_acos_obj_with_roas_obj(scale)
        acos = replace_acos_obj_with_roas_obj(acos)  # pode existir aqui dependendo do seu ml_report
        pause = replace_acos_obj_with_roas_obj(pause)
        enter = replace_acos_obj_with_roas_obj(enter)

        st.success("Relatório gerado com sucesso.")

    except Exception as e:
        st.error("Erro ao processar os arquivos.")
        st.exception(e)
        return

    # KPIs
    st.subheader("KPIs")
    cols = st.columns(4)

    cols[0].metric("Investimento Ads", fmt_money_br(float(kpis.get("Investimento Ads (R$)", 0))))
    cols[1].metric("Receita Ads", fmt_money_br(float(kpis.get("Receita Ads (R$)", 0))))
    cols[2].metric("ROAS", fmt_number_br(float(kpis.get("ROAS", 0)), 2))

    tacos_val = float(kpis.get("TACOS", 0))
    tacos_pct = tacos_val * 100 if tacos_val <= 2 else tacos_val
    cols[3].metric("TACOS", fmt_percent_br(tacos_pct))

    with st.expander("Ver tabela de KPIs"):
        show_df(pd.DataFrame([kpis]))

    st.divider()

    if daily is not None:
        st.subheader("Série diária")
        show_df(daily)

    st.subheader("Painel geral")
    panel_raw = ml.build_control_panel(camp_strat)
    panel_raw = replace_acos_obj_with_roas_obj(panel_raw)
    panel_fmt = format_panel_geral_br(panel_raw)
    st.dataframe(panel_fmt, use_container_width=True)

    st.divider()

    st.subheader("Matriz CPI")
    show_df(camp_strat, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pausar ou revisar")
        show_df(pause, use_container_width=True)
    with c2:
        st.subheader("Entrar em Ads")
        show_df(enter, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Escalar orçamento")
        show_df(scale, use_container_width=True)
    with c4:
        st.subheader("Subir ROAS objetivo")
        show_df(acos, use_container_width=True)

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
            daily=daily,
        )

        st.download_button(
            "Baixar Excel do relatório",
            data=excel_bytes,
            file_name="relatorio_meli_ads.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        st.error("Nao consegui gerar o Excel.")
        st.exception(e)


if __name__ == "__main__":
    main()
