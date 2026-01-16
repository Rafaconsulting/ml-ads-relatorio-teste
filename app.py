import streamlit as st
import pandas as pd
import inspect
from datetime import datetime

import ml_report as ml


# -------------------------
# Exibicao padronizada
# -------------------------
def _is_money_col(col_name: str) -> bool:
    c = str(col_name).strip().lower()
    money_keys = [
        "orcamento", "orçamento", "investimento", "receita", "vendas_brutas",
        "potencial_receita", "potencial receita", "faturamento", "vendas (r$)",
    ]
    return any(k in c for k in money_keys)


_PERCENT_COLS = {
    "acos real", "acos_real",
    "acos objetivo n", "acos_objetivo_n",
    "cpi_share", "cpi share",
    "cpi_cum", "cpi cum",
    "con_visitas_vendas", "con visitas vendas",
    "conv_visitas_vendas", "conv visitas vendas",
    "conv_visitas_compradores", "conv visitas compradores",
    "perdidas_orc", "perdidas_class",
    "cvr", "cvr\n(conversion rate)",
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

    # Percentuais: se vierem como fracao (0 a 1.x), multiplica por 100 so para exibicao
    for c in percent_cols:
        ser = pd.to_numeric(_df[c], errors="coerce")
        try:
            vmax = ser.max(skipna=True)
            if pd.notna(vmax) and vmax <= 2:
                _df[c] = ser * 100
            else:
                _df[c] = ser
        except Exception:
            _df[c] = ser

    n_rows, n_cols = _df.shape
    n_special = len(money_cols) + len(percent_cols)

    if _dataframe_accepts_column_config() and n_rows <= 5000 and n_cols <= 70 and n_special <= 40:
        try:
            col_config = {}
            for c in money_cols:
                col_config[c] = st.column_config.NumberColumn(format="R$ %.2f")
            for c in percent_cols:
                col_config[c] = st.column_config.NumberColumn(format="%.2f%%")
            st.dataframe(_df, column_config=col_config, **kwargs)
            return
        except Exception:
            pass

    if n_rows <= 1500 and n_cols <= 50:
        try:
            fmt = {c: "R$ {:,.2f}" for c in money_cols}
            fmt.update({c: "{:.2f}%" for c in percent_cols})
            st.dataframe(_df.style.format(fmt), **kwargs)
            return
        except Exception:
            pass

    # Fallback final, transforma so as colunas especiais em string
    for c in money_cols:
        _df[c] = pd.to_numeric(_df[c], errors="coerce")
        _df[c] = _df[c].map(lambda x: "" if pd.isna(x) else f"R$ {x:,.2f}")
    for c in percent_cols:
        _df[c] = pd.to_numeric(_df[c], errors="coerce")
        _df[c] = _df[c].map(lambda x: "" if pd.isna(x) else f"{x:.2f}%")

    st.dataframe(_df, **kwargs)


# -------------------------
# App
# -------------------------
def main():
    st.set_page_config(page_title="Mercado Livre Ads", layout="wide")
    st.title("Mercado Livre Ads - Dashboard e Relatorio")

    with st.sidebar:
        st.caption(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        st.divider()

        st.subheader("Arquivos")
        organico_file = st.file_uploader("Relatorio Orgânico (Excel)", type=["xlsx"])
        patrocinados_file = st.file_uploader("Relatorio Anuncios Patrocinados (Excel)", type=["xlsx"])
        campanhas_file = st.file_uploader("Relatorio de Campanha (Excel)", type=["xlsx"])

        st.divider()
        st.subheader("Modo Campanhas")
        modo = st.radio("Como ler o relatorio de campanha", ["diario", "consolidado"], horizontal=True)

        st.divider()
        st.subheader("Filtros de regra")
        enter_visitas_min = st.number_input("Entrar em Ads: visitas min", min_value=0, value=50, step=10)
        enter_conv_min = st.number_input("Entrar em Ads: conversao min", min_value=0.0, value=0.05, step=0.01, format="%.2f")
        pause_invest_min = st.number_input("Pausar: investimento min (R$)", min_value=0.0, value=100.0, step=50.0, format="%.2f")
        pause_cvr_max = st.number_input("Pausar: CVR max", min_value=0.0, value=0.01, step=0.01, format="%.2f")

        st.divider()
        executar = st.button("Gerar relatorio", use_container_width=True)

    if not (organico_file and patrocinados_file and campanhas_file):
        st.info("Envie os 3 arquivos na barra lateral para liberar o relatorio.")
        return

    if not executar:
        st.warning("Quando estiver pronto, clique em Gerar relatorio.")
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

        st.success("Relatorio gerado com sucesso.")

    except Exception as e:
        st.error("Deu erro ao processar os arquivos.")
        st.exception(e)
        return

    # KPIs
    st.subheader("KPIs")
    kpi_df = pd.DataFrame([kpis])

    cols = st.columns(4)
    cols[0].metric("Investimento Ads", f"R$ {float(kpis.get('Investimento Ads (R$)', 0)):,.2f}")
    cols[1].metric("Receita Ads", f"R$ {float(kpis.get('Receita Ads (R$)', 0)):,.2f}")
    cols[2].metric("ROAS", f"{float(kpis.get('ROAS', 0)):.2f}")
    cols[3].metric("TACOS", f"{float(kpis.get('TACOS', 0)) * 100:.2f}%")

    with st.expander("Ver tabela de KPIs"):
        show_df(kpi_df)

    st.divider()

    # Serie diaria
    if daily is not None:
        st.subheader("Serie diaria")
        show_df(daily)

    st.subheader("Painel geral (controle)")
    panel = ml.build_control_panel(camp_strat)
    show_df(panel, use_container_width=True)

    st.divider()

    st.subheader("Matriz CPI (campanhas com estrategia)")
    show_df(camp_strat, use_container_width=True)

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pausar ou revisar campanhas")
        show_df(pause, use_container_width=True)
    with c2:
        st.subheader("Entrar em Ads (organico forte sem Ads)")
        show_df(enter, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Escalar orcamento")
        show_df(scale, use_container_width=True)
    with c4:
        st.subheader("Subir ACOS objetivo")
        show_df(acos, use_container_width=True)

    st.divider()

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
            "Baixar Excel do relatorio",
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
