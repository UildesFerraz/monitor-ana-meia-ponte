import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Importando os módulos criados
from ana_api import load_credentials, get_api_token, fetch_historical_data
from curva_chave import calcular_vazao, processar_dados_ana
from model_forecasting import extrapolar_decaimento_fisico, prever_com_prophet

st.set_page_config(page_title="Monitoramento - ANA", layout="wide")

# Custom CSS for Premium Design
st.markdown("""
    <style>
        /* Import Outfit font */
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        
        /* Apply fonts globally */
        html, body, [class*="css"], .stApp {
            font-family: 'Outfit', sans-serif !important;
        }
        
        /* Main Title styling */
        .main-title {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #00c6ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 2rem;
            text-align: center;
        }
        
        /* Glassmorphic Metric Cards */
        .metric-card {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.4);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.06);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            text-align: center;
            margin-bottom: 1.5rem;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.12);
            border-color: rgba(30, 60, 114, 0.2);
        }
        
        .metric-label {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: #64748b;
            font-weight: 600;
            margin-bottom: 6px;
        }
        
        .metric-value {
            font-size: 2rem;
            font-weight: 800;
            color: #1e293b;
        }
        
        .metric-unit {
            font-size: 1.1rem;
            font-weight: 500;
            color: #64748b;
        }
        
        .metric-footer {
            font-size: 0.75rem;
            color: #94a3b8;
            margin-top: 6px;
        }
        
        /* Custom styling for Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
        
        /* Custom headers */
        h2, h3 {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            color: #1e293b !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🌧️ Previsão de Nível e Vazão - Estação ANA</div>', unsafe_allow_html=True)

# Constantes do Projeto
ESTACAO_CODIGO = "60635200"
NIVEL_ATENCAO_ESTIAGEM = 2.80 # Exemplo: Ajuste conforme necessário
NIVEL_ALERTA_CHEIA = 5.00     # Exemplo: Ajuste conforme necessário

@st.cache_data(ttl=3600)
def carregar_dados():
    """Função cacheada para não sobrecarregar a API."""
    usuario, senha = None, None
    # Tenta carregar dos Secrets do Streamlit Cloud primeiro (mais seguro para a nuvem)
    try:
        if "ANA_USER" in st.secrets and "ANA_PASS" in st.secrets:
            usuario = st.secrets["ANA_USER"]
            senha = st.secrets["ANA_PASS"]
    except Exception:
        # Ignora erro se st.secrets não estiver configurado localmente
        pass
        
    if not usuario or not senha:
        # Fallback local
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        cred_path = os.path.join(BASE_DIR, "API_ANA.txt")
        if os.path.exists(cred_path):
            usuario, senha = load_credentials(cred_path)
            
    if not usuario:
        st.error("Credenciais não encontradas. Configure st.secrets no Streamlit Cloud ou verifique API_ANA.txt localmente.")
        return pd.DataFrame()
        
    token = get_api_token(usuario, senha)
    if not token:
        st.error("Falha ao obter o token da API.")
        return pd.DataFrame()
        
    # Busca 24 meses (2 anos) para ter histórico suficiente
    df = fetch_historical_data(token, ESTACAO_CODIGO, datetime.now(), num_meses=24)
    
    if not df.empty:
        df = processar_dados_ana(df)
        # Resample para médias diárias
        # Isso reduz o tamanho do DataFrame de ~70.000 registros de 15 minutos para ~730 médias diárias.
        # Evita OOM (Out Of Memory) no Streamlit Cloud e reduz o tempo de treinamento do Prophet de 50 segundos para menos de 1 segundo!
        df = df[['Nivel_Real', 'Vazao_Calculada']].resample('D').mean()
        df = df.dropna(subset=['Nivel_Real'])
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
    
    # KPIs Rápidos com design premium
    col1, col2, col3 = st.columns(3)
    nivel_atual = df_dados['Nivel_Real'].iloc[-1] if 'Nivel_Real' in df_dados else 0
    vazao_atual = df_dados['Vazao_Calculada'].iloc[-1] if 'Vazao_Calculada' in df_dados else 0
    data_atualizacao = df_dados.index[-1].strftime('%d/%m/%Y') if not df_dados.empty else "N/A"
    
    col1.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Última Atualização</div>
            <div class="metric-value">{data_atualizacao}</div>
            <div class="metric-footer">Estação ANA {ESTACAO_CODIGO}</div>
        </div>
    """, unsafe_allow_html=True)
    
    col2.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Nível Atual</div>
            <div class="metric-value">{nivel_atual:.2f} <span class="metric-unit">m</span></div>
            <div class="metric-footer">Cota da calha do rio</div>
        </div>
    """, unsafe_allow_html=True)
    
    col3.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Vazão Atual</div>
            <div class="metric-value">{vazao_atual:.2f} <span class="metric-unit">m³/s</span></div>
            <div class="metric-footer">Calculado via curva-chave</div>
        </div>
    """, unsafe_allow_html=True)

    st.subheader(f"Histórico e Projeções - {metrica}")
    
    # 1. Gráfico Histórico
    fig = go.Figure()
    
    coluna_y = 'Nivel_Real' if metrica == "Nível (m)" else 'Vazao_Calculada'
    
    fig.add_trace(go.Scatter(
        x=df_dados.index, 
        y=df_dados[coluna_y],
        mode='lines',
        name='Histórico Observado',
        line=dict(color='#1e3c72', width=3, shape='spline')
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
            name='Extrapolação Física (Decaimento Exponencial)',
            line=dict(color='#ef4444', width=2.5, dash='dash')
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
                line=dict(color='#10b981', width=2.5, dash='dot')
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
                fillcolor='rgba(16, 185, 129, 0.15)',
                line=dict(width=0),
                name='Intervalo Confiança Prophet'
            ))
    except ImportError:
        pass
        
    fig.update_layout(
        height=600, 
        template="plotly_white", 
        title={
            'text': f"Evolução de {metrica}",
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': {'size': 20, 'family': 'Outfit', 'color': '#1e293b'}
        },
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=40, t=80, b=40),
        xaxis=dict(
            gridcolor='rgba(226, 232, 240, 0.6)',
            linecolor='#cbd5e1'
        ),
        yaxis=dict(
            gridcolor='rgba(226, 232, 240, 0.6)',
            linecolor='#cbd5e1'
        )
    )
    st.plotly_chart(fig, use_container_width=True)

    # Exibir tabela bruta
    with st.expander("Ver Dados em Tabela"):
        st.dataframe(df_dados.tail(100))
