import pandas as pd
from io import BytesIO

EMOJI_GREEN = "\U0001F7E2"   # green circle
EMOJI_YELLOW = "\U0001F7E1"  # yellow circle
EMOJI_BLUE = "\U0001F535"    # blue circle
EMOJI_RED = "\U0001F534"     # red circle

def _reorder_action_before_motivo(df: pd.DataFrame) -> pd.DataFrame:
    """Move Acao_Recomendada para ficar antes de Confianca_Dado e Motivo (se existirem).

    Regra: Acao_Recomendada sempre antes de Motivo, mantendo o resto na ordem original.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    cols = list(df.columns)
    if 'Acao_Recomendada' not in cols:
        return df

    def _pop(col):
        if col in cols:
            cols.remove(col)
            return col
        return None

    acao = _pop('Acao_Recomendada')
    conf = _pop('Confianca_Dado')
    motivo = _pop('Motivo')

    # tenta inserir apos Perdidas_Class, se existir; senao, apos ROAS_Real; senao, no inicio
    anchor = None
    for cand in ['Perdidas_Class', 'Perdidas_Orc', 'ROAS_Real', 'ROAS', 'Receita']:
        if cand in cols:
            anchor = cand
            break

    insert_at = 0
    if anchor is not None:
        insert_at = cols.index(anchor) + 1

    # insere na ordem desejada
    for col in [acao, conf, motivo]:
        if col is not None:
            cols.insert(insert_at, col)
            insert_at += 1

    return df[cols].copy()


def load_organico(organico_file) -> pd.DataFrame:
    org = pd.read_excel(organico_file, header=4)
    org.columns = [
        "ID","Titulo","Status","Variacao","SKU",
        "Visitas","Qtd_Vendas","Compradores",
        "Unidades","Vendas_Brutas","Participacao",
        "Conv_Visitas_Vendas","Conv_Visitas_Compradores"
    ]
    org = org[org["ID"] != "ID do anúncio"].copy()

    for c in ["Visitas","Qtd_Vendas","Compradores","Unidades","Vendas_Brutas",
              "Participacao","Conv_Visitas_Vendas","Conv_Visitas_Compradores"]:
        org[c] = pd.to_numeric(org[c], errors="coerce")

    org["ID"] = org["ID"].astype(str).str.replace("MLB", "", regex=False)
    return org


def load_patrocinados(patrocinados_file) -> pd.DataFrame:
    pat = pd.read_excel(patrocinados_file, sheet_name="Relatório Anúncios patrocinados", header=1)
    pat["ID"] = pat["Código do anúncio"].astype(str).str.replace("MLB", "", regex=False)

    for c in ["Impressões","Cliques","Receita\n(Moeda local)","Investimento\n(Moeda local)",
              "Vendas por publicidade\n(Diretas + Indiretas)"]:
        if c in pat.columns:
            pat[c] = pd.to_numeric(pat[c], errors="coerce")
    return pat


def _coerce_campaign_numeric(df: pd.DataFrame) -> pd.DataFrame:
    cols_num = [
        "Impressões","Cliques","Receita\n(Moeda local)","Investimento\n(Moeda local)",
        "Vendas por publicidade\n(Diretas + Indiretas)","ROAS\n(Receitas / Investimento)",
        "CVR\n(Conversion rate)","% de impressões perdidas por orçamento",
        "% de impressões perdidas por classificação","Orçamento","ACOS Objetivo"
    ]
    for c in cols_num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_campanhas_diario(campanhas_file) -> pd.DataFrame:
    camp = pd.read_excel(campanhas_file, sheet_name="Relatório de campanha", header=1)
    if "Desde" in camp.columns:
        camp["Desde"] = pd.to_datetime(camp["Desde"], errors="coerce")
    camp = _coerce_campaign_numeric(camp)
    return camp


def load_campanhas_consolidado(campanhas_file) -> pd.DataFrame:
    camp = pd.read_excel(campanhas_file, sheet_name="Relatório de campanha", header=1)
    camp = _coerce_campaign_numeric(camp)
    return camp


def build_daily_from_diario(camp_diario: pd.DataFrame) -> pd.DataFrame:
    daily = camp_diario.groupby("Desde", as_index=False).agg(
        Investimento=("Investimento\n(Moeda local)", "sum"),
        Receita=("Receita\n(Moeda local)", "sum"),
        Vendas=("Vendas por publicidade\n(Diretas + Indiretas)", "sum"),
        Cliques=("Cliques", "sum"),
        Impressoes=("Impressões", "sum"),
    )
    return daily.sort_values("Desde")


def build_campaign_agg(camp: pd.DataFrame, modo: str) -> pd.DataFrame:
    if modo == "diario":
        camp_agg = camp.groupby("Nome", as_index=False).agg(
            Status=("Status", "last"),
            Orçamento=("Orçamento", "last"),
            **{
                "ACOS Objetivo": ("ACOS Objetivo", "last"),
                "Impressões": ("Impressões", "sum"),
                "Cliques": ("Cliques", "sum"),
                "Receita": ("Receita\n(Moeda local)", "sum"),
                "Investimento": ("Investimento\n(Moeda local)", "sum"),
                "Vendas": ("Vendas por publicidade\n(Diretas + Indiretas)", "sum"),
                "ROAS": ("ROAS\n(Receitas / Investimento)", "mean"),
                "CVR": ("CVR\n(Conversion rate)", "mean"),
                "Perdidas_Orc": ("% de impressões perdidas por orçamento", "mean"),
                "Perdidas_Class": ("% de impressões perdidas por classificação", "mean"),
            }
        )
        return camp_agg

    camp_agg = camp.rename(columns={
        "Receita\n(Moeda local)": "Receita",
        "Investimento\n(Moeda local)": "Investimento",
        "Vendas por publicidade\n(Diretas + Indiretas)": "Vendas",
        "ROAS\n(Receitas / Investimento)": "ROAS",
        "CVR\n(Conversion rate)": "CVR",
        "% de impressões perdidas por orçamento": "Perdidas_Orc",
        "% de impressões perdidas por classificação": "Perdidas_Class",
    }).copy()

    needed = [
        "Nome","Status","Orçamento","ACOS Objetivo",
        "Impressões","Cliques","Receita","Investimento","Vendas",
        "ROAS","CVR","Perdidas_Orc","Perdidas_Class"
    ]
    for col in needed:
        if col not in camp_agg.columns:
            camp_agg[col] = pd.NA

    return camp_agg[needed].copy()


def _safe_div(a, b) -> float:
    try:
        if b and float(b) != 0.0:
            return float(a) / float(b)
    except Exception:
        pass
    return 0.0


def add_strategy_fields(
    camp_agg: pd.DataFrame,
    acos_over_pct: float = 0.30,
    roas_mina: float = 7.0,
    lost_budget_mina: float = 40.0,
    lost_rank_gigante: float = 50.0,
    roas_hemorragia: float = 3.0,
    # Travas incrementais
    comp_invest_min: float = 200.0,
    comp_clicks_min: int = 100,
    comp_sales_min: int = 2,
    hiper_roas_mult: float = 1.50,
    impacto_factor: float = 0.30,
) -> pd.DataFrame:
    df = camp_agg.copy()

    for c in [
        "Receita","Investimento","Vendas","Cliques","Impressões","ROAS","CVR",
        "Perdidas_Orc","Perdidas_Class","ACOS Objetivo","Orçamento"
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["ROAS_Real"] = df.apply(lambda r: _safe_div(r.get("Receita", 0), r.get("Investimento", 0)), axis=1)
    df["ACOS_Real"] = df.apply(lambda r: _safe_div(r.get("Investimento", 0), r.get("Receita", 0)), axis=1)

    if "ACOS Objetivo" in df.columns:
        df["ACOS_Objetivo_N"] = df["ACOS Objetivo"].copy()
        df.loc[df["ACOS_Objetivo_N"] > 1.5, "ACOS_Objetivo_N"] = df.loc[
            df["ACOS_Objetivo_N"] > 1.5, "ACOS_Objetivo_N"
        ] / 100.0
    else:
        df["ACOS_Objetivo_N"] = pd.NA

    def _roas_obj(acos_obj_n):
        try:
            if pd.notna(acos_obj_n) and float(acos_obj_n) > 0:
                return 1.0 / float(acos_obj_n)
        except Exception:
            pass
        return pd.NA

    df["ROAS_Objetivo"] = df["ACOS_Objetivo_N"].map(_roas_obj)

    total_receita = float(pd.to_numeric(df.get("Receita"), errors="coerce").fillna(0).sum())
    receita_relevante = max(500.0, total_receita * 0.05)

    df = df.sort_values("Receita", ascending=False).reset_index(drop=True)
    df["Receita"] = pd.to_numeric(df.get("Receita"), errors="coerce").fillna(0)
    df["CPI_Share"] = df["Receita"] / total_receita if total_receita else 0.0
    df["CPI_Cum"] = df["CPI_Share"].cumsum()
    df["CPI_80"] = df["CPI_Cum"] <= 0.80

    # Confianca de dado (nao muda o calculo, apenas blinda recomendacao)
    def _confidence(row):
        invest = float(row.get("Investimento", 0) or 0)
        clicks = float(row.get("Cliques", 0) or 0)
        sales = float(row.get("Vendas", 0) or 0)
        if (invest >= 300.0) or (clicks >= 200) or (sales >= 5):
            return "ALTA"
        if (invest >= 100.0) or (clicks >= 80) or (sales >= 2):
            return "MEDIA"
        return "BAIXA"

    df["Confianca_Dado"] = df.apply(_confidence, axis=1)

    def _impacto_estimado(row):
        receita = float(row.get("Receita", 0) or 0)
        lost_b = float(row.get("Perdidas_Orc", 0) or 0)
        if lost_b <= 0:
            return 0.0
        return receita * (lost_b / 100.0) * float(impacto_factor)

    df["Impacto_Estimado_R$"] = df.apply(_impacto_estimado, axis=1)

    def classify(row):
        roas = float(row.get("ROAS_Real", 0) or 0)
        lost_b = float(row.get("Perdidas_Orc", 0) or 0)
        lost_r = float(row.get("Perdidas_Class", 0) or 0)
        receita = float(row.get("Receita", 0) or 0)
        acos_real = float(row.get("ACOS_Real", 0) or 0)
        roas_obj = row.get("ROAS_Objetivo", pd.NA)
        invest = float(row.get("Investimento", 0) or 0)
        clicks = int(float(row.get("Cliques", 0) or 0))
        sales = int(float(row.get("Vendas", 0) or 0))

        if (roas >= roas_mina) and (lost_b >= lost_budget_mina):
            return "ESCALA_ORCAMENTO"

        # Competitividade (Rank) com trava de elasticidade
        if (receita >= receita_relevante) and (lost_r >= lost_rank_gigante):
            volume_ok = (invest >= comp_invest_min) and ((clicks >= comp_clicks_min) or (sales >= comp_sales_min))
            if volume_ok and pd.notna(roas_obj) and float(roas_obj) > 0:
                # Se estiver hiper eficiente vs objetivo, manter estavel
                if roas > (float(roas_obj) * float(hiper_roas_mult)):
                    return "ESTAVEL"
                return "COMPETITIVIDADE"

        hem = (roas > 0 and roas < roas_hemorragia)
        acos_obj_n = row.get("ACOS_Objetivo_N", pd.NA)
        if pd.notna(acos_obj_n) and acos_obj_n and float(acos_obj_n) > 0:
            if acos_real > (float(acos_obj_n) * (1.0 + acos_over_pct)):
                hem = True
        if hem:
            return "HEMORRAGIA"

        return "ESTAVEL"

    df["Quadrante"] = df.apply(classify, axis=1)

    def motivo(row):
        q = row.get("Quadrante")
        if q == "ESCALA_ORCAMENTO":
            return "ROAS forte com perda por orcamento alta"
        if q == "COMPETITIVIDADE":
            return "Receita relevante com perda por classificacao alta e ROAS perto do objetivo"
        if q == "HEMORRAGIA":
            acos_obj_n = row.get("ACOS_Objetivo_N", pd.NA)
            acos_real = float(row.get("ACOS_Real", 0) or 0)
            if pd.notna(acos_obj_n) and float(acos_obj_n) > 0 and acos_real > (float(acos_obj_n) * (1.0 + acos_over_pct)):
                return "ACOS real acima do objetivo"
            return "ROAS abaixo do minimo"
        return "Sem sinal claro de escala ou risco"

    df["Motivo"] = df.apply(motivo, axis=1)

    def action(row):
        q = row.get("Quadrante")
        conf = row.get("Confianca_Dado")

        # Baixa confianca, nunca empurra ajuste. Mantem como lista de atencao.
        if conf == "BAIXA":
            return f"{EMOJI_BLUE} Manter"

        if q == "ESCALA_ORCAMENTO":
            return f"{EMOJI_GREEN} Aumentar orcamento"
        if q == "COMPETITIVIDADE":
            return f"{EMOJI_YELLOW} Baixar ROAS objetivo"
        if q == "HEMORRAGIA":
            return f"{EMOJI_RED} Revisar/pausar"
        return f"{EMOJI_BLUE} Manter"

    df["Acao_Recomendada"] = df.apply(action, axis=1)

    # Se confianca baixa, registra motivo claro
    df.loc[df["Confianca_Dado"] == "BAIXA", "Motivo"] = "Baixo volume, manter coletando dado"

    # Ordem de leitura nas tabelas: acao antes de confianca e motivo
    df = _reorder_action_before_motivo(df)

    return df


def build_executive_diagnosis(camp_agg_strat: pd.DataFrame, daily: pd.DataFrame = None) -> dict:
    df = camp_agg_strat.copy()

    invest = float(pd.to_numeric(df["Investimento"], errors="coerce").fillna(0).sum())
    receita = float(pd.to_numeric(df["Receita"], errors="coerce").fillna(0).sum())
    vendas = float(pd.to_numeric(df["Vendas"], errors="coerce").fillna(0).sum())
    roas = _safe_div(receita, invest)
    acos = _safe_div(invest, receita)

    trend = {"cpc_proxy_up": None, "ticket_down": None, "roas_down": None}

    if daily is not None and len(daily) >= 14 and "Desde" in daily.columns:
        d = daily.copy().sort_values("Desde")
        last7 = d.tail(7)
        prev7 = d.tail(14).head(7)

        inv_l = float(pd.to_numeric(last7["Investimento"], errors="coerce").fillna(0).sum())
        clk_l = float(pd.to_numeric(last7["Cliques"], errors="coerce").fillna(0).sum())
        rec_l = float(pd.to_numeric(last7["Receita"], errors="coerce").fillna(0).sum())
        ven_l = float(pd.to_numeric(last7["Vendas"], errors="coerce").fillna(0).sum())

        inv_p = float(pd.to_numeric(prev7["Investimento"], errors="coerce").fillna(0).sum())
        clk_p = float(pd.to_numeric(prev7["Cliques"], errors="coerce").fillna(0).sum())
        rec_p = float(pd.to_numeric(prev7["Receita"], errors="coerce").fillna(0).sum())
        ven_p = float(pd.to_numeric(prev7["Vendas"], errors="coerce").fillna(0).sum())

        cpc_l = _safe_div(inv_l, clk_l)
        cpc_p = _safe_div(inv_p, clk_p)
        ticket_l = _safe_div(rec_l, ven_l)
        ticket_p = _safe_div(rec_p, ven_p)
        roas_l = _safe_div(rec_l, inv_l)
        roas_p = _safe_div(rec_p, inv_p)

        if cpc_p > 0:
            trend["cpc_proxy_up"] = (cpc_l / cpc_p) - 1.0
        if ticket_p > 0:
            trend["ticket_down"] = (ticket_l / ticket_p) - 1.0
        if roas_p > 0:
            trend["roas_down"] = (roas_l / roas_p) - 1.0

    mines = df[df["Quadrante"] == "ESCALA_ORCAMENTO"]
    giants = df[df["Quadrante"] == "COMPETITIVIDADE"]
    hemorr = df[df["Quadrante"] == "HEMORRAGIA"]

    mines_cnt = int(len(mines))
    giants_cnt = int(len(giants))
    hemorr_share_inv = _safe_div(float(pd.to_numeric(hemorr["Investimento"], errors="coerce").fillna(0).sum()), invest)

    if (mines_cnt + giants_cnt) >= 3:
        verdict = "Estamos deixando dinheiro na mesa."
    elif hemorr_share_inv >= 0.30 and roas < 4:
        verdict = "Precisamos estancar sangria."
    else:
        verdict = "Conta esta controlada, priorize destravar escala."

    return {
        "Investimento": invest,
        "Receita": receita,
        "Vendas": vendas,
        "ROAS": roas,
        "ACOS_real": acos,
        "Tendencias": trend,
        "Veredito": verdict
    }


def build_opportunity_highlights(camp_agg_strat: pd.DataFrame) -> dict:
    df = camp_agg_strat.copy()

    locomotivas = df[(df["CPI_80"] == True) & (df["Quadrante"] == "COMPETITIVIDADE")].copy()
    locomotivas = locomotivas.sort_values("Receita", ascending=False).head(5)

    minas = df[df["Quadrante"] == "ESCALA_ORCAMENTO"].copy()
    # Prioriza impacto estimado e depois perda por orcamento
    sort_cols = [c for c in ["Impacto_Estimado_R$", "Perdidas_Orc", "ROAS_Real"] if c in minas.columns]
    if sort_cols:
        minas = minas.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(5)
    else:
        minas = minas.sort_values(["ROAS_Real", "Perdidas_Orc"], ascending=[False, False]).head(5)

    def proj(row):
        receita = float(row.get("Receita", 0) or 0)
        lost = float(row.get("Perdidas_Orc", 0) or 0)
        if lost <= 0 or lost >= 95:
            return 0.0
        factor = lost / max(1.0, (100.0 - lost))
        return receita * factor

    minas["Potencial_Receita"] = minas.apply(proj, axis=1)
    return {"Locomotivas": locomotivas, "Minas": minas}


def build_7_day_plan(camp_agg_strat: pd.DataFrame) -> pd.DataFrame:
    df = camp_agg_strat.copy()

    cols_d1 = [c for c in ["Nome","Orçamento","Perdidas_Orc","ROAS_Real","Impacto_Estimado_R$","Acao_Recomendada","Confianca_Dado","Motivo"] if c in df.columns]
    d1 = df[df["Quadrante"] == "ESCALA_ORCAMENTO"][cols_d1].copy()
    d1["Dia"] = "Dia 1"
    d1["Tarefa"] = "Aumentar orcamento com controle (+20% a +40%)"

    cols_d2 = [c for c in ["Nome","ROAS_Objetivo","Perdidas_Class","Receita","Acao_Recomendada","Confianca_Dado","Motivo"] if c in df.columns]
    d2 = df[df["Quadrante"] == "COMPETITIVIDADE"][cols_d2].copy()
    d2["Dia"] = "Dia 2"
    d2["Tarefa"] = "Baixar ROAS objetivo (abrir funil) apenas se houver elasticidade"

    cols_d5 = [c for c in ["Nome","Investimento","Receita","ROAS_Real","Perdidas_Orc","Perdidas_Class","Acao_Recomendada","Confianca_Dado"] if c in df.columns]
    d5 = df[df["Quadrante"].isin(["ESCALA_ORCAMENTO","COMPETITIVIDADE","HEMORRAGIA"])][cols_d5].copy()
    d5["Dia"] = "Dia 5"
    d5["Tarefa"] = "Monitorar investimento, ROAS e perdas"

    plan = pd.concat([d1, d2, d5], ignore_index=True, sort=False)
    return plan.sort_values(["Dia"], ascending=True)


def build_control_panel(camp_agg_strat: pd.DataFrame) -> pd.DataFrame:
    df = camp_agg_strat.copy()
    # Ordem de leitura: diagnostico -> acao -> confianca -> justificativa -> impacto
    base_cols = [
        "Nome","Orçamento","ACOS Objetivo","ROAS_Objetivo","ROAS_Real",
        "Perdidas_Orc","Perdidas_Class",
        "Acao_Recomendada","Confianca_Dado","Motivo","Impacto_Estimado_R$",
    ]
    cols = [c for c in base_cols if c in df.columns]
    panel = df[cols].copy()

    if "Receita" in df.columns:
        panel = panel.join(df[["Nome","Receita"]].set_index("Nome"), on="Nome")
        panel = panel.sort_values("Receita", ascending=False).drop(columns=["Receita"])

    return panel


def build_tables(
    org: pd.DataFrame,
    camp_agg: pd.DataFrame,
    pat: pd.DataFrame,
    enter_visitas_min: int = 50,
    enter_conv_min: float = 0.05,
    pause_invest_min: float = 100.0,
    pause_cvr_max: float = 0.01
):
    camp_strat = add_strategy_fields(camp_agg)

    pause = camp_strat[
        (camp_strat["Investimento"] > pause_invest_min) &
        ((camp_strat["Vendas"] <= 0) | (camp_strat["CVR"] < pause_cvr_max) | (camp_strat["Quadrante"] == "HEMORRAGIA"))
    ].copy()
    pause["Ação"] = "PAUSAR/REVISAR"
    pause = pause.sort_values("Investimento", ascending=False)
    pause = _reorder_action_before_motivo(pause)

    ads_ids = set(pat["ID"].dropna().astype(str).unique())
    enter = org[
        (org["Visitas"] >= enter_visitas_min) &
        (org["Conv_Visitas_Vendas"] > enter_conv_min) &
        (~org["ID"].astype(str).isin(ads_ids))
    ].copy()
    enter["Codigo_MLB"] = "MLB" + enter["ID"].astype(str)
    enter["Ação"] = "INSERIR EM ADS"
    enter = enter.sort_values(["Conv_Visitas_Vendas","Visitas"], ascending=[False, False])
    enter = enter[["ID","Codigo_MLB","Titulo","Conv_Visitas_Vendas","Visitas","Qtd_Vendas","Vendas_Brutas","Ação"]]

    scale = camp_strat[camp_strat["Quadrante"] == "ESCALA_ORCAMENTO"].copy()
    scale["Ação"] = "AUMENTAR ORCAMENTO"
    if "Impacto_Estimado_R$" in scale.columns:
        scale = scale.sort_values(["Impacto_Estimado_R$","Perdidas_Orc"], ascending=[False, False])
    elif "Perdidas_Orc" in scale.columns:
        scale = scale.sort_values("Perdidas_Orc", ascending=False)

    scale = _reorder_action_before_motivo(scale)

    acos = camp_strat[camp_strat["Quadrante"] == "COMPETITIVIDADE"].copy()
    acos["Ação"] = "BAIXAR ROAS OBJETIVO"
    if "Perdidas_Class" in acos.columns:
        acos = acos.sort_values(["Perdidas_Class","Receita"], ascending=[False, False])

    acos = _reorder_action_before_motivo(acos)

    invest_total = float(pd.to_numeric(camp_agg["Investimento"], errors="coerce").fillna(0).sum())
    receita_total = float(pd.to_numeric(camp_agg["Receita"], errors="coerce").fillna(0).sum())
    vendas_total = int(pd.to_numeric(camp_agg["Vendas"], errors="coerce").fillna(0).sum())
    roas_total = (receita_total / invest_total) if invest_total else 0.0

    # TACOS = Investimento Ads / Faturamento total da conta.
    # Faturamento total da conta vem do relatorio organico (publicacoes), coluna Vendas_Brutas.
    faturamento_total = float(pd.to_numeric(org.get("Vendas_Brutas"), errors="coerce").fillna(0).sum())
    tacos = (invest_total / faturamento_total) if faturamento_total else 0.0

    kpis = {
        "Campanhas únicas": int(camp_agg["Nome"].nunique()),
        "IDs patrocinados únicos": int(pat["ID"].nunique()),
        "Investimento Ads (R$)": invest_total,
        "Receita Ads (R$)": receita_total,
        "Vendas Ads": vendas_total,
        "ROAS": roas_total,
        "TACOS": tacos,
        "Faturamento total (R$)": faturamento_total,
    }

    camp_strat = _reorder_action_before_motivo(camp_strat)
    return kpis, pause, enter, scale, acos, camp_strat


def gerar_excel(kpis, camp_agg, pause, enter, scale, acos, camp_strat, daily=None) -> bytes:
    diagnosis = build_executive_diagnosis(camp_strat, daily=daily)
    highlights = build_opportunity_highlights(camp_strat)
    plan7 = build_7_day_plan(camp_strat)
    panel = build_control_panel(camp_strat)

    resumo = pd.DataFrame([kpis])
    diag_df = pd.DataFrame([{
        "Investimento": diagnosis["Investimento"],
        "Receita": diagnosis["Receita"],
        "Vendas": diagnosis["Vendas"],
        "ROAS": diagnosis["ROAS"],
        "ACOS_real": diagnosis["ACOS_real"],
        "Veredito": diagnosis["Veredito"],
        "Trend_cpc_proxy": diagnosis["Tendencias"]["cpc_proxy_up"],
        "Trend_ticket": diagnosis["Tendencias"]["ticket_down"],
        "Trend_roas": diagnosis["Tendencias"]["roas_down"],
    }])

    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        diag_df.to_excel(writer, index=False, sheet_name="DIAGNOSTICO_EXEC")
        resumo.to_excel(writer, index=False, sheet_name="RESUMO")
        panel.to_excel(writer, index=False, sheet_name="PAINEL_GERAL")
        camp_strat.to_excel(writer, index=False, sheet_name="MATRIZ_CPI")
        highlights["Locomotivas"].to_excel(writer, index=False, sheet_name="LOCOMOTIVAS")
        highlights["Minas"].to_excel(writer, index=False, sheet_name="MINAS_LIMITADAS")
        plan7.to_excel(writer, index=False, sheet_name="PLANO_7_DIAS")
        pause.to_excel(writer, index=False, sheet_name="PAUSAR_CAMPANHAS")
        enter.to_excel(writer, index=False, sheet_name="ENTRAR_EM_ADS")
        scale.to_excel(writer, index=False, sheet_name="ESCALAR_ORCAMENTO")
        acos.to_excel(writer, index=False, sheet_name="BAIXAR_ROAS")
        camp_agg.to_excel(writer, index=False, sheet_name="BASE_CAMPANHAS_AGG")
        if daily is not None:
            daily.to_excel(writer, index=False, sheet_name="SERIE_DIARIA")
    out.seek(0)
    return out.read()
