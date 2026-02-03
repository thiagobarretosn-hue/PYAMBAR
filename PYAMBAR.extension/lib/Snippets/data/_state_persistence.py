# -*- coding: utf-8 -*-
"""
_state_persistence.py
Sistema de persistência de estado para janelas WPF (posição, tamanho, controles).

USAGE:
    from Snippets.data._state_persistence import (
        save_state,
        load_state,
        get_state_file_path,
        restore_window_state,
        save_window_state
    )

    # Em uma janela WPF personalizada
    class MinhaJanela(Window):
        def __init__(self):
            self.state_folder = "state"
            self.state_file_name = "minha_janela_state.json"

        def carregar_estado(self):
            state = load_state(self.state_folder, self.state_file_name)
            if state:
                # Restaurar controles personalizados
                if 'parameters' in state:
                    for param_name, param_state in state['parameters'].items():
                        # Aplicar estado aos controles

        def salvar_estado(self):
            state = {
                'parameters': {},
                'csv_file': self.current_csv,
                'timestamp': datetime.now().isoformat()
            }
            save_state(state, self.state_folder, self.state_file_name)

DEPENDENCIES:
    - codecs, os, json

AUTHOR: Thiago Barreto
VERSION: 1.0 (Extraído de ParameterPalette em ITERATION 2 - 29/11/2025)
NOTES:
    - 100% compatível com formato JSON do ParameterPalette v2.3.1
    - Suporta estados personalizados para qualquer janela WPF
    - Cria pasta de estado automaticamente
    - Usa UTF-8 encoding para caracteres especiais
"""

import codecs
import os
import json
from datetime import datetime


def get_state_file_path(script_path, state_folder_name="state", state_file_name="state.json"):
    """
    Retorna caminho completo do arquivo de estado.

    Args:
        script_path (str): Caminho do script (usar __file__ ou PATH_SCRIPT)
        state_folder_name (str): Nome da pasta de estado (padrão: "state")
        state_file_name (str): Nome do arquivo JSON (padrão: "state.json")

    Returns:
        str: Caminho completo do arquivo de estado

    Example:
        >>> PATH_SCRIPT = "C:\\...\\ParameterPalette.pushbutton"
        >>> state_file = get_state_file_path(PATH_SCRIPT, "state", "palette_state.json")
        >>> print(state_file)
        'C:\\...\\ParameterPalette.pushbutton\\state\\palette_state.json'
    """
    state_folder = os.path.join(script_path, state_folder_name)
    if not os.path.exists(state_folder):
        try:
            os.makedirs(state_folder)
        except Exception as e:
            print("⚠️ ERRO ao criar pasta de estado: {}".format(str(e)))
            return None

    return os.path.join(state_folder, state_file_name)


def save_state(state_dict, script_path, state_folder_name="state", state_file_name="state.json"):
    """
    Salva estado em arquivo JSON com UTF-8.

    Args:
        state_dict (dict): Dicionário com dados a salvar
        script_path (str): Caminho do script
        state_folder_name (str): Nome da pasta de estado
        state_file_name (str): Nome do arquivo JSON

    Returns:
        bool: True se salvamento bem-sucedido, False se erro

    Example:
        >>> state = {
        ...     'parameters': {'Comentarios': {'enabled': True, 'selected_value': 'Pilar'}},
        ...     'csv_file': 'data.csv',
        ...     'timestamp': datetime.now().isoformat()
        ... }
        >>> sucesso = save_state(state, PATH_SCRIPT, "state", "palette_state.json")

    Notes:
        - Adiciona timestamp automaticamente se não fornecido
        - Usa indent=2 para legibilidade
        - ensure_ascii=False preserva caracteres UTF-8
    """
    try:
        # Adicionar timestamp se não existir
        if 'timestamp' not in state_dict:
            state_dict['timestamp'] = datetime.now().isoformat()

        state_file = get_state_file_path(script_path, state_folder_name, state_file_name)
        if not state_file:
            return False

        with codecs.open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print("⚠️ ERRO ao salvar estado: {}".format(str(e)))
        return False


def load_state(script_path, state_folder_name="state", state_file_name="state.json"):
    """
    Carrega estado de arquivo JSON.

    Args:
        script_path (str): Caminho do script
        state_folder_name (str): Nome da pasta de estado
        state_file_name (str): Nome do arquivo JSON

    Returns:
        dict: Dicionário com estado salvo, ou None se não existir/erro

    Example:
        >>> state = load_state(PATH_SCRIPT, "state", "palette_state.json")
        >>> if state:
        ...     print("CSV anterior:", state.get('csv_file'))
        ...     print("Timestamp:", state.get('timestamp'))
    """
    try:
        state_file = get_state_file_path(script_path, state_folder_name, state_file_name)
        if not state_file or not os.path.exists(state_file):
            return None

        with codecs.open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        return state

    except Exception as e:
        print("⚠️ ERRO ao carregar estado: {}".format(str(e)))
        return None


def save_window_state(window, script_path, state_folder_name="state", state_file_name="window_state.json"):
    """
    Salva posição e tamanho de janela WPF.

    Args:
        window: Objeto Window do WPF (System.Windows.Window)
        script_path (str): Caminho do script
        state_folder_name (str): Nome da pasta de estado
        state_file_name (str): Nome do arquivo JSON

    Returns:
        bool: True se salvamento bem-sucedido, False se erro

    Example:
        >>> # Em event handler de fechamento de janela
        >>> def window_closing(sender, args):
        ...     save_window_state(self, PATH_SCRIPT, "state", "palette_window.json")
    """
    try:
        state = {
            'window': {
                'left': window.Left,
                'top': window.Top,
                'width': window.Width,
                'height': window.Height,
                'window_state': str(window.WindowState)  # Normal, Minimized, Maximized
            },
            'timestamp': datetime.now().isoformat()
        }

        return save_state(state, script_path, state_folder_name, state_file_name)

    except Exception as e:
        print("⚠️ ERRO ao salvar estado da janela: {}".format(str(e)))
        return False


def restore_window_state(window, script_path, state_folder_name="state", state_file_name="window_state.json"):
    """
    Restaura posição e tamanho de janela WPF.

    Args:
        window: Objeto Window do WPF
        script_path (str): Caminho do script
        state_folder_name (str): Nome da pasta de estado
        state_file_name (str): Nome do arquivo JSON

    Returns:
        bool: True se restauração bem-sucedida, False se não há estado salvo

    Example:
        >>> # Ao inicializar janela
        >>> class MinhaJanela(Window):
        ...     def __init__(self):
        ...         wpf.LoadComponent(self, xaml_file)
        ...         restore_window_state(self, PATH_SCRIPT, "state", "palette_window.json")
    """
    try:
        state = load_state(script_path, state_folder_name, state_file_name)
        if not state or 'window' not in state:
            return False

        window_state = state['window']

        # Restaurar posição e tamanho
        if 'left' in window_state:
            window.Left = window_state['left']
        if 'top' in window_state:
            window.Top = window_state['top']
        if 'width' in window_state:
            window.Width = window_state['width']
        if 'height' in window_state:
            window.Height = window_state['height']

        return True

    except Exception as e:
        print("⚠️ ERRO ao restaurar estado da janela: {}".format(str(e)))
        return False


def restore_parameter_controls(param_controls, state_dict):
    """
    Restaura estado de controles de parâmetros (específico para ParameterPalette).

    Args:
        param_controls (dict): Dicionário de controles {param_name: {'combo': combo, 'toggle': toggle}}
        state_dict (dict): Estado carregado com load_state()

    Returns:
        bool: True se restauração bem-sucedida, False se erro

    Example:
        >>> # Em ParameterPalette após criar controles
        >>> state = load_state(PATH_SCRIPT, "state", "palette_state.json")
        >>> if state:
        ...     restore_parameter_controls(self.param_controls, state)

    Notes:
        - Compatível 100% com formato JSON do ParameterPalette v2.3.1
        - Restaura IsChecked do ToggleButton
        - Restaura Text do ComboBox
    """
    if not state_dict or 'parameters' not in state_dict:
        return False

    try:
        for param_name, param_state in state_dict['parameters'].items():
            if param_name in param_controls:
                controls = param_controls[param_name]
                combo = controls.get("combo")
                toggle = controls.get("toggle")

                # Restaurar toggle (enabled/disabled)
                if toggle and 'enabled' in param_state:
                    toggle.IsChecked = param_state['enabled']

                # Restaurar valor selecionado no combo
                if combo and 'selected_value' in param_state:
                    selected_value = param_state['selected_value']
                    if selected_value:
                        combo.Text = selected_value

        return True

    except Exception as e:
        print("⚠️ ERRO ao restaurar controles: {}".format(str(e)))
        return False


def restore_combobox_selection(combobox, state_dict, state_key):
    """
    Restaura seleção de ComboBox genérico.

    Args:
        combobox: Objeto ComboBox do WPF
        state_dict (dict): Estado carregado
        state_key (str): Chave do estado (ex: 'selected_template')

    Returns:
        bool: True se restauração bem-sucedida, False se não encontrado

    Example:
        >>> # Restaurar template selecionado
        >>> state = load_state(PATH_SCRIPT)
        >>> if state:
        ...     restore_combobox_selection(self.combo_template, state, 'selected_template')
    """
    if not state_dict or state_key not in state_dict:
        return False

    try:
        selected_value = state_dict[state_key]
        if not selected_value:
            return False

        # Buscar item correspondente
        for i in range(combobox.Items.Count):
            if str(combobox.Items[i]) == selected_value:
                combobox.SelectedIndex = i
                return True

        return False

    except Exception as e:
        print("⚠️ ERRO ao restaurar ComboBox: {}".format(str(e)))
        return False


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _state_persistence.py ===\n")

    # Criar pasta temporária de teste
    import tempfile
    temp_dir = tempfile.mkdtemp()
    print("Pasta temporária: {}".format(temp_dir))

    # Teste 1: get_state_file_path
    state_file = get_state_file_path(temp_dir, "state", "test_state.json")
    print("1. get_state_file_path: {}".format(state_file))
    assert state_file is not None, "Caminho de estado não criado"
    assert os.path.exists(os.path.dirname(state_file)), "Pasta de estado não criada"

    # Teste 2: save_state
    state_teste = {
        'parameters': {
            'Comentarios': {'enabled': True, 'selected_value': 'Pilar 1'},
            'Mark': {'enabled': False, 'selected_value': None}
        },
        'csv_file': 'data.csv',
        'selected_template': 'Template 1'
    }
    sucesso = save_state(state_teste, temp_dir, "state", "test_state.json")
    print("2. save_state: sucesso={}".format(sucesso))
    assert sucesso == True, "Salvamento falhou"
    assert os.path.exists(state_file), "Arquivo de estado não criado"

    # Teste 3: load_state
    state_carregado = load_state(temp_dir, "state", "test_state.json")
    print("3. load_state: {} chaves".format(len(state_carregado) if state_carregado else 0))
    assert state_carregado is not None, "Carregamento falhou"
    assert 'parameters' in state_carregado, "Chave 'parameters' não encontrada"
    assert 'timestamp' in state_carregado, "Timestamp não adicionado"
    assert state_carregado['csv_file'] == 'data.csv', "Valor incorreto"

    # Teste 4: Verificar estrutura de parâmetros
    params = state_carregado['parameters']
    print("4. Parâmetros carregados: {}".format(len(params)))
    assert 'Comentarios' in params, "Parâmetro 'Comentarios' não encontrado"
    assert params['Comentarios']['enabled'] == True, "Estado 'enabled' incorreto"
    assert params['Comentarios']['selected_value'] == 'Pilar 1', "Valor selecionado incorreto"

    # Teste 5: save_state com timestamp automático
    state_sem_timestamp = {'teste': 'valor'}
    sucesso = save_state(state_sem_timestamp, temp_dir, "state", "test_auto_timestamp.json")
    state_auto = load_state(temp_dir, "state", "test_auto_timestamp.json")
    print("5. Timestamp automático: {}".format('timestamp' in state_auto if state_auto else False))
    assert state_auto is not None, "Carregamento falhou"
    assert 'timestamp' in state_auto, "Timestamp não foi adicionado automaticamente"

    # Teste 6: load_state com arquivo inexistente
    state_inexistente = load_state(temp_dir, "state", "arquivo_que_nao_existe.json")
    print("6. load_state (inexistente): {}".format(state_inexistente))
    assert state_inexistente is None, "Deveria retornar None para arquivo inexistente"

    # Limpar pasta temporária
    import shutil
    shutil.rmtree(temp_dir)

    print("\n✅ TODOS OS 6 TESTES PASSARAM!")
    print("\nNOTA: Testes de WPF (restore_window_state, restore_parameter_controls)")
    print("      requerem ambiente Revit com System.Windows.Window disponível")
