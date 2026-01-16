import streamlit as st
from datetime import datetime
import ml_report as ml

st.set_page_config(page_title="ML Ads - Dashboard & Relatorio", layout="wide")
st.title("Mercado Livre Ads - Dashboard e Relatorio Automatico (Estrategico)")

modo = st.radio(
    "Selecione o tipo de relatorio de campanhas que voce exportou:",
    ["CONSOLIDADO (decisao)", "DIARIO (monitoramento)"],
    horizontal=True
)
modo_key = "consolidado" if "CONSOLIDADO" in modo else "diario"

with st.expander("Regras (ajustaveis)"):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        enter_visitas_min = st.number_input("ENTRAR: Visitas min.", min_value=0, value=50, step=10)
    with c2:
        enter_conv_pct = st.number_input("ENTRAR: Conversao organica min. (%)", min_value=0.0, value=5.0, step=0.5)
    with c3:
        pause_invest_min = st.number_input("PAUSAR: Investimento min. (R$)", min_value=0.0, value=100.0, step=50.0)
    with c4:
        pause_cvr_pct = st.number_input("PAUSAR: CVR max. (%)", min_value=0.0, value=1.0, step=0.2)

u1, u2, u3 = st.columns(3)
with u1:
    organico_file = st.file_uploader("Relatorio organico (publicacoes)", type=["xlsx"])
with u2:
    campanhas_file = st.file_uploader("Relatorio campanhas Ads", type=["xlsx"])
with u3:
    patrocinados_file = st.file_uploader("Relatorio anuncios patrocinados", type=["xlsx"])

if not (organico_file and campanhas_file and patrocinados_file):
    st.info("Envie os 3 arquivos para liberar o dashboard.")
    st.stop()

with st.spinner("Lendo arquivos..."):
    org = ml.load_organico(organico_file)
    pat = ml.load_patrocinados(patrocinados_file)
    camp = ml.load_campanhas_diario(campanhas_file) if modo_key == "diario" else ml.load_campanhas_consolidado(campanhas_file)

camp_agg = ml.build_campaign_agg(camp, modo_key)

kpis, pause, enter, scale, acos, camp_strat = ml.build_tables(
    org, camp_agg, pat,
    enter_visitas_min=int(enter_visitas_min),
    enter_conv_min=float(enter_conv_pct) / 100.0,
    pause_invest_min=float(pause_invest_min),
    pause_cvr_max=float(pause_cvr_pct) / 100.0,
)

daily = None
if modo_key == "diario":
    daily = ml.build_daily_from_diario(camp)

diagnosis = ml.build_executive_diagnosis(camp_strat, daily=daily)
panel = ml.build_control_panel(camp_strat)
high = ml.build_opportunity_highlights(camp_strat)
plan7 = ml.build_7_day_plan(camp_strat)

tab1, tab2 = st.tabs(["Dashboard", "Gerar Excel"])

with tab1:
    st.subheader("Diagnostico Executivo")
    st.write(f"ROAS da conta: **{diagnosis['ROAS']:.2f}** | ACOS real: **{diagnosis['ACOS_real']:.2f}**")
    st.write(f"**Veredito:** {diagnosis['Veredito']}")

    t = diagnosis.get("Tendencias", {})
    if t and (t.get("cpc_proxy_up") is not None):
        st.caption(
            f"Tendencias (ultimos 7d vs 7d anteriores) | "
            f"CPC proxy: {t['cpc_proxy_up']:+.1%} | "
            f"Ticket: {t['ticket_down']:+.1%} | "
            f"ROAS: {t['roas_down']:+.1%}"
        )
    st.divider()

    st.subheader("KPIs")
    a, b, c, d, e, f = st.columns(6)
    a.metric("Investimento", f"R$ {kpis['Investimento Ads (R$)']:.2f}")
    b.metric("Receita", f"R$ {kpis['Receita Ads (R$)']:.2f}")
    c.metric("Vendas", kpis["Vendas Ads"])
    d.metric("ROAS", f"{kpis['ROAS']:.2f}")
    e.metric("Campanhas unicas", kpis["Campanhas únicas"])
    f.metric("IDs patrocinados", kpis["IDs patrocinados únicos"])

    st.divider()

    if modo_key == "diario":
        st.subheader("Evolucao diaria")
        daily2 = daily.set_index("Desde")
        st.line_chart(daily2[["Investimento", "Receita", "Vendas"]])
        st.divider()

    st.subheader("Top 10 campanhas por Receita (fixo)")
    bar = camp_agg.copy()
    for col in ["Receita", "Investimento", "Vendas", "ROAS", "CVR"]:
        if col in bar.columns:
            bar[col] = bar[col].astype(float)
    bar = bar.sort_values("Receita", ascending=False).head(10).set_index("Nome")
    st.bar_chart(bar[["Receita"]])

    st.divider()

    st.subheader("Matriz de Oportunidade (Destaques)")
    cA, cB = st.columns(2)
    with cA:
        st.write("Locomotivas (CPI 80% + perda por classificacao)")
        st.dataframe(high["Locomotivas"], use_container_width=True)
    with cB:
        st.write("Minas Limitadas (ROAS alto + perda por orcamento)")
        st.dataframe(high["Minas"], use_container_width=True)

    st.divider()

    st.subheader("Plano de Acao - 7 dias")
    # Formata apenas a exibicao da Matriz de Oportunidade para limitar em 2 casas decimais.
_matriz_df = plan7.copy()
_num_cols = _matriz_df.select_dtypes(include=["number"]).columns

_fmt_map = {}
for _c in _num_cols:
    _lc = str(_c).lower()
    if "ctr" in _lc or "tacos" in _lc:
        _fmt_map[_c] = "{:.2%}"
    else:
        _fmt_map[_c] = "{:,.2f}"

st.dataframe(_matriz_df.style.format(_fmt_map), use_container_width=True)

    st.divider()

    st.subheader("Painel de Controle Geral (todas as campanhas)")
    st.dataframe(panel, use_container_width=True)

    st.divider()

    cC, cD = st.columns(2)
    with cC:
        st.subheader("Campanhas para PAUSAR/REVISAR")
        st.dataframe(pause, use_container_width=True)
    with cD:
        st.subheader("Anuncios para ENTRAR em Ads (organico forte)")
        st.dataframe(enter, use_container_width=True)

with tab2:
    st.subheader("Gerar relatorio final (Excel)")
    if st.button("Gerar e baixar Excel"):
        with st.spinner("Gerando Excel..."):
            bytes_xlsx = ml.gerar_excel(kpis, camp_agg, pause, enter, scale, acos, camp_strat, daily=daily)

        nome = f"Relatorio_ML_ADs_Estrategico_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
        st.download_button(
            "Baixar Excel",
            data=bytes_xlsx,
            file_name=nome,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.success("OK")
