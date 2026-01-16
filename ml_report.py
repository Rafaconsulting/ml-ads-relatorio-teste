import pandas as pd
import numpy as np


def safe_div(n, d):
    if d == 0 or pd.isna(d):
        return 0
    return n / d


def build_campaign_summary(df):
    grouped = (
        df.groupby("Campanha", as_index=False)
        .agg(
            Investimento=("Custo", "sum"),
            Receita=("Receita", "sum"),
            Cliques=("Cliques", "sum"),
            Impressoes=("Impressoes", "sum"),
            Conversoes=("Conversoes", "sum"),
        )
    )

    grouped["ROAS"] = grouped.apply(
        lambda r: safe_div(r["Receita"], r["Investimento"]), axis=1
    )
    grouped["CPC"] = grouped.apply(
        lambda r: safe_div(r["Investimento"], r["Cliques"]), axis=1
    )
    grouped["CTR"] = grouped.apply(
        lambda r: safe_div(r["Cliques"], r["Impressoes"]), axis=1
    )
    grouped["CPA"] = grouped.apply(
        lambda r: safe_div(r["Investimento"], r["Conversoes"]), axis=1
    )

    return grouped


def classify_campaigns(df, roas_target=3):
    conditions = [
        (df["Investimento"] > 0) & (df["ROAS"] < roas_target),
        (df["Investimento"] > 0) & (df["ROAS"] >= roas_target),
    ]

    choices = [
        "Minas Limitadas",
        "Escala",
    ]

    df["Classificacao"] = np.select(conditions, choices, default="Observacao")
    return df


def build_opportunity_highlights(df):
    minas = df[df["Classificacao"] == "Minas Limitadas"].copy()

    def proj(row):
        gap = max(0, 3 - row["ROAS"])
        return row["Receita"] * (1 + gap)

    minas["Potencial_Receita"] = minas.apply(proj, axis=1)

    # >>> PATCH ADICIONADO <<<
    # Projecoes de receita para Minas Limitadas com cenarios de aumento de orcamento
    # Premissa: ROAS constante, receita escala linearmente com o orcamento
    if "Receita" in minas.columns:
        minas["Receita"] = pd.to_numeric(minas["Receita"], errors="coerce").fillna(0.0)
        minas["Receita proj (+30% orcamento)"] = minas["Receita"] * 1.30
        minas["Receita proj (+60% orcamento)"] = minas["Receita"] * 1.60
    # >>> FIM DO PATCH <<<

    return {
        "Minas": minas.sort_values("Potencial_Receita", ascending=False)
    }


def generate_excel_report(
    campaign_summary,
    highlights,
    output_path="ml_ads_report.xlsx",
):
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        campaign_summary.to_excel(writer, sheet_name="Resumo_Campanhas", index=False)

        if "Minas" in highlights:
            highlights["Minas"].to_excel(
                writer, sheet_name="MINAS_LIMITADAS", index=False
            )

    return output_path
