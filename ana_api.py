import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE_URL = "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas"

def load_credentials(filepath):
    """Carrega as credenciais do arquivo API_ANA.txt."""
    creds = {}
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Arquivo de credenciais não encontrado: {filepath}")
        
    with open(filepath, 'r') as f:
        for line in f:
            if '=' in line:
                key, val = line.strip().split('=', 1)
                creds[key.strip()] = val.strip()
    return creds.get('ANA_USER'), creds.get('ANA_PASS')

def get_api_token(usuario, senha):
    """
    Faz a autenticação na API (ana.gov.br) e retorna o token de acesso.
    Possui sistema de retentativas caso a ANA retorne 504 ou 500.
    """
    auth_url = f"{API_BASE_URL}/OAUth/v1"
    headers = {
        'Identificador': usuario,
        'Senha': senha,
        'Expect': '' # Correção do erro 417 original
    }
    
    max_retries = 3
    for tentativa in range(max_retries):
        print(f"Tentando autenticar na API da ANA... (Tentativa {tentativa+1}/{max_retries})")
        try:
            response = requests.get(auth_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            token = data['items']['tokenautenticacao']
            print("Sucesso! Token obtido.")
            return token
        except Exception as e:
            print(f"Ocorreu um erro ao extrair o token na tentativa {tentativa+1}: {e}")
            if tentativa < max_retries - 1:
                print("Aguardando 5 segundos antes de tentar novamente...")
                time.sleep(5)
            else:
                print("Todas as tentativas de login falharam.")
                return None

def fetch_historical_data(token, codigo_estacao, data_fim_busca, num_meses=12):
    """
    Busca dados na API fazendo requests em paralelo (ThreadPoolExecutor) para
    evitar gargalos e timeouts no Streamlit Cloud.
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Expect': '',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    # Gerar os parâmetros para cada bloco de 30 dias
    request_params = []
    data_atual = data_fim_busca
    for i in range(num_meses):
        data_str = data_atual.strftime('%Y-%m-%d')
        params = {
            'Código da Estação': str(codigo_estacao),
            'Tipo Filtro Data': 'DATA_LEITURA',
            'Data de Busca (yyyy-MM-dd)': data_str,
            'Range Intervalo de busca': 'DIAS_30'
        }
        request_params.append(params)
        data_atual = data_atual - timedelta(days=30)
        
    all_items = []
    
    def fetch_single_month(params):
        url = f"{API_BASE_URL}/HidroinfoanaSerieTelemetricaDetalhada/v1"
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get('items'):
                return data['items']
        except Exception as e:
            print(f"     Erro ao buscar dados para {params['Data de Busca (yyyy-MM-dd)']}: {e}")
        return []

    print(f"\nColetando histórico da Estação: {codigo_estacao} ({num_meses} meses) em paralelo...")
    
    max_workers = min(10, num_meses)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single_month, p): p['Data de Busca (yyyy-MM-dd)'] for p in request_params}
        for future in as_completed(futures):
            date_str = futures[future]
            try:
                items = future.result()
                if items:
                    all_items.extend(items)
                    print(f"  -> Sucesso: {date_str} ({len(items)} registros)")
                else:
                    print(f"  -> Sem dados: {date_str}")
            except Exception as e:
                print(f"  -> Erro na thread para {date_str}: {e}")
                
    if not all_items:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_items)
    return process_raw_data(df)

def process_raw_data(df):
    """Limpa e formata os dados brutos recebidos da API."""
    if df.empty:
        return df
        
    # As colunas exatas dependem da resposta JSON, vamos identificar a data e o nível.
    # Geralmente a ANA retorna 'DataHora', 'Nivel', 'Chuva' etc.
    # Exibir colunas primeiro para debugar, mas já tentar conversões básicas
    print(f"\nForam coletados {len(df)} registros no total.")
    return df

if __name__ == "__main__":
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(BASE_DIR, "API_ANA.txt")
    
    usuario, senha = load_credentials(cred_path)
    
    if not usuario or not senha:
        print("Erro: Credenciais não encontradas.")
    else:
        token = get_api_token(usuario, senha)
        if token:
            # Buscar os últimos 24 meses (aprox 2 anos) como teste inicial
            df = fetch_historical_data(token, "60635200", datetime.now(), num_meses=24)
            print("\nAmostra dos dados:")
            print(df.head())
            print("\nColunas encontradas:", df.columns)
            
            # Salvar backup para analisar os campos
            df.to_csv(os.path.join(BASE_DIR, "dados_brutos.csv"), index=False)
            print("\nDados salvos em dados_brutos.csv para inspeção.")
