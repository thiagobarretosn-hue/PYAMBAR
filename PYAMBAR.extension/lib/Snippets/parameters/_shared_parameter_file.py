# -*- coding: utf-8 -*-
"""
_shared_parameter_file.py
Funções para criação e gerenciamento de arquivos de parâmetros compartilhados.

USAGE:
    from Snippets.parameters._shared_parameter_file import criar_arquivo_parametros_temporario
    from Snippets.parameters._shared_parameter_file import adicionar_parametro_ao_arquivo

    # Criar arquivo temporário
    param_file = criar_arquivo_parametros_temporario("MeuScript")

    # Adicionar parâmetros
    adicionar_parametro_ao_arquivo(param_file, "Coord_X", "NUMBER", "GEOMETRY")
    adicionar_parametro_ao_arquivo(param_file, "Coord_Y", "NUMBER", "GEOMETRY")

    # Usar no Revit
    app.SharedParametersFilename = param_file

DEPENDENCIES:
    - Snippets.core._revit_version_helpers (obter_tipo_parametro, obter_parameter_group)
    - tempfile, codecs, os, datetime, uuid

AUTHOR: Thiago Barreto
VERSION: 1.0
"""

import codecs
import os
import tempfile
from datetime import datetime
import uuid

from Snippets.core._revit_version_helpers import obter_tipo_parametro, obter_parameter_group


def criar_arquivo_parametros_temporario(nome_script="PyRevit"):
    """
    Cria arquivo temporário de parâmetros compartilhados com formato Revit.

    Args:
        nome_script (str): Nome do script para identificação no nome do arquivo

    Returns:
        str: Caminho completo do arquivo temporário criado

    Example:
        >>> param_file = criar_arquivo_parametros_temporario("CoordenadasXYZ")
        >>> print(param_file)
        'C:\\Users\\...\\Temp\\CoordRevit_CoordenadasXYZ_20251127143025.txt'
    """
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nome_arquivo = "CoordRevit_{}_{}.txt".format(nome_script, timestamp)
    param_file = os.path.join(temp_dir, nome_arquivo)

    # Criar arquivo com cabeçalho padrão Revit
    with codecs.open(param_file, 'w', encoding='utf-8') as f:
        f.write("# This is a Revit shared parameter file.\n")
        f.write("# Do not edit manually when editing in Revit\n")
        f.write("*META\tVERSION\tMINVERSION\n")
        f.write("META\t2\t1\n")
        f.write("*GROUP\tID\tNAME\n")
        f.write("GROUP\t1\tParametros Customizados\n")
        f.write("*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION\tUSERMODIFIABLE\n")

    return param_file


def adicionar_parametro_ao_arquivo(arquivo_parametros, nome_param, tipo='TEXT', grupo='GENERAL',
                                   visivel=True, descricao='', modificavel=True):
    """
    Adiciona definição de parâmetro ao arquivo de parâmetros compartilhados.

    Args:
        arquivo_parametros (str): Caminho do arquivo de parâmetros
        nome_param (str): Nome do parâmetro a criar
        tipo (str): Tipo do parâmetro ('TEXT', 'NUMBER', 'LENGTH', 'AREA', 'VOLUME', 'YESNO', etc.)
        grupo (str): Grupo do parâmetro ('GEOMETRY', 'IDENTITY_DATA', 'CONSTRAINTS', etc.)
        visivel (bool): Se parâmetro é visível na UI
        descricao (str): Descrição do parâmetro
        modificavel (bool): Se usuário pode modificar o valor

    Returns:
        bool: True se adicionado com sucesso

    Example:
        >>> arquivo = criar_arquivo_parametros_temporario("Teste")
        >>> adicionar_parametro_ao_arquivo(arquivo, "Coord_X", "NUMBER", "GEOMETRY")
        >>> adicionar_parametro_ao_arquivo(arquivo, "Observacao", "TEXT", "DATA")
    """
    try:
        # Gerar GUID único para o parâmetro
        param_guid = str(uuid.uuid4())

        # Mapear tipo e grupo (validação)
        tipo_validado = tipo.upper()
        grupo_validado = grupo.upper()

        # Determinar DATATYPE e DATACATEGORY baseado no tipo
        # Para Revit 2024+, usar nomes modernos
        DATATYPE_MAP = {
            'TEXT': 'TEXT',
            'NUMBER': 'NUMBER',
            'INTEGER': 'INTEGER',
            'LENGTH': 'LENGTH',
            'AREA': 'AREA',
            'VOLUME': 'VOLUME',
            'ANGLE': 'ANGLE',
            'YESNO': 'YESNO',
            'URL': 'URL',
        }

        datatype = DATATYPE_MAP.get(tipo_validado, 'TEXT')
        datacategory = ''  # Vazio para parâmetros gerais

        # Formatar linha de parâmetro
        visivel_str = '1' if visivel else '0'
        modificavel_str = '1' if modificavel else '0'

        linha_param = "PARAM\t{}\t{}\t{}\t{}\t1\t{}\t{}\t{}\n".format(
            param_guid,
            nome_param,
            datatype,
            datacategory,
            visivel_str,
            descricao,
            modificavel_str
        )

        # Adicionar ao arquivo
        with codecs.open(arquivo_parametros, 'a', encoding='utf-8') as f:
            f.write(linha_param)

        return True

    except Exception as e:
        print("ERRO ao adicionar parâmetro '{}': {}".format(nome_param, str(e)))
        return False


def adicionar_multiplos_parametros(arquivo_parametros, parametros_lista):
    """
    Adiciona múltiplos parâmetros de uma vez ao arquivo.

    Args:
        arquivo_parametros (str): Caminho do arquivo de parâmetros
        parametros_lista (list): Lista de dicionários com definições de parâmetros
            Cada dicionário deve ter: {'nome': str, 'tipo': str, 'grupo': str, ...}

    Returns:
        tuple: (sucesso_count, falha_count)

    Example:
        >>> arquivo = criar_arquivo_parametros_temporario("Coordenadas")
        >>> params = [
        ...     {'nome': 'Coord_X', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        ...     {'nome': 'Coord_Y', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        ...     {'nome': 'Coord_Z', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        ... ]
        >>> sucesso, falha = adicionar_multiplos_parametros(arquivo, params)
        >>> print("Adicionados: {}, Falhas: {}".format(sucesso, falha))
        Adicionados: 3, Falhas: 0
    """
    sucesso = 0
    falha = 0

    for param_def in parametros_lista:
        nome = param_def.get('nome', '')
        tipo = param_def.get('tipo', 'TEXT')
        grupo = param_def.get('grupo', 'GENERAL')
        visivel = param_def.get('visivel', True)
        descricao = param_def.get('descricao', '')
        modificavel = param_def.get('modificavel', True)

        if not nome:
            print("AVISO: Parâmetro sem nome ignorado")
            falha += 1
            continue

        resultado = adicionar_parametro_ao_arquivo(
            arquivo_parametros, nome, tipo, grupo, visivel, descricao, modificavel
        )

        if resultado:
            sucesso += 1
        else:
            falha += 1

    return (sucesso, falha)


def criar_arquivo_com_parametros(nome_script, parametros_lista):
    """
    Cria arquivo temporário e adiciona todos os parâmetros de uma vez.
    Função de conveniência que combina criação + adição.

    Args:
        nome_script (str): Nome do script
        parametros_lista (list): Lista de definições de parâmetros

    Returns:
        str: Caminho do arquivo criado (ou None se erro)

    Example:
        >>> params = [
        ...     {'nome': 'Coord_X', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        ...     {'nome': 'Coord_Y', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        ... ]
        >>> arquivo = criar_arquivo_com_parametros("CoordXYZ", params)
        >>> print("Arquivo criado: {}".format(arquivo))
    """
    try:
        # Criar arquivo
        arquivo = criar_arquivo_parametros_temporario(nome_script)

        # Adicionar parâmetros
        sucesso, falha = adicionar_multiplos_parametros(arquivo, parametros_lista)

        print("Arquivo criado: {}".format(arquivo))
        print("Parâmetros adicionados: {} | Falhas: {}".format(sucesso, falha))

        return arquivo

    except Exception as e:
        print("ERRO ao criar arquivo com parâmetros: {}".format(str(e)))
        return None


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _shared_parameter_file.py ===\n")

    # Teste 1: Criar arquivo temporário
    arquivo = criar_arquivo_parametros_temporario("TESTE")
    print("1. Arquivo criado: {}".format(arquivo))
    assert os.path.exists(arquivo), "Arquivo não foi criado"

    # Teste 2: Adicionar parâmetro único
    resultado = adicionar_parametro_ao_arquivo(arquivo, "Teste_Param", "TEXT", "GENERAL")
    print("2. Parâmetro adicionado: {}".format(resultado))
    assert resultado == True, "Falha ao adicionar parâmetro"

    # Teste 3: Adicionar múltiplos parâmetros
    params = [
        {'nome': 'Coord_X', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        {'nome': 'Coord_Y', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
        {'nome': 'Coord_Z', 'tipo': 'NUMBER', 'grupo': 'GEOMETRY'},
    ]
    sucesso, falha = adicionar_multiplos_parametros(arquivo, params)
    print("3. Múltiplos parâmetros: Sucesso={}, Falha={}".format(sucesso, falha))
    assert sucesso == 3 and falha == 0, "Erro ao adicionar múltiplos"

    # Teste 4: Ler arquivo criado
    with codecs.open(arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    print("4. Conteúdo do arquivo ({} caracteres)".format(len(conteudo)))
    assert 'Coord_X' in conteudo, "Parâmetro não encontrado no arquivo"

    # Limpar arquivo de teste
    os.remove(arquivo)
    print("\n✅ TODOS OS TESTES PASSARAM!")
