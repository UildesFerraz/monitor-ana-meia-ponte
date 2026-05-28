import traceback
try:
    from main import carregar_dados_interno, get_dashboard_data
    print("Iniciando teste de carga...")
    df = carregar_dados_interno()
    print("Dados carregados com sucesso. Linhas:", len(df))
    print("Gerando JSON do dashboard...")
    dados = get_dashboard_data(30)
    print("JSON gerado com sucesso. Chaves:", dados.keys())
    print("TUDO OK!")
except Exception as e:
    print("ERRO ENCONTRADO:")
    traceback.print_exc()
