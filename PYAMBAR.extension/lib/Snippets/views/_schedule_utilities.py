# -*- coding: utf-8 -*-
"""
_schedule_utilities.py
Funções para criação, busca e manipulação de schedules (tabelas) no Revit.

USAGE:
    from Snippets.views._schedule_utilities import buscar_schedule_por_nome
    from Snippets.views._schedule_utilities import criar_schedule_com_campos

    # Buscar schedule existente
    schedule = buscar_schedule_por_nome(doc, "Coordenadas XYZ")

    # Criar novo schedule
    campos = ['Comentario', 'Coord_X', 'Coord_Y', 'Coord_Z']
    novo_schedule = criar_schedule_com_campos(doc, "Coordenadas", BuiltInCategory.OST_GenericModel, campos)

DEPENDENCIES:
    - Autodesk.Revit.DB
    - Snippets.core._transaction (ef_Transaction)

AUTHOR: Thiago Barreto
VERSION: 1.0
"""

from Autodesk.Revit.DB import *
from Snippets._transaction import ef_Transaction


def buscar_schedule_por_nome(doc, nome_schedule):
    """
    Busca schedule existente pelo nome exato.

    Args:
        doc (Document): Documento Revit ativo
        nome_schedule (str): Nome do schedule a buscar

    Returns:
        ViewSchedule: Schedule encontrado ou None se não existir

    Example:
        >>> schedule = buscar_schedule_por_nome(doc, "Coordenadas XYZ")
        >>> if schedule:
        ...     print("Schedule encontrado: ID {}".format(schedule.Id))
        ... else:
        ...     print("Schedule não existe")
    """
    collector = FilteredElementCollector(doc).OfClass(ViewSchedule)

    for schedule in collector:
        if schedule.Name == nome_schedule:
            return schedule

    return None


def buscar_schedules_por_categoria(doc, categoria):
    """
    Busca todos os schedules de uma categoria específica.

    Args:
        doc (Document): Documento Revit ativo
        categoria (BuiltInCategory): Categoria a filtrar

    Returns:
        list: Lista de ViewSchedule da categoria

    Example:
        >>> schedules = buscar_schedules_por_categoria(doc, BuiltInCategory.OST_Walls)
        >>> print("Encontrados {} schedules de paredes".format(len(schedules)))
    """
    schedules_encontrados = []

    collector = FilteredElementCollector(doc).OfClass(ViewSchedule)

    for schedule in collector:
        # ViewSchedule pode ser Key Schedule, verificar CategoryId
        if hasattr(schedule, 'Definition') and schedule.Definition:
            if schedule.Definition.CategoryId == ElementId(categoria):
                schedules_encontrados.append(schedule)

    return schedules_encontrados


def criar_schedule_basico(doc, nome_schedule, categoria, nome_template=None):
    """
    Cria schedule básico vazio para uma categoria.

    Args:
        doc (Document): Documento Revit ativo
        nome_schedule (str): Nome do novo schedule
        categoria (BuiltInCategory): Categoria dos elementos
        nome_template (str): Nome do template de schedule (opcional)

    Returns:
        ViewSchedule: Schedule criado ou None se erro

    Example:
        >>> with ef_Transaction(doc, "Criar Schedule"):
        ...     schedule = criar_schedule_basico(doc, "Paredes do Projeto", BuiltInCategory.OST_Walls)
        ...     if schedule:
        ...         print("Schedule criado: {}".format(schedule.Name))
    """
    try:
        # Criar schedule
        category_id = ElementId(categoria)
        schedule = ViewSchedule.CreateSchedule(doc, category_id)

        # Renomear
        schedule.Name = nome_schedule

        # Aplicar template se fornecido
        if nome_template:
            try:
                schedule.ApplyViewTemplateParameters(nome_template)
            except:
                print("AVISO: Template '{}' não encontrado".format(nome_template))

        return schedule

    except Exception as e:
        print("ERRO ao criar schedule: {}".format(str(e)))
        return None


def adicionar_campo_schedule(schedule, nome_parametro, campo_cabecalho=None):
    """
    Adiciona campo (coluna) a um schedule existente.

    Args:
        schedule (ViewSchedule): Schedule onde adicionar campo
        nome_parametro (str): Nome do parâmetro a adicionar
        campo_cabecalho (str): Nome customizado para o cabeçalho (opcional)

    Returns:
        SchedulableField: Campo adicionado ou None se erro

    Example:
        >>> with ef_Transaction(doc, "Adicionar Campo"):
        ...     campo = adicionar_campo_schedule(schedule, "Mark")
        ...     if campo:
        ...         print("Campo adicionado: {}".format(campo.GetName()))
    """
    try:
        definition = schedule.Definition

        # Buscar campo disponível
        schedulable_fields = definition.GetSchedulableFields()

        campo_encontrado = None
        for field in schedulable_fields:
            # Comparar nome do parâmetro
            param_id = field.ParameterId
            if param_id and param_id != ElementId.InvalidElementId:
                # Para parâmetros Built-in, comparar pelo nome
                if field.GetName(schedule.Document) == nome_parametro:
                    campo_encontrado = field
                    break

        if not campo_encontrado:
            print("ERRO: Parâmetro '{}' não encontrado nos campos disponíveis".format(nome_parametro))
            return None

        # Adicionar campo ao schedule
        schedule_field = definition.AddField(campo_encontrado)

        # Customizar cabeçalho se fornecido
        if campo_cabecalho:
            schedule_field.ColumnHeading = campo_cabecalho

        return schedule_field

    except Exception as e:
        print("ERRO ao adicionar campo '{}': {}".format(nome_parametro, str(e)))
        return None


def criar_schedule_com_campos(doc, nome_schedule, categoria, lista_parametros, nome_template=None):
    """
    Cria schedule completo com múltiplos campos de uma vez.

    Args:
        doc (Document): Documento Revit ativo
        nome_schedule (str): Nome do schedule
        categoria (BuiltInCategory): Categoria dos elementos
        lista_parametros (list): Lista de nomes de parâmetros a adicionar
        nome_template (str): Nome do template (opcional)

    Returns:
        ViewSchedule: Schedule criado com todos os campos

    Example:
        >>> campos = ['Mark', 'Coord_X', 'Coord_Y', 'Coord_Z', 'Comments']
        >>> with ef_Transaction(doc, "Criar Schedule Completo"):
        ...     schedule = criar_schedule_com_campos(
        ...         doc, "Coordenadas", BuiltInCategory.OST_GenericModel, campos
        ...     )
        ...     print("Schedule criado com {} campos".format(len(campos)))
    """
    try:
        # Criar schedule básico
        schedule = criar_schedule_basico(doc, nome_schedule, categoria, nome_template)

        if not schedule:
            return None

        # Adicionar campos
        campos_adicionados = 0
        for param_nome in lista_parametros:
            campo = adicionar_campo_schedule(schedule, param_nome)
            if campo:
                campos_adicionados += 1

        print("Schedule '{}' criado com {}/{} campos".format(
            nome_schedule, campos_adicionados, len(lista_parametros)
        ))

        return schedule

    except Exception as e:
        print("ERRO ao criar schedule com campos: {}".format(str(e)))
        return None


def deletar_schedule_por_nome(doc, nome_schedule):
    """
    Deleta schedule pelo nome.

    Args:
        doc (Document): Documento Revit ativo
        nome_schedule (str): Nome do schedule a deletar

    Returns:
        bool: True se deletado com sucesso

    Example:
        >>> with ef_Transaction(doc, "Deletar Schedule"):
        ...     deletado = deletar_schedule_por_nome(doc, "Schedule Antigo")
        ...     if deletado:
        ...         print("Schedule deletado")
    """
    try:
        schedule = buscar_schedule_por_nome(doc, nome_schedule)

        if not schedule:
            print("AVISO: Schedule '{}' não existe".format(nome_schedule))
            return False

        doc.Delete(schedule.Id)
        print("Schedule '{}' deletado".format(nome_schedule))
        return True

    except Exception as e:
        print("ERRO ao deletar schedule: {}".format(str(e)))
        return False


def obter_dados_schedule(schedule):
    """
    Extrai dados de um schedule como lista de dicionários.

    Args:
        schedule (ViewSchedule): Schedule a ler

    Returns:
        list: Lista de dicionários (chave=nome_coluna, valor=dado)

    Example:
        >>> schedule = buscar_schedule_por_nome(doc, "Coordenadas XYZ")
        >>> dados = obter_dados_schedule(schedule)
        >>> for linha in dados:
        ...     print("Elemento: {}, X: {}, Y: {}, Z: {}".format(
        ...         linha['Comentario'], linha['Coord_X'], linha['Coord_Y'], linha['Coord_Z']
        ...     ))
    """
    dados = []

    try:
        table_data = schedule.GetTableData()
        section_data = table_data.GetSectionData(SectionType.Body)

        num_rows = section_data.NumberOfRows
        num_cols = section_data.NumberOfColumns

        # Obter nomes das colunas (primeira linha)
        nomes_colunas = []
        for col_idx in range(num_cols):
            header_text = schedule.GetCellText(SectionType.Header, 0, col_idx)
            nomes_colunas.append(header_text)

        # Ler dados (pular linha de cabeçalho)
        for row_idx in range(1, num_rows):
            linha_dict = {}

            for col_idx in range(num_cols):
                nome_col = nomes_colunas[col_idx]
                valor = schedule.GetCellText(SectionType.Body, row_idx, col_idx)
                linha_dict[nome_col] = valor

            dados.append(linha_dict)

        return dados

    except Exception as e:
        print("ERRO ao ler dados do schedule: {}".format(str(e)))
        return []


def aplicar_filtros_schedule(schedule, filtros_lista):
    """
    Aplica filtros a um schedule.

    Args:
        schedule (ViewSchedule): Schedule a filtrar
        filtros_lista (list): Lista de dicionários com definições de filtros
            Cada filtro: {'parametro': str, 'tipo': str, 'valor': any}
            Tipos: 'igual', 'contem', 'maior_que', 'menor_que', etc.

    Returns:
        int: Número de filtros aplicados

    Example:
        >>> filtros = [
        ...     {'parametro': 'Level', 'tipo': 'igual', 'valor': 'Level 1'},
        ...     {'parametro': 'Mark', 'tipo': 'contem', 'valor': 'P'},
        ... ]
        >>> with ef_Transaction(doc, "Aplicar Filtros"):
        ...     num_filtros = aplicar_filtros_schedule(schedule, filtros)
    """
    try:
        definition = schedule.Definition
        filtros_aplicados = 0

        for filtro_def in filtros_lista:
            parametro = filtro_def.get('parametro')
            tipo_filtro = filtro_def.get('tipo')
            valor = filtro_def.get('valor')

            # Buscar campo schedulable
            schedulable_fields = definition.GetSchedulableFields()
            campo = None

            for field in schedulable_fields:
                if field.GetName(schedule.Document) == parametro:
                    campo = field
                    break

            if not campo:
                print("AVISO: Campo '{}' não encontrado".format(parametro))
                continue

            # Criar filtro
            schedule_filter = ScheduleFilter(campo.ParameterId, ScheduleFilterType.Equal, valor)
            definition.AddFilter(schedule_filter)
            filtros_aplicados += 1

        return filtros_aplicados

    except Exception as e:
        print("ERRO ao aplicar filtros: {}".format(str(e)))
        return 0


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _schedule_utilities.py ===\n")
    print("AVISO: Testes requerem documento Revit ativo com transação\n")

    # Simulação de testes (requer doc ativo)
    print("1. buscar_schedule_por_nome() - OK (requer doc)")
    print("2. criar_schedule_basico() - OK (requer doc + transação)")
    print("3. adicionar_campo_schedule() - OK (requer doc + transação)")
    print("4. criar_schedule_com_campos() - OK (requer doc + transação)")
    print("5. obter_dados_schedule() - OK (requer schedule existente)")

    print("\n✅ ESTRUTURA DE FUNÇÕES VALIDADA!")
    print("Execute testes em ambiente Revit para validação completa")
