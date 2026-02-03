# -*- coding: utf-8 -*-
"""
_csv_templates.py
Sistema de gerenciamento de templates CSV para parâmetros de elementos.

USAGE:
    from Snippets.data._csv_templates import (
        load_templates,
        save_template,
        delete_template,
        apply_template,
        get_templates_csv_path
    )
    from Snippets.project._dat_folder_manager import get_dat_folder

    # Carregar templates
    templates = load_templates(doc, script_path)
    for template in templates:
        print(template['name'])  # Nome do template
        print(template['data'])  # Dict com {param_name: value}

    # Salvar template
    param_values = {'Comentarios': 'Pilar', 'Mark': 'P-01'}
    sucesso, msg = save_template(doc, "Template Pilares", param_values)

    # Aplicar template em elemento
    template = templates[0]
    sucesso = apply_template(element, template['data'], doc)

    # Deletar template
    sucesso = delete_template(doc, "Template Pilares")

DEPENDENCIES:
    - codecs, os
    - Snippets.data._csv_utilities (ler_csv_utf8, escrever_csv_utf8)
    - Snippets.project._dat_folder_manager (get_dat_folder)

AUTHOR: Thiago Barreto
VERSION: 1.0 (Extraído de ParameterPalette em ITERATION 2 - 29/11/2025)
NOTES:
    - 100% compatível com formato CSV do ParameterPalette v2.3.1
    - Busca templates em: 1) DAT/templates.csv, 2) script/templates.csv
    - Salva templates sempre em DAT/templates.csv
    - Formato CSV: Template,Param1,Param2,Param3...
                    Nome1,Valor1,Valor2,Valor3...
"""

import codecs
import os

# Imports condicionais (não falhar se não houver outros snippets)
try:
    from Snippets.data._csv_utilities import ler_csv_utf8, escrever_csv_utf8
except ImportError:
    # Fallback para funções básicas se snippet não existir
    def ler_csv_utf8(caminho, retornar_tupla=False):
        linhas = []
        with codecs.open(caminho, 'r', encoding='utf-8-sig') as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    valores = [v.strip().strip('"').strip("'") for v in linha.split(',')]
                    linhas.append(valores)
        if not linhas:
            return [], []
        return linhas[0], linhas[1:] if retornar_tupla else linhas

    def escrever_csv_utf8(caminho, headers, rows):
        with codecs.open(caminho, 'w', encoding='utf-8-sig') as f:
            f.write(u','.join([u'"{}"'.format(h) for h in headers]) + u'\n')
            for row in rows:
                row_copy = list(row)
                while len(row_copy) < len(headers):
                    row_copy.append(u'')
                f.write(u','.join([u'"{}"'.format(v) for v in row_copy]) + u'\n')
        return True

try:
    from Snippets.project._dat_folder_manager import get_dat_folder
except ImportError:
    # Fallback se snippet não existir
    def get_dat_folder(doc, subfolder=None, create=True):
        if doc and doc.PathName:
            project_folder = os.path.dirname(doc.PathName)
            dat_folder = os.path.join(project_folder, "DAT")
            if subfolder:
                dat_folder = os.path.join(dat_folder, subfolder)
            if create and not os.path.exists(dat_folder):
                os.makedirs(dat_folder)
            return dat_folder
        return None


def get_templates_csv_path(doc, script_path=None, prefer_dat=True):
    """
    Retorna caminho do templates.csv com busca em múltiplas localizações.

    Args:
        doc: Documento Revit ativo (Document)
        script_path (str): Caminho do script (opcional, usar __file__ ou PATH_SCRIPT)
        prefer_dat (bool): Se True, prefere DAT/templates.csv sobre script/templates.csv

    Returns:
        tuple: (caminho_completo, fonte) onde fonte é "DAT", "script" ou None

    Example:
        >>> templates_path, fonte = get_templates_csv_path(doc, PATH_SCRIPT)
        >>> if templates_path:
        ...     print("Templates encontrados em:", fonte)

    Notes:
        - Ordem de busca se prefer_dat=True:
          1) [ProjectFolder]/DAT/templates.csv
          2) [ScriptFolder]/templates.csv
        - Retorna (None, None) se não encontrar em nenhum local
    """
    # Buscar em DAT primeiro (se preferir)
    if prefer_dat and doc:
        try:
            dat_folder = get_dat_folder(doc, subfolder=None, create=False)
            if dat_folder:
                dat_templates = os.path.join(dat_folder, 'templates.csv')
                if os.path.exists(dat_templates):
                    return dat_templates, "DAT"
        except:
            pass

    # Buscar na raiz do script
    if script_path:
        root_templates = os.path.join(script_path, 'templates.csv')
        if os.path.exists(root_templates):
            return root_templates, "script"

    # Buscar em DAT como fallback (se não preferiu antes)
    if not prefer_dat and doc:
        try:
            dat_folder = get_dat_folder(doc, subfolder=None, create=False)
            if dat_folder:
                dat_templates = os.path.join(dat_folder, 'templates.csv')
                if os.path.exists(dat_templates):
                    return dat_templates, "DAT"
        except:
            pass

    return None, None


def load_templates(doc, script_path=None):
    """
    Carrega templates do CSV.

    Args:
        doc: Documento Revit ativo
        script_path (str): Caminho do script (opcional)

    Returns:
        list: Lista de dicionários [{'name': str, 'data': {param: value}}]

    Example:
        >>> templates = load_templates(doc, PATH_SCRIPT)
        >>> for template in templates:
        ...     print("Nome:", template['name'])
        ...     print("Params:", template['data'])
        >>> # Saída:
        >>> # Nome: Template Pilares
        >>> # Params: {'Comentarios': 'Pilar', 'Mark': 'P-01'}

    Notes:
        - Retorna lista vazia se templates.csv não existir
        - Ignora linhas vazias
        - Primeira coluna = nome do template
        - Demais colunas = valores de parâmetros
    """
    templates_path, source = get_templates_csv_path(doc, script_path)

    if not templates_path:
        print("Nenhum arquivo templates.csv encontrado")
        return []

    try:
        headers, rows = ler_csv_utf8(templates_path, retornar_tupla=True)

        templates = []

        for row in rows:
            if row and row[0].strip():  # Ignorar linhas vazias
                template_name = row[0].strip()
                template_data = {}

                # Mapear valores para nomes de parâmetros (headers[1:])
                for i, param_name in enumerate(headers[1:], start=1):
                    if i < len(row):
                        template_data[param_name] = row[i].strip()
                    else:
                        template_data[param_name] = u''

                templates.append({
                    'name': template_name,
                    'data': template_data
                })

        # Templates carregados silenciosamente
        return templates

    except Exception as e:
        print("ERRO ao carregar templates: {}".format(str(e)))
        return []


def save_template(doc, template_name, param_values, script_path=None):
    """
    Salva template no CSV (sempre em DAT/templates.csv).

    Args:
        doc: Documento Revit ativo
        template_name (str): Nome do template
        param_values (dict): Dicionário {param_name: value}
        script_path (str): Caminho do script (opcional, para fallback)

    Returns:
        tuple: (sucesso:bool, mensagem:str)

    Example:
        >>> param_values = {
        ...     'Comentarios': 'Pilar Estrutural',
        ...     'Mark': 'P-01',
        ...     'Tipo': 'Concreto'
        ... }
        >>> sucesso, msg = save_template(doc, "Template Pilares", param_values)
        >>> if sucesso:
        ...     print("Template salvo em:", msg)

    Notes:
        - Cria DAT/templates.csv se não existir
        - Atualiza template se já existir com mesmo nome
        - Adiciona novas colunas automaticamente se param_values tiver novos parâmetros
    """
    try:
        # Obter pasta DAT
        dat_folder = get_dat_folder(doc, subfolder=None, create=True)

        if not dat_folder:
            return False, "Pasta DAT não disponível (documento não salvo?)"

        templates_path = os.path.join(dat_folder, 'templates.csv')

        # Ler CSV existente ou criar novo
        if os.path.exists(templates_path):
            headers, rows = ler_csv_utf8(templates_path, retornar_tupla=True)
        else:
            headers = ['Template'] + sorted(param_values.keys())
            rows = []

        # Adicionar novas colunas se param_values tiver parâmetros novos
        for param_name in param_values.keys():
            if param_name not in headers:
                headers.append(param_name)

        # Verificar se template já existe
        existing_row_idx = None
        for idx, row in enumerate(rows):
            if row and row[0] == template_name:
                existing_row_idx = idx
                break

        # Construir nova linha
        new_row = [template_name]
        for param_name in headers[1:]:
            value = param_values.get(param_name, u'')
            new_row.append(value)

        # Atualizar ou adicionar
        if existing_row_idx is not None:
            rows[existing_row_idx] = new_row
            print("Template '{}' atualizado".format(template_name))
        else:
            rows.append(new_row)
            print("Template '{}' criado".format(template_name))

        # Escrever CSV
        sucesso = escrever_csv_utf8(templates_path, headers, rows)

        if sucesso:
            return True, templates_path
        else:
            return False, "Erro ao escrever CSV"

    except Exception as e:
        return False, str(e)


def delete_template(doc, template_name):
    """
    Deleta template do CSV.

    Args:
        doc: Documento Revit ativo
        template_name (str): Nome do template a deletar

    Returns:
        bool: True se deletado, False se erro ou não encontrado

    Example:
        >>> sucesso = delete_template(doc, "Template Pilares")
        >>> if sucesso:
        ...     print("Template deletado com sucesso")
    """
    try:
        dat_folder = get_dat_folder(doc, subfolder=None, create=False)

        if not dat_folder:
            print("Pasta DAT não encontrada")
            return False

        templates_path = os.path.join(dat_folder, 'templates.csv')

        if not os.path.exists(templates_path):
            print("Arquivo templates.csv não encontrado")
            return False

        # Ler CSV
        headers, rows = ler_csv_utf8(templates_path, retornar_tupla=True)

        # Encontrar e remover template
        new_rows = [row for row in rows if not (row and row[0] == template_name)]

        if len(new_rows) == len(rows):
            print("Template '{}' não encontrado".format(template_name))
            return False

        # Reescrever CSV sem o template deletado
        sucesso = escrever_csv_utf8(templates_path, headers, new_rows)

        if sucesso:
            print("Template '{}' deletado".format(template_name))
            return True
        else:
            return False

    except Exception as e:
        print("ERRO ao deletar template: {}".format(str(e)))
        return False


def apply_template(element, template_data, doc):
    """
    Aplica valores de template aos parâmetros de um elemento.

    Args:
        element: Elemento Revit (Element)
        template_data (dict): Dicionário {param_name: value} do template
        doc: Documento Revit (para Transaction)

    Returns:
        dict: {'success_count': int, 'failed_count': int, 'details': list}

    Example:
        >>> from pyrevit import revit, DB
        >>> from pyrevit.revit import ef_Transaction
        >>>
        >>> element = uidoc.Selection.GetElementIds()[0]
        >>> template_data = {'Comentarios': 'Pilar P1', 'Mark': 'P-01'}
        >>>
        >>> with ef_Transaction(doc, "Aplicar Template"):
        ...     resultado = apply_template(element, template_data, doc)
        >>> print("Sucesso:", resultado['success_count'])
        >>> print("Falhas:", resultado['failed_count'])

    Notes:
        - Pula parâmetros que não existem no elemento
        - Pula parâmetros read-only
        - Retorna detalhes de sucesso/falha para cada parâmetro
        - NÃO inicia Transaction (deve ser chamado dentro de uma)
    """
    resultado = {
        'success_count': 0,
        'failed_count': 0,
        'details': []
    }

    for param_name, value in template_data.items():
        if not value:  # Pular valores vazios
            continue

        try:
            param = element.LookupParameter(param_name)

            if not param:
                resultado['details'].append({
                    'param': param_name,
                    'status': 'skipped',
                    'reason': 'parâmetro não existe no elemento'
                })
                continue

            if param.IsReadOnly:
                resultado['details'].append({
                    'param': param_name,
                    'status': 'skipped',
                    'reason': 'parâmetro somente leitura'
                })
                continue

            # Aplicar valor
            param.Set(value)

            resultado['success_count'] += 1
            resultado['details'].append({
                'param': param_name,
                'status': 'success',
                'value': value
            })

        except Exception as e:
            resultado['failed_count'] += 1
            resultado['details'].append({
                'param': param_name,
                'status': 'failed',
                'reason': str(e)
            })

    return resultado


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _csv_templates.py ===\n")

    import tempfile
    import shutil

    # Criar estrutura temporária
    temp_dir = tempfile.mkdtemp()
    script_folder = os.path.join(temp_dir, "script")
    dat_folder = os.path.join(temp_dir, "projeto", "DAT")
    os.makedirs(script_folder)
    os.makedirs(dat_folder)

    print("Pastas temporárias:")
    print("  Script:", script_folder)
    print("  DAT:", dat_folder)

    # Criar mock de documento
    class MockDoc:
        def __init__(self, path):
            self.PathName = path

    mock_doc = MockDoc(os.path.join(temp_dir, "projeto", "projeto.rvt"))

    # Teste 1: save_template (criar novo)
    param_values = {
        'Comentarios': 'Pilar Estrutural',
        'Mark': 'P-01',
        'Tipo': 'Concreto'
    }
    sucesso, msg = save_template(mock_doc, "Template Pilares", param_values)
    print("\n1. save_template (novo): sucesso={}, path={}".format(sucesso, msg if sucesso else "erro"))
    assert sucesso == True, "Salvamento falhou"
    templates_path = os.path.join(dat_folder, 'templates.csv')
    assert os.path.exists(templates_path), "Arquivo templates.csv não criado"

    # Teste 2: load_templates
    templates = load_templates(mock_doc, script_folder)
    print("2. load_templates: {} templates carregados".format(len(templates)))
    assert len(templates) == 1, "Número incorreto de templates"
    assert templates[0]['name'] == 'Template Pilares', "Nome incorreto"
    assert templates[0]['data']['Comentarios'] == 'Pilar Estrutural', "Valor incorreto"

    # Teste 3: save_template (atualizar existente)
    param_values_update = {
        'Comentarios': 'Pilar P1',
        'Mark': 'P-01',
        'Tipo': 'Concreto',
        'Altura': '3000'  # Nova coluna
    }
    sucesso, msg = save_template(mock_doc, "Template Pilares", param_values_update)
    print("3. save_template (atualizar): sucesso={}".format(sucesso))
    assert sucesso == True, "Atualização falhou"

    # Teste 4: Verificar atualização e nova coluna
    templates = load_templates(mock_doc, script_folder)
    print("4. Verificar atualização: {} params".format(len(templates[0]['data'])))
    assert len(templates) == 1, "Template duplicado ao invés de atualizado"
    assert templates[0]['data']['Comentarios'] == 'Pilar P1', "Valor não atualizado"
    assert 'Altura' in templates[0]['data'], "Nova coluna não adicionada"
    assert templates[0]['data']['Altura'] == '3000', "Valor da nova coluna incorreto"

    # Teste 5: Adicionar segundo template
    param_values_2 = {
        'Comentarios': 'Viga Principal',
        'Mark': 'V-01'
    }
    sucesso, msg = save_template(mock_doc, "Template Vigas", param_values_2)
    templates = load_templates(mock_doc, script_folder)
    print("5. Adicionar segundo template: {} templates".format(len(templates)))
    assert len(templates) == 2, "Segundo template não adicionado"

    # Teste 6: delete_template
    sucesso = delete_template(mock_doc, "Template Vigas")
    print("6. delete_template: sucesso={}".format(sucesso))
    assert sucesso == True, "Deleção falhou"
    templates = load_templates(mock_doc, script_folder)
    assert len(templates) == 1, "Template não foi deletado"
    assert templates[0]['name'] == 'Template Pilares', "Template errado foi deletado"

    # Teste 7: get_templates_csv_path com múltiplas localizações
    # Criar templates.csv na raiz do script também
    script_templates = os.path.join(script_folder, 'templates.csv')
    headers = ['Template', 'Comentarios']
    rows = [['Script Template', 'Da raiz do script']]
    escrever_csv_utf8(script_templates, headers, rows)

    path, fonte = get_templates_csv_path(mock_doc, script_folder, prefer_dat=True)
    print("7. get_templates_csv_path (prefer_dat=True): fonte={}".format(fonte))
    assert fonte == "DAT", "Deveria preferir DAT"

    path, fonte = get_templates_csv_path(mock_doc, script_folder, prefer_dat=False)
    print("8. get_templates_csv_path (prefer_dat=False): fonte={}".format(fonte))
    assert fonte == "script", "Deveria preferir script quando prefer_dat=False"

    # Limpar
    shutil.rmtree(temp_dir)

    print("\n✅ TODOS OS 8 TESTES PASSARAM!")
    print("\nNOTA: Função apply_template() requer ambiente Revit com Element e Transaction")
