import pandas as pd
from io import BytesIO
import unicodedata
import re

EMOJI_GREEN = '🟢'   # green circle
EMOJI_YELLOW = '🟡'  # yellow circle
EMOJI_BLUE = '🔵'    # blue circle
EMOJI_RED = '🔴'     # red circle






def _safe_seek(x, pos=0):
    try:
        x.seek(pos)
    except Exception:
        pass


def _pick_sheet(excel_file, preferred_names=None, must_have_terms=None):
    preferred_names = preferred_names or []
    must_have_terms = must_have_terms or []

    _safe_seek(excel_file, 0)
    xls = pd.ExcelFile(excel_file)
    sheets = list(xls.sheet_names)

    # match direto por nome preferido
    for p in preferred_names:
        if p in sheets:
            return p

    # match por termos (normalizado)
    sheets_norm = {s: _norm_col_key(s) for s in sheets}
    terms = [_norm_col_key(t) for t in must_have_terms]

    for s, sn in sheets_norm.items():
        ok = True
        for t in terms:
            if t and t not in sn:
                ok = False
                break
        if ok:
            return s

    # fallback
    return sheets[0] if sheets else None

def _norm_col_key(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower().replace("\n", " ").replace("\r", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _standardize_cols_by_candidates(df: pd.DataFrame, candidates_map: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    col_keys = {_norm_col_key(c): c for c in df.columns}
    ren = {}

    for canonical, cands in candidates_map.items():
        for cand in cands:
            k = _norm_col_key(cand)
            if k in col_keys:
                ren[col_keys[k]] = canonical
                break

    if ren:
        df = df.rename(columns=ren)

    return df


_CAMPAIGN_COL_CANDIDATES = {
    "Nome": ["Nome", "Nome da campanha", "Campanha", "Campaign"],
    "Status": ["Status", "Status atual"],
    "Orçamento": [
        "Orçamento",
        "Orcamento",
        "Orçamento diário",
        "Orcamento diario",
        "Orçamento (Moeda local)",
        "Orcamento (Moeda local)",
    ],
    "ACOS Objetivo": ["ACOS Objetivo", "ACOS objetivo", "ACOS alvo", "ACOS target"],
    "Impressões": ["Impressões", "Impressoes", "Impressions"],
    "Cliques": ["Cliques", "Clicks"],
    "Receita\n(Moeda local)": [
        "Receita\n(Moeda local)",
        "Receita (Moeda local)",
        "Receita (moeda local)",
        "Receita",
    ],
    "Investimento\n(Moeda local)": [
        "Investimento\n(Moeda local)",
        "Investimento (Moeda local)",
        "Investimento (moeda local)",
        "Gasto",
        "Spend",
        "Investimento",
    ],
    "Vendas por publicidade\n(Diretas + Indiretas)": [
        "Vendas por publicidade\n(Diretas + Indiretas)",
        "Vendas por publicidade (Diretas + Indiretas)",
        "Vendas por publicidade",
        "Vendas por ads",
        "Sales from ads",
    ],
    "ROAS\n(Receitas / Investimento)": [
        "ROAS\n(Receitas / Investimento)",
        "ROAS (Receitas / Investimento)",
        "ROAS",
    ],
    "CVR\n(Conversion rate)": [
        "CVR\n(Conversion rate)",
        "CVR (Conversion rate)",
        "CVR",
        "Taxa de conversão",
    ],
    "% de impressões perdidas por orçamento": [
        "% de impressões perdidas por orçamento",
        "% de impressoes perdidas por orcamento",
        "% de impressões perdidas por orçamento (IS lost budget)",
    ],
    "% de impressões perdidas por classificação": [
        "% de impressões perdidas por classificação",
        "% de impressoes perdidas por classificacao",
        "% de impressões perdidas por classificação (IS lost rank)",
    ],
    "Desde": ["Desde", "Data", "Date"],
}

def _is_active_status(val) -> bool:
    """Retorna True para status 'Ativa/Ativo/Active' (ignorando caixa e acentos)."""
    if val is None:
        return False
    s = str(val).strip().lower()
    # normaliza acentos básicos
    s = (
        s.replace("á","a").replace("à","a").replace("â","a").replace("ã","a")
         .replace("é","e").replace("ê","e")
         .replace("í","i")
         .replace("ó","o").replace("ô","o").replace("õ","o")
         .replace("ú","u")
         .replace("ç","c")
    )
    return (s.startswith("ativa") or s.startswith("ativo") or s.startswith("active"))


def _to_number_ptbr(val):
    # Converte strings pt-BR (1.234,56 | 52,00% | R$ 1.234,56) para float
    if val is None:
        return None
    try:
        # pandas NA
        if val is pd.NA:
            return None
    except Exception:
        pass

    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if s == '' or s.lower() in {'nan', 'none', '<na>'}:
        return None

    # remove moeda e espacos
    s = s.replace('R$', '').replace(' ', ' ').strip()
    # remove separador de milhar
    s = s.replace('.', '')

    # lida com porcentagem (mantem em "pontos". Ex: 52,00% -> 52.0)
    if s.endswith('%'):
        s = s[:-1].strip()

    # decimal pt-BR
    s = s.replace(',', '.')

    # mantem apenas digitos, sinal e ponto
    cleaned = []
    for ch in s:
        if ch.isdigit() or ch in {'.', '-', '+'}:
            cleaned.append(ch)
    s = ''.join(cleaned)

    try:
        return float(s)
    except Exception:
        return None


def _coerce_series_numeric_ptbr(series: pd.Series) -> pd.Series:
    if series is None:
        return series
    return series.apply(_to_number_ptbr)



def load_organico(organico_file) -> pd.DataFrame:
    # Relatorio de desempenho de publicacoes (Excel exportado do Mercado Livre)
    # Problema recorrente: a coluna "Vendas brutas" pode vir como numero (float)
    # quando o Excel/pandas interpreta "3.144" como 3.144, mas no padrao pt-BR isso
    # significa 3.144,00 (tres mil cento e quarenta e quatro).
    # Para evitar isso, lemos como texto e convertemos com parser pt-BR.

    # Descobre automaticamente a linha de cabecalho (onde aparece "ID do anúncio")
    preview = pd.read_excel(organico_file, sheet_name="Relatório", header=None, nrows=40)
    header_row = None
    for i in range(len(preview)):
        row = preview.iloc[i].astype(str)
        if row.str.contains(r"\bID do anúncio\b", case=False, na=False).any():
            header_row = i
            break
    if header_row is None:
        # fallback historico
        header_row = 4

    org = pd.read_excel(organico_file, sheet_name="Relatório", header=header_row, dtype=str)

    # Normaliza nomes esperados
    rename_map = {
        "ID do anúncio": "ID",
        "Anúncio": "Titulo",
        "Status atual": "Status",
        "Variação": "Variacao",
        "SKU": "SKU",
        "Visitas únicas": "Visitas",
        "Quantidade de vendas": "Qtd_Vendas",
        "Compradores únicos": "Compradores",
        "Unidades vendidas": "Unidades",
        "Vendas brutas (BRL)": "Vendas_Brutas",
        "% de participação": "Participacao",
        "Conversão de visitas em vendas": "Conv_Visitas_Vendas",
        "Conversão de visitas em compradores": "Conv_Visitas_Compradores",
    }
    org = org.rename(columns={k: v for k, v in rename_map.items() if k in org.columns})

    # remove linhas repetidas de cabecalho, se existirem
    if "ID" in org.columns:
        org = org[org["ID"].astype(str).str.strip().str.lower() != "id do anúncio"].copy()

    for c in ["Visitas","Qtd_Vendas","Compradores","Unidades","Vendas_Brutas",
              "Participacao","Conv_Visitas_Vendas","Conv_Visitas_Compradores"]:
        if c in org.columns:
            org[c] = _coerce_series_numeric_ptbr(org[c])

    
    # Recalcula conversões de forma consistente usando as colunas-base.
    # Mantemos em percentual (0 a 100), pois o app usa regra e exibição em %.
    if "Visitas" in org.columns and "Qtd_Vendas" in org.columns:
        v = pd.to_numeric(org["Visitas"], errors="coerce").fillna(0)
        s = pd.to_numeric(org["Qtd_Vendas"], errors="coerce").fillna(0)
        conv = (s / v.replace({0: pd.NA})) * 100
        conv = conv.fillna(0).clip(lower=0, upper=100)
        org["Conv_Visitas_Vendas"] = conv

    if "Visitas" in org.columns and "Compradores" in org.columns:
        v = pd.to_numeric(org["Visitas"], errors="coerce").fillna(0)
        b = pd.to_numeric(org["Compradores"], errors="coerce").fillna(0)
        convb = (b / v.replace({0: pd.NA})) * 100
        convb = convb.fillna(0).clip(lower=0, upper=100)
        org["Conv_Visitas_Compradores"] = convb
    if "ID" in org.columns:
        org["ID"] = org["ID"].astype(str).str.replace("MLB", "", regex=False).str.replace(r"\.0$", "", regex=True)
    return org


def save_snapshot_v2(df_campanha_estrategica, df_anuncio_estrategico, snapshot_path, kpis_globais=None):
    """
    Salva um snapshot completo (campanhas e anúncios) em um arquivo Excel.
    df_campanha_estrategica: DataFrame com a análise de campanhas.
    df_anuncio_estrategico: DataFrame com a análise de anúncios.
    snapshot_path: Caminho completo para salvar o arquivo Excel.
    kpis_globais: Dicionário com os KPIs totais da conta (Investimento, Receita, etc).
    """
    if df_campanha_estrategica is None or df_campanha_estrategica.empty:
        raise ValueError("O DataFrame de Campanhas Estratégicas está vazio.")
    if df_anuncio_estrategico is None or df_anuncio_estrategico.empty:
        raise ValueError("O DataFrame de Anúncios Estratégicos está vazio.")

    # Colunas essenciais para o snapshot de campanhas
    camp_cols = [
        "Nome", "Investimento", "Receita", "ROAS_Real", "ACOS_Objetivo", 
        "Quadrante", "Acao_Recomendada", "Confianca_Dado", "Motivo",
        "% de impressões perdidas por orçamento", "% de impressões perdidas por classificação"
    ]
    camp_snap = df_campanha_estrategica[[c for c in camp_cols if c in df_campanha_estrategica.columns]].copy()

    # Colunas essenciais para o snapshot de anúncios
    anuncio_cols = [
        "ID", "Titulo", "Campanha", "Investimento", "Receita", "ROAS_Real", "CVR_pct",
        "Status_Anuncio", "Acao_Anuncio", "Confianca_Anuncio", "Motivo_Anuncio", "Refino_Campanha"
    ]
    anuncio_snap = df_anuncio_estrategico[[c for c in anuncio_cols if c in df_anuncio_estrategico.columns]].copy()

    # Salva em abas separadas
    with pd.ExcelWriter(snapshot_path, engine='xlsxwriter') as writer:
        camp_snap.to_excel(writer, sheet_name='Campanhas_Snapshot', index=False)
        anuncio_snap.to_excel(writer, sheet_name='Anuncios_Snapshot', index=False)
        
        # Salva KPIs globais em uma aba dedicada para garantir paridade total
        if kpis_globais:
            df_kpis = pd.DataFrame([kpis_globais])
            df_kpis.to_excel(writer, sheet_name='KPIs_Globais', index=False)

    return snapshot_path


def load_snapshot_v2(snapshot_file) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Carrega o snapshot v2 (campanhas, anúncios e KPIs) de um arquivo Excel.
    """
    if snapshot_file is None:
        return None, None, None

    try:
        camp_snap = pd.read_excel(snapshot_file, sheet_name='Campanhas_Snapshot')
        anuncio_snap = pd.read_excel(snapshot_file, sheet_name='Anuncios_Snapshot')
        
        kpis_snap = None
        try:
            # Tenta ler a aba de KPIs Globais
            df_kpis = pd.read_excel(snapshot_file, sheet_name='KPIs_Globais')
            if not df_kpis.empty:
                # Converte todos os valores para float para garantir paridade
                kpis_snap = {k: float(v) if isinstance(v, (int, float, str)) else v for k, v in df_kpis.iloc[0].to_dict().items()}
        except Exception as e:
            # Fallback para snapshots antigos que não tinham essa aba
            print(f"Aviso: Aba KPIs_Globais não encontrada no snapshot. Usando fallback. ({e})")
            
        return camp_snap, anuncio_snap, kpis_snap
    except Exception as e:
        print(f"Erro ao carregar snapshot v2: {e}")
        return None, None, None


def compare_snapshots_campanha(df_atual: pd.DataFrame, df_snapshot: pd.DataFrame) -> pd.DataFrame:
    """
    Compara o DataFrame de campanhas atual com o snapshot anterior.
    Adiciona colunas de variação (delta) e migração de quadrante.
    """
    if df_snapshot is None or df_snapshot.empty:
        df_out = df_atual.copy()
        df_out["Delta_Investimento"] = 0.0
        df_out["Delta_Receita"] = 0.0
        df_out["Delta_ROAS"] = 0.0
        return df_out

    # Renomear colunas do snapshot para evitar conflito
    snap_cols_map = {
        "Investimento": "Investimento_Snap",
        "Receita": "Receita_Snap",
        "ROAS_Real": "ROAS_Real_Snap",
        "Quadrante": "Quadrante_Snap",
        "Acao_Recomendada": "Acao_Recomendada_Snap",
    }
    df_snapshot_renamed = df_snapshot.rename(columns=snap_cols_map)

    # Merge pelo nome da campanha
    df_merged = df_atual.merge(
        df_snapshot_renamed,
        on="Nome",
        how="left",
        suffixes=("_Atual", "_Snap")
    )

    # Cálculo das variações (Delta)
    df_merged["Delta_Investimento"] = df_merged["Investimento"] - df_merged.get("Investimento_Snap", 0)
    df_merged["Delta_Receita"] = df_merged["Receita"] - df_merged.get("Receita_Snap", 0)
    df_merged["Delta_ROAS"] = df_merged["ROAS_Real"] - df_merged.get("ROAS_Real_Snap", 0)

    # Migração de Quadrante
    def _migracao(row):
        atual = str(row.get("Quadrante", "")).strip().upper()
        snap = str(row.get("Quadrante_Snap", "")).strip().upper()
        if not snap or snap == "NAN":
            return "NOVA"
        if atual == snap:
            return "ESTÁVEL"
        return f"DE {snap} PARA {atual}"

    df_merged["Migracao_Quadrante"] = df_merged.apply(_migracao, axis=1)

    return df_merged


def compare_snapshots_anuncio(df_atual: pd.DataFrame, df_snapshot: pd.DataFrame) -> pd.DataFrame:
    """
    Compara o DataFrame de anúncios atual com o snapshot anterior.
    Adiciona colunas de variação (delta) e migração de status.
    """
    if df_snapshot is None or df_snapshot.empty:
        df_out = df_atual.copy()
        df_out["Delta_Investimento"] = 0.0
        df_out["Delta_Receita"] = 0.0
        df_out["Delta_ROAS"] = 0.0
        return df_out

    # Renomear colunas do snapshot para evitar conflito
    snap_cols_map = {
        "Investimento": "Investimento_Snap",
        "Receita": "Receita_Snap",
        "ROAS_Real": "ROAS_Real_Snap",
        "Status_Anuncio": "Status_Anuncio_Snap",
        "Acao_Anuncio": "Acao_Anuncio_Snap",
    }
    df_snapshot_renamed = df_snapshot.rename(columns=snap_cols_map)

    # Padroniza ID para string para evitar erro de merge entre object e int64
    df_atual = df_atual.copy()
    df_snapshot_renamed = df_snapshot_renamed.copy()
    df_atual["ID"] = df_atual["ID"].astype(str).str.strip()
    df_snapshot_renamed["ID"] = df_snapshot_renamed["ID"].astype(str).str.strip()

    # Merge pelo ID do anúncio (MLB)
    df_merged = df_atual.merge(
        df_snapshot_renamed,
        on="ID",
        how="left",
        suffixes=("_Atual", "_Snap")
    )

    # Cálculo das variações (Delta)
    df_merged["Delta_Investimento"] = df_merged["Investimento"] - df_merged.get("Investimento_Snap", 0)
    df_merged["Delta_Receita"] = df_merged["Receita"] - df_merged.get("Receita_Snap", 0)
    df_merged["Delta_ROAS"] = df_merged["ROAS_Real"] - df_merged.get("ROAS_Real_Snap", 0)

    # Migração de Status
    def _migracao(row):
        atual = str(row.get("Status_Anuncio", "")).strip().upper()
        snap = str(row.get("Status_Anuncio_Snap", "")).strip().upper()
        if not snap or snap == "NAN":
            return "NOVO"
        if atual == snap:
            return "ESTÁVEL"
        return f"DE {snap} PARA {atual}"

    df_merged["Migracao_Status"] = df_merged.apply(_migracao, axis=1)

    return df_merged


def load_patrocinados(patrocinados_file) -> pd.DataFrame:
    _safe_seek(patrocinados_file, 0)
    sheet = _pick_sheet(
        patrocinados_file,
        preferred_names=["Relatório Anúncios patrocinados", "Relatorio Anuncios patrocinados", "Relatório de anúncios patrocinados", "Relatorio de anuncios patrocinados"],
        must_have_terms=["relatorio", "anuncio"],
    )
    _safe_seek(patrocinados_file, 0)
    pat = pd.read_excel(patrocinados_file, sheet_name=sheet, header=1)

    if "Código do anúncio" in pat.columns:
        pat["ID"] = pat["Código do anúncio"].astype(str).str.replace("MLB", "", regex=False).str.replace(r"\.0$", "", regex=True)
    else:
        # fallback: tenta achar alguma coluna com "codigo" e "anuncio"
        cand = None
        for c in pat.columns:
            ck = _norm_col_key(c)
            if "codigo" in ck and "anuncio" in ck:
                cand = c
                break
        if cand is None:
            cand = pat.columns[0]
        pat["ID"] = pat[cand].astype(str).str.replace("MLB", "", regex=False).str.replace(r"\.0$", "", regex=True)

    cols_num = [
        "Impressões",
        "Cliques",
        "CPC \n(Custo por clique)",
        "CTR\n(Click Through Rate)",
        "CVR\n(Conversion rate)",
        "Receita\n(Moeda local)",
        "Investimento\n(Moeda local)",
        "ACOS\n (Investimento / Receitas)",
        "ROAS\n(Receitas / Investimento)",
        "Vendas diretas",
        "Vendas indiretas",
        "Vendas por publicidade\n(Diretas + Indiretas)",
    ]
    for c in cols_num:
        if c in pat.columns:
            pat[c] = _coerce_series_numeric_ptbr(pat[c])

    return pat


def _coerce_campaign_numeric(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    cols_num = [
        "Impressões",
        "Cliques",
        "Receita\n(Moeda local)",
        "Investimento\n(Moeda local)",
        "Vendas por publicidade\n(Diretas + Indiretas)",
        "ROAS\n(Receitas / Investimento)",
        "CVR\n(Conversion rate)",
        "% de impressões perdidas por orçamento",
        "% de impressões perdidas por classificação",
        "Orçamento",
        "ACOS Objetivo",
    ]
    for c in cols_num:
        if c in df.columns:
            df[c] = _coerce_series_numeric_ptbr(df[c])
    return df


def load_campanhas_diario(campanhas_file) -> pd.DataFrame:
    _safe_seek(campanhas_file, 0)
    sheet = _pick_sheet(
        campanhas_file,
        preferred_names=["Relatório de campanha", "Relatorio de campanha"],
        must_have_terms=["relatorio", "campanha"],
    )
    _safe_seek(campanhas_file, 0)
    camp = pd.read_excel(campanhas_file, sheet_name=sheet, header=1)

    camp = _standardize_cols_by_candidates(camp, _CAMPAIGN_COL_CANDIDATES)

    if "Desde" in camp.columns:
        camp["Desde"] = pd.to_datetime(camp["Desde"], errors="coerce")

    camp = _coerce_campaign_numeric(camp)
    return camp


def load_campanhas_consolidado(campanhas_file) -> pd.DataFrame:
    _safe_seek(campanhas_file, 0)
    sheet = _pick_sheet(
        campanhas_file,
        preferred_names=["Relatório de campanha", "Relatorio de campanha"],
        must_have_terms=["relatorio", "campanha"],
    )
    _safe_seek(campanhas_file, 0)
    camp = pd.read_excel(campanhas_file, sheet_name=sheet, header=1)
    camp = _standardize_cols_by_candidates(camp, _CAMPAIGN_COL_CANDIDATES)
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

    def _reorder_action_block(d: pd.DataFrame) -> pd.DataFrame:
        """Padroniza leitura: Acao_Recomendada antes de Confianca_Dado e Motivo.
        Mantem o restante na ordem original.
        """
        if d is None or d.empty:
            return d

        block = [c for c in ["Acao_Recomendada", "Confianca_Dado", "Motivo", "Impacto_Estimado_R$"] if c in d.columns]
        if not block:
            return d

        # Remove o bloco e reinsere no ponto ideal
        cols = [c for c in d.columns if c not in block]

        # Insere o bloco no ponto de decisao: logo apos Perdidas (diagnostico), antes de campos auxiliares
        anchor = None
        for a in ["Perdidas_Class", "Perdidas_Orc", "ROAS_Real", "ROAS_Objetivo"]:
            if a in cols:
                anchor = a
                break

        if anchor is None:
            return d[cols + block]

        idx = cols.index(anchor) + 1
        cols = cols[:idx] + block + cols[idx:]
        return d[cols]

    for c in [
        "Receita","Investimento","Vendas","Cliques","Impressões","ROAS","CVR",
        "Perdidas_Orc","Perdidas_Class","ACOS Objetivo","Orçamento"
    ]:
        if c in df.columns:
            df[c] = _coerce_series_numeric_ptbr(df[c])

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

    # Garante ordem de leitura em todas as visoes que usam camp_strat
    df = _reorder_action_block(df)
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


def build_15_day_plan(camp_agg_strat: pd.DataFrame) -> pd.DataFrame:
    """Gera um plano de 15 dias respeitando a janela de 7 dias do algoritmo."""
    df = camp_agg_strat.copy()

    # --- SEMANA 1: AJUSTES ---
    cols_base = ["Nome", "Acao_Recomendada", "Confianca_Dado"]
    
    # Dia 1: Escala e Hemorragia (Urgente)
    d1 = df[df["Quadrante"].isin(["ESCALA_ORCAMENTO", "HEMORRAGIA"])].copy()
    d1["Dia"] = "Dia 01"
    d1["Fase"] = "Semana 1: Ajustes"
    d1["Tarefa"] = d1["Quadrante"].map({
        "ESCALA_ORCAMENTO": "Aumentar orçamento (+20%)",
        "HEMORRAGIA": "Pausar ou reduzir ROAS objetivo drasticamente"
    })

    # Dia 3: Competitividade
    d3 = df[df["Quadrante"] == "COMPETITIVIDADE"].copy()
    d3["Dia"] = "Dia 03"
    d3["Fase"] = "Semana 1: Ajustes"
    d3["Tarefa"] = "Reduzir ROAS objetivo em 1 ou 2 pontos"

    # --- SEMANA 2: APRENDIZADO (TRAVA) ---
    # Dia 8: Monitoramento das alterações da Semana 1
    d8 = pd.concat([d1, d3], ignore_index=True)
    d8["Dia"] = "Dia 08"
    d8["Fase"] = "Semana 2: Aprendizado"
    d8["Tarefa"] = "APRENDIZADO: Não alterar. Apenas monitorar ROAS e CPC."

    # Dia 15: Reavaliação Final
    d15 = d8[d8["Dia"] == "Dia 08"].copy()
    d15["Dia"] = "Dia 15"
    d15["Fase"] = "Semana 2: Aprendizado"
    d15["Tarefa"] = "Fim do ciclo. Se ROAS estabilizou, planejar novo ajuste."

    cols_final = ["Dia", "Fase", "Nome", "Tarefa", "Acao_Recomendada", "Confianca_Dado"]
    plan = pd.concat([d1, d3, d8, d15], ignore_index=True, sort=False)
    
    # Garantir que as colunas existam
    for c in cols_final:
        if c not in plan.columns:
            plan[c] = ""
            
    return plan[cols_final].sort_values(["Dia", "Nome"], ascending=True)


def build_7_day_plan(camp_agg_strat: pd.DataFrame) -> pd.DataFrame:
    # Mantido por compatibilidade, mas o dashboard usará o de 15 dias
    return build_15_day_plan(camp_agg_strat)


def build_control_panel(camp_agg_strat: pd.DataFrame) -> pd.DataFrame:
    df = camp_agg_strat.copy()
    base_cols = [
        "Nome","Orçamento","ACOS Objetivo","ROAS_Objetivo","ROAS_Real",
        "Perdidas_Orc","Perdidas_Class","Acao_Recomendada","Confianca_Dado","Motivo","Impacto_Estimado_R$"
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
    pause_cvr_max: float = 0.01,
    **kwargs
):
    # KPIs devem considerar TODAS as campanhas (ativas e inativas).
    camp_agg_all = camp_agg.copy() if camp_agg is not None else camp_agg

    # Tabelas de ação consideram apenas campanhas ATIVAS
    camp_agg_active = camp_agg
    if camp_agg_active is not None and not camp_agg_active.empty and "Status" in camp_agg_active.columns:
        camp_agg_active = camp_agg_active[camp_agg_active["Status"].map(_is_active_status)].copy()
    camp_strat = add_strategy_fields(camp_agg_active)

    pause = camp_strat[
        (camp_strat["Investimento"] > pause_invest_min) &
        ((camp_strat["Vendas"] <= 0) | (camp_strat["CVR"] < pause_cvr_max) | (camp_strat["Quadrante"] == "HEMORRAGIA"))
    ].copy()
    pause["Ação"] = "PAUSAR/REVISAR"
    pause = pause.sort_values("Investimento", ascending=False)

    ads_ids = set(pat["ID"].dropna().astype(str).unique())
    # Considerar apenas anúncios ATIVOS para recomendação de entrada em Ads
    org_active = org
    if org is not None and not org.empty and "Status" in org.columns:
        org_active = org[org["Status"].map(_is_active_status)].copy()

    enter = org_active[
        (org_active["Visitas"] >= enter_visitas_min) &
        (org_active["Conv_Visitas_Vendas"] > enter_conv_min) &
        (~org_active["ID"].astype(str).isin(ads_ids))
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

    acos = camp_strat[camp_strat["Quadrante"] == "COMPETITIVIDADE"].copy()
    acos["Ação"] = "BAIXAR ROAS OBJETIVO"
    if "Perdidas_Class" in acos.columns:
        acos = acos.sort_values(["Perdidas_Class","Receita"], ascending=[False, False])

    invest_total = float(pd.to_numeric(camp_agg_all["Investimento"], errors="coerce").fillna(0).sum())
    receita_total = float(pd.to_numeric(camp_agg_all["Receita"], errors="coerce").fillna(0).sum())
    vendas_total = int(pd.to_numeric(camp_agg_all["Vendas"], errors="coerce").fillna(0).sum())
    roas_total = (receita_total / invest_total) if invest_total else 0.0

    # TACOS = Investimento Ads / Faturamento total da conta.
    # Faturamento total da conta vem do relatorio organico (publicacoes), coluna Vendas_Brutas.
    faturamento_total = float(pd.to_numeric(org.get("Vendas_Brutas"), errors="coerce").fillna(0).sum())
    tacos = (invest_total / faturamento_total) if faturamento_total else 0.0

    kpis = {
        "Campanhas únicas": int(camp_agg_all["Nome"].nunique()),
        "IDs patrocinados únicos": int(pat["ID"].nunique()),
        "Investimento Ads (R$)": invest_total,
        "Receita Ads (R$)": receita_total,
        "Vendas Ads": vendas_total,
        "ROAS": roas_total,
        "TACOS": tacos,
        "Faturamento total (R$)": faturamento_total,
    }
    ads_panel = build_ads_panel(
        pat,
        camp_strat=camp_strat,
        ads_min_imp=int(kwargs.get("ads_min_imp", 500)),
        ads_min_clk=int(kwargs.get("ads_min_clk", 10)),
        ads_ctr_min_abs=float(kwargs.get("ads_ctr_min_abs", 0.60)),
        ads_cvr_min=float(kwargs.get("ads_cvr_min", 1.00)),
        ads_pause_invest_min=float(kwargs.get("ads_pause_invest_min", 20.0)),
    )

    ads_pausar = pd.DataFrame()
    ads_vencedores = pd.DataFrame()
    ads_otim_fotos = pd.DataFrame()
    ads_otim_keywords = pd.DataFrame()
    ads_otim_oferta = pd.DataFrame()

    if ads_panel is not None and not ads_panel.empty:
        if "Acao_Anuncio" in ads_panel.columns:
            ads_pausar = ads_panel[ads_panel["Acao_Anuncio"] == "Pausar anúncio"].copy()
            ads_otim_fotos = ads_panel[ads_panel["Acao_Anuncio"] == "Revisar Fotos e Clips"].copy()
            ads_otim_keywords = ads_panel[ads_panel["Acao_Anuncio"] == "Otimizar Palavras-chave"].copy()
            ads_otim_oferta = ads_panel[ads_panel["Acao_Anuncio"] == "Revisar Oferta"].copy()
        if "Status_Anuncio" in ads_panel.columns:
            ads_vencedores = ads_panel[ads_panel["Status_Anuncio"] == "Vencedor"].copy()

    return kpis, pause, enter, scale, acos, camp_strat, ads_panel, ads_pausar, ads_vencedores, ads_otim_fotos, ads_otim_keywords, ads_otim_oferta


def gerar_excel(kpis, camp_agg, pause, enter, scale, acos, camp_strat, daily=None) -> bytes:
    # Se for um snapshot simplificado, gera um Excel basico
    is_snapshot = "Data_Snapshot" in camp_strat.columns
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        if is_snapshot:
            camp_strat.to_excel(writer, index=False, sheet_name="Campanhas Estrategicas")
        else:
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
                "Trend_cpc_proxy": diagnosis["Tendencias"].get("cpc_proxy_up", 0),
                "Trend_ticket": diagnosis["Tendencias"].get("ticket_down", 0),
                "Trend_roas": diagnosis["Tendencias"].get("roas_down", 0),
            }])

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

def compare_snapshots(df_current: pd.DataFrame, df_reference: pd.DataFrame) -> pd.DataFrame:
    """Compara o estado atual das campanhas com um snapshot de referência."""
    if df_current is None or df_reference is None:
        return pd.DataFrame()
    
    # Garantir que temos as colunas necessárias
    cols_ref = ["Nome", "ROAS_Real", "Investimento", "Receita", "Quadrante"]
    df_ref_sub = df_reference[[c for c in cols_ref if c in df_reference.columns]].copy()
    
    # Renomear colunas de referência para evitar conflito
    df_ref_sub = df_ref_sub.rename(columns={
        "ROAS_Real": "ROAS_Ref",
        "Investimento": "Invest_Ref",
        "Receita": "Receita_Ref",
        "Quadrante": "Quadrante_Ref"
    })
    
    # Merge com os dados atuais
    comparison = pd.merge(df_current, df_ref_sub, on="Nome", how="inner")
    
    # Calcular variações
    comparison["Delta_ROAS"] = comparison["ROAS_Real"] - comparison["ROAS_Ref"]
    comparison["Delta_Invest"] = comparison["Investimento"] - comparison["Invest_Ref"]
    
    # Identificar melhoria de status
    def check_status_improvement(row):
        q_ref = str(row.get("Quadrante_Ref", ""))
        q_curr = str(row.get("Quadrante", ""))
        if q_ref == q_curr: return "Mantido"
        if q_ref == "HEMORRAGIA" and q_curr != "HEMORRAGIA": return "Recuperado"
        if q_curr == "ESCALA_ORCAMENTO": return "Potencializado"
        return "Alterado"
        
    comparison["Evolucao_Status"] = comparison.apply(check_status_improvement, axis=1)
    
    return comparison

def build_ads_panel(
    pat: pd.DataFrame,
    camp_strat: pd.DataFrame | None = None,
    ads_min_imp: int = 500,
    ads_min_clk: int = 10,
    ads_ctr_min_abs: float = 0.60,
    ads_cvr_min: float = 1.00,
    ads_pause_invest_min: float = 20.0,
    share_prejudicial_min: float = 0.25,
    roas_bad_mult: float = 0.70,
) -> pd.DataFrame:
    """Painel tático por anúncio (patrocinados).

    Ideia:
    - Campanha continua sendo unidade de controle.
    - Anúncio vira unidade de diagnóstico e refinamento da ação.
    - Sem CPC como alavanca (não é controlável no ML).
    """

    # Normalização de limiares: aceita valores em fração (0.022) ou em percentual (2.2)
    # Internamente, CTR_pct e CVR_pct estão em percentual (0 a 100).
    if 0 < ads_ctr_min_abs < 0.05:
        ads_ctr_min_abs *= 100
    if 0 < ads_cvr_min < 0.05:
        ads_cvr_min *= 100

    if pat is None or pat.empty:
        return pd.DataFrame()

    df = pat.copy()

    # cria Codigo_MLB e Titulo se existirem colunas conhecidas
    if "Codigo_MLB" not in df.columns:
        df["Codigo_MLB"] = "MLB" + df["ID"].astype(str)

    if "Título do anúncio patrocinado" in df.columns and "Titulo" not in df.columns:
        df["Titulo"] = df["Título do anúncio patrocinado"]
    elif "Titulo" not in df.columns:
        df["Titulo"] = pd.NA

    # camp
    if "Campanha" not in df.columns:
        cand = None
        for c in df.columns:
            ck = _norm_col_key(c)
            if "campanha" in ck:
                cand = c
                break
        df["Campanha"] = df[cand] if cand else pd.NA

    if "Status" not in df.columns:
        df["Status"] = pd.NA

    # agregação (tolerante a nomes com \n)
    agg_map = {
        "Impressões": "sum",
        "Cliques": "sum",
        "Receita\n(Moeda local)": "sum",
        "Investimento\n(Moeda local)": "sum",
        "Vendas por publicidade\n(Diretas + Indiretas)": "sum",
    }

    agg_dict = {}
    for c in ["Campanha", "Codigo_MLB", "Titulo", "Status"]:
        if c in df.columns:
            agg_dict[c] = "first"
    for c, fn in agg_map.items():
        if c in df.columns:
            agg_dict[c] = fn

    out = df.groupby(["ID"], as_index=False).agg(agg_dict)

    out = out.rename(columns={
        "Impressões": "Impressoes",
        "Receita\n(Moeda local)": "Receita",
        "Investimento\n(Moeda local)": "Investimento",
        "Vendas por publicidade\n(Diretas + Indiretas)": "Vendas",
    })

    for c in ["Impressoes", "Cliques", "Receita", "Investimento", "Vendas"]:
        if c not in out.columns:
            out[c] = 0.0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    # métricas por anúncio
    out["CTR_pct"] = out.apply(lambda r: (r["Cliques"] / r["Impressoes"] * 100) if r["Impressoes"] else 0.0, axis=1)
    out["CVR_pct"] = out.apply(lambda r: (r["Vendas"] / r["Cliques"] * 100) if r["Cliques"] else 0.0, axis=1)
    out["ROAS_Real"] = out.apply(lambda r: (r["Receita"] / r["Investimento"]) if r["Investimento"] else 0.0, axis=1)
    out["ACOS_Real_pct"] = out.apply(lambda r: (r["Investimento"] / r["Receita"] * 100) if r["Receita"] else 0.0, axis=1)

    # métricas por campanha a partir do próprio patrocinado
    camp_base = out.groupby("Campanha", as_index=False).agg(
        Invest_Campanha=("Investimento", "sum"),
        Receita_Campanha=("Receita", "sum"),
        Cliques_Campanha=("Cliques", "sum"),
        Vendas_Campanha=("Vendas", "sum"),
    )
    camp_base["ROAS_Campanha"] = camp_base.apply(
        lambda r: (r["Receita_Campanha"] / r["Invest_Campanha"]) if r["Invest_Campanha"] else 0.0, axis=1
    )
    camp_base["CVR_Campanha_pct"] = camp_base.apply(
        lambda r: (r["Vendas_Campanha"] / r["Cliques_Campanha"] * 100) if r["Cliques_Campanha"] else 0.0, axis=1
    )

    out = out.merge(camp_base, on="Campanha", how="left")
    out["Pct_Invest_Campanha"] = out.apply(
        lambda r: (r["Investimento"] / r["Invest_Campanha"]) if r.get("Invest_Campanha") else 0.0, axis=1
    ) * 100.0

    # puxa ROAS objetivo da campanha (se disponível)
    out["ROAS_Objetivo_Campanha"] = pd.NA
    out["Quadrante_Campanha"] = pd.NA
    out["Acao_Campanha"] = pd.NA

    if camp_strat is not None and not camp_strat.empty:
        cols_need = [c for c in ["Nome", "ROAS_Objetivo", "Quadrante", "Acao_Recomendada"] if c in camp_strat.columns]
        if "Nome" in cols_need:
            camp_pick = camp_strat[cols_need].copy()
            camp_pick = camp_pick.rename(columns={
                "Nome": "Campanha",
                "ROAS_Objetivo": "ROAS_Objetivo_Campanha",
                "Quadrante": "Quadrante_Campanha",
                "Acao_Recomendada": "Acao_Campanha",
            })
            out = out.merge(camp_pick, on="Campanha", how="left")

    # fallback do objetivo: se não tem objetivo, usa o ROAS real da campanha como referência
    def _roas_ref(r):
        ro = r.get("ROAS_Objetivo_Campanha")
        try:
            if pd.notna(ro) and float(ro) > 0:
                return float(ro)
        except Exception:
            pass
        return float(r.get("ROAS_Campanha") or 0.0)

    out["ROAS_Ref"] = out.apply(_roas_ref, axis=1)

    def _classificar(r):
        imp = float(r.get("Impressoes") or 0)
        clk = float(r.get("Cliques") or 0)
        inv = float(r.get("Investimento") or 0)
        rec = float(r.get("Receita") or 0)
        roas = float(r.get("ROAS_Real") or 0)
        ctr = float(r.get("CTR_pct") or 0)
        cvr = float(r.get("CVR_pct") or 0)
        cvr_camp = float(r.get("CVR_Campanha_pct") or 0)
        share = float(r.get("Pct_Invest_Campanha") or 0)
        roas_ref = float(r.get("ROAS_Ref") or 0)

        if imp < ads_min_imp or clk < ads_min_clk:
            return "Neutro", "Manter", "BAIXA", "Pouco volume, coletar mais dados"

        if inv >= ads_pause_invest_min and rec <= 0:
            return "Prejudicial", "Pausar anúncio", "ALTA", "Gasto sem retorno"

        if inv >= ads_pause_invest_min and roas_ref > 0 and roas < (roas_ref * roas_bad_mult):
            conf = "ALTA" if share >= (share_prejudicial_min * 100) else "MEDIA"
            return "Prejudicial", "Pausar anúncio", conf, "ROAS abaixo do alvo da campanha"

        if ctr < ads_ctr_min_abs:
            return "Neutro", "Revisar Fotos e Clips", "MEDIA", "Baixa atratividade, revisar Fotos e Clips"

        if cvr < ads_cvr_min:
            if cvr_camp > 0 and cvr < (cvr_camp * 0.75):
                if ctr < (ads_ctr_min_abs * 2):
                    return "Neutro", "Otimizar Palavras-chave", "MEDIA", "Tráfego desalinhado, otimizar palavras-chave"
                return "Neutro", "Revisar Oferta", "MEDIA", "Oferta pouco competitiva ou possível movimento de concorrência"
            return "Neutro", "Manter", "MEDIA", "Conversão baixa no contexto da campanha, monitorar"

        if roas_ref > 0 and roas >= roas_ref and cvr >= max(ads_cvr_min, cvr_camp):
            return "Vencedor", "Manter", "ALTA", "Acima do alvo da campanha, preservar"

        return "Neutro", "Manter", "MEDIA", "Dentro do esperado, monitorar"

    tmp = out.apply(lambda r: pd.Series(_classificar(r), index=["Status_Anuncio", "Acao_Anuncio", "Confianca_Anuncio", "Motivo_Anuncio"]), axis=1)
    out = pd.concat([out, tmp], axis=1)

    def _acao_cruzada(r):
        quad = str(r.get("Quadrante_Campanha") or "")
        status = str(r.get("Status_Anuncio") or "")
        acao = str(r.get("Acao_Anuncio") or "")

        if ("ESCALA" in quad) and (status == "Prejudicial" or acao == "Pausar anúncio"):
            return "Pausar anúncio, preservar campanha para escala"

        if (("HEMORRAGIA" in quad) or ("PAUSAR" in quad)) and (status == "Vencedor"):
            return "Preservar vencedor, revisar fracos antes de pausar campanha"

        return ""

    out["Refino_Campanha"] = out.apply(_acao_cruzada, axis=1)

    out = out.sort_values(["Status_Anuncio", "Investimento"], ascending=[True, False]).reset_index(drop=True)
    return out

