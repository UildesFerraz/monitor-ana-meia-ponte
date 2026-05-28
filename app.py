import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Importando os módulos criados
from ana_api import load_credentials, get_api_token, fetch_historical_data
from curva_chave import calcular_vazao
from model_forecasting import extrapolar_decaimento_fisico, prever_com_prophet

st.set_page_config(page_title="Monitoramento - ANA", layout="wide")
st.title("🌧️ Previsão de Nível e Vazão - Estação ANA")

# Constantes do Projeto
ESTACAO_CODIGO = "60635200"
NIVEL_ATENCAO_ESTIAGEM = 2.80 # Exemplo: Ajuste conforme necessário
NIVEL_ALERTA_CHEIA = 5.00     # Exemplo: Ajuste conforme necessário

@st.cache_data(ttl=3600)
def carregar_dados():
    """Função cacheada para não sobrecarregar a API."""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(BASE_DIR, "API_ANA.txt")
    
    usuario, senha = load_credentials(cred_path)
    if not usuario:
        st.error("Credenciais não encontradas. Verifique API_ANA.txt")
        return pd.DataFrame()
        
    token = get_api_token(usuario, senha)
    if not token:
        st.error("Falha ao obter o token da API.")
        return pd.DataFrame()
        
    # Busca 24 meses (2 anos) para ter histórico suficiente
    df = fetch_historical_data(token, ESTACAO_CODIGO, datetime.now(), num_meses=24)
    
    if not df.empty and 'Nivel_Real' in df.columns:
        # Calcular vazão com a curva chave
        df['Vazao_Calculada'] = calcular_vazao(df['Nivel_Real'])
    return df

st.write("Baixando e processando dados históricos... Isso pode levar alguns segundos na primeira execução.")
with st.spinner('Processando...'):
    df_dados = carregar_dados()

if df_dados.empty:
    st.warning("Nenhum dado retornado da API ou erro no processamento.")
else:
    # Sidebar
    st.sidebar.header("Configurações")
    dias_previsao = st.sidebar.slider("Dias de Previsão Futura", min_value=7, max_value=60, value=30)
    metrica = st.sidebar.selectbox("Métrica para Visualizar", ["Nível (m)", "Vazão (m³/s)"])
    
    # KPIs Rápidos
    col1, col2, col3 = st.columns(3)
    nivel_atual = df_dados['Nivel_Real'].iloc[-1] if 'Nivel_Real' in df_dados else 0
    vazao_atual = df_dados['Vazao_Calculada'].iloc[-1] if 'Vazao_Calculada' in df_dados else 0
    data_atualizacao = df_dados.index[-1].strftime('%d/%m/%Y') if not df_dados.empty else "N/A"
    
    col1.metric("Última Atualização", data_atualizacao)
    col2.metric("Nível Atual (m)", f"{nivel_atual:.2f}")
    col3.metric("Vazão Atual (m³/s)", f"{vazao_atual:.2f}")

    st.subheader(f"Histórico e Projeções - {metrica}")
    
    # 1. Gráfico Histórico
    fig = go.Figure()
    
    coluna_y = 'Nivel_Real' if metrica == "Nível (m)" else 'Vazão_Calculada'
    
    fig.add_trace(go.Scatter(
        x=df_dados.index, 
        y=df_dados[coluna_y],
        mode='lines',
        name='Histórico Observado',
        line=dict(color='blue')
    ))
    
    # 2. Extrapolação Baseada em Decaimento Físico (Recessão)
    if 'Nivel_Real' in df_dados.columns:
        projecao_niveis, taxa_media = extrapolar_decaimento_fisico(df_dados, nivel_atual, dias_futuros=dias_previsao)
        datas_futuras = [df_dados.index[-1] + timedelta(days=i) for i in range(1, dias_previsao + 1)]
        
        projecao_y = projecao_niveis if metrica == "Nível (m)" else calcular_vazao(projecao_niveis)
        
        fig.add_trace(go.Scatter(
            x=datas_futuras, 
            y=projecao_y,
            mode='lines',
            name='Extrapolação Física (Pior Cenário Estiagem)',
            line=dict(color='red', dash='dash')
        ))
        
        # 3. Limiares de Alerta (Linhas horizontais)
        if metrica == "Nível (m)":
            fig.add_hline(y=NIVEL_ATENCAO_ESTIAGEM, line_dash="dot", annotation_text="Atenção Estiagem", line_color="orange")
            fig.add_hline(y=NIVEL_ALERTA_CHEIA, line_dash="dot", annotation_text="Alerta Cheia", line_color="purple")
            
            # Previsão: quando chega na estiagem?
            if nivel_atual > NIVEL_ATENCAO_ESTIAGEM:
                dias_para_estiagem = (nivel_atual - NIVEL_ATENCAO_ESTIAGEM) / taxa_media if taxa_media > 0 else float('inf')
                st.info(f"**Projeção de Estiagem:** Mantida a taxa de decaimento histórico ({taxa_media:.3f} m/dia), o nível de alerta será atingido em aprox. **{int(dias_para_estiagem)} dias**.")
        else:
            # Para Vazão
            vazao_estiagem = calcular_vazao(NIVEL_ATENCAO_ESTIAGEM)
            fig.add_hline(y=vazao_estiagem, line_dash="dot", annotation_text="Vazão Crítica", line_color="orange")

    # 4. (Opcional) Modelo Prophet
    try:
        from prophet import Prophet
        # Apenas mostrar Prophet se o módulo estiver disponível
        forecast = prever_com_prophet(df_dados, dias_futuros=dias_previsao, col_nivel=coluna_y)
        if forecast is not None:
            fig.add_trace(go.Scatter(
                x=forecast['ds'], 
                y=forecast['yhat'],
                mode='lines',
                name='Previsão Prophet',
                line=dict(color='green', dash='dot')
            ))
            fig.add_trace(go.Scatter(
                x=forecast['ds'], 
                y=forecast['yhat_upper'],
                mode='lines',
                line=dict(width=0),
                showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=forecast['ds'], 
                y=forecast['yhat_lower'],
                mode='lines',
                fill='tonexty',
                fillcolor='rgba(0, 128, 0, 0.2)',
                line=dict(width=0),
                name='Intervalo Confiança Prophet'
            ))
    except ImportError:
        pass # Prophet não disponível no ambiente atual, apenas pula a renderização deste

    fig.update_layout(height=600, template="plotly_white", title=f"Evolução de {metrica}")
    st.plotly_chart(fig, use_container_width=True)

    # Exibir tabela bruta
    with st.expander("Ver Dados em Tabela"):
        st.dataframe(df_dados.tail(100))
