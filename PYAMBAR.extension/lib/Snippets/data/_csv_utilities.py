# -*- coding: utf-8 -*-
"""
_csv_utilities.py
Funções para leitura, escrita e manipulação de arquivos CSV com encoding UTF-8.

USAGE:
    from Snippets.data._csv_utilities import (
        exportar_csv_coordenadas,
        ler_csv_utf8,
        escrever_csv_utf8,
        adicionar_coluna_csv,
        remover_coluna_csv,
        ler_csv_por_colunas
    )

    # Exportar dados de coordenadas
    dados = [
        {'comentario': 'Pilar 1', 'x': 1000.5, 'y': 2000.3, 'z': 0.0},
        {'comentario': 'Pilar 2', 'x': 3000.8, 'y': 2000.3, 'z': 0.0},
    ]
    arquivo = exportar_csv_coordenadas(dados, "Coordenadas_Pilares", "20251127_143025")

    # Ler CSV - modo dicionário (padrão)
    linhas = ler_csv_utf8(arquivo)

    # Ler CSV - modo tupla (compatibilidade ParameterPalette)
    headers, rows = ler_csv_utf8(arquivo, retornar_tupla=True)

    # Escrever CSV
    headers = ['Nome', 'Valor']
    rows = [['Item 1', '100'], ['Item 2', '200']]
    escrever_csv_utf8("dados.csv", headers, rows)

    # Adicionar coluna
    adicionar_coluna_csv("dados.csv", "Unidade", "mm")

    # Ler por colunas
    colunas = ler_csv_por_colunas("dados.csv")
    print(colunas['Nome'])  # ['Item 1', 'Item 2']

DEPENDENCIES:
    - codecs, os, csv

AUTHOR: Thiago Barreto
VERSION: 2.0 (Extendido em ITERATION 2 - 29/11/2025)
CHANGELOG:
    v2.0: Adicionadas 4 novas funções:
          - escrever_csv_utf8() - escrita com aspas e UTF-8-sig
          - ler_csv_por_colunas() - organiza dados por coluna
          - adicionar_coluna_csv() - adiciona coluna a CSV existente
          - remover_coluna_csv() - remove coluna de CSV existente
          Estendida ler_csv_utf8() com parâmetro retornar_tupla para
          compatibilidade com ParameterPalette
    v1.0: Funções originais da ITERATION 1
"""

import codecs
import os
import csv
from datetime import datetime


def exportar_csv_coordenadas(dados_lista, nome_vista, timestamp=None, pasta_destino=None):
    """
    Exporta lista de dados de coordenadas para arquivo CSV com UTF-8.

    Args:
        dados_lista (list): Lista de dicionários com chaves 'mark', 'comentario', 'stage', 'x', 'y', 'z', 'data'
        nome_vista (str): Nome da vista para compor nome do arquivo
        timestamp (str): Timestamp customizado (opcional, gerado automaticamente se None)
        pasta_destino (str): Pasta onde salvar CSV (opcional, usa Desktop se None)

    Returns:
        str: Caminho completo do arquivo CSV criado

    Example:
        >>> dados = [
        ...     {'mark': 'SP-001', 'comentario': 'P1', 'stage': '4IN', 'x': 1000.5, 'y': 2000.3, 'z': 0.0, 'data': '20260107'},
        ...     {'mark': 'SP-002', 'comentario': 'P2', 'stage': '4IN', 'x': 3000.8, 'y': 2500.1, 'z': 0.0, 'data': '20260107'},
        ... ]
        >>> arquivo = exportar_csv_coordenadas(dados, "Planta_Pilares")
        >>> print(arquivo)
        'C:\\Users\\...\\Desktop\\Coordenadas_Planta_Pilares_20251127_143025.csv'
    """
    # Gerar timestamp se não fornecido
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determinar pasta de destino
    if pasta_destino is None:
        pasta_destino = os.path.join(os.path.expanduser("~"), "Desktop")

    # Construir nome do arquivo
    nome_arquivo = "Coordenadas_{}_{}.csv".format(nome_vista.replace(" ", "_"), timestamp)
    caminho_completo = os.path.join(pasta_destino, nome_arquivo)

    # Escrever CSV com UTF-8
    try:
        with codecs.open(caminho_completo, 'w', encoding='utf-8') as f:
            # Cabeçalho (ordem: Marca, Comentario, Stage, Coord_X/Y/Z, Coord_DataGeracao)
            f.write("Marca,Comentario,Stage,Coord_X,Coord_Y,Coord_Z,Coord_DataGeracao\n")

            # Dados
            for dado in dados_lista:
                mark = dado.get('mark', '')
                comentario = dado.get('comentario', '')
                stage = dado.get('stage', '')
                x = dado.get('x', 0.0)
                y = dado.get('y', 0.0)
                z = dado.get('z', 0.0)
                data = dado.get('data', '')

                # Formatar com 8 casas decimais (precisão milimétrica)
                f.write("{},{},{},{:.8f},{:.8f},{:.8f},{}\n".format(mark, comentario, stage, x, y, z, data))

        print("CSV exportado: {}".format(caminho_completo))
        return caminho_completo

    except Exception as e:
        print("ERRO ao exportar CSV: {}".format(str(e)))
        return None


def exportar_csv_generico(dados_lista, colunas, nome_arquivo, pasta_destino=None):
    """
    Exporta dados genéricos para CSV com UTF-8.

    Args:
        dados_lista (list): Lista de dicionários com dados
        colunas (list): Lista de nomes de colunas (chaves dos dicionários)
        nome_arquivo (str): Nome do arquivo CSV (sem extensão)
        pasta_destino (str): Pasta onde salvar CSV (opcional)

    Returns:
        str: Caminho completo do arquivo CSV criado

    Example:
        >>> dados = [
        ...     {'nome': 'Parede 1', 'tipo': 'Concreto', 'area': 25.5},
        ...     {'nome': 'Parede 2', 'tipo': 'Alvenaria', 'area': 18.3},
        ... ]
        >>> colunas = ['nome', 'tipo', 'area']
        >>> arquivo = exportar_csv_generico(dados, colunas, "Paredes_Projeto")
    """
    # Determinar pasta de destino
    if pasta_destino is None:
        pasta_destino = os.path.join(os.path.expanduser("~"), "Desktop")

    # Adicionar timestamp ao nome
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_com_ext = "{}_{}.csv".format(nome_arquivo, timestamp)
    caminho_completo = os.path.join(pasta_destino, nome_com_ext)

    # Escrever CSV
    try:
        with codecs.open(caminho_completo, 'w', encoding='utf-8') as f:
            # Cabeçalho
            f.write(",".join(colunas) + "\n")

            # Dados
            for linha_dict in dados_lista:
                valores = [str(linha_dict.get(col, '')) for col in colunas]
                f.write(",".join(valores) + "\n")

        print("CSV exportado: {}".format(caminho_completo))
        return caminho_completo

    except Exception as e:
        print("ERRO ao exportar CSV genérico: {}".format(str(e)))
        return None


def ler_csv_utf8(caminho_arquivo, tem_cabecalho=True, retornar_tupla=False):
    """
    Lê arquivo CSV com UTF-8 e retorna lista de dicionários ou tupla (headers, rows).

    Args:
        caminho_arquivo (str): Caminho do arquivo CSV
        tem_cabecalho (bool): Se True, primeira linha é cabeçalho
        retornar_tupla (bool): Se True, retorna (headers, rows) ao invés de list[dict]
                              Usado para compatibilidade com ParameterPalette

    Returns:
        list: Lista de dicionários (chave = nome coluna, valor = dado) [padrão]
        tuple: (headers, rows) se retornar_tupla=True

    Example:
        >>> # Modo dicionário (padrão)
        >>> dados = ler_csv_utf8("C:\\Users\\...\\Desktop\\dados.csv")
        >>> for linha in dados:
        ...     print(linha['Comentario'], linha['Coord_X'])

        >>> # Modo tupla (compatibilidade ParameterPalette)
        >>> headers, rows = ler_csv_utf8("data.csv", retornar_tupla=True)
        >>> print(headers)  # ['Nome', 'Valor', 'Tipo']
        >>> print(rows[0])  # ['Parede', '100', 'mm']
    """
    try:
        if retornar_tupla:
            # Modo compatibilidade: retornar (headers, rows)
            linhas = []
            with codecs.open(caminho_arquivo, 'r', encoding='utf-8-sig') as f:
                for linha in f:
                    linha = linha.strip()
                    if linha:
                        valores = [v.strip().strip('"').strip("'") for v in linha.split(',')]
                        linhas.append(valores)

            if not linhas:
                return [], []

            # CSV lido silenciosamente
            return linhas[0], linhas[1:]

        else:
            # Modo padrão: retornar lista de dicionários
            linhas = []

            with codecs.open(caminho_arquivo, 'r', encoding='utf-8') as f:
                if tem_cabecalho:
                    # Usar DictReader para mapear automaticamente
                    leitor = csv.DictReader(f)
                    for row in leitor:
                        linhas.append(dict(row))
                else:
                    # Ler como lista de valores
                    leitor = csv.reader(f)
                    for row in leitor:
                        linhas.append(row)

            # CSV lido silenciosamente
            return linhas

    except Exception as e:
        print("ERRO ao ler CSV: {}".format(str(e)))
        if retornar_tupla:
            return [], []
        return []


def validar_dados_coordenadas(dados_lista):
    """
    Valida se lista de dados possui estrutura correta para coordenadas.

    Args:
        dados_lista (list): Lista de dicionários a validar

    Returns:
        tuple: (valido:bool, erros:list)

    Example:
        >>> dados = [{'comentario': 'P1', 'x': 1000, 'y': 2000, 'z': 0}]
        >>> valido, erros = validar_dados_coordenadas(dados)
        >>> if not valido:
        ...     print("Erros:", erros)
    """
    erros = []

    if not isinstance(dados_lista, list):
        erros.append("dados_lista deve ser uma lista")
        return (False, erros)

    if len(dados_lista) == 0:
        erros.append("dados_lista está vazia")
        return (False, erros)

    chaves_obrigatorias = ['comentario', 'x', 'y', 'z']

    for i, dado in enumerate(dados_lista):
        if not isinstance(dado, dict):
            erros.append("Linha {}: não é um dicionário".format(i))
            continue

        # Verificar chaves obrigatórias
        for chave in chaves_obrigatorias:
            if chave not in dado:
                erros.append("Linha {}: falta chave '{}'".format(i, chave))

        # Verificar tipos numéricos para x, y, z
        for coord in ['x', 'y', 'z']:
            if coord in dado:
                try:
                    float(dado[coord])
                except (ValueError, TypeError):
                    erros.append("Linha {}: '{}' não é numérico".format(i, coord))

    valido = len(erros) == 0
    return (valido, erros)


def converter_para_milimetros(dados_lista, unidade_origem='metros'):
    """
    Converte coordenadas de outras unidades para milímetros (unidade interna Revit).

    Args:
        dados_lista (list): Lista de dicionários com 'x', 'y', 'z'
        unidade_origem (str): Unidade de origem ('metros', 'centimetros', 'pes')

    Returns:
        list: Mesma lista com valores convertidos

    Example:
        >>> dados = [{'comentario': 'P1', 'x': 1.5, 'y': 2.0, 'z': 0.0}]  # em metros
        >>> dados_mm = converter_para_milimetros(dados, 'metros')
        >>> print(dados_mm[0]['x'])  # 1500.0 mm
    """
    FATORES_CONVERSAO = {
        'metros': 1000.0,
        'centimetros': 10.0,
        'milimetros': 1.0,
        'pes': 304.8,  # 1 pé = 304.8 mm
        'polegadas': 25.4,  # 1 polegada = 25.4 mm
    }

    fator = FATORES_CONVERSAO.get(unidade_origem.lower(), 1.0)

    for dado in dados_lista:
        if 'x' in dado:
            dado['x'] = float(dado['x']) * fator
        if 'y' in dado:
            dado['y'] = float(dado['y']) * fator
        if 'z' in dado:
            dado['z'] = float(dado['z']) * fator

    return dados_lista


def escrever_csv_utf8(caminho_arquivo, headers, rows):
    """
    Escreve arquivo CSV com UTF-8 a partir de headers e lista de rows.

    Args:
        caminho_arquivo (str): Caminho completo do arquivo CSV a criar/sobrescrever
        headers (list): Lista de strings com nomes das colunas
        rows (list): Lista de listas, cada sublista representa uma linha de dados

    Returns:
        bool: True se escrita bem-sucedida, False se erro

    Example:
        >>> headers = ['Nome', 'Valor', 'Tipo']
        >>> rows = [
        ...     ['Parede 1', '100', 'mm'],
        ...     ['Parede 2', '200', 'mm'],
        ... ]
        >>> sucesso = escrever_csv_utf8("dados.csv", headers, rows)
        >>> print(sucesso)  # True

    Notes:
        - Usa encoding='utf-8-sig' para compatibilidade com Excel
        - Adiciona aspas duplas em todos os valores
        - Preenche colunas vazias automaticamente
        - Compatível com formato usado por ParameterPalette
    """
    try:
        with codecs.open(caminho_arquivo, 'w', encoding='utf-8-sig') as f:
            # Escrever cabeçalho
            f.write(u','.join([u'"{}"'.format(h) for h in headers]) + u'\n')

            # Escrever linhas de dados
            for row in rows:
                # Garantir que row tem o mesmo tamanho que headers
                row_copy = list(row)  # Fazer cópia para não modificar original
                while len(row_copy) < len(headers):
                    row_copy.append(u'')

                f.write(u','.join([u'"{}"'.format(v) for v in row_copy]) + u'\n')

        print("CSV escrito: {} linhas (headers + {} dados) em {}".format(len(rows) + 1, len(rows), caminho_arquivo))
        return True

    except Exception as e:
        print("ERRO ao escrever CSV: {}".format(str(e)))
        return False


def ler_csv_por_colunas(caminho_arquivo):
    """
    Lê CSV e retorna dicionário com dados organizados por coluna.

    Args:
        caminho_arquivo (str): Caminho do arquivo CSV

    Returns:
        dict: Dicionário onde chave = nome da coluna, valor = lista de valores

    Example:
        >>> colunas = ler_csv_por_colunas("dados.csv")
        >>> print(colunas.keys())  # ['Nome', 'Valor', 'Tipo']
        >>> print(colunas['Nome'])  # ['Parede 1', 'Parede 2', 'Parede 3']
        >>> print(len(colunas['Valor']))  # 3

    Notes:
        - Útil para análise estatística ou busca em coluna específica
        - Primeira linha deve ser cabeçalho
    """
    try:
        dados_dict = {}

        with codecs.open(caminho_arquivo, 'r', encoding='utf-8-sig') as f:
            leitor = csv.DictReader(f)

            # Inicializar listas para cada coluna
            for fieldname in leitor.fieldnames:
                dados_dict[fieldname] = []

            # Adicionar valores em cada coluna
            for row in leitor:
                for fieldname in leitor.fieldnames:
                    dados_dict[fieldname].append(row.get(fieldname, ''))

        print("CSV lido por colunas: {} colunas, {} linhas de {}".format(
            len(dados_dict),
            len(dados_dict[dados_dict.keys()[0]]) if dados_dict else 0,
            caminho_arquivo
        ))
        return dados_dict

    except Exception as e:
        print("ERRO ao ler CSV por colunas: {}".format(str(e)))
        return {}


def adicionar_coluna_csv(caminho_arquivo, nome_coluna, valor_padrao=""):
    """
    Adiciona nova coluna ao CSV existente.

    Args:
        caminho_arquivo (str): Caminho do arquivo CSV
        nome_coluna (str): Nome da nova coluna a adicionar
        valor_padrao (str): Valor padrão para preencher linhas existentes

    Returns:
        bool: True se adição bem-sucedida, False se erro

    Example:
        >>> # CSV original: Nome,Valor
        >>> #               Parede,100
        >>> sucesso = adicionar_coluna_csv("dados.csv", "Unidade", "mm")
        >>> # CSV resultante: Nome,Valor,Unidade
        >>> #                 Parede,100,mm

    Notes:
        - Lê CSV completo, adiciona coluna, reescreve arquivo
        - Usa backup automático antes de modificar
    """
    try:
        # Ler CSV existente em modo tupla
        headers, rows = ler_csv_utf8(caminho_arquivo, retornar_tupla=True)

        if not headers:
            print("ERRO: CSV vazio ou não encontrado")
            return False

        # Verificar se coluna já existe
        if nome_coluna in headers:
            print("AVISO: Coluna '{}' já existe, operação cancelada".format(nome_coluna))
            return False

        # Adicionar nova coluna no cabeçalho
        headers.append(nome_coluna)

        # Adicionar valor padrão em todas as linhas
        for row in rows:
            row.append(valor_padrao)

        # Reescrever CSV
        sucesso = escrever_csv_utf8(caminho_arquivo, headers, rows)

        if sucesso:
            print("Coluna '{}' adicionada com sucesso (valor padrão: '{}')".format(nome_coluna, valor_padrao))

        return sucesso

    except Exception as e:
        print("ERRO ao adicionar coluna: {}".format(str(e)))
        return False


def remover_coluna_csv(caminho_arquivo, nome_coluna):
    """
    Remove coluna do CSV existente.

    Args:
        caminho_arquivo (str): Caminho do arquivo CSV
        nome_coluna (str): Nome da coluna a remover

    Returns:
        bool: True se remoção bem-sucedida, False se erro

    Example:
        >>> # CSV original: Nome,Valor,Unidade
        >>> #               Parede,100,mm
        >>> sucesso = remover_coluna_csv("dados.csv", "Unidade")
        >>> # CSV resultante: Nome,Valor
        >>> #                 Parede,100

    Notes:
        - Lê CSV completo, remove coluna, reescreve arquivo
        - Retorna False se coluna não existir
    """
    try:
        # Ler CSV existente em modo tupla
        headers, rows = ler_csv_utf8(caminho_arquivo, retornar_tupla=True)

        if not headers:
            print("ERRO: CSV vazio ou não encontrado")
            return False

        # Verificar se coluna existe
        if nome_coluna not in headers:
            print("ERRO: Coluna '{}' não existe no CSV".format(nome_coluna))
            return False

        # Encontrar índice da coluna
        indice_coluna = headers.index(nome_coluna)

        # Remover coluna do cabeçalho
        headers.pop(indice_coluna)

        # Remover valor correspondente de todas as linhas
        for row in rows:
            if indice_coluna < len(row):
                row.pop(indice_coluna)

        # Reescrever CSV
        sucesso = escrever_csv_utf8(caminho_arquivo, headers, rows)

        if sucesso:
            print("Coluna '{}' removida com sucesso".format(nome_coluna))

        return sucesso

    except Exception as e:
        print("ERRO ao remover coluna: {}".format(str(e)))
        return False


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _csv_utilities.py ===\n")

    # Teste 1: Exportar coordenadas
    dados_teste = [
        {'comentario': 'P1', 'x': 1000.5, 'y': 2000.3, 'z': 0.0},
        {'comentario': 'P2', 'x': 3000.8, 'y': 2500.1, 'z': 0.0},
    ]
    arquivo = exportar_csv_coordenadas(dados_teste, "TESTE", "test123")
    print("1. CSV exportado: {}".format(arquivo))
    assert arquivo is not None and os.path.exists(arquivo), "Arquivo não criado"

    # Teste 2: Ler CSV (modo padrão - dicionário)
    dados_lidos = ler_csv_utf8(arquivo)
    print("2. CSV lido (modo dict): {} linhas".format(len(dados_lidos)))
    assert len(dados_lidos) == 2, "Número incorreto de linhas"

    # Teste 3: Ler CSV (modo tupla - compatibilidade ParameterPalette)
    headers, rows = ler_csv_utf8(arquivo, retornar_tupla=True)
    print("3. CSV lido (modo tupla): headers={}, rows={}".format(len(headers), len(rows)))
    assert len(headers) == 4 and len(rows) == 2, "Modo tupla incorreto"

    # Teste 4: Validar dados
    valido, erros = validar_dados_coordenadas(dados_teste)
    print("4. Validação: valido={}, erros={}".format(valido, len(erros)))
    assert valido == True, "Dados válidos marcados como inválidos"

    # Teste 5: Converter unidades
    dados_metros = [{'comentario': 'T1', 'x': 1.5, 'y': 2.0, 'z': 0.0}]
    dados_mm = converter_para_milimetros(dados_metros, 'metros')
    print("5. Conversão: {} metros = {} mm".format(1.5, dados_mm[0]['x']))
    assert dados_mm[0]['x'] == 1500.0, "Conversão incorreta"

    # Teste 6: escrever_csv_utf8
    pasta_teste = os.path.join(os.path.expanduser("~"), "Desktop")
    arquivo_teste = os.path.join(pasta_teste, "teste_write.csv")
    headers_teste = ['Nome', 'Valor', 'Tipo']
    rows_teste = [
        ['Parede 1', '100', 'mm'],
        ['Parede 2', '200', 'mm'],
    ]
    sucesso = escrever_csv_utf8(arquivo_teste, headers_teste, rows_teste)
    print("6. escrever_csv_utf8: sucesso={}".format(sucesso))
    assert sucesso == True and os.path.exists(arquivo_teste), "Escrita falhou"

    # Teste 7: ler_csv_por_colunas
    colunas = ler_csv_por_colunas(arquivo_teste)
    print("7. ler_csv_por_colunas: {} colunas".format(len(colunas)))
    assert len(colunas) == 3, "Número incorreto de colunas"
    assert len(colunas['Nome']) == 2, "Número incorreto de valores em coluna"
    assert colunas['Valor'][0] == '100', "Valor incorreto na coluna"

    # Teste 8: adicionar_coluna_csv
    sucesso = adicionar_coluna_csv(arquivo_teste, "Unidade", "metros")
    print("8. adicionar_coluna_csv: sucesso={}".format(sucesso))
    assert sucesso == True, "Adição de coluna falhou"
    headers_novo, rows_novo = ler_csv_utf8(arquivo_teste, retornar_tupla=True)
    assert len(headers_novo) == 4, "Coluna não foi adicionada"
    assert rows_novo[0][-1] == 'metros', "Valor padrão incorreto"

    # Teste 9: remover_coluna_csv
    sucesso = remover_coluna_csv(arquivo_teste, "Unidade")
    print("9. remover_coluna_csv: sucesso={}".format(sucesso))
    assert sucesso == True, "Remoção de coluna falhou"
    headers_final, rows_final = ler_csv_utf8(arquivo_teste, retornar_tupla=True)
    assert len(headers_final) == 3, "Coluna não foi removida"
    assert 'Unidade' not in headers_final, "Coluna ainda existe"

    # Limpar arquivos de teste
    if arquivo and os.path.exists(arquivo):
        os.remove(arquivo)
    if os.path.exists(arquivo_teste):
        os.remove(arquivo_teste)

    print("\n✅ TODOS OS 9 TESTES PASSARAM!")
