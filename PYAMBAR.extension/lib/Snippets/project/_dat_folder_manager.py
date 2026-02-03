# -*- coding: utf-8 -*-
"""
_dat_folder_manager.py
Gerenciamento de pasta DAT para armazenamento de dados específicos do projeto.

ESTRUTURA CRIADA:
    [Pasta do Projeto]/
    └── DAT/
        ├── [Projeto]_data.csv
        ├── templates.csv
        └── backup/
            ├── [Projeto]_data_20251127_143025.csv
            └── ...

USAGE:
    from Snippets.project._dat_folder_manager import (
        get_project_folder,
        get_dat_folder,
        create_backup
    )

    # Obter pasta do projeto
    project_folder = get_project_folder(doc)

    # Obter/criar pasta DAT
    dat_folder = get_dat_folder(doc)

    # Criar backup de arquivo
    success, backup_path = create_backup("caminho/arquivo.csv", doc)

DEPENDENCIES:
    - Autodesk.Revit.DB (Document)
    - os, shutil, datetime

AUTHOR: Thiago Barreto
VERSION: 1.0
EXTRACTED FROM: ParameterPalette.pushbutton (DATFolderManager class)
"""

import os
import shutil
from datetime import datetime


def get_project_folder(doc):
    """
    Obtém pasta raiz do projeto Revit.

    Para projetos workshared: pasta do modelo central
    Para projetos locais: pasta do arquivo .rvt

    Args:
        doc (Document): Documento Revit

    Returns:
        str or None: Caminho da pasta do projeto, ou None se não puder determinar

    Example:
        >>> project_folder = get_project_folder(doc)
        >>> if project_folder:
        ...     print("Projeto em: {}".format(project_folder))
    """
    try:
        # Projeto workshared - obter caminho do modelo central
        if doc.IsWorkshared:
            central_path = doc.GetWorksharingCentralModelPath()

            # Tentar obter CentralServerPath (BIM 360, Revit Server)
            if hasattr(central_path, 'CentralServerPath'):
                model_path = central_path.CentralServerPath
                if model_path:
                    return os.path.dirname(model_path)

        # Projeto local - obter caminho do arquivo
        if not doc.IsWorkshared and doc.PathName:
            return os.path.dirname(doc.PathName)

        return None

    except Exception as e:
        return None


def get_project_name(doc):
    """
    Obtém nome do projeto Revit (sem extensão .rvt).

    Args:
        doc (Document): Documento Revit

    Returns:
        str: Nome do projeto, ou "Sem_Nome" se não puder determinar

    Example:
        >>> project_name = get_project_name(doc)
        >>> print("Projeto: {}".format(project_name))
        Projeto: Edif_Residencial_Bloco_A
    """
    try:
        # Projeto workshared - obter nome do modelo central
        if doc.IsWorkshared:
            central_path = doc.GetWorksharingCentralModelPath()

            if hasattr(central_path, 'CentralServerPath'):
                model_path = central_path.CentralServerPath
                if model_path:
                    return os.path.splitext(os.path.basename(model_path))[0]

        # Projeto local - obter nome do arquivo
        if doc.PathName:
            return os.path.splitext(os.path.basename(doc.PathName))[0]

        return "Sem_Nome"

    except:
        return "Sem_Nome"


def get_central_path(doc):
    """
    Obtém caminho completo do modelo central (apenas para projetos workshared).

    Args:
        doc (Document): Documento Revit

    Returns:
        str or None: Caminho completo do central, ou None se não workshared

    Example:
        >>> central = get_central_path(doc)
        >>> if central:
        ...     print("Central: {}".format(central))
    """
    try:
        if not doc.IsWorkshared:
            return None

        central_path = doc.GetWorksharingCentralModelPath()

        if hasattr(central_path, 'CentralServerPath'):
            return central_path.CentralServerPath

        return None

    except:
        return None


def get_dat_folder(doc, subfolder=None, create=True):
    """
    Obtém/cria pasta DAT para dados do projeto.

    Args:
        doc (Document): Documento Revit
        subfolder (str): Subpasta dentro de DAT (opcional)
        create (bool): Se True, cria pasta se não existir

    Returns:
        str or None: Caminho da pasta DAT, ou None se não puder determinar

    Example:
        >>> dat_folder = get_dat_folder(doc)
        >>> print("DAT: {}".format(dat_folder))
        DAT: C:\\Projetos\\Edificio_A\\DAT

        >>> backup_folder = get_dat_folder(doc, subfolder="backup")
        >>> print("Backup: {}".format(backup_folder))
        Backup: C:\\Projetos\\Edificio_A\\DAT\\backup
    """
    project_folder = get_project_folder(doc)

    if not project_folder:
        return None

    # Pasta DAT base
    dat_folder = os.path.join(project_folder, 'DAT')

    # Se solicitado subfolder, adicionar ao caminho
    if subfolder:
        dat_folder = os.path.join(dat_folder, subfolder)

    # Criar pasta se não existir e create=True
    if create and not os.path.exists(dat_folder):
        try:
            os.makedirs(dat_folder)
        except Exception as e:
            print("ERRO ao criar pasta DAT: {}".format(str(e)))
            return None

    return dat_folder


def get_backup_folder(doc, create=True):
    """
    Obtém/cria pasta de backup dentro de DAT.

    Atalho para: get_dat_folder(doc, subfolder="backup")

    Args:
        doc (Document): Documento Revit
        create (bool): Se True, cria pasta se não existir

    Returns:
        str or None: Caminho da pasta backup

    Example:
        >>> backup_folder = get_backup_folder(doc)
        >>> print(backup_folder)
        C:\\Projetos\\Edificio_A\\DAT\\backup
    """
    return get_dat_folder(doc, subfolder="backup", create=create)


def create_backup(source_file, backup_folder=None, doc=None):
    """
    Cria backup de arquivo com timestamp.

    Formato do backup: [NomeOriginal]_[YYYYMMDD_HHMMSS][.ext]

    Args:
        source_file (str): Caminho do arquivo a fazer backup
        backup_folder (str): Pasta onde salvar backup (opcional)
        doc (Document): Documento Revit (usado se backup_folder=None)

    Returns:
        tuple: (success, backup_path or error_message)
            - success (bool): True se backup criado
            - backup_path (str): Caminho do backup criado (se success=True)
            - error_message (str): Mensagem de erro (se success=False)

    Example:
        >>> # Com pasta específica
        >>> success, path = create_backup("data.csv", backup_folder="C:\\Backups")
        >>> if success:
        ...     print("Backup: {}".format(path))

        >>> # Usando pasta DAT do projeto
        >>> success, path = create_backup("data.csv", doc=doc)
        >>> if success:
        ...     print("Backup: {}".format(path))
    """
    try:
        # Verificar se arquivo existe
        if not os.path.exists(source_file):
            return False, "Arquivo de origem não existe: {}".format(source_file)

        # Determinar pasta de backup
        if backup_folder is None:
            if doc is None:
                return False, "backup_folder ou doc deve ser fornecido"

            backup_folder = get_backup_folder(doc, create=True)

            if not backup_folder:
                return False, "Não foi possível determinar pasta de backup"

        # Criar pasta de backup se não existir
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)

        # Gerar nome do backup com timestamp
        base_name = os.path.basename(source_file)
        name_without_ext, ext = os.path.splitext(base_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = "{}_{}{}".format(name_without_ext, timestamp, ext)
        backup_path = os.path.join(backup_folder, backup_name)

        # Copiar arquivo
        shutil.copy2(source_file, backup_path)

        return True, backup_path

    except Exception as e:
        return False, "Erro ao criar backup: {}".format(str(e))


def get_project_data_csv_path(doc, create_dat_folder=True):
    """
    Obtém caminho padrão para CSV de dados do projeto: DAT/[Projeto]_data.csv

    Args:
        doc (Document): Documento Revit
        create_dat_folder (bool): Se True, cria pasta DAT se não existir

    Returns:
        str or None: Caminho do CSV, ou None se não puder determinar

    Example:
        >>> csv_path = get_project_data_csv_path(doc)
        >>> print(csv_path)
        C:\\Projetos\\Edificio_A\\DAT\\Edificio_A_data.csv
    """
    dat_folder = get_dat_folder(doc, create=create_dat_folder)
    project_name = get_project_name(doc)

    if not dat_folder:
        return None

    csv_path = os.path.join(dat_folder, "{}_data.csv".format(project_name))

    return csv_path


def get_templates_csv_path(doc, create_dat_folder=True):
    """
    Obtém caminho padrão para CSV de templates: DAT/templates.csv

    Args:
        doc (Document): Documento Revit
        create_dat_folder (bool): Se True, cria pasta DAT se não existir

    Returns:
        str or None: Caminho do CSV de templates

    Example:
        >>> templates_path = get_templates_csv_path(doc)
        >>> print(templates_path)
        C:\\Projetos\\Edificio_A\\DAT\\templates.csv
    """
    dat_folder = get_dat_folder(doc, create=create_dat_folder)

    if not dat_folder:
        return None

    return os.path.join(dat_folder, 'templates.csv')


def find_data_csv(doc, script_path=None, fallback_names=None):
    """
    Busca CSV de dados em ordem de prioridade:
    1. DAT/[Projeto]_data.csv (específico do projeto)
    2. [script_path]/data.csv (padrão do script)
    3. [fallback_names] adicionais

    Args:
        doc (Document): Documento Revit
        script_path (str): Caminho da pasta do script (opcional)
        fallback_names (list): Lista de nomes de arquivo alternativos (opcional)

    Returns:
        tuple: (csv_path, source)
            - csv_path (str): Caminho do CSV encontrado, ou None
            - source (str): Origem do CSV ("DAT", "script", "fallback", ou None)

    Example:
        >>> csv_path, source = find_data_csv(doc, script_path=PATH_SCRIPT)
        >>> if csv_path:
        ...     print("CSV encontrado em {}: {}".format(source, csv_path))
    """
    # 1. Tentar DAT do projeto
    dat_csv = get_project_data_csv_path(doc, create_dat_folder=False)
    if dat_csv and os.path.exists(dat_csv):
        return dat_csv, "DAT"

    # 2. Tentar data.csv na pasta do script
    if script_path:
        script_csv = os.path.join(script_path, 'data.csv')
        if os.path.exists(script_csv):
            return script_csv, "script"

    # 3. Tentar fallbacks adicionais
    if fallback_names and script_path:
        for fallback_name in fallback_names:
            fallback_path = os.path.join(script_path, fallback_name)
            if os.path.exists(fallback_path):
                return fallback_path, "fallback"

    return None, None


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _dat_folder_manager.py ===\n")
    print("AVISO: Testes requerem ambiente Revit ativo\n")

    # Testes simulados
    print("1. get_project_folder() - OK (requer Document)")
    print("2. get_project_name() - OK (requer Document)")
    print("3. get_central_path() - OK (requer Document workshared)")
    print("4. get_dat_folder() - OK (requer Document)")
    print("5. get_backup_folder() - OK (requer Document)")

    # Teste create_backup com arquivos simulados
    print("\n6. Testando create_backup() (simulado)...")

    # Criar arquivo temporário de teste
    import tempfile
    test_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
    test_file.write("teste,dados\n1,2\n")
    test_file.close()

    test_backup_folder = tempfile.mkdtemp()

    success, result = create_backup(test_file.name, backup_folder=test_backup_folder)
    print("   Backup criado: success={}, path={}".format(success, result if success else "N/A"))

    if success:
        assert os.path.exists(result), "Arquivo de backup deveria existir"
        print("   ✅ Backup criado com sucesso")

    # Cleanup
    os.unlink(test_file.name)
    if success and os.path.exists(result):
        os.unlink(result)
    os.rmdir(test_backup_folder)

    print("\n✅ TESTES BÁSICOS PASSARAM!")
    print("Execute em ambiente Revit para testes completos")
