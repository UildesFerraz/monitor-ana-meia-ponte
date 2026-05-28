from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import pandas as pd
from datetime import datetime, timedelta

from ana_api import load_credentials, get_api_token, fetch_historical_data
from curva_chave import calcular_vazao
from model_forecasting import extrapolar_decaimento_fisico, prever_com_prophet

app = FastAPI(title="ANA Forecasting API")

# Permite acesso do Vite frontend (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir de qualquer lugar local
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ESTACAO_CODIGO = "60635200"

# Cache em memória simplificado
cache = {
    "df_dados": pd.DataFrame(),
    "last_update": None
}

def carregar_dados_interno(forcar_atualizacao=False):
    """Busca os dados e mantém no cache por 1 hora."""
    agora = datetime.now()
    if not forcar_atualizacao and not cache["df_dados"].empty and cache["last_update"]:
        if (agora - cache["last_update"]).total_seconds() < 3600:
            return cache["df_dados"]
            
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(BASE_DIR, "API_ANA.txt")
    
    usuario, senha = load_credentials(cred_path)
    if not usuario:
        raise Exception("Credenciais não encontradas. Verifique API_ANA.txt")
        
    token = get_api_token(usuario, senha)
    if not token:
        raise Exception("Falha ao obter token da API da ANA.")
        
    # Busca um histórico de 5 anos (60 meses) para treinar o Prophet adequadamente
    df = fetch_historical_data(token, ESTACAO_CODIGO, agora, num_meses=60)
    
    # Limpeza e Padronização
    if not df.empty:
        colunas_originais = list(df.columns)
        df.columns = [str(c).lower() for c in df.columns]
        
        col_data = next((c for c in df.columns if 'data' in c or 'date' in c), None)
        if col_data:
            df['Data'] = pd.to_datetime(df[col_data], errors='coerce')
            df.set_index('Data', inplace=True)
            df.sort_index(inplace=True)
            df = df[~df.index.duplicated(keep='last')]
            
        col_nivel = None
        for opcao in ['cota_adotada', 'cota_sensor', 'cota_manual', 'nivel', 'nivel_real']:
            if opcao in df.columns:
                col_nivel = opcao
                break
                
        if col_nivel:
            df['Nivel_Real'] = pd.to_numeric(df[col_nivel], errors='coerce') / 100.0
        else:
            df['Nivel_Real'] = 0.0 
            
        # AGRUPAMENTO DIÁRIO (MÉDIA)
        # Transforma os dados de 15 em 15 minutos em Média Diária. 
        # Isso remove o "ruído" da água, arruma a extrapolação física e calibra o Prophet.
        df = df[['Nivel_Real']].resample('D').mean()
        df = df.dropna(subset=['Nivel_Real'])
            
        df['Vazao_Calculada'] = calcular_vazao(df['Nivel_Real'])
            
    cache["df_dados"] = df
    cache["last_update"] = agora
    return df

@app.get("/api/dashboard")
def get_dashboard_data(dias_previsao: int = 180):
    try:
        df = carregar_dados_interno()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    if df.empty:
        raise HTTPException(status_code=404, detail="Nenhum dado retornado da API da ANA.")

    # 1. Histórico Observado
    # Como agora usamos Média Diária, 5 anos dão ~1825 linhas (JSON levíssimo). 
    # Enviamos tudo para o gráfico exibir o histórico longo.
    df_historico = df.copy()
    historico = []
    for idx, row in df_historico.iterrows():
        historico.append({
            "data": idx.strftime('%Y-%m-%d'),
            "nivel": row['Nivel_Real'] if pd.notna(row['Nivel_Real']) else None,
            "vazao": row['Vazao_Calculada'] if pd.notna(row['Vazao_Calculada']) else None
        })

    # 2. Extrapolação Física
    nivel_atual = df['Nivel_Real'].iloc[-1]
    projecao_niveis, taxa_media = extrapolar_decaimento_fisico(df, nivel_atual, dias_futuros=dias_previsao)
    
    ultima_data = df.index[-1]
    extrapolacao = []
    for i, n in enumerate(projecao_niveis):
        d_futura = ultima_data + timedelta(days=i+1)
        extrapolacao.append({
            "data": d_futura.strftime('%Y-%m-%d'),
            "nivel": n,
            "vazao": calcular_vazao(n).item() if hasattr(calcular_vazao(n), 'item') else calcular_vazao(n)
        })

    # 3. Prophet (Tenta gerar)
    prophet_data = []
    try:
        # Prever com a coluna Nivel_Real
        forecast = prever_com_prophet(df, dias_futuros=dias_previsao, col_nivel='Nivel_Real')
        if forecast is not None:
            # Pega só os dias do futuro
            forecast_futuro = forecast[forecast['ds'] > ultima_data]
            for _, row in forecast_futuro.iterrows():
                prophet_data.append({
                    "data": row['ds'].strftime('%Y-%m-%d'),
                    "nivel_yhat": row['yhat'],
                    "nivel_lower": row['yhat_lower'],
                    "nivel_upper": row['yhat_upper'],
                    "vazao_yhat": calcular_vazao(row['yhat']).item() if hasattr(calcular_vazao(row['yhat']), 'item') else calcular_vazao(row['yhat'])
                })
    except Exception as e:
        print(f"Erro no Prophet: {e}")

    return {
        "status": "success",
        "atualizacao": cache["last_update"].strftime('%Y-%m-%d %H:%M:%S'),
        "nivel_atual": nivel_atual,
        "vazao_atual": calcular_vazao(nivel_atual).item() if hasattr(calcular_vazao(nivel_atual), 'item') else calcular_vazao(nivel_atual),
        "taxa_decaimento_media": taxa_media,
        "dados": historico,
        "extrapolacao_fisica": extrapolacao,
        "previsao_prophet": prophet_data
    }
