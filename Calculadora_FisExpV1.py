import sympy as sp
import numpy as np
import pandas as pd
import os
import re

# =================================================================
# --- SPRINT 1: MOTOR SIMBÓLICO (MÚLTIPLAS EQUAÇÕES) ---
# =================================================================
def obter_formulas():
    print("=== Expressões Simbólicas ===")
    print("Você pode digitar várias equações separadas por vírgula ou ponto e vírgula.")
    print("Exemplo: Z = V/i, P = R*i**2, XL = VL/i")
    
    entrada = input("\nDigite as fórmulas: ")
    # Quebra a string por vírgulas ou ponto-e-vírgulas
    partes = re.split(r'[,;]', entrada)
    
    dict_formulas = {}
    contador_anonimas = 1
    
    for parte in partes:
        parte = parte.strip()
        if not parte: continue
        
        try:
            if "=" in parte:
                nome, expressao = parte.split("=")
                nome = nome.strip()
                dict_formulas[nome] = sp.sympify(expressao.strip())
            else:
                nome = f"Eq{contador_anonimas}"
                dict_formulas[nome] = sp.sympify(parte)
                contador_anonimas += 1
        except Exception as e:
            print(f"[ERRO FATAL] Falha ao interpretar a formula: {parte} | Detalhe: {e}")
            return None
            
    return dict_formulas

# =================================================================
# --- SPRINT 2: CLASSIFICAÇÃO DE VARIÁVEIS (CONJUNTO ÚNICO) ---
# =================================================================
def organizar_variaveis(dict_formulas):
    variaveis_medidas = set()
    constantes = {}
    dict_derivadas = {nome: {} for nome in dict_formulas}
    
    # Extrai todas as variáveis únicas de todas as fórmulas combinadas
    simbolos_unicos = set()
    for formula in dict_formulas.values():
        simbolos_unicos.update(formula.free_symbols)
        
    print("\n--- Configuração de Parâmetros Globais ---")
    for s in simbolos_unicos:
        opcao = input(f"O símbolo '{s}' é uma (v)ariável medida ou (c)onstante? ").lower().strip()
        
        if opcao == 'v':
            variaveis_medidas.add(str(s))
            # Calcula a derivada dessa variável para cada fórmula que a contenha
            for nome, formula in dict_formulas.items():
                if s in formula.free_symbols:
                    dict_derivadas[nome][str(s)] = sp.diff(formula, s)
        else:
            valor = float(input(f"Digite o valor estático de {s}: "))
            constantes[str(s)] = valor

    return variaveis_medidas, constantes, dict_derivadas

# =================================================================
# --- SPRINT 3: MOTOR DE INCERTEZAS (REFATORADO PARA CSV) ---
# =================================================================
def processar_incertezas(variaveis_medidas):
    print("\n--- Processamento de Incerteza (Coleta de Dados via CSV) ---")
    
    arquivo_csv = input("Digite o caminho do arquivo .csv (ex: dados.csv): ").strip()
    
    try:
        # Lê o CSV. O pandas automaticamente coloca np.nan nas células vazias
        df = pd.read_csv(arquivo_csv)
    except FileNotFoundError:
        raise FileNotFoundError(f"[ERRO] Arquivo '{arquivo_csv}' não encontrado. Verifique o caminho.")
    except Exception as e:
        raise RuntimeError(f"[ERRO] Falha ao ler o CSV: {e}")

    dados_brutos = {}
    incertezas_tipo_b = {}
    tamanho_vetor = len(df)
    
    colunas_csv = list(df.columns)
    print(f"\n[SISTEMA] CSV carregado com sucesso. {tamanho_vetor} linhas detectadas.")
    print(f"[SISTEMA] Colunas detectadas: {', '.join(colunas_csv)}")

    # Itera estritamente sobre as colunas do CSV para definir as variáveis
    for var in colunas_csv:
        print(f"\n===== Analisando Variável/Coluna: {var} =====")
        
        # Seleção do Perfil do Instrumento
        print("Qual o tipo de instrumento utilizado para esta medição?")
        print("(A) Simples / Analógico")
        print("(B) Avançado / Multímetro Digital (via datasheet)")
        tipo_inst = input("Escolha (A/B): ").strip().upper()
        
        fator_instrumento = float(input(f"Multiplicador SI para a RESOLUÇÃO de {var} (ex: 1e-3 para mili): "))
        
        if tipo_inst == 'A':
            resolucao = float(input(f"Resolução do instrumento para {var}: "))
            u_b = (resolucao / np.sqrt(3)) * fator_instrumento
            
        elif tipo_inst == 'B':
            valor_lido = float(input(f"Valor Lido (Fundo de escala ou nominal): "))
            erro_pct = float(input(f"Erro percentual da leitura (%): "))
            digitos = float(input(f"Número de dígitos de resolução: "))
            resolucao = float(input(f"Resolução do dígito (ex: 0.1): "))
            
            erro_calculado = (valor_lido * (erro_pct / 100.0)) + (resolucao * digitos)
            u_b = (erro_calculado / np.sqrt(3)) * fator_instrumento
        else:
            print("[ERRO] Opção inválida. Assumindo incerteza zero.")
            u_b = 0.0
            
        incertezas_tipo_b[var] = u_b
        print(f"  > Incerteza Tipo B (SI): {u_b:.6e}")
        
        # Coleta de Dados via Pandas Series
        fator_medida = float(input(f"Multiplicador SI para os VALORES MEDIDOS da coluna '{var}': "))
        # Converte a coluna inteira (preservando NaNs) multiplicando pelo fator SI
        arr_convertido = df[var].to_numpy(dtype=float) * fator_medida
        dados_brutos[var] = arr_convertido

    print("\n=== NATUREZA DOS DADOS VETORIZADOS ===")
    print("Estes dados representam:")
    print("(1) Medições repetidas do mesmo estado físico (permite u_A)")
    print("(2) Medições de estados/circuitos diferentes (ex: lote de ensaios independentes)")
    natureza_medicao = input("Escolha (1/2): ").strip()

    return dados_brutos, incertezas_tipo_b, tamanho_vetor, natureza_medicao

# =================================================================
# --- SPRINT 4: PROPAGAÇÃO VETORIZADA EM LOTE (BLINDADA PARA NAN) ---
# =================================================================
def calcular_resultados_em_lote(dict_formulas, dados_brutos, incertezas_tipo_b, dict_derivadas, constantes, tamanho_vetor, natureza_medicao):
    print("\n=== EXECUTANDO MOTOR DE CÁLCULO VETORIZADO (LOTE) ===")
    
    variaveis_completas = {**constantes, **dados_brutos}
    simbolos = list(variaveis_completas.keys())
    tupla_simbolos = tuple(simbolos)
    
    matriz_dados = []
    for s in simbolos:
        val = variaveis_completas[s]
        if np.isscalar(val):
            matriz_dados.append(np.full(tamanho_vetor, val))
        else:
            matriz_dados.append(val)
            
    resultados_finais = {} 
    estatisticas_finais = {} 
    
    for nome_eq, formula in dict_formulas.items():
        print(f"\n--- Processando Equação: {nome_eq} ---")
        
        # =====================================================================
        # BLINDAGEM MATEMÁTICA: Silencia RuntimeWarnings gerados por NaNs
        # =====================================================================
        with np.errstate(invalid='ignore', divide='ignore'):
            
            # 1. Cálculo Nominal O(1)
            func_nominal = sp.lambdify(tupla_simbolos, formula, modules='numpy')
            res_nominais = np.atleast_1d(func_nominal(*matriz_dados))
            if res_nominais.size == 1 and tamanho_vetor > 1:
                res_nominais = np.full(tamanho_vetor, res_nominais[0], dtype=float)
                
            # 2. Propagação da Incerteza (Tipo B)
            variancia_total = np.zeros(tamanho_vetor, dtype=float)
            for var, derivada in dict_derivadas[nome_eq].items():
                func_derivada = sp.lambdify(tupla_simbolos, derivada, modules='numpy')
                valores_derivada = np.atleast_1d(func_derivada(*matriz_dados))
                if valores_derivada.size == 1 and tamanho_vetor > 1:
                    valores_derivada = np.full(tamanho_vetor, valores_derivada[0], dtype=float)
                    
                # A incerteza u_B só se aplica se houver variável mapeada (constantes não entram aqui)
                if var in incertezas_tipo_b:
                    u_b_var = incertezas_tipo_b[var]
                    variancia_total += (valores_derivada * u_b_var) ** 2
                
            u_B_propagada = np.sqrt(variancia_total)
            resultados_finais[nome_eq] = {
                'nominais': res_nominais,
                'incertezas': u_B_propagada
            }
            
            # 3. Avaliação Estatística (Ignorando NaNs para não quebrar a média do lote)
            if tamanho_vetor > 1:
                # np.nanmean ignora as linhas com NaN ao calcular a média geral do experimento
                resultado_medio = np.nanmean(res_nominais)
                u_B_final = np.sqrt(np.nanmean(u_B_propagada**2))
                
                if natureza_medicao == '1':
                    # np.nanstd garante cálculo de incerteza A correto considerando n real das amostras válidas
                    u_A_final = np.nanstd(res_nominais, ddof=1) / np.sqrt(np.count_nonzero(~np.isnan(res_nominais)))
                    print(f"  > u_A calculado via desvio padrão da média: {u_A_final:.4e}")
                else:
                    u_A_final = 0.0
                    print(f"  > u_A forçado a 0 (processamento de múltiplos estados em lote).")
                    
                erro_final = np.sqrt(u_A_final**2 + u_B_final**2)
            else:
                resultado_medio = res_nominais[0]
                erro_final = u_B_propagada[0]
                
            estatisticas_finais[nome_eq] = (resultado_medio, erro_final)
        
    return resultados_finais, estatisticas_finais

# =================================================================
# --- SPRINT 5: RELATÓRIO E EXPORTAÇÃO EM LOTE (ESTRUTURADO) ---
# =================================================================
def gerar_relatorio_lote(dict_formulas, resultados_finais, estatisticas, dados_brutos, incertezas_b, tam_vetor, nome_arquivo="dados_experimento.dat"):
    print("\n" + "=" * 60)
    print("📊 RELATÓRIO ANALÍTICO E EXPORTAÇÃO (BATCH)")
    print("=" * 60)
    
    tabela_dados = []
    for i in range(tam_vetor):
        linha = {"Medicao": i + 1}
        
        # Colunas de Entrada (Inputs)
        for var, valores in dados_brutos.items():
            val = valores[i] if isinstance(valores, np.ndarray) else valores
            linha[f"IN_{var}_val"] = val
            linha[f"IN_{var}_unc"] = incertezas_b[var]
            
        # Colunas de Saída (Outputs Calculados)
        for nome_eq, res in resultados_finais.items():
            linha[f"OUT_{nome_eq}_val"] = res['nominais'][i]
            linha[f"OUT_{nome_eq}_unc"] = res['incertezas'][i]
            
        tabela_dados.append(linha)
        
    df_exportacao = pd.DataFrame(tabela_dados)
    pd.options.display.float_format = '{:.6e}'.format
    
    print("\n--- Dados Experimentais Combinados (SI) ---")
    # Imprime preservando a estrutura de NaN
    print(df_exportacao.to_string(index=False, na_rep='NaN'))
    print("-" * 60)
    
    print("\n--- Síntese Simbólica por Equação ---")
    for nome, formula in dict_formulas.items():
        media, erro = estatisticas[nome]
        print(f"[{nome}] Equação Base: ", end="")
        sp.pprint(formula)
        print(f"Resultado Final Médio ({nome}): {media:.6e} ± {erro:.6e}\n")
        
    caminho_arquivo = os.path.join(os.getcwd(), nome_arquivo)
    try:
        # Exporta com tabulações, preservando 'NaN' nos índices em branco para o Gnuplot
        df_exportacao.to_csv(caminho_arquivo, sep='\t', index=False, na_rep='NaN')
        print("=" * 60)
        print(f"[SISTEMA] Arquivo exportado: {caminho_arquivo}")
    except IOError as e:
        print(f"\n[ERRO DE I/O] Falha ao gravar arquivo: {e}")

# =================================================================
# --- PIPELINE DE EXECUÇÃO ---
# =================================================================
if __name__ == "__main__":
    dict_formulas = obter_formulas()
    
    if dict_formulas:
        vars_medidas, dict_constantes, dict_derivadas = organizar_variaveis(dict_formulas)
        dados_brutos, incertezas_b, tam_vetor, nat_medida = processar_incertezas(vars_medidas)
        
        resultados, estatisticas = calcular_resultados_em_lote(
            dict_formulas, dados_brutos, incertezas_b, dict_derivadas, dict_constantes, tam_vetor, nat_medida
        )
        
        gerar_relatorio_lote(
            dict_formulas, resultados, estatisticas, dados_brutos, incertezas_b, tam_vetor
        )
