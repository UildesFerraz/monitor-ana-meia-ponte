import numpy as np

def calcular_vazao(nivel):
    """
    Calcula a vazão (Q) com base no nível (H) usando a Curva Chave.
    
    Parâmetros:
    -----------
    nivel : float ou pd.Series
        Nível do rio (H) em metros.
        
    Retorna:
    --------
    float ou pd.Series
        Vazão (Q) calculada. Retorna 0 se nivel <= 2.5.
    """
    
    # Se for uma série do Pandas, aplicamos de forma vetorizada
    if hasattr(nivel, 'map'):
        return nivel.apply(_calcular_vazao_valor)
    elif isinstance(nivel, (list, np.ndarray)):
        return np.array([_calcular_vazao_valor(x) for x in nivel])
    else:
        return _calcular_vazao_valor(nivel)

def _calcular_vazao_valor(h):
    if pd.isna(h) or h is None:
        return np.nan
        
    try:
        h = float(h)
    except ValueError:
        return np.nan
        
    if h <= 2.5:
        return 0.0
    elif h <= 3.13:
        # Tramo 1
        a1 = 54.63092
        h0 = 2.5
        b1 = 2.17368
        return a1 * (h - h0) ** b1
    else:
        # Tramo 2
        a2 = 42.11397
        h0 = 2.5
        b2 = 1.61047
        return a2 * (h - h0) ** b2

def processar_dados_ana(df):
    """
    Processa o DataFrame retornado pela API da ANA, 
    limpando os dados e calculando a vazão.
    """
    if df.empty:
        return df
        
    # Identificar colunas corretamente (a API costuma retornar 'dataHora' e 'nivel')
    # Ajuste os nomes caso a API retorne diferente (ex: 'DataHora' ou 'data_medicao')
    col_data = next((col for col in df.columns if 'data' in col.lower() and 'hora' in col.lower()), None)
    col_nivel = next((col for col in df.columns if 'nivel' in col.lower() or 'cota' in col.lower()), None)
    
    if col_data:
        df['Data'] = pd.to_datetime(df[col_data])
        # Vamos manter apenas um registro por dia (média diária) se houver muitos
        df.set_index('Data', inplace=True)
        
    if col_nivel:
        # Converter para float
        df['Nivel_Real'] = pd.to_numeric(df[col_nivel], errors='coerce')
        # Calcular Vazão usando a curva chave
        df['Vazao_Calculada'] = calcular_vazao(df['Nivel_Real'])
        
    return df
    
import pandas as pd # Importando aqui para garantir que esteja no escopo
