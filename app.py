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

# Custom CSS for CIMEHGO Dark Forest Green Theme & Single Viewport Layout
st.markdown("""
    <style>
        /* Import Outfit font */
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        
        /* Apply fonts and background globally */
        html, body, [class*="css"], .stApp {
            font-family: 'Outfit', sans-serif !important;
            background-color: #0a140d !important;
            color: #e2ede4 !important;
        }
        
        /* Streamlit layout optimization to fit screen */
        .block-container {
            padding-top: 3.5rem !important;
            padding-bottom: 1.0rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        
        .stHeading {
            margin-top: -10px !important;
            margin-bottom: 8px !important;
        }
        
        /* Main Title styling */
        .main-title {
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #4ade80 0%, #10b981 50%, #059669 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.8rem;
            text-align: center;
        }
        
        /* Custom sidebar styling */
        section[data-testid="stSidebar"] {
            background-color: #0f1c12 !important;
            border-right: 1px solid #1c3522 !important;
        }
        
        section[data-testid="stSidebar"] p, 
        section[data-testid="stSidebar"] label, 
        section[data-testid="stSidebar"] span {
            color: #e2ede4 !important;
        }
        
        /* Compact Metric Cards */
        .metric-card {
            background: #112517 !important;
            border: 1px solid #1c3522 !important;
            border-radius: 10px;
            padding: 10px 14px !important;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
            text-align: center;
            margin-bottom: 0.6rem !important;
        }
        
        .metric-card:hover {
            transform: translateY(-2px);
            border-color: #4ade80 !important;
            box-shadow: 0 4px 20px rgba(74, 222, 128, 0.15);
        }
        
        .metric-label {
            font-size: 0.72rem !important;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: #8fa492 !important;
            font-weight: 600;
            margin-bottom: 2px !important;
        }
        
        .metric-value {
            font-size: 1.55rem !important;
            font-weight: 800;
            color: #ffffff !important;
        }
        
        .metric-unit {
            font-size: 0.95rem !important;
            font-weight: 500;
            color: #8fa492 !important;
        }
        
        .metric-footer {
            font-size: 0.7rem !important;
            color: #55725d !important;
            margin-top: 2px !important;
        }
        
        /* Compact Critical Alert Cards */
        .alerta-card {
            background: #112517 !important;
            border: 1px solid #1c3522 !important;
            border-radius: 10px;
            padding: 8px 12px !important;
            margin-bottom: 0.5rem !important;
            transition: all 0.2s ease;
            box-shadow: 0 3px 10px rgba(0,0,0,0.15);
        }
        
        .alerta-card:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        }
        
        .alerta-titulo {
            font-size: 0.72rem !important;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 2px !important;
        }
        
        .alerta-status {
            font-size: 0.95rem !important;
            font-weight: 800;
            color: #ffffff !important;
            margin-bottom: 2px !important;
        }
        
        .alerta-detalhe {
            font-size: 0.7rem !important;
            color: #8fa492 !important;
        }
        
        /* Native Streamlit Elements */
        div[data-testid="stExpander"], .stDataFrame {
            background-color: #112517 !important;
            border: 1px solid #1c3522 !important;
            border-radius: 10px !important;
            color: #e2ede4 !important;
        }
        
        div[data-testid="stExpander"] summary {
            color: #ffffff !important;
            font-weight: 600 !important;
        }
        
        /* Table styles */
        table {
            color: #e2ede4 !important;
        }
        th {
            background-color: #0c150e !important;
            color: #ffffff !important;
        }
        td {
            background-color: #112517 !important;
            color: #e2ede4 !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🌧️ Previsão de Nível e Vazão - Estação ANA (CIMEHGO)</div>', unsafe_allow_html=True)

# Constantes do Projeto
ESTACAO_CODIGO = "60635200"
NIVEL_ATENCAO_ESTIAGEM = 2.80 
NIVEL_ALERTA_CHEIA = 5.00     

# Limiares de Alerta Oficial (Bacia do Rio Meia Ponte - SEMAD / CIMEHGO)
ALERTAS_VAZAO = [
    {"nome": "Atenção (12m³/s)", "valor": 12.0, "cor": "#fde047"},
    {"nome": "Alerta (9m³/s)", "valor": 9.0, "cor": "#fbbf24"},
    {"nome": "Crítico 1 (5.5m³/s)", "valor": 5.5, "cor": "#f97316"},
    {"nome": "Crítico 2 (4.0m³/s)", "valor": 4.0, "cor": "#ef4444"},
    {"nome": "Crítico 3 (3.0m³/s)", "valor": 3.0, "cor": "#b91c1c"},
    {"nome": "Crítico 4 (2.0m³/s)", "valor": 2.0, "cor": "#7f1d1d"}
]

@st.cache_data(ttl=3600)
def carregar_dados():
    """Função cacheada para não sobrecarregar a API."""
    usuario, senha = None, None
    try:
        if "ANA_USER" in st.secrets and "ANA_PASS" in st.secrets:
            usuario = st.secrets["ANA_USER"]
            senha = st.secrets["ANA_PASS"]
    except Exception:
        pass
        
    if not usuario or not senha:
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
        
    # Busca 60 meses (5 anos) em paralelo para ter o histórico completo e a mesma acurácia do projeto local
    df = fetch_historical_data(token, ESTACAO_CODIGO, datetime.now(), num_meses=60)
    
    if not df.empty:
        df = processar_dados_ana(df)
        df = df[['Nivel_Real', 'Vazao_Calculada']].resample('D').mean()
        df = df.dropna(subset=['Nivel_Real'])
    return df

@st.cache_data(ttl=3600)
def cached_prever_com_prophet(df, dias, col):
    return prever_com_prophet(df, dias_futuros=dias, col_nivel=col)

@st.cache_data(ttl=3600)
def cached_extrapolar_decaimento_fisico(df, nivel, dias):
    return extrapolar_decaimento_fisico(df, nivel, dias_futuros=dias)

st.write("Baixando e processando dados históricos... Isso pode levar alguns segundos na primeira execução.")
with st.spinner('Processando...'):
    df_dados = carregar_dados()

if df_dados.empty:
    st.warning("Nenhum dado retornado da API ou erro no processamento.")
else:
    # Sidebar - Configurações
    st.sidebar.header("Configurações")
    dias_previsao = st.sidebar.slider("Dias de Previsão Futura", min_value=7, max_value=60, value=30)
    
    # Horizonte histórico para visualização (inicia com os últimos 7 dias automaticamente)
    dias_historicos_sel = st.sidebar.selectbox(
        "Horizonte Histórico no Gráfico",
        options=["Últimos 7 dias", "Últimos 15 dias", "Últimos 30 dias", "Últimos 90 dias", "Últimos 180 dias", "Último ano", "Histórico Completo"],
        index=0
    )
    
    dias_map = {
        "Últimos 7 dias": 7,
        "Últimos 15 dias": 15,
        "Últimos 30 dias": 30,
        "Últimos 90 dias": 90,
        "Últimos 180 dias": 180,
        "Último ano": 365,
        "Histórico Completo": len(df_dados)
    }
    dias_filtrar = dias_map[dias_historicos_sel]
    
    metrica = st.sidebar.selectbox("Métrica para Visualizar", ["Nível (m)", "Vazão (m³/s)"])
    
    nivel_atual = df_dados['Nivel_Real'].iloc[-1] if 'Nivel_Real' in df_dados else 0
    vazao_atual = df_dados['Vazao_Calculada'].iloc[-1] if 'Vazao_Calculada' in df_dados else 0
    data_atualizacao = df_dados.index[-1].strftime('%d/%m/%Y') if not df_dados.empty else "N/A"

    # Projeções Físicas & Prophet (Calculado sobre toda a base histórica para acurácia máxima)
    projecao_niveis, taxa_media = cached_extrapolar_decaimento_fisico(df_dados, nivel_atual, dias_previsao)
    projecao_vazao_fisica = calcular_vazao(projecao_niveis)
    
    projecao_vazao_prophet = None
    try:
        from prophet import Prophet
        # Executa previsão da vazão com Prophet
        forecast = cached_prever_com_prophet(df_dados, dias_previsao, 'Vazao_Calculada')
        if forecast is not None:
            forecast_futuro = forecast[forecast['ds'] > df_dados.index[-1]].head(dias_previsao)
            projecao_vazao_prophet = forecast_futuro['yhat'].values
    except Exception:
        pass

    # Calcular dias de entrada nos níveis críticos (Vazão)
    kpis_criticos = []
    for alerta in ALERTAS_VAZAO:
        valor_limite = alerta["valor"]
        cor_alerta = alerta["cor"]
        nome_alerta = alerta["nome"]
        
        if vazao_atual <= valor_limite:
            status_str = "Atingido"
            detalhe_str = f"Vazão atual abaixo de {valor_limite:.1f} m³/s"
            cor_texto = cor_alerta
        else:
            # Encontrar na extrapolação física
            data_fisica = None
            dias_fisica = None
            for idx, q_val in enumerate(projecao_vazao_fisica):
                if q_val <= valor_limite:
                    dias_fisica = idx + 1
                    data_fisica = (df_dados.index[-1] + timedelta(days=dias_fisica)).strftime('%d/%m')
                    break
            
            # Encontrar no Prophet
            data_prophet = None
            dias_prophet = None
            if projecao_vazao_prophet is not None:
                for idx, q_val in enumerate(projecao_vazao_prophet):
                    if q_val <= valor_limite:
                        dias_prophet = idx + 1
                        data_prophet = (df_dados.index[-1] + timedelta(days=dias_prophet)).strftime('%d/%m')
                        break
            
            parts = []
            if data_fisica:
                parts.append(f"Fís.: {data_fisica} ({dias_fisica}d)")
            else:
                parts.append(f"Fís.: >{dias_previsao}d")
                
            if data_prophet:
                parts.append(f"Prop.: {data_prophet} ({dias_prophet}d)")
            else:
                parts.append(f"Prop.: >{dias_previsao}d")
                
            status_str = " | ".join(parts)
            detalhe_str = f"Previsão de entrada para {valor_limite:.1f} m³/s"
            cor_texto = "#ffffff"
            
        kpis_criticos.append({
            "nome": nome_alerta,
            "status": status_str,
            "detalhe": detalhe_str,
            "cor": cor_alerta,
            "cor_texto": cor_texto
        })

    # Dividir a tela em Esquerda (Métricas & Alertas) e Direita (Gráfico)
    col_dados, col_grafico = st.columns([2, 3])

    with col_dados:
        st.subheader("📊 Situação Atual")
        
        # KPIs Rápidos
        kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
        
        kpi_col1.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Última Leitura</div>
                <div class="metric-value">{data_atualizacao}</div>
                <div class="metric-footer">Estação {ESTACAO_CODIGO}</div>
            </div>
        """, unsafe_allow_html=True)
        
        kpi_col2.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Nível Atual</div>
                <div class="metric-value">{nivel_atual:.2f} <span class="metric-unit">m</span></div>
                <div class="metric-footer">Cota da calha do rio</div>
            </div>
        """, unsafe_allow_html=True)
        
        kpi_col3.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Vazão Atual</div>
                <div class="metric-value">{(vazao_atual * 1000):,.0f} <span class="metric-unit">L/s</span></div>
                <div class="metric-footer">Equivalente a {vazao_atual:.2f} m³/s</div>
            </div>
        """, unsafe_allow_html=True)

        st.subheader("⚠️ Projeção de Níveis Críticos (Vazão)")
        
        # Alertas em grid de 2 colunas
        alt_col1, alt_col2 = st.columns(2)
        for idx, kpi in enumerate(kpis_criticos):
            target_col = alt_col1 if idx % 2 == 0 else alt_col2
            target_col.markdown(f"""
                <div class="alerta-card" style="border-left: 5px solid {kpi['cor']};">
                    <div class="alerta-titulo" style="color: {kpi['cor']};">{kpi['nome']}</div>
                    <div class="alerta-status" style="color: {kpi['cor_texto']};">{kpi['status']}</div>
                    <div class="alerta-detalhe">{kpi['detalhe']}</div>
                </div>
            """, unsafe_allow_html=True)

    with col_grafico:
        st.subheader(f"Evolução e Projeções - {metrica}")
        
        fig = go.Figure()
        coluna_y = 'Nivel_Real' if metrica == "Nível (m)" else 'Vazao_Calculada'
        
        # Filtrar o histórico conforme o limite selecionado na barra lateral
        df_plot_hist = df_dados.tail(dias_filtrar)
        y_hist = df_plot_hist[coluna_y]
        if metrica == "Vazão (m³/s)":
            y_hist = y_hist * 1000
            
        # 1. Gráfico Histórico (Com marcadores se a janela histórica for pequena)
        mode_style = 'lines+markers' if dias_filtrar <= 15 else 'lines'
        fig.add_trace(go.Scatter(
            x=df_plot_hist.index, 
            y=y_hist,
            mode=mode_style,
            name='Histórico Observado',
            line=dict(color='#38bdf8', width=3, shape='spline')
        ))
        
        # 2. Extrapolação Baseada em Decaimento Físico (Recessão)
        if 'Nivel_Real' in df_dados.columns:
            datas_futuras = [df_dados.index[-1] + timedelta(days=i) for i in range(1, dias_previsao + 1)]
            projecao_y = projecao_niveis if metrica == "Nível (m)" else projecao_vazao_fisica
            if metrica == "Vazão (m³/s)":
                projecao_y = projecao_y * 1000
                
            fig.add_trace(go.Scatter(
                x=datas_futuras, 
                y=projecao_y,
                mode='lines',
                name='Extrapolação Física (Recessão)',
                line=dict(color='#f43f5e', width=2.5, dash='dash')
            ))
            
            # 3. Limiares de Alerta no Gráfico (Linhas horizontais)
            if metrica == "Nível (m)":
                fig.add_hline(y=NIVEL_ATENCAO_ESTIAGEM, line_dash="dot", annotation_text="Atenção Estiagem (2.80m)", line_color="#fbbf24")
                fig.add_hline(y=NIVEL_ALERTA_CHEIA, line_dash="dot", annotation_text="Alerta Cheia (5.00m)", line_color="#818cf8")
            else:
                for alerta in ALERTAS_VAZAO:
                    fig.add_hline(
                        y=alerta["valor"] * 1000,
                        line_dash="dot",
                        line_color=alerta["cor"],
                        annotation_text=alerta["nome"].split("(")[0], # Remove o m³/s para encurtar
                        annotation_position="bottom right",
                        annotation_font=dict(size=9, color="#8fa492")
                    )

        # 4. Modelo Prophet (Opcional)
        try:
            forecast = cached_prever_com_prophet(df_dados, dias_previsao, coluna_y)
            if forecast is not None:
                forecast_futuro = forecast[forecast['ds'] > df_dados.index[-1]].head(dias_previsao)
                
                y_prophet = forecast_futuro['yhat'].values
                y_prophet_upper = forecast_futuro['yhat_upper'].values
                y_prophet_lower = forecast_futuro['yhat_lower'].values
                
                if metrica == "Vazão (m³/s)":
                    y_prophet = y_prophet * 1000
                    y_prophet_upper = y_prophet_upper * 1000
                    y_prophet_lower = y_prophet_lower * 1000
                    
                fig.add_trace(go.Scatter(
                    x=forecast_futuro['ds'], 
                    y=y_prophet,
                    mode='lines',
                    name='Previsão Prophet',
                    line=dict(color='#10b981', width=2.5, dash='dot')
                ))
                fig.add_trace(go.Scatter(
                    x=forecast_futuro['ds'], 
                    y=y_prophet_upper,
                    mode='lines',
                    line=dict(width=0),
                    showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=forecast_futuro['ds'], 
                    y=y_prophet_lower,
                    mode='lines',
                    fill='tonexty',
                    fillcolor='rgba(16, 185, 129, 0.12)',
                    line=dict(width=0),
                    name='Intervalo Confiança Prophet'
                ))
        except Exception:
            pass
            
        fig.update_layout(
            height=460, 
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Outfit, sans-serif", size=11, color="#e2ede4"),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                font=dict(color="#e2ede4")
            ),
            margin=dict(l=40, r=40, t=50, b=40),
            xaxis=dict(
                gridcolor='rgba(28, 53, 34, 0.4)',
                linecolor='#1c3522',
                tickfont=dict(color="#8fa492")
            ),
            yaxis=dict(
                title="Nível (m)" if metrica == "Nível (m)" else "Vazão (L/s)",
                gridcolor='rgba(28, 53, 34, 0.4)',
                linecolor='#1c3522',
                tickfont=dict(color="#8fa492")
            )
        )
        st.plotly_chart(fig, use_container_width=True)

        # Exibir tabela bruta compacta
        with st.expander("Ver Dados em Tabela"):
            df_tabela = df_dados.copy()
            if metrica == "Vazão (m³/s)":
                df_tabela['Vazao_L_s'] = df_tabela['Vazao_Calculada'] * 1000
                st.dataframe(df_tabela[['Nivel_Real', 'Vazao_Calculada', 'Vazao_L_s']].tail(100))
            else:
                st.dataframe(df_tabela[['Nivel_Real', 'Vazao_Calculada']].tail(100))
