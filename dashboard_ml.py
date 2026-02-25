import streamlit as st
import pandas as pd
import numpy as np
import re
from datetime import datetime
import io

# Configuração da página
st.set_page_config(page_title="Dashboard Mercado Livre", layout="wide")

# Dicionário para tradução de meses
MESES_PT_EN = {
    "janeiro": "January", "fevereiro": "February", "março": "March",
    "abril": "April", "maio": "May", "junho": "June",
    "julho": "July", "agosto": "August", "setembro": "September",
    "outubro": "October", "novembro": "November", "dezembro": "December"
}

def parse_ml_date(date_str):
    """
    Tratamento de Data (Padrão ML): "25 de fevereiro de 2026 08:46 hs."
    Extrai dia, traduz mês, extrai ano e converte para datetime.
    """
    try:
        if pd.isna(date_str): return pd.NaT
        # Remover " hs." e extrair partes
        clean_str = str(date_str).replace(" hs.", "").strip()
        match = re.search(r'(\d{1,2}) de (\w+) de (\d{4})', clean_str)
        if match:
            day, month_pt, year = match.groups()
            month_en = MESES_PT_EN.get(month_pt.lower(), month_pt)
            date_formatted = f"{day} {month_en} {year}"
            return pd.to_datetime(date_formatted, format='%d %B %Y')
    except Exception:
        return pd.NaT
    return pd.NaT

def clean_currency(value):
    """
    Tratamento de Moeda: "R$ 1.500,00" -> 1500.00
    """
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    
    # Remover símbolos e espaços
    clean_val = re.sub(r'[^\d,.-]', '', str(value))
    
    # Lógica para tratar ponto como milhar e vírgula como decimal
    if ',' in clean_val and '.' in clean_val:
        clean_val = clean_val.replace('.', '').replace(',', '.')
    elif ',' in clean_val:
        clean_val = clean_val.replace(',', '.')
        
    try:
        return float(clean_val)
    except ValueError:
        return 0.0

def calculate_abc(series):
    """
    Calcula a Curva ABC (80/15/5)
    """
    if series.sum() == 0:
        return pd.Series(['C'] * len(series), index=series.index)
    
    sorted_series = series.sort_values(ascending=False)
    cum_perc = sorted_series.cumsum() / sorted_series.sum()
    
    def classify(p):
        if p <= 0.80: return 'A'
        if p <= 0.95: return 'B'
        return 'C'
    
    return cum_perc.apply(classify).reindex(series.index)

def format_brl(val):
    if pd.isna(val) or val == "": return ""
    try:
        return f"R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return val

def style_dataframe(df, is_revenue=False):
    """
    Aplica estilos ao DataFrame (Deltas, Curvas, Total Geral)
    """
    # Identificar colunas de delta
    delta_cols = [c for c in df.columns if 'Δ' in str(c)]
    abc_cols = [c for c in df.columns if 'Curva' in str(c)]
    
    def apply_row_styles(row):
        styles = [''] * len(row)
        
        # Estilo para TOTAL GERAL
        if row.name == "TOTAL GERAL":
            return ['background-color: #f1f5f9; color: black; font-weight: bold'] * len(row)
        
        for i, col in enumerate(df.columns):
            # Estilo para Deltas
            if col in delta_cols:
                val = row[col]
                if isinstance(val, (int, float)):
                    if val > 0:
                        styles[i] = 'color: #15803d; font-weight: bold'
                    elif val < 0:
                        styles[i] = 'color: #b91c1c; font-weight: bold'
            
            # Estilo para Curvas ABC
            elif col in abc_cols:
                val = row[col]
                if val == 'A': styles[i] = 'background-color: #dcfce7; color: #166534'
                elif val == 'B': styles[i] = 'background-color: #fef9c3; color: #854d0e'
                elif val == 'C': styles[i] = 'background-color: #fee2e2; color: #991b1b'
        
        return styles

    st_df = df.style.apply(apply_row_styles, axis=1)
    
    # Formatação de valores
    format_dict = {}
    for col in df.columns:
        if col in delta_cols:
            format_dict[col] = "{:.2%}"
        elif is_revenue and (col == "Total do Mês" or "Semana" in str(col)):
            if col != "TOTAL GERAL" and 'Δ' not in str(col) and 'Curva' not in str(col):
                format_dict[col] = format_brl
    
    if format_dict:
        st_df = st_df.format(format_dict)
        
    return st_df

def process_data(file):
    # 1. Encontrar a linha do cabeçalho (SKU)
    preview = pd.read_excel(file, header=None, nrows=30)
    header_idx = -1
    for i, row in preview.iterrows():
        if "SKU" in row.values:
            header_idx = i
            break
    
    if header_idx == -1:
        st.error("Não foi possível encontrar a coluna 'SKU' no arquivo.")
        return None

    # Ler o arquivo novamente com o header correto
    file.seek(0)
    df = pd.read_excel(file, header=header_idx)
    
    # 2. Limpeza e Tratamento
    cols = df.columns.tolist()
    sku_col = 'SKU'
    date_col = 'Data da venda'
    units_col = 'Unidades'
    
    # Encontrar coluna de receita
    revenue_keywords = ['Receita', 'Total', 'Faturamento', 'Valor']
    revenue_col = next((c for c in cols if any(k in str(c) for k in revenue_keywords) and 'BRL' in str(c)), None)
    if not revenue_col:
        revenue_col = next((c for c in cols if any(k in str(c) for k in revenue_keywords)), None)
    
    if not all(c in df.columns for c in [sku_col, date_col, units_col]) or not revenue_col:
        st.error(f"Colunas obrigatórias não encontradas. Detectadas: {cols}")
        return None

    # Remover SKUs nulos
    df = df.dropna(subset=[sku_col])
    
    # Tratamento de Moeda
    df['Receita_Clean'] = df[revenue_col].apply(clean_currency)
    
    # Tratamento de Data
    df['Data_Clean'] = df[date_col].apply(parse_ml_date)
    df = df.dropna(subset=['Data_Clean'])
    
    # 3. Regras de Negócio
    min_date = df['Data_Clean'].min()
    df['Dias'] = (df['Data_Clean'] - min_date).dt.days
    
    def categorize_week(days):
        if days <= 6: return 'Semana 1'
        if days <= 13: return 'Semana 2'
        if days <= 20: return 'Semana 3'
        if days <= 27: return 'Semana 4'
        return 'Semana 5+'
    
    df['Semana'] = df['Dias'].apply(categorize_week)
    
    # Tabelas Pivot
    pivot_units = df.pivot_table(index=sku_col, columns='Semana', values=units_col, aggfunc='sum', fill_value=0)
    pivot_revenue = df.pivot_table(index=sku_col, columns='Semana', values='Receita_Clean', aggfunc='sum', fill_value=0)
    
    # Garantir que todas as semanas existam
    semanas_ordem = ['Semana 1', 'Semana 2', 'Semana 3', 'Semana 4', 'Semana 5+']
    for sem in semanas_ordem:
        if sem not in pivot_units.columns: pivot_units[sem] = 0
        if sem not in pivot_revenue.columns: pivot_revenue[sem] = 0
    
    pivot_units = pivot_units[semanas_ordem]
    pivot_revenue = pivot_revenue[semanas_ordem]
    
    # Deltas Percentuais
    def add_deltas(pivot_df):
        new_df = pivot_df.copy()
        for i in range(1, len(semanas_ordem)):
            curr = semanas_ordem[i]
            prev = semanas_ordem[i-1]
            delta_name = f"Δ {curr}"
            new_df[delta_name] = np.where(
                new_df[prev] == 0,
                np.where(new_df[curr] > 0, 1.0, 0.0),
                (new_df[curr] - new_df[prev]) / new_df[prev]
            )
        return new_df

    pivot_units = add_deltas(pivot_units)
    pivot_revenue = add_deltas(pivot_revenue)
    
    # Curva ABC
    pivot_abc = pivot_revenue[semanas_ordem].copy()
    for sem in semanas_ordem:
        pivot_abc[f"Curva {sem}"] = calculate_abc(pivot_abc[sem])
    
    # Total do Mês e Curva Final
    pivot_units['Total do Mês'] = pivot_units[semanas_ordem].sum(axis=1)
    pivot_revenue['Total do Mês'] = pivot_revenue[semanas_ordem].sum(axis=1)
    pivot_abc['Total do Mês'] = pivot_revenue['Total do Mês']
    pivot_abc['Curva Final'] = calculate_abc(pivot_abc['Total do Mês'])
    
    # Linha TOTAL GERAL
    def add_total_row(df_to_total, is_abc=False):
        total_row = {}
        for col in df_to_total.columns:
            if 'Δ' in str(col) or 'Curva' in str(col):
                total_row[col] = ""
            else:
                total_row[col] = df_to_total[col].sum()
        
        if not is_abc:
            for i in range(1, len(semanas_ordem)):
                curr = semanas_ordem[i]
                prev = semanas_ordem[i-1]
                delta_name = f"Δ {curr}"
                val_prev = total_row[prev]
                val_curr = total_row[curr]
                total_row[delta_name] = (val_curr - val_prev) / val_prev if val_prev != 0 else (1.0 if val_curr > 0 else 0.0)
        
        new_df = pd.concat([df_to_total, pd.DataFrame([total_row], index=["TOTAL GERAL"], columns=df_to_total.columns)])
        return new_df

    pivot_units = add_total_row(pivot_units)
    pivot_revenue = add_total_row(pivot_revenue)
    pivot_abc = add_total_row(pivot_abc, is_abc=True)
    
    return pivot_units, pivot_revenue, pivot_abc

# --- UI Interface ---
st.title("📊 Análise de Vendas Mercado Livre")

uploaded_file = st.file_uploader("Faça upload do relatório bruto do Mercado Livre (.xlsx)", type=["xlsx", "xls"])

if uploaded_file:
    with st.spinner("Processando dados..."):
        results = process_data(uploaded_file)
        
    if results:
        df_units, df_revenue, df_abc = results
        
        total_vendas = int(df_units.loc['TOTAL GERAL', 'Total do Mês'])
        st.success(f"Processamento concluído! Total de unidades vendidas: {total_vendas}")
        
        tab1, tab2, tab3 = st.tabs(["📦 Volume de Vendas", "💰 Faturamento Bruto", "📈 Evolução Curva ABC"])
        
        with tab1:
            st.subheader("Unidades Vendidas por SKU")
            st.dataframe(style_dataframe(df_units), use_container_width=True)
            
        with tab2:
            st.subheader("Faturamento por SKU (BRL)")
            st.dataframe(style_dataframe(df_revenue, is_revenue=True), use_container_width=True)
            
        with tab3:
            st.subheader("Análise da Curva ABC")
            curvas_disponiveis = ['A', 'B', 'C']
            selected_curvas = st.multiselect("Filtrar por Curva Final:", curvas_disponiveis, default=curvas_disponiveis)
            
            mask = df_abc['Curva Final'].isin(selected_curvas)
            df_abc_filtered = df_abc[mask].copy()
            if "TOTAL GERAL" in df_abc.index:
                df_abc_filtered = pd.concat([df_abc_filtered, df_abc.loc[["TOTAL GERAL"]]])
            
            st.dataframe(style_dataframe(df_abc_filtered), use_container_width=True)
            
        st.divider()
        st.subheader("📥 Exportar Resultados")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_units.to_excel(writer, sheet_name='Volume')
            df_revenue.to_excel(writer, sheet_name='Receita')
            df_abc.to_excel(writer, sheet_name='Curva ABC')
            
        st.download_button(
            label="Baixar Relatório Consolidado (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"analise_ml_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Aguardando upload do arquivo para iniciar a análise.")
