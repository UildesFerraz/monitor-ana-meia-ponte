import pandas as pd
import numpy as np

def aplicar_filtro_recessao(df, col_nivel='Nivel_Real', min_dias_queda=3):
    """
    Identifica períodos onde o nível do rio está apenas caindo (recessão/estiagem).
    
    Retorna o DataFrame com uma nova coluna 'Recessao_ID' (0 para não-recessão, 
    ou o ID numérico do período de recessão).
    """
    df = df.copy()
    if df.empty or col_nivel not in df.columns:
        return df
        
    df['variacao'] = df[col_nivel].diff()
    
    # É recessão se a variação for negativa ou zero (nível caindo ou estável)
    df['is_falling'] = df['variacao'] <= 0
    
    # Identificar blocos contínuos de queda
    df['block'] = (~df['is_falling']).cumsum()
    
    # Filtrar blocos que têm pelo menos `min_dias_queda` dias de queda
    counts = df[df['is_falling']].groupby('block').size()
    valid_blocks = counts[counts >= min_dias_queda].index
    
    df['Recessao_ID'] = 0
    df.loc[df['block'].isin(valid_blocks) & df['is_falling'], 'Recessao_ID'] = df['block']
    
    return df

def calcular_taxa_decaimento(df_recessoes, col_nivel='Nivel_Real'):
    """
    Calcula a taxa média de decaimento para cada período de recessão.
    """
    taxas = []
    ids = df_recessoes[df_recessoes['Recessao_ID'] > 0]['Recessao_ID'].unique()
    
    for rid in ids:
        trecho = df_recessoes[df_recessoes['Recessao_ID'] == rid]
        if len(trecho) > 1:
            queda_total = trecho[col_nivel].iloc[0] - trecho[col_nivel].iloc[-1]
            dias = (trecho.index[-1] - trecho.index[0]).days
            if dias > 0:
                taxas.append(queda_total / dias)
                
    if taxas:
        return np.mean(taxas)
    return 0.0

def prever_com_prophet(df, dias_futuros=30, col_nivel='Nivel_Real'):
    """
    Treina um modelo Prophet com os dados históricos e prevê o nível futuro.
    (Essa função depende do pacote 'prophet')
    """
    try:
        from prophet import Prophet
    except ImportError:
        print("Prophet não instalado. Use: pip install prophet")
        return None
        
    if df.empty or col_nivel not in df.columns:
        return None
        
    # Preparar df para Prophet: colunas 'ds' (data) e 'y' (valor)
    df_prophet = df.reset_index()[['Data', col_nivel]].rename(columns={'Data': 'ds', col_nivel: 'y'})
    df_prophet = df_prophet.dropna()
    
    m = Prophet(daily_seasonality=False)
    m.fit(df_prophet)
    
    future = m.make_future_dataframe(periods=dias_futuros)
    forecast = m.predict(future)
    
    return forecast

def extrapolar_decaimento_fisico(df, nivel_atual, dias_futuros=120):
    """
    Projeca o nível usando um modelo de Recessão Exponencial Baseflow.
    Aplica-se H_eff(t) = H_eff(0) * (1 - k)^t, onde H_eff = Nivel - 2.5
    Esse modelo simula a secagem do lençol freático sem atingir zero bruscamente.
    """
    # 1. Obter a taxa percentual recente (últimos 15 a 30 dias)
    df_recent = df.tail(30).copy()
    
    # Calcular H efetivo (acima de 2.5m)
    df_recent['H_eff'] = df_recent['Nivel_Real'] - 2.5
    df_recent['H_eff'] = df_recent['H_eff'].clip(lower=0.01) # Evitar negativo
    
    # Calcular a variação percentual diária (positiva quando cai)
    df_recent['taxa_queda'] = -df_recent['H_eff'].diff() / df_recent['H_eff'].shift(1)
    
    # Filtrar apenas os dias em que a água efetivamente caiu (recessão pura)
    quedas = df_recent[df_recent['taxa_queda'] > 0]['taxa_queda']
    
    if len(quedas) >= 3:
        # Usa a mediana para isolar outliers (chuvas ou erros de sensor)
        taxa_diaria = quedas.median()
    else:
        taxa_diaria = 0.02 # Padrão de 2% ao dia se não houver dados de queda recente
        
    # Travar entre limites realistas (0.5% a 5% ao dia)
    taxa_diaria = min(max(taxa_diaria, 0.005), 0.05)
    
    projecao = []
    h_eff_atual = max(nivel_atual - 2.5, 0.01)
    
    for i in range(1, dias_futuros + 1):
        h_eff_atual = h_eff_atual * (1 - taxa_diaria)
        nivel_proj = 2.5 + h_eff_atual
        projecao.append(nivel_proj)
        
    # Retornar também a queda absoluta estimada pro primeiro dia, só para info
    queda_dia_1 = (max(nivel_atual - 2.5, 0.01)) * taxa_diaria
    
    return projecao, queda_dia_1
