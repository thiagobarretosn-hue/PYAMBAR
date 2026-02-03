# -*- coding: utf-8 -*-
__title__ = "Color-FiLL Forge"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.2.2"
__doc__ = """Gerenciador visual de cores e criador de legendas inteligentes.

FEATURES v1.2.2 - PADRONIZACAO:
- [FIX] Usar revit.doc/uidoc/app em vez de __revit__

FEATURES v1.2.1 - FIX FILTROS ELEMENTID:
- [FIX] Corrigido criação de filtros para parâmetros do tipo ElementId (Material, Type, etc)
- [NOVO] Função CreateFilterRuleForParameter detecta StorageType automaticamente
- [FIX] Parâmetro "Material" em Tubulação agora preenche regra corretamente
- [MELHORIA] Suporte completo para String, ElementId, Double e Integer em regras de filtro
- [MELHORIA] Logs detalhados quando elemento não é encontrado

FEATURES v7.0.0 - TAGS ONLY + AUTO IMPORT:
- [NOVO] Auto-importação da família TAG Legenda items.rfa se não existir
- [REMOVIDO] Fallback para TextNote - apenas Tags são usadas
- [ALTERADO] CS_Title_Invisible removido - título usa CS_Border_White
- [ALTERADO] Título: Tag CS_Border_White centralizada, 1" da borda superior
- [FIX] CS_Border_White com máscara desabilitada
- [FIX] Borda superior a 3" da primeira caixa

FEATURES v6.9 - SELEÇÃO COMPLETA DE FONTES:
- [NOVO] ComboBox dinâmico com TODOS os tipos de texto disponíveis no projeto
- [NOVO] Busca automática de versão com underline para títulos
- [NOVO] Ordenação alfabética dos tipos de texto para fácil localização

FEATURES v6.8 - SISTEMA LEGEND COMPLETO:
- [NOVO] Interface completamente redesenhada com valores FRACIONAIS em polegadas:
  * Dimensões: 1/4", 1/2", 3/4", 7/8", 1", 1-1/4", 1-1/2", 2"
  * ComboBoxes para todas as configurações (não mais TextBoxes)
  * Valores padrão: caixas 1"x1", espaçamentos 1"

- [NOVO] Seleção de tipo de texto configurável:
  * 2.0mm Arial (Padrão System Legend)
  * 2.5mm Arial
  * 3.0mm Arial
  * Primeiro tipo disponível (fallback)

- [NOVO] Controle completo de espaçamentos:
  * Distância Caixa → Texto: configurável (padrão 1")
  * Espaçamento entre linhas: configurável (padrão 1")
  * Espaçamento Título → Primeira linha: configurável (padrão 2")

- [NOVO] Borda externa desenhada automaticamente:
  * Checkbox para habilitar/desabilitar
  * Margem configurável (1/4" a 1-1/2")
  * Criada com DetailLines formando retângulo

- [FIX] Alinhamento de texto corrigido:
  * Texto alinhado ao TOPO da caixa (não ao centro)
  * Título centralizado em relação ao CONTEÚDO TOTAL (não apenas às caixas)

- [NOVO] Conversão automática polegadas → pés em tempo real
- [NOVO] Logs detalhados de todas as configurações aplicadas
- Template-Based: duplica legenda existente (solução robusta API)
- [FIX] Select All / Deselect All funcionando corretamente
- [NOVO] Diálogo de legenda completamente redesenhado
- [NOVO] Opções de ordenação (Original, Alfabética, por Quantidade)
- [NOVO] Opção para mostrar/ocultar contagem na legenda
- [NOVO] Configuração de espaçamento entre linhas
- Checkboxes para selecionar quais valores colorir
- Interface intuitiva com preview
- Persistência em %APPDATA%
- Restauração em cascata
- Suporte a Múltiplos Parâmetros
- Engenharia Reversa de cores existentes

USO:
1. Selecione categorias e parâmetros.
2. Marque os valores que deseja colorir.
3. Clique nas cores para editá-las.
4. Aplique cores apenas aos valores marcados!
5. Configure a legenda com as novas opções avançadas!

IMPORTANTE - CRIAÇÃO DE LEGENDAS:
- A API do Revit NÃO permite criar Legend views do zero (limitação da Autodesk)
- O script usa método TEMPLATE-BASED: duplica uma legenda existente e modifica
- Se não houver legendas no projeto, usa Drafting view como fallback
- RECOMENDAÇÃO: Crie manualmente uma legenda vazia antes de usar (View > Create > Legend)

NOTA: Aplicação mantida como MODAL para segurança com Revit API.
"""

# ============================================================================
# IMPORTS
# ============================================================================
import codecs
import json
import os
import random
import traceback
from datetime import datetime

import clr

# .NET References
clr.AddReference("System")
clr.AddReference("System.Core")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Windows.Forms")

import System

# Revit API
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

# pyRevit
from pyrevit import forms, revit, HOST_APP
from System.Collections.Generic import List
from System.Collections.ObjectModel import ObservableCollection
from System.IO import MemoryStream
from System.Text import Encoding

# WPF Types
from System.Windows import ResizeMode, Window, WindowStartupLocation
from System.Windows.Forms import Application as WinFormsApp
from System.Windows.Forms import ColorDialog, DialogResult
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, Brushes, SolidColorBrush
from System.Windows.Media import Color as WpfColor

# ============================================================================
# TRANSACTION WRAPPER
# ============================================================================
try:
    from Snippets import _transaction
except ImportError:
    class _transaction:
        class ef_Transaction:
            def __init__(self, doc, name):
                self.t = Transaction(doc, name)
            def __enter__(self):
                self.t.Start()
                return self.t
            def __exit__(self, type, value, traceback):
                if self.t.GetStatus() == TransactionStatus.Started:
                    self.t.Commit()

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================
doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
rvt_year = int(app.VersionNumber)

# ============================================================================
# HELPERS
# ============================================================================
def GetIdValue(element_id):
    if hasattr(element_id, "Value"): return element_id.Value
    return element_id.IntegerValue

def GetSolidFill(doc):
    patterns = FilteredElementCollector(doc).OfClass(FillPatternElement)
    for p in patterns:
        if p.GetFillPattern().IsSolidFill: return p.Id
    first = patterns.FirstElementId()
    return first if first else ElementId.InvalidElementId

def CreateFilterRuleForParameter(doc, param, value_string, revit_year):
    """
    Cria FilterRule apropriada baseada no StorageType do parâmetro.

    Args:
        doc: Document do Revit
        param: Parameter object
        value_string: Valor como string (ex: "Polyvinyl Chloride - Rigid")
        revit_year: Ano da versão do Revit

    Returns:
        FilterRule ou None se falhar
    """
    try:
        param_id = param.Id
        storage_type = param.StorageType

        # CASO 1: Parâmetro de Texto (String)
        if storage_type == StorageType.String:
            if revit_year >= 2023:
                return ParameterFilterRuleFactory.CreateEqualsRule(param_id, value_string)
            else:
                return ParameterFilterRuleFactory.CreateEqualsRule(param_id, value_string, True)

        # CASO 2: Parâmetro do tipo ElementId (Material, Type, etc)
        elif storage_type == StorageType.ElementId:
            # Procurar elemento pelo nome
            found_element_id = None

            # Tentar Materials primeiro (caso mais comum)
            materials = FilteredElementCollector(doc).OfClass(Material)
            for mat in materials:
                if mat.Name == value_string:
                    found_element_id = mat.Id
                    break

            # Se não encontrou em Materials, tentar ElementType genérico
            if not found_element_id:
                all_types = FilteredElementCollector(doc).WhereElementIsElementType()
                for elem_type in all_types:
                    if hasattr(elem_type, 'Name') and elem_type.Name == value_string:
                        found_element_id = elem_type.Id
                        break

            # Se encontrou o elemento, criar regra ElementId
            if found_element_id:
                if revit_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, found_element_id)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, found_element_id, True)
            else:
                # Não encontrou o elemento - retornar None
                print("AVISO: Elemento '{}' não encontrado para criar regra.".format(value_string))
                return None

        # CASO 3: Parâmetro Numérico (Double)
        elif storage_type == StorageType.Double:
            try:
                numeric_value = float(value_string)
                if revit_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, numeric_value, 0.0001)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, numeric_value, 0.0001, True)
            except ValueError:
                print("AVISO: Não foi possível converter '{}' para número.".format(value_string))
                return None

        # CASO 4: Parâmetro Inteiro (Integer)
        elif storage_type == StorageType.Integer:
            try:
                int_value = int(value_string)
                if revit_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, int_value)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, int_value, True)
            except ValueError:
                print("AVISO: Não foi possível converter '{}' para inteiro.".format(value_string))
                return None

        else:
            print("AVISO: StorageType {} não suportado.".format(storage_type))
            return None

    except Exception as e:
        print("ERRO ao criar FilterRule: {}".format(e))
        return None

CAT_EXCLUDED = (
    -2000278, -1,
    int(BuiltInCategory.OST_RoomSeparationLines),
    int(BuiltInCategory.OST_Cameras),
    int(BuiltInCategory.OST_CurtainGrids),
    int(BuiltInCategory.OST_Elev),
    int(BuiltInCategory.OST_Grids),
    int(BuiltInCategory.OST_IOSModelGroups),
    int(BuiltInCategory.OST_Views),
    int(BuiltInCategory.OST_SectionBox),
    int(BuiltInCategory.OST_ShaftOpening),
    int(BuiltInCategory.OST_BeamAnalytical),
    int(BuiltInCategory.OST_StructuralFramingOpening),
    int(BuiltInCategory.OST_MEPSpaceSeparationLines),
    int(BuiltInCategory.OST_DuctSystem),
    int(BuiltInCategory.OST_Lines),
    int(BuiltInCategory.OST_PipingSystem),
    int(BuiltInCategory.OST_Matchline),
    int(BuiltInCategory.OST_CenterLines),
    int(BuiltInCategory.OST_CurtainGridsRoof),
    int(BuiltInCategory.OST_SWallRectOpening)
)

# ============================================================================
# PERSISTÊNCIA SEGURA (APPDATA)
# ============================================================================
APPDATA = os.getenv('APPDATA')
STATE_DIR = os.path.join(APPDATA, "ColorFiLLForge")
if not os.path.exists(STATE_DIR):
    try: os.makedirs(STATE_DIR)
    except: pass

STATE_FILE = os.path.join(STATE_DIR, "user_state.json")

class StateManager:
    @staticmethod
    def load():
        if os.path.exists(STATE_FILE):
            try:
                with codecs.open(STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    @staticmethod
    def save(data):
        try:
            with codecs.open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

# ============================================================================
# PRESET MANAGER - v1.2.0
# ============================================================================
PRESETS_DIR = os.path.join(STATE_DIR, "presets")
if not os.path.exists(PRESETS_DIR):
    try: os.makedirs(PRESETS_DIR)
    except: pass

class PresetManager:
    @staticmethod
    def list_presets():
        """Retorna lista de nomes de presets disponíveis."""
        try:
            if not os.path.exists(PRESETS_DIR):
                return []
            presets = []
            for filename in os.listdir(PRESETS_DIR):
                if filename.endswith('.json'):
                    preset_name = filename[:-5]  # Remove .json
                    presets.append(preset_name)
            return sorted(presets)
        except:
            return []

    @staticmethod
    def save_preset(name, colors_data):
        """
        Salva preset com nome e dados de cores.
        colors_data = {valor: (R, G, B), ...}
        """
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            preset = {
                "name": name,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colors": colors_data
            }
            with codecs.open(filename, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=4, ensure_ascii=False)
            return True
        except:
            return False

    @staticmethod
    def load_preset(name):
        """
        Carrega preset por nome.
        Retorna: {valor: (R, G, B), ...} ou None se falhar
        """
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filename):
                with codecs.open(filename, 'r', encoding='utf-8') as f:
                    preset = json.load(f)
                return preset.get("colors", {})
            return None
        except:
            return None

    @staticmethod
    def delete_preset(name):
        """Deleta preset por nome."""
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filename):
                os.remove(filename)
                return True
            return False
        except:
            return False

# ============================================================================
# VIEW MODEL COM NOTIFICAÇÃO
# ============================================================================
class ValueItem(object):
    """Item de valor com propriedades observáveis para WPF binding."""

    def __init__(self, value, element_ids, r=None, g=None, b=None, is_checked=True):
        self.Value = str(value)
        self.ElementIds = element_ids
        self.Count = len(element_ids)
        self.IsChecked = is_checked

        if r is None:
            self.R = random.randint(50, 240)
            self.G = random.randint(50, 240)
            self.B = random.randint(50, 240)
        else:
            self.R, self.G, self.B = int(r), int(g), int(b)

        self.UpdateBrush()

    def UpdateBrush(self):
        """Atualiza a cor WPF baseado em R, G, B."""
        self.WpfColor = WpfColor.FromRgb(self.R, self.G, self.B)
        self.ColorBrush = SolidColorBrush(self.WpfColor)

    def GetRevitColor(self):
        """Retorna cor no formato Revit API."""
        return Color(self.R, self.G, self.B)

# ============================================================================
# XAML - LEGENDA (MELHORADO)
# ============================================================================
xaml_legend = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Configurar Legenda - System Legend Standard" Height="600" Width="550"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- Header -->
        <Border Grid.Row="0" Background="#4F46E5" Padding="15,10">
            <TextBlock Text="Configuração da Legenda - Padrão System Legend" FontSize="16" FontWeight="Bold" Foreground="White"/>
        </Border>

        <!-- Content -->
        <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto">
            <StackPanel Margin="15">
                <!-- Título -->
                <GroupBox Header="Nome da Vista" Padding="10" Margin="0,0,0,10">
                    <TextBox x:Name="txtTitle" Text="Legenda de Cores" Height="28" FontSize="13"/>
                </GroupBox>

                <!-- Dimensões (Sistema Imperial - Fracionário) -->
                <GroupBox Header="Dimensões das Caixas Coloridas" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <TextBlock Text="Largura e Altura (polegadas fracionais):" Margin="0,0,0,5" FontWeight="SemiBold"/>
                        <Grid Margin="0,0,0,8">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="15"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <StackPanel Grid.Column="0">
                                <TextBlock Text="Largura:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbWidth" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/4&quot; (0.25)"/>
                                    <ComboBoxItem Content="1/2&quot; (0.5)"/>
                                    <ComboBoxItem Content="3/4&quot; (0.75)"/>
                                    <ComboBoxItem Content="7/8&quot; (0.875)"/>
                                    <ComboBoxItem Content="1&quot; (1.0)"/>
                                    <ComboBoxItem Content="1-1/4&quot; (1.25)"/>
                                    <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                                    <ComboBoxItem Content="2&quot; (2.0)"/>
                                </ComboBox>
                            </StackPanel>
                            <StackPanel Grid.Column="2">
                                <TextBlock Text="Altura:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbHeight" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/4&quot; (0.25)"/>
                                    <ComboBoxItem Content="1/2&quot; (0.5)"/>
                                    <ComboBoxItem Content="3/4&quot; (0.75)"/>
                                    <ComboBoxItem Content="7/8&quot; (0.875)"/>
                                    <ComboBoxItem Content="1&quot; (1.0)"/>
                                    <ComboBoxItem Content="1-1/4&quot; (1.25)"/>
                                    <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                                    <ComboBoxItem Content="2&quot; (2.0)"/>
                                </ComboBox>
                            </StackPanel>
                        </Grid>
                    </StackPanel>
                </GroupBox>

                <!-- Espaçamentos -->
                <GroupBox Header="Espaçamentos (polegadas fracionais)" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <Grid Margin="0,0,0,8">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="15"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <StackPanel Grid.Column="0">
                                <TextBlock Text="Distância Caixa → Texto:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbOffset" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/8&quot; (0.125)"/>
                                    <ComboBoxItem Content="1/4&quot; (0.25)"/>
                                    <ComboBoxItem Content="3/8&quot; (0.375)"/>
                                    <ComboBoxItem Content="1/2&quot; (0.5)"/>
                                    <ComboBoxItem Content="1&quot; (1.0)"/>
                                    <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                                    <ComboBoxItem Content="2&quot; (2.0)"/>
                                    <ComboBoxItem Content="2-1/2&quot; (2.5)"/>
                                    <ComboBoxItem Content="3&quot; (3.0)"/>
                                </ComboBox>
                            </StackPanel>
                            <StackPanel Grid.Column="2">
                                <TextBlock Text="Espaçamento Entre Linhas:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbSpacing" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/8&quot; (0.125)"/>
                                    <ComboBoxItem Content="1/4&quot; (0.25)"/>
                                    <ComboBoxItem Content="3/8&quot; (0.375)"/>
                                    <ComboBoxItem Content="1/2&quot; (0.5)"/>
                                    <ComboBoxItem Content="1&quot; (1.0)"/>
                                    <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                                    <ComboBoxItem Content="2&quot; (2.0)"/>
                                    <ComboBoxItem Content="2-1/2&quot; (2.5)"/>
                                    <ComboBoxItem Content="3&quot; (3.0)"/>
                                </ComboBox>
                            </StackPanel>
                        </Grid>

                        <TextBlock Text="Espaçamento Título → Primeira Linha:" Margin="0,8,0,3"/>
                        <ComboBox x:Name="cmbTitleSpacing" Height="25" SelectedIndex="5">
                            <ComboBoxItem Content="1/2&quot; (0.5)"/>
                            <ComboBoxItem Content="3/4&quot; (0.75)"/>
                            <ComboBoxItem Content="1&quot; (1.0)"/>
                            <ComboBoxItem Content="1-1/4&quot; (1.25)"/>
                            <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                            <ComboBoxItem Content="2&quot; (2.0)"/>
                        </ComboBox>
                    </StackPanel>
                </GroupBox>

                <!-- Borda Externa (Obrigatória) -->
                <GroupBox Header="Borda Externa (Obrigatória)" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <TextBlock Text="Margem da borda (offset do conteúdo):" Margin="0,0,0,3"/>
                        <ComboBox x:Name="cmbBorderOffset" Height="25" SelectedIndex="4" Margin="0,0,0,8">
                            <ComboBoxItem Content="1/4&quot; (0.25)"/>
                            <ComboBoxItem Content="1/2&quot; (0.5)"/>
                            <ComboBoxItem Content="3/4&quot; (0.75)"/>
                            <ComboBoxItem Content="7/8&quot; (0.875)"/>
                            <ComboBoxItem Content="1&quot; (1.0)"/>
                            <ComboBoxItem Content="1-1/4&quot; (1.25)"/>
                            <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                        </ComboBox>
                        <TextBlock Text="Margem inferior (abaixo da última caixa):" Margin="0,0,0,3"/>
                        <ComboBox x:Name="cmbBorderBottom" Height="25" SelectedIndex="5">
                            <ComboBoxItem Content="1/4&quot; (0.25)"/>
                            <ComboBoxItem Content="1/2&quot; (0.5)"/>
                            <ComboBoxItem Content="3/4&quot; (0.75)"/>
                            <ComboBoxItem Content="7/8&quot; (0.875)"/>
                            <ComboBoxItem Content="1&quot; (1.0)"/>
                            <ComboBoxItem Content="1-1/4&quot; (1.25)"/>
                            <ComboBoxItem Content="1-1/2&quot; (1.5)"/>
                            <ComboBoxItem Content="2&quot; (2.0)"/>
                        </ComboBox>
                    </StackPanel>
                </GroupBox>

                <!-- Ordenação -->
                <GroupBox Header="Ordenação e Contagem" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <RadioButton x:Name="rbOrderOriginal" Content="Ordem Original (como aparece na lista)" IsChecked="True" Margin="0,0,0,5"/>
                        <RadioButton x:Name="rbOrderAlpha" Content="Ordem Alfabética por Valor" Margin="0,0,0,5"/>
                        <RadioButton x:Name="rbOrderCount" Content="Ordem por Quantidade (maior primeiro)" Margin="0,0,0,8"/>

                        <CheckBox x:Name="chkShowCount" Content="Mostrar quantidade de elementos após o valor" IsChecked="True"/>
                    </StackPanel>
                </GroupBox>

                <!-- Preview Info -->
                <Border Background="#F0F9FF" BorderBrush="#3B82F6" BorderThickness="1" Padding="10" CornerRadius="4">
                    <StackPanel>
                        <TextBlock Text="ℹ️ Informações" FontWeight="Bold" Foreground="#1E40AF" Margin="0,0,0,5"/>
                        <TextBlock x:Name="txtPreview" TextWrapping="Wrap" Foreground="#374151" FontSize="11">
                            A legenda será criada seguindo o padrão System Legend.
                        </TextBlock>
                    </StackPanel>
                </Border>
            </StackPanel>
        </ScrollViewer>

        <!-- Footer Buttons -->
        <Border Grid.Row="2" Background="#F3F4F6" Padding="15,10" BorderBrush="#E5E7EB" BorderThickness="0,1,0,0">
            <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
                <Button x:Name="btnCancel" Content="Cancelar" Width="100" Height="32" Margin="0,0,10,0" Background="White" BorderBrush="#D1D5DB"/>
                <Button x:Name="btnCreate" Content="Criar Legenda" Width="130" Height="32" Background="#4F46E5" Foreground="White" FontWeight="Bold" BorderThickness="0"/>
            </StackPanel>
        </Border>
    </Grid>
</Window>
"""

class LegendConfigWindow(object):
    # Mapa de valores fracionais para decimais
    FRACTIONAL_VALUES = {
        0: 0.25,   # 1/4"
        1: 0.5,    # 1/2"
        2: 0.75,   # 3/4"
        3: 0.875,  # 7/8"
        4: 1.0,    # 1"
        5: 1.25,   # 1-1/4"
        6: 1.5,    # 1-1/2"
        7: 2.0     # 2"
    }

    BORDER_BOTTOM_VALUES = {
        0: 0.25,   # 1/4"
        1: 0.5,    # 1/2"
        2: 0.75,   # 3/4"
        3: 0.875,  # 7/8"
        4: 1.0,    # 1"
        5: 1.25,   # 1-1/4"
        6: 1.5,    # 1-1/2"
        7: 2.0     # 2"
    }

    SPACING_VALUES = {
        0: 0.125,  # 1/8"
        1: 0.25,   # 1/4"
        2: 0.375,  # 3/8"
        3: 0.5,    # 1/2"
        4: 1.0,    # 1"
        5: 1.5,    # 1-1/2"
        6: 2.0,    # 2"
        7: 2.5,    # 2-1/2"
        8: 3.0     # 3"
    }

    TITLE_SPACING_VALUES = {
        0: 0.5,    # 1/2"
        1: 0.75,   # 3/4"
        2: 1.0,    # 1"
        3: 1.25,   # 1-1/4"
        4: 1.5,    # 1-1/2"
        5: 2.0     # 2"
    }

    TEXT_TYPE_MAP = {
        0: "2.0mm",
        1: "2.5mm",
        2: "3.0mm",
        3: "first"
    }

    def __init__(self, callback, items_count):
        self.callback = callback
        stream = MemoryStream(Encoding.UTF8.GetBytes(xaml_legend))
        self.window = XamlReader.Load(stream)

        # Find Controls
        self.txtTitle = self.window.FindName("txtTitle")
        self.cmbWidth = self.window.FindName("cmbWidth")
        self.cmbHeight = self.window.FindName("cmbHeight")
        self.cmbOffset = self.window.FindName("cmbOffset")
        self.cmbSpacing = self.window.FindName("cmbSpacing")
        self.cmbTitleSpacing = self.window.FindName("cmbTitleSpacing")
        self.cmbBorderOffset = self.window.FindName("cmbBorderOffset")
        self.cmbBorderBottom = self.window.FindName("cmbBorderBottom")
        self.chkShowCount = self.window.FindName("chkShowCount")
        self.rbOrderOriginal = self.window.FindName("rbOrderOriginal")
        self.rbOrderAlpha = self.window.FindName("rbOrderAlpha")
        self.rbOrderCount = self.window.FindName("rbOrderCount")
        self.txtPreview = self.window.FindName("txtPreview")
        self.btnCreate = self.window.FindName("btnCreate")
        self.btnCancel = self.window.FindName("btnCancel")

        # v1.1: Carregar estado salvo da última execução
        self.LoadLegendState()

        # Update Preview
        self.txtPreview.Text = "Serão criados {} itens na legenda seguindo o padrão System Legend.\n\nApenas valores marcados (✓) serão incluídos.".format(items_count)

        # Events
        self.btnCreate.Click += self.OnCreateClick
        self.btnCancel.Click += self.OnCancelClick

    def LoadLegendState(self):
        """Carrega configurações salvas da última legenda criada."""
        try:
            state = StateManager.load()
            legend_state = state.get("legend_config", {})

            if legend_state:
                # Restaurar valores dos ComboBoxes (usar índices salvos)
                if "width_idx" in legend_state:
                    self.cmbWidth.SelectedIndex = legend_state["width_idx"]
                if "height_idx" in legend_state:
                    self.cmbHeight.SelectedIndex = legend_state["height_idx"]
                if "offset_idx" in legend_state:
                    self.cmbOffset.SelectedIndex = legend_state["offset_idx"]
                if "spacing_idx" in legend_state:
                    self.cmbSpacing.SelectedIndex = legend_state["spacing_idx"]
                if "title_spacing_idx" in legend_state:
                    self.cmbTitleSpacing.SelectedIndex = legend_state["title_spacing_idx"]
                if "border_offset_idx" in legend_state:
                    self.cmbBorderOffset.SelectedIndex = legend_state["border_offset_idx"]
                if "border_bottom_idx" in legend_state:
                    self.cmbBorderBottom.SelectedIndex = legend_state["border_bottom_idx"]

                # Restaurar CheckBox
                if "show_count" in legend_state:
                    self.chkShowCount.IsChecked = legend_state["show_count"]

                # Restaurar RadioButtons de ordenação
                order = legend_state.get("order", "original")
                if order == "alpha":
                    self.rbOrderAlpha.IsChecked = True
                elif order == "count":
                    self.rbOrderCount.IsChecked = True
                else:
                    self.rbOrderOriginal.IsChecked = True
        except Exception:
            pass  # Se falhar, usar valores padrão

    def SaveLegendState(self, config):
        """Salva configurações da legenda para próxima execução."""
        try:
            state = StateManager.load()

            # Salvar índices dos ComboBoxes (não valores, para manter se mudar enum)
            legend_state = {
                "width_idx": self.cmbWidth.SelectedIndex,
                "height_idx": self.cmbHeight.SelectedIndex,
                "offset_idx": self.cmbOffset.SelectedIndex,
                "spacing_idx": self.cmbSpacing.SelectedIndex,
                "title_spacing_idx": self.cmbTitleSpacing.SelectedIndex,
                "border_offset_idx": self.cmbBorderOffset.SelectedIndex,
                "border_bottom_idx": self.cmbBorderBottom.SelectedIndex,
                "show_count": config["show_count"],
                "order": config["order"]
            }

            state["legend_config"] = legend_state
            StateManager.save(state)
        except Exception:
            pass  # Falha silenciosa ao salvar

    def ShowDialog(self):
        return self.window.ShowDialog()

    def Close(self):
        try:
            self.window.Close()
        except:
            pass

    def OnCreateClick(self, sender, args):
        try:
            config = {
                "title": self.txtTitle.Text,
                "text_type_id": None,  # Not used anymore - tags handle text display
                "width": self.FRACTIONAL_VALUES[self.cmbWidth.SelectedIndex],
                "height": self.FRACTIONAL_VALUES[self.cmbHeight.SelectedIndex],
                "offset": self.SPACING_VALUES[self.cmbOffset.SelectedIndex],
                "spacing": self.SPACING_VALUES[self.cmbSpacing.SelectedIndex],
                "title_spacing": self.TITLE_SPACING_VALUES[self.cmbTitleSpacing.SelectedIndex],
                "draw_border": True,  # v7.0.7: Borda sempre obrigatória
                "border_offset": self.FRACTIONAL_VALUES[self.cmbBorderOffset.SelectedIndex],
                "border_bottom": self.BORDER_BOTTOM_VALUES[self.cmbBorderBottom.SelectedIndex],
                "show_count": self.chkShowCount.IsChecked,
                "order": "original" if self.rbOrderOriginal.IsChecked else ("alpha" if self.rbOrderAlpha.IsChecked else "count")
            }

            # v1.1: Salvar estado da legenda para próxima execução
            self.SaveLegendState(config)

            self.callback(config)
            self.window.Close()
        except Exception as e:
            forms.alert("Erro ao processar configurações:\n\n{}".format(str(e)))
            import traceback
            traceback.print_exc()

    def OnCancelClick(self, sender, args):
        self.window.Close()

# ============================================================================
# XAML - PRINCIPAL (COM CHECKBOXES)
# ============================================================================
xaml_main = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Grid.Resources>
        <Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Segoe UI"/><Setter Property="Foreground" Value="#111827"/></Style>
        <Style TargetType="Button">
            <Setter Property="Height" Value="28"/><Setter Property="Margin" Value="2"/>
            <Setter Property="Background" Value="White"/><Setter Property="BorderBrush" Value="#D1D5DB"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
        </Style>
        <Style x:Key="BtnPrimary" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Background" Value="#4F46E5"/><Setter Property="Foreground" Value="White"/><Setter Property="BorderThickness" Value="0"/>
        </Style>
    </Grid.Resources>
    <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
    <Border Grid.Row="0" Background="#4F46E5" Height="4"/>
    <Grid Grid.Row="1" Margin="10">
        <Grid.ColumnDefinitions><ColumnDefinition Width="280"/><ColumnDefinition Width="15"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
        <Grid Grid.Column="0">
            <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>
            <GroupBox Header="1. Escopo" Margin="0,0,0,10" Padding="5">
                <StackPanel Orientation="Horizontal">
                    <RadioButton x:Name="rbActiveView" Content="Vista Ativa" IsChecked="True" Margin="0,0,15,0"/>
                    <RadioButton x:Name="rbProject" Content="Projeto Inteiro"/>
                </StackPanel>
            </GroupBox>
            <Grid Grid.Row="1">
                <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>
                <TextBlock Text="Categorias (Selecão múltipla Shift/Ctrl)" FontWeight="Bold" Margin="0,0,0,5"/>
                <Border Grid.Row="1" BorderBrush="#E5E7EB" BorderThickness="1">
                    <ListBox x:Name="lbCategories" SelectionMode="Extended" BorderThickness="0">
                        <ListBox.ItemTemplate>
                            <DataTemplate>
                                <StackPanel Orientation="Horizontal">
                                    <CheckBox IsChecked="{Binding IsSelected, RelativeSource={RelativeSource AncestorType=ListBoxItem}, Mode=TwoWay}" Margin="0,0,5,0" VerticalAlignment="Center"/>
                                    <TextBlock Text="{Binding Name}" VerticalAlignment="Center"/>
                                </StackPanel>
                            </DataTemplate>
                        </ListBox.ItemTemplate>
                    </ListBox>
                </Border>
            </Grid>
            <Grid Grid.Row="3">
                <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>
                <DockPanel Grid.Row="0" Margin="0,10,0,5">
                    <TextBlock Text="Parâmetro(s) (Selecão múltipla Shift/Ctrl)" FontWeight="Bold" DockPanel.Dock="Top"/>
                    <TextBox x:Name="txtSearch" Height="22" Margin="0,2,0,0" Padding="2" Text="Buscar..." Foreground="Gray"/>
                </DockPanel>
                <Border Grid.Row="1" BorderBrush="#E5E7EB" BorderThickness="1">
                    <ListBox x:Name="lbParameters" SelectionMode="Extended" BorderThickness="0">
                        <ListBox.ItemTemplate>
                            <DataTemplate>
                                <StackPanel Orientation="Horizontal">
                                    <CheckBox IsChecked="{Binding IsSelected, RelativeSource={RelativeSource AncestorType=ListBoxItem}, Mode=TwoWay}" Margin="0,0,5,0" VerticalAlignment="Center"/>
                                    <TextBlock Text="{Binding}" VerticalAlignment="Center"/>
                                </StackPanel>
                            </DataTemplate>
                        </ListBox.ItemTemplate>
                    </ListBox>
                </Border>
            </Grid>
        </Grid>
        <Grid Grid.Column="2">
            <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
            <StackPanel Orientation="Horizontal" Margin="0,0,0,10">
                <TextBlock Text="" FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,15,0"/>
                <Button x:Name="btnSelectAll" Content="✓ Select All" Width="90" Margin="0,0,5,0"/>
                <Button x:Name="btnDeselectAll" Content="☐ Deselect All" Width="90"/>
                <StackPanel Orientation="Horizontal" Margin="15,0,0,0">
                    <Button x:Name="btnRandom" Content="🎲 Random" Width="80"/>
                    <Button x:Name="btnGradient" Content="🌈 Gradiente" Width="90"/>
                    <Button x:Name="btnSavePreset" Content="💾 Salvar" Width="75" Margin="5,0,0,0" ToolTip="Salvar esquema de cores como preset"/>
                    <Button x:Name="btnLoadPreset" Content="📂 Carregar" Width="85" ToolTip="Carregar preset salvo"/>
                    <Button x:Name="btnReset" Content="Resetar Cores" Width="100" Margin="5,0,0,0" Foreground="#EF4444"/>
                </StackPanel>
            </StackPanel>
            <Border Grid.Row="1" BorderBrush="#E5E7EB" BorderThickness="1" Background="White">
                <ListView x:Name="lvValues" BorderThickness="0">
                    <ListView.View>
                        <GridView>
                            <GridViewColumn Header="✓" Width="35">
                                <GridViewColumn.CellTemplate><DataTemplate>
                                    <CheckBox IsChecked="{Binding IsChecked}" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                                </DataTemplate></GridViewColumn.CellTemplate>
                            </GridViewColumn>
                            <GridViewColumn Header="Cor" Width="55">
                                <GridViewColumn.CellTemplate><DataTemplate>
                                    <Border Width="35" Height="18" Background="{Binding ColorBrush}" BorderBrush="#9CA3AF" BorderThickness="1" CornerRadius="3" Cursor="Hand" ToolTip="Duplo-clique para editar"/>
                                </DataTemplate></GridViewColumn.CellTemplate>
                            </GridViewColumn>
                            <GridViewColumn Header="Valor" Width="200" DisplayMemberBinding="{Binding Value}"/>
                            <GridViewColumn Header="Qtd" Width="50" DisplayMemberBinding="{Binding Count}"/>
                        </GridView>
                    </ListView.View>
                </ListView>
            </Border>
            <StackPanel Grid.Row="2" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
                <CheckBox x:Name="chkAllViews" Content="Aplicar Filtros em Todas as Vistas" VerticalAlignment="Center" Margin="0,0,15,0" ToolTip="Se marcado, aplica os filtros em todas as vistas compatíveis do projeto"/>
                <Button x:Name="btnLegend" Content="Criar Legenda..." Width="120" Margin="0,0,5,0"/>
                <Button x:Name="btnFilters" Content="Criar Filtros" Width="120" Margin="0,0,5,0"/>
                <Button x:Name="btnApply" Content="APLICAR CORES" Style="{StaticResource BtnPrimary}" Width="150" FontWeight="Bold"/>
            </StackPanel>
        </Grid>
    </Grid>
    <Border Grid.Row="2" Background="#F3F4F6" Padding="10,4">
        <TextBlock x:Name="txtStatus" Text="Pronto." FontSize="11" Foreground="#6B7280"/>
    </Border>
</Grid>
"""

class MainWindow(Window):
    def __init__(self):
        self.Title = "Color-FiLL Forge "
        self.Height = 650
        self.Width = 1050
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = BrushConverter().ConvertFrom("#F9FAFB")

        self.type_cache = {}
        self.existing_filters_cache = self.scan_view_filters()

        stream = MemoryStream(Encoding.UTF8.GetBytes(xaml_main))
        self.Content = XamlReader.Load(stream)

        # CONTROLS
        self.lbCategories = self.Content.FindName("lbCategories")
        self.lbParameters = self.Content.FindName("lbParameters")
        self.lvValues = self.Content.FindName("lvValues")
        self.txtSearch = self.Content.FindName("txtSearch")
        self.txtStatus = self.Content.FindName("txtStatus")
        self.rbActiveView = self.Content.FindName("rbActiveView")
        self.rbProject = self.Content.FindName("rbProject")

        self.btnSelectAll = self.Content.FindName("btnSelectAll")
        self.btnDeselectAll = self.Content.FindName("btnDeselectAll")
        self.btnRandom = self.Content.FindName("btnRandom")
        self.btnGradient = self.Content.FindName("btnGradient")
        self.btnSavePreset = self.Content.FindName("btnSavePreset")
        self.btnLoadPreset = self.Content.FindName("btnLoadPreset")
        self.btnApply = self.Content.FindName("btnApply")
        self.btnReset = self.Content.FindName("btnReset")
        self.btnFilters = self.Content.FindName("btnFilters")
        self.btnLegend = self.Content.FindName("btnLegend")
        self.chkAllViews = self.Content.FindName("chkAllViews")

        # EVENTS
        self.lbCategories.SelectionChanged += self.OnCategoryChanged
        self.lbParameters.SelectionChanged += self.OnParameterChanged
        self.rbActiveView.Checked += self.OnScopeChanged
        self.rbProject.Checked += self.OnScopeChanged
        self.txtSearch.GotFocus += self.OnSearchFocus
        self.txtSearch.TextChanged += self.OnSearchChanged

        # CHECKBOX EVENTS
        self.btnSelectAll.Click += self.OnSelectAllClick
        self.btnDeselectAll.Click += self.OnDeselectAllClick

        # COLOR EVENTS
        self.btnRandom.Click += self.OnRandomClick
        self.btnGradient.Click += self.OnGradientClick
        self.lvValues.MouseDoubleClick += self.OnValueDoubleClick

        # PRESET EVENTS
        self.btnSavePreset.Click += self.OnSavePresetClick
        self.btnLoadPreset.Click += self.OnLoadPresetClick

        # ACTIONS
        self.btnApply.Click += self.OnApplyClick
        self.btnFilters.Click += self.OnCreateFilters
        self.btnLegend.Click += self.OnOpenLegendDialog
        self.btnReset.Click += self.OnResetClick
        self.Closing += self.OnWindowClosing

        # DATA
        self.all_params = []
        self.current_values = ObservableCollection[object]()
        self.lvValues.ItemsSource = self.current_values
        self.saved_state = StateManager.load()

        # INIT
        self.PopulateCategories()
        self.RestoreState()

    def scan_view_filters(self):
        """Mapeia cores de filtros já aplicados na vista."""
        view = doc.ActiveView
        filter_colors = {}
        try:
            filters = view.GetFilters()
            for fid in filters:
                felem = doc.GetElement(fid)
                ogs = view.GetFilterOverrides(fid)
                color = ogs.SurfaceForegroundPatternColor
                if color.IsValid:
                    filter_colors[felem.Name] = (color.Red, color.Green, color.Blue)
        except: pass
        return filter_colors

    def RestoreState(self):
        """Restaura o estado em Cascata."""
        if not self.saved_state: return

        # 1. Escopo
        if self.saved_state.get("scope") == "Project":
            self.rbProject.IsChecked = True

        # 2. Categorias
        saved_cats = self.saved_state.get("categories", [])
        if saved_cats:
            for item in self.lbCategories.Items:
                if item.Name in saved_cats:
                    self.lbCategories.SelectedItems.Add(item)
            self.UpdateParametersList()

        # 3. Parâmetros
        saved_params = self.saved_state.get("parameters", [])
        if saved_params:
            for p_name in saved_params:
                if p_name in self.all_params:
                    self.lbParameters.SelectedItems.Add(p_name)
            self.UpdateValuesList()

    def OnWindowClosing(self, sender, args):
        state = {
            "scope": "Project" if self.rbProject.IsChecked else "ActiveView",
            "categories": [c.Name for c in self.lbCategories.SelectedItems],
            "parameters": [str(p) for p in self.lbParameters.SelectedItems],
            "colors": {item.Value: (item.R, item.G, item.B) for item in self.current_values},
            "checked": {item.Value: item.IsChecked for item in self.current_values}
        }
        StateManager.save(state)

    # --- CHECKBOX ACTIONS ---
    def OnSelectAllClick(self, sender, args):
        """Marca todos os valores."""
        for item in self.current_values:
            item.IsChecked = True
        self.lvValues.Items.Refresh()  # FIX: Forçar atualização da UI
        self.txtStatus.Text = "Todos marcados ({} valores).".format(len(self.current_values))

    def OnDeselectAllClick(self, sender, args):
        """Desmarca todos os valores."""
        for item in self.current_values:
            item.IsChecked = False
        self.lvValues.Items.Refresh()  # FIX: Forçar atualização da UI
        self.txtStatus.Text = "Todos desmarcados."

    # --- CORE LOGIC ---
    def GetCollector(self):
        if self.rbProject.IsChecked: return FilteredElementCollector(doc)
        return FilteredElementCollector(doc, doc.ActiveView.Id)

    def PopulateCategories(self):
        collector = self.GetCollector().WhereElementIsNotElementType()
        categories = []; unique_cats = set()
        for elem in collector:
            cat = elem.Category
            if cat:
                cat_id_val = GetIdValue(cat.Id)
                if cat_id_val not in CAT_EXCLUDED and cat_id_val not in unique_cats:
                    unique_cats.add(cat_id_val); categories.append(cat)
        categories.sort(key=lambda x: x.Name)
        self.lbCategories.ItemsSource = categories
        self.txtStatus.Text = "{} categorias.".format(len(categories))

    def OnScopeChanged(self, sender, args):
        self.PopulateCategories()
        self.lbParameters.ItemsSource = None
        self.current_values.Clear()

    def OnCategoryChanged(self, sender, args):
        self.UpdateParametersList()

    def UpdateParametersList(self):
        selected_cats = list(self.lbCategories.SelectedItems)
        if not selected_cats:
            self.lbParameters.ItemsSource = None
            return

        self.txtStatus.Text = "Analisando parâmetros..."
        WinFormsApp.DoEvents()

        selected_cat_ids = set([GetIdValue(c.Id) for c in selected_cats])
        cat_params = {cid: set() for cid in selected_cat_ids}
        collector = self.GetCollector().WhereElementIsNotElementType()

        def extract_params(element, target_set):
            for p in element.Parameters: target_set.add(p.Definition.Name)
            try:
                type_id = element.GetTypeId()
                if type_id != ElementId.InvalidElementId:
                    if type_id not in self.type_cache:
                        elem_type = doc.GetElement(type_id)
                        # Validar elemento antes de cachear
                        if elem_type:
                            self.type_cache[type_id] = elem_type
                    else:
                        elem_type = self.type_cache[type_id]
                        if elem_type:
                            for p in elem_type.Parameters: target_set.add(p.Definition.Name)
            except: pass

        count_map = {cid: 0 for cid in selected_cat_ids}
        for elem in collector:
            if elem.Category:
                cid = GetIdValue(elem.Category.Id)
                if cid in selected_cat_ids and count_map[cid] < 20:
                    extract_params(elem, cat_params[cid])
                    count_map[cid] += 1

        common_params = None
        for cid in selected_cat_ids:
            if count_map[cid] > 0:
                if common_params is None: common_params = cat_params[cid]
                else: common_params = common_params.intersection(cat_params[cid])

        if common_params is None: common_params = []
        self.all_params = sorted(list(common_params))
        self.lbParameters.ItemsSource = self.all_params
        self.txtStatus.Text = "{} parâmetros comuns.".format(len(self.all_params))

    def OnSearchFocus(self, sender, args):
        if self.txtSearch.Text == "Buscar...":
            self.txtSearch.Text = ""; self.txtSearch.Foreground = Brushes.Black

    def OnSearchChanged(self, sender, args):
        text = self.txtSearch.Text.lower()
        if not text or text == "buscar...":
            self.lbParameters.ItemsSource = self.all_params
            return
        filtered = [p for p in self.all_params if text in p.lower()]
        self.lbParameters.ItemsSource = filtered

    def OnParameterChanged(self, sender, args):
        self.UpdateValuesList()

    def UpdateValuesList(self):
        selected_params = list(self.lbParameters.SelectedItems)
        if not selected_params: return

        self.current_values.Clear()
        self.txtStatus.Text = "Lendo valores..."
        WinFormsApp.DoEvents()

        selected_cats = list(self.lbCategories.SelectedItems)
        cat_ids = [c.Id for c in selected_cats]
        cat_filter = ElementMulticategoryFilter(List[ElementId](cat_ids))
        collector = self.GetCollector().WherePasses(cat_filter).WhereElementIsNotElementType()

        values_map = {}
        elements = list(collector)
        total = len(elements)

        for i, elem in enumerate(elements):
            if i % 200 == 0:
                self.txtStatus.Text = "Lendo: {}/{}...".format(i, total)
                WinFormsApp.DoEvents()

            val_parts = []
            valid_element = False
            for p_name in selected_params:
                v = self.GetParamValue(elem, p_name)
                if v is not None:
                    val_parts.append(v)
                    valid_element = True
                else:
                    val_parts.append("-")

            if not valid_element: continue

            full_val = " | ".join(val_parts)
            if full_val not in values_map: values_map[full_val] = []
            values_map[full_val].append(elem.Id)

        saved_colors = self.saved_state.get("colors", {})
        saved_checked = self.saved_state.get("checked", {})

        for key in sorted(values_map.keys()):
            r, g, b = None, None, None
            is_checked = saved_checked.get(key, True)  # Por padrão marcado

            # 1. Recuperar do State
            if key in saved_colors:
                r, g, b = saved_colors[key]
            # 2. Engenharia Reversa
            else:
                p_names_str = "_".join(selected_params)
                safe_val = "".join([c for c in key if c.isalnum() or c in (' ', '_', '-')])
                expected_filter_name = "{} = {}".format(p_names_str, safe_val)

                if expected_filter_name in self.existing_filters_cache:
                    r, g, b = self.existing_filters_cache[expected_filter_name]

            self.current_values.Add(ValueItem(key, values_map[key], r, g, b, is_checked))

        self.txtStatus.Text = "Concluído: {} valores.".format(len(self.current_values))

    def GetParamValue(self, elem, param_name):
        param = elem.LookupParameter(param_name)
        if not param:
            try:
                type_id = elem.GetTypeId()
                if type_id != ElementId.InvalidElementId:
                    if type_id not in self.type_cache:
                        self.type_cache[type_id] = doc.GetElement(type_id)
                    t = self.type_cache[type_id]
                    if t: param = t.LookupParameter(param_name)
            except: pass
        if not param:
            for p in elem.Parameters:
                if p.Definition.Name == param_name:
                    param = p
                    break
        if not param: return None
        if param.StorageType == StorageType.String: v = param.AsString()
        else: v = param.AsValueString()
        return v if v and v.strip() != "" else "<Vazio>"

    def OnRandomClick(self, sender, args):
        for item in self.current_values:
            item.R = random.randint(50, 240)
            item.G = random.randint(50, 240)
            item.B = random.randint(50, 240)
            item.UpdateBrush()
        self.lvValues.Items.Refresh()

    def OnGradientClick(self, sender, args):
        if len(self.current_values) < 2: return
        steps = len(self.current_values)
        sR, sG, sB = 65, 105, 225
        eR, eG, eB = 220, 20, 60
        for i, item in enumerate(self.current_values):
            r = float(i) / (steps - 1)
            item.R = int(sR + (eR - sR) * r)
            item.G = int(sG + (eG - sG) * r)
            item.B = int(sB + (eB - sB) * r)
            item.UpdateBrush()
        self.lvValues.Items.Refresh()

    def OnValueDoubleClick(self, sender, args):
        if self.lvValues.SelectedItem:
            item = self.lvValues.SelectedItem
            try:
                cd = ColorDialog()
                cd.Color = System.Drawing.Color.FromArgb(item.R, item.G, item.B)
                if cd.ShowDialog() == DialogResult.OK:
                    item.R, item.G, item.B = cd.Color.R, cd.Color.G, cd.Color.B
                    item.UpdateBrush()
                    self.lvValues.Items.Refresh()
            except: pass

    # --- ACTIONS (MODAL) ---
    def OnApplyClick(self, sender, args):
        if not self.current_values: return

        # NOVO: Aplicar apenas valores marcados
        checked_items = [item for item in self.current_values if item.IsChecked]
        if not checked_items:
            forms.alert("Nenhum valor marcado! Marque os valores que deseja colorir.")
            return

        solid = GetSolidFill(doc)
        if solid == ElementId.InvalidElementId:
            forms.alert("Padrão Sólido não encontrado.")
            return

        view = doc.ActiveView
        with _transaction.ef_Transaction(doc, "Color-FiLL Forge: Aplicar"):
            for item in checked_items:
                ogs = OverrideGraphicSettings()
                c = item.GetRevitColor()
                ogs.SetSurfaceForegroundPatternId(solid)
                ogs.SetSurfaceForegroundPatternColor(c)
                ogs.SetCutForegroundPatternId(solid)
                ogs.SetCutForegroundPatternColor(c)
                for eid in item.ElementIds:
                    try: view.SetElementOverrides(eid, ogs)
                    except: pass

        uidoc.RefreshActiveView()
        self.txtStatus.Text = "Cores aplicadas! ({} valores marcados)".format(len(checked_items))

    def OnResetClick(self, sender, args):
        """
        Reseta as cores dos elementos para o padrão.
        Prioridade:
        1. Se houver valores carregados, reseta os elementos desses valores
        2. Se não, reseta todos os elementos das categorias selecionadas
        """
        view = doc.ActiveView
        reset_count = 0

        with _transaction.ef_Transaction(doc, "Color-FiLL Forge: Reset"):
            # MÉTODO 1: Usar elementos dos valores carregados (mais preciso)
            if self.current_values and len(self.current_values) > 0:
                for item in self.current_values:
                    for eid in item.ElementIds:
                        try:
                            view.SetElementOverrides(eid, OverrideGraphicSettings())
                            reset_count += 1
                        except:
                            pass
            else:
                # MÉTODO 2: Fallback - usar categorias selecionadas
                cats = [c.Id for c in self.lbCategories.SelectedItems]
                if not cats:
                    forms.alert("Nenhuma categoria selecionada e nenhum valor carregado.\n\nSelecione categorias ou carregue valores primeiro.", exitscript=False)
                    return

                try:
                    coll = FilteredElementCollector(doc, view.Id)\
                        .WherePasses(ElementMulticategoryFilter(List[ElementId](cats)))\
                        .ToElementIds()
                    for eid in coll:
                        try:
                            view.SetElementOverrides(eid, OverrideGraphicSettings())
                            reset_count += 1
                        except:
                            pass
                except Exception as e:
                    forms.alert("Erro ao resetar por categoria: {}".format(str(e)), exitscript=False)
                    return

        uidoc.RefreshActiveView()
        self.txtStatus.Text = "Resetado! ({} elementos)".format(reset_count)

    # --- PRESET MANAGEMENT ---
    def OnSavePresetClick(self, sender, args):
        """Salva esquema de cores atual como preset nomeado."""
        if not self.current_values:
            forms.alert("Nenhuma cor definida para salvar!", exitscript=False)
            return

        # Pedir nome do preset
        preset_name = forms.ask_for_string(
            prompt="Nome do preset:",
            title="Salvar Preset de Cores",
            default="Meu Preset"
        )

        if not preset_name:
            return  # Usuário cancelou

        # Coletar dados de cores: {valor: (R, G, B)}
        colors_data = {}
        for item in self.current_values:
            colors_data[item.Value] = (item.R, item.G, item.B)

        # Salvar usando PresetManager
        if PresetManager.save_preset(preset_name, colors_data):
            self.txtStatus.Text = "Preset '{}' salvo com {} cores.".format(preset_name, len(colors_data))
            forms.alert("Preset '{}' salvo com sucesso!\n\n{} cores salvas.".format(preset_name, len(colors_data)), exitscript=False)
        else:
            forms.alert("Erro ao salvar preset '{}'.".format(preset_name), exitscript=False)

    def OnLoadPresetClick(self, sender, args):
        """Carrega preset salvo e aplica cores aos valores atuais."""
        if not self.current_values:
            forms.alert("Nenhum valor na lista para aplicar cores!", exitscript=False)
            return

        # Listar presets disponíveis
        presets = PresetManager.list_presets()
        if not presets:
            forms.alert("Nenhum preset salvo encontrado!\n\nSalve um preset primeiro usando o botão 💾 Salvar.", exitscript=False)
            return

        # Criar menu com opção de deletar
        options = presets + ["🗑️ Deletar preset..."]
        selected = forms.CommandSwitchWindow.show(
            options,
            message="Selecione o preset para carregar:"
        )

        if not selected:
            return  # Usuário cancelou

        # Se escolheu deletar
        if selected == "🗑️ Deletar preset...":
            preset_to_delete = forms.CommandSwitchWindow.show(
                presets,
                message="Selecione o preset para DELETAR:"
            )
            if preset_to_delete:
                if PresetManager.delete_preset(preset_to_delete):
                    self.txtStatus.Text = "Preset '{}' deletado.".format(preset_to_delete)
                    forms.alert("Preset '{}' deletado com sucesso!".format(preset_to_delete), exitscript=False)
                else:
                    forms.alert("Erro ao deletar preset '{}'.".format(preset_to_delete), exitscript=False)
            return

        # Carregar preset selecionado
        colors_data = PresetManager.load_preset(selected)
        if not colors_data:
            forms.alert("Erro ao carregar preset '{}'.".format(selected), exitscript=False)
            return

        # Aplicar cores aos valores correspondentes
        applied_count = 0
        for item in self.current_values:
            if item.Value in colors_data:
                r, g, b = colors_data[item.Value]
                item.R, item.G, item.B = int(r), int(g), int(b)
                item.UpdateBrush()
                applied_count += 1

        # Atualizar UI
        self.lvValues.Items.Refresh()
        self.txtStatus.Text = "Preset '{}' carregado ({}/{} cores aplicadas).".format(
            selected, applied_count, len(self.current_values)
        )

        if applied_count < len(self.current_values):
            forms.alert(
                "Preset '{}' carregado!\n\n{} de {} valores tiveram cores aplicadas.\n\nValores não encontrados no preset mantiveram suas cores atuais.".format(
                    selected, applied_count, len(self.current_values)
                ),
                exitscript=False
            )
        else:
            forms.alert("Preset '{}' carregado com sucesso!\n\nTodas as {} cores foram aplicadas.".format(selected, applied_count), exitscript=False)

    def OnCreateFilters(self, sender, args):
        if not self.current_values: return

        # NOVO: Criar filtros apenas para valores marcados
        checked_items = [item for item in self.current_values if item.IsChecked]
        if not checked_items:
            forms.alert("Nenhum valor marcado! Marque os valores que deseja criar filtros.")
            return

        selected_param_names = list(self.lbParameters.SelectedItems)
        cat_ids = List[ElementId]([c.Id for c in self.lbCategories.SelectedItems])
        solid = GetSolidFill(doc)

        first_elem_id = checked_items[0].ElementIds[0]
        first_elem = doc.GetElement(first_elem_id)

        # MODIFICADO: Armazenar Parameter objects, não apenas IDs
        params = {}
        for p_name in selected_param_names:
            p = first_elem.LookupParameter(p_name)
            if not p:
                try: p = doc.GetElement(first_elem.GetTypeId()).LookupParameter(p_name)
                except: pass
            if p: params[p_name] = p

        if len(params) != len(selected_param_names):
            forms.alert("Não foi possível encontrar os parâmetros selecionados.")
            return

        with _transaction.ef_Transaction(doc, "Criar Filtros"):
            for item in checked_items:
                val_parts = item.Value.split(" | ")
                if len(val_parts) != len(selected_param_names): continue

                rules = List[FilterRule]()
                for i, p_name in enumerate(selected_param_names):
                    param = params[p_name]
                    val = val_parts[i]

                    # CORRIGIDO: Usar função helper que detecta StorageType
                    rule = CreateFilterRuleForParameter(doc, param, val, rvt_year)
                    if rule:
                        rules.Add(rule)

                if rules.Count == 0: continue

                if rules.Count == 1: final_filter = ElementParameterFilter(rules[0])
                else:
                    elem_filters = List[ElementFilter]()
                    for r in rules: elem_filters.Add(ElementParameterFilter(r))
                    final_filter = LogicalAndFilter(elem_filters)

                p_names_str = "_".join(selected_param_names)
                safe_val = "".join([c for c in item.Value if c.isalnum() or c in (' ', '_', '-')])
                f_name = "{} = {}".format(p_names_str, safe_val)

                f_elem = None
                exist = FilteredElementCollector(doc).OfClass(ParameterFilterElement)
                for e in exist:
                    if e.Name == f_name: f_elem = e; break

                if not f_elem:
                    try: f_elem = ParameterFilterElement.Create(doc, f_name, cat_ids, final_filter)
                    except: continue
                else:
                    try: f_elem.SetCategories(cat_ids)
                    except: pass

                # Preparar OverrideGraphicSettings
                ogs = OverrideGraphicSettings()
                c = item.GetRevitColor()
                ogs.SetSurfaceForegroundPatternId(solid)
                ogs.SetSurfaceForegroundPatternColor(c)
                ogs.SetCutForegroundPatternId(solid)
                ogs.SetCutForegroundPatternColor(c)

                # Determinar vistas alvo
                if self.chkAllViews.IsChecked:
                    # Aplicar em todas as vistas compativeis
                    target_views = []
                    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
                    for v in all_views:
                        try:
                            # Ignorar templates, legendas, schedules, etc
                            if v.IsTemplate:
                                continue
                            vt = v.ViewType
                            if vt in [ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.ThreeD,
                                     ViewType.Section, ViewType.Elevation, ViewType.AreaPlan,
                                     ViewType.EngineeringPlan, ViewType.Detail]:
                                target_views.append(v)
                        except:
                            pass
                else:
                    target_views = [doc.ActiveView]

                # Aplicar filtro em cada vista
                for view in target_views:
                    try:
                        view.AddFilter(f_elem.Id)
                        view.SetFilterVisibility(f_elem.Id, True)
                        view.SetFilterOverrides(f_elem.Id, ogs)
                    except:
                        pass

        if self.chkAllViews.IsChecked:
            self.txtStatus.Text = "Filtros criados em todas as vistas! ({} valores)".format(len(checked_items))
        else:
            self.txtStatus.Text = "Filtros Criados! ({} marcados)".format(len(checked_items))

    def OnOpenLegendDialog(self, sender, args):
        if not self.current_values: return

        # Contar valores marcados
        checked_items = [item for item in self.current_values if item.IsChecked]
        if not checked_items:
            forms.alert("Nenhum valor marcado! Marque os valores que deseja incluir na legenda.")
            return

        def callback(config):
            self.CreateLegendLogic(config)

        self.legend_config_window = LegendConfigWindow(callback, len(checked_items))
        self.legend_config_window.ShowDialog()

    def CreateLegendLogic(self, config):
        """Cria legenda usando método de DUPLICAÇÃO (Template-Based).

        IMPORTANTE: A API do Revit NÃO permite criar Legend views do zero.
        Devemos duplicar uma legenda existente e modificá-la.
        """
        try:
            # v7.0: Verificar e importar família TAG Legenda items.rfa se necessário
            # Usar caminho relativo ao script
            script_dir = os.path.dirname(__file__)
            tag_family_path = os.path.join(script_dir, "TAG Legenda items.rfa")
            tag_family_loaded = False

            # Verificar se a família já existe
            for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
                try:
                    if symbol.Family.Name == "TAG Legenda items":
                        tag_family_loaded = True
                        break
                except:
                    pass

            # Se não existe, importar
            if not tag_family_loaded:
                if os.path.exists(tag_family_path):
                    try:
                        with _transaction.ef_Transaction(doc, "Importar Família Tag"):
                            if doc.LoadFamily(tag_family_path):
                                tag_family_loaded = True
                            else:
                                print("ERRO: LoadFamily retornou False ao importar TAG Legenda items")
                    except Exception as e:
                        print("ERRO ao importar família TAG Legenda items: {}".format(str(e)))
                        forms.alert("ERRO: Não foi possível importar a família TAG Legenda items.rfa\n\nCaminho: {}\n\nErro: {}".format(
                            tag_family_path, str(e)))
                        return
                else:
                    forms.alert("ERRO: Arquivo de família não encontrado!\n\nCaminho esperado:\n{}".format(tag_family_path))
                    return

            # NOVO: Criar legenda apenas para valores marcados
            checked_items = [item for item in self.current_values if item.IsChecked]
            if not checked_items:
                forms.alert("Nenhum valor marcado! Marque os valores que deseja incluir na legenda.")
                return

            # Ordenar itens conforme configuração
            if config["order"] == "alpha":
                checked_items = sorted(checked_items, key=lambda x: x.Value)
            elif config["order"] == "count":
                checked_items = sorted(checked_items, key=lambda x: x.Count, reverse=True)
            # Se "original", mantém a ordem atual

            solid = GetSolidFill(doc)
            if solid == ElementId.InvalidElementId:
                forms.alert("Padrão sólido não encontrado.")
                return

            # PASSO 1: Buscar legendas existentes no projeto
            existing_legends = []
            all_views = FilteredElementCollector(doc).OfClass(View)
            for v in all_views:
                try:
                    if v.ViewType == ViewType.Legend and not v.IsTemplate:
                        existing_legends.append(v)
                except:
                    pass

            # Se não há legendas, tentar criar uma drafting view como fallback
            template_view = None
            if not existing_legends:
                # Buscar ViewFamilyType de Drafting (fallback)
                drafting_type = None
                for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
                    if vft.ViewFamily == ViewFamily.Drafting:
                        drafting_type = vft
                        break

                if not drafting_type:
                    forms.alert("ERRO: Não foi possível criar legenda.\n\n"
                              "A API do Revit exige uma legenda existente como template.\n"
                              "Crie manualmente uma legenda vazia no projeto primeiro:\n"
                              "View > Create > Legend\n\n"
                              "Depois execute este comando novamente.")
                    return

                # Criar uma drafting view como alternativa
                with _transaction.ef_Transaction(doc, "Criar Vista Base"):
                    template_view = ViewDrafting.Create(doc, drafting_type.Id)
                    template_view.Name = "ColorFiLLForge_Base_" + str(random.randint(1000,9999))
            else:
                # Usar a primeira legenda encontrada como template
                template_view = existing_legends[0]

            # PASSO 2: Duplicar a vista template
            with _transaction.ef_Transaction(doc, "Criar Legenda"):
                # Duplicar vista
                new_view_id = template_view.Duplicate(ViewDuplicateOption.Duplicate)
                view = doc.GetElement(new_view_id)

                # Configurar nome
                try:
                    view.Name = config["title"]
                except:
                    view.Name = config["title"] + "_" + str(random.randint(1,999))

                # Configurar escala 1"=1' (scale 12)
                try:
                    view.Scale = 12
                except:
                    pass

                # PASSO 3: Limpar conteúdo existente da vista duplicada
                elements_to_delete = []
                view_elements = FilteredElementCollector(doc, view.Id).ToElements()
                for elem in view_elements:
                    if isinstance(elem, FilledRegion) or isinstance(elem, TextNote):
                        elements_to_delete.append(elem.Id)

                if elements_to_delete:
                    try:
                        doc.Delete(List[ElementId](elements_to_delete))
                    except:
                        pass

                # Usar o tipo de texto selecionado diretamente pelo usuário
                selected_text_type_id = config.get("text_type_id")

                if selected_text_type_id:
                    # Usar o tipo selecionado para corpo e título
                    body_type = selected_text_type_id

                    # Tentar encontrar versão com underline do mesmo tipo para o título
                    title_type = None
                    selected_type = doc.GetElement(selected_text_type_id)
                    if selected_type:
                        selected_name = selected_type.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()

                        # Buscar versão com underline para o título
                        for txt_type in FilteredElementCollector(doc).OfClass(TextNoteType):
                            try:
                                type_name = txt_type.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
                                if type_name and "Underline" in type_name:
                                    # Verificar se tem o mesmo tamanho base
                                    if selected_name.replace(" Underline", "").replace(" underline", "") in type_name:
                                        title_type = txt_type.Id
                                        break
                            except:
                                pass

                    # Se não encontrar título com underline, usar o mesmo tipo
                    if not title_type:
                        title_type = selected_text_type_id
                else:
                    # Fallback: usar primeiro tipo disponível
                    first_type = FilteredElementCollector(doc).OfClass(TextNoteType).FirstElementId()
                    title_type = first_type
                    body_type = first_type

                # ===== CONVERSÃO: Polegadas → Pés =====
                # 1 inch = 1/12 feet = 0.0833333 ft
                def inches_to_feet(inches):
                    return inches / 12.0

                # Converter todas as dimensões de polegadas para pés
                box_width = inches_to_feet(config["width"])
                box_height = inches_to_feet(config["height"])
                text_offset = inches_to_feet(config["offset"])
                line_spacing = inches_to_feet(config["spacing"])
                title_spacing = inches_to_feet(config["title_spacing"])
                border_offset = inches_to_feet(config["border_offset"]) if config["draw_border"] else 0.0

                # v7.0: Criar FilledRegionType CS_Border_White (usado para borda E título)
                # Importante: CS_Border_White deve ter BackgroundPatternId = InvalidElementId (máscara desabilitada)
                border_fr_type = None
                for frt in FilteredElementCollector(doc).OfClass(FilledRegionType):
                    try:
                        if frt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() == "CS_Border_White":
                            border_fr_type = frt
                            break
                    except:
                        pass

                if not border_fr_type:
                    temp = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
                    if temp:
                        border_fr_type = temp.Duplicate("CS_Border_White")
                        border_fr_type.ForegroundPatternId = solid
                        border_fr_type.ForegroundPatternColor = Color(255, 255, 255)  # Branco
                        # v7.0: DESABILITAR background pattern E máscara
                        border_fr_type.BackgroundPatternId = ElementId.InvalidElementId
                        # v7.0: DESABILITAR máscara (IsMasking = False)
                        try:
                            border_fr_type.IsMasking = False
                        except:
                            pass

                # v7.0.5: PASSO 3A: Calcular posição do título
                # Título deve estar centralizado no eixo X, 1" da borda superior
                # Borda superior está a 3" da primeira caixa
                border_top = -inches_to_feet(3.0)  # Borda superior a 3" acima
                title_y = border_top - inches_to_feet(1.0)  # Título 1" abaixo da borda superior

                # Centralizar no eixo X (centro do conteúdo)
                title_x = border_offset + (box_width / 2.0)

                # v7.0.5: Inicializar variáveis para título
                title_right_x = 0.0
                title_tag = None
                title_region_created = False

                # Posição inicial dos itens (abaixo do título + espaçamento configurado)
                start_y = title_y - title_spacing
                y = start_y

                # PASSO 4: Criar novos elementos (FilledRegions + Tags)
                regions_created = 0
                texts_created = 0
                max_tag_x = border_offset + box_width + text_offset  # Rastrear posição X máxima das tags

                for idx, item in enumerate(checked_items):
                    filled_region = None  # Inicializar para evitar referência antes de atribuição
                    # Criar ou reutilizar FilledRegionType
                    fr_name = "CS_RGB_{}_{}_{}".format(item.R, item.G, item.B)
                    fr_type = None

                    # Buscar tipo existente
                    for frt in FilteredElementCollector(doc).OfClass(FilledRegionType):
                        try:
                            if frt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() == fr_name:
                                fr_type = frt
                                break
                        except:
                            pass

                    # Criar novo se não existir
                    if not fr_type:
                        temp = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
                        if temp:
                            try:
                                fr_type = temp.Duplicate(fr_name)
                                fr_type.ForegroundPatternId = solid
                                fr_type.ForegroundPatternColor = item.GetRevitColor()
                                # DESABILITAR background pattern (sem marcação de borda)
                                fr_type.BackgroundPatternId = ElementId.InvalidElementId
                            except Exception as e:
                                print("Erro ao criar FilledRegionType: {}".format(str(e)))

                    if fr_type:
                        # Criar retângulo colorido (1" x 1") com border offset
                        x_start = border_offset
                        x_end = border_offset + box_width

                        loop = CurveLoop()
                        loop.Append(Line.CreateBound(XYZ(x_start, y, 0), XYZ(x_end, y, 0)))
                        loop.Append(Line.CreateBound(XYZ(x_end, y, 0), XYZ(x_end, y - box_height, 0)))
                        loop.Append(Line.CreateBound(XYZ(x_end, y - box_height, 0), XYZ(x_start, y - box_height, 0)))
                        loop.Append(Line.CreateBound(XYZ(x_start, y - box_height, 0), XYZ(x_start, y, 0)))

                        try:
                            filled_region = FilledRegion.Create(doc, fr_type.Id, view.Id, List[CurveLoop]([loop]))
                            regions_created += 1

                            # Preencher parâmetro Comments com o texto do item
                            text_content = item.Value
                            if config["show_count"]:
                                text_content = "{} ({})".format(item.Value, item.Count)

                            # Definir parâmetro Comments (usado pelas tags)
                            try:
                                comments_param = filled_region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                                if comments_param and not comments_param.IsReadOnly:
                                    comments_param.Set(text_content)
                            except:
                                pass

                        except Exception as e:
                            print("ERRO ao criar FilledRegion {}: {}".format(idx, str(e)))

                    # v7.0: Criar Tag (TAG Legenda items) - SEM fallback para TextNote
                    tag_created = False

                    if filled_region:
                        doc.Regenerate()

                        try:
                            # v7.0: Buscar FamilySymbol "TAG Legenda items" especificamente
                            tag_symbol = None
                            for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
                                try:
                                    if symbol.Family.Name == "TAG Legenda items":
                                        tag_symbol = symbol
                                        break
                                except:
                                    pass

                            if tag_symbol:
                                if not tag_symbol.IsActive:
                                    tag_symbol.Activate()

                                # Posição da tag: ao lado direito da caixa, centro vertical
                                tag_x = border_offset + box_width + text_offset
                                tag_y = y - (box_height / 2.0)
                                tag_position = XYZ(tag_x, tag_y, 0)

                                try:
                                    new_tag = IndependentTag.Create(
                                        doc,
                                        view.Id,
                                        Reference(filled_region),
                                        False,
                                        TagMode.TM_ADDBY_CATEGORY,
                                        TagOrientation.Horizontal,
                                        tag_position
                                    )

                                    if new_tag:
                                        new_tag.ChangeTypeId(tag_symbol.Id)
                                        tag_created = True
                                        texts_created += 1

                                        # v7.0.3: Calcular max_tag_x usando BoundingBox real da tag
                                        doc.Regenerate()
                                        try:
                                            tag_bbox = new_tag.get_BoundingBox(view)
                                            if tag_bbox:
                                                actual_tag_right = tag_bbox.Max.X
                                                if actual_tag_right > max_tag_x:
                                                    max_tag_x = actual_tag_right
                                        except:
                                            pass
                                except Exception as e:
                                    print("ERRO ao criar Tag para item {}: {}".format(idx, str(e)))
                            else:
                                print("ERRO CRÍTICO: Família 'TAG Legenda items' não encontrada no projeto!")

                        except Exception as e:
                            print("ERRO ao processar Tag para item {}: {}".format(idx, str(e)))

                    # v7.0: REMOVIDO fallback para TextNote - apenas Tags são usadas
                    if not tag_created:
                        print("AVISO: Tag não criada para item {} - verifique família TAG Legenda items".format(idx))

                    # Próximo item (descer = altura do box + espaçamento)
                    y -= (box_height + line_spacing)

                # v7.0.5: PASSO 5: Desenhar borda externa usando CS_Border_White (se configurado)
                # border_top já foi definido anteriormente como -inches_to_feet(3.0)
                border_created = False
                if config["draw_border"]:
                    try:
                        # v7.0.6: Calcular borda inferior com valor configurável
                        border_left = 0.0
                        border_right_temp = max_tag_x + inches_to_feet(2.0)  # Temporário maior
                        border_bottom = y - inches_to_feet(config["border_bottom"])

                        # v7.0: Usar border_fr_type já criado anteriormente
                        if border_fr_type:
                            # Criar borda temporária
                            border_loop_temp = CurveLoop()
                            border_loop_temp.Append(Line.CreateBound(XYZ(border_left, border_top, 0), XYZ(border_right_temp, border_top, 0)))
                            border_loop_temp.Append(Line.CreateBound(XYZ(border_right_temp, border_top, 0), XYZ(border_right_temp, border_bottom, 0)))
                            border_loop_temp.Append(Line.CreateBound(XYZ(border_right_temp, border_bottom, 0), XYZ(border_left, border_bottom, 0)))
                            border_loop_temp.Append(Line.CreateBound(XYZ(border_left, border_bottom, 0), XYZ(border_left, border_top, 0)))

                            border_region = FilledRegion.Create(doc, border_fr_type.Id, view.Id, List[CurveLoop]([border_loop_temp]))

                            # v7.0.8: Preencher Comments da borda temporária
                            comments_param_temp = border_region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                            if comments_param_temp and not comments_param_temp.IsReadOnly:
                                comments_param_temp.Set(config["title"])
                            doc.Regenerate()

                            # v7.0.8: Criar tag do título na borda temporária para obter BoundingBox
                            title_tag_temp = None
                            title_right_x = 0.0  # Se falhar, cairá no else (max_tag_x + 1") - comportamento correto
                            try:
                                # Buscar tag symbol TAG Legenda items
                                tag_symbol = None
                                for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
                                    try:
                                        if symbol.Family.Name == "TAG Legenda items":
                                            tag_symbol = symbol
                                            break
                                    except:
                                        pass

                                if tag_symbol:
                                    if not tag_symbol.IsActive:
                                        tag_symbol.Activate()
                                        doc.Regenerate()

                                    # Criar tag temporária
                                    temp_tag_position = XYZ(border_left + inches_to_feet(1.0), border_top - inches_to_feet(0.5), 0)
                                    title_tag_temp = IndependentTag.Create(
                                        doc,
                                        view.Id,
                                        Reference(border_region),
                                        False,
                                        TagMode.TM_ADDBY_CATEGORY,
                                        TagOrientation.Horizontal,
                                        temp_tag_position
                                    )
                                    title_tag_temp.ChangeTypeId(tag_symbol.Id)
                                    doc.Regenerate()

                                    # Mover tag para posição correta
                                    title_tag_temp.TagHeadPosition = XYZ(title_x, title_y, 0)
                                    doc.Regenerate()

                                    # Obter BoundingBox do título
                                    try:
                                        title_bbox = title_tag_temp.get_BoundingBox(view)
                                        if title_bbox:
                                            title_right_x = title_bbox.Max.X
                                    except:
                                        pass

                            except Exception as title_e:
                                print("ERRO ao criar tag temporária do título: {}".format(str(title_e)))

                            # v7.0.8: Comparar título vs tags e calcular borda_right final
                            if title_right_x > max_tag_x:
                                # Título é maior - usar border_offset como margem direita (simetria)
                                border_right = title_right_x + border_offset
                            else:
                                # Tags dos itens são maiores - usar 1" como margem
                                border_right = max_tag_x + inches_to_feet(1.0)

                            # v7.1: RECALCULAR title_x para centralizar na largura final da borda
                            largura_total_borda = border_right - border_left
                            title_x = border_left + (largura_total_borda / 2.0)

                            # Deletar borda temporária (e tag associada será deletada automaticamente)
                            doc.Delete(border_region.Id)
                            doc.Regenerate()

                            # Recriar com dimensões finais corretas
                            final_border_loop = CurveLoop()
                            final_border_loop.Append(Line.CreateBound(XYZ(border_left, border_top, 0), XYZ(border_right, border_top, 0)))
                            final_border_loop.Append(Line.CreateBound(XYZ(border_right, border_top, 0), XYZ(border_right, border_bottom, 0)))
                            final_border_loop.Append(Line.CreateBound(XYZ(border_right, border_bottom, 0), XYZ(border_left, border_bottom, 0)))
                            final_border_loop.Append(Line.CreateBound(XYZ(border_left, border_bottom, 0), XYZ(border_left, border_top, 0)))

                            final_border_region = FilledRegion.Create(doc, border_fr_type.Id, view.Id, List[CurveLoop]([final_border_loop]))

                            # Preencher Comments da borda final
                            final_comments_param = final_border_region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                            if final_comments_param and not final_comments_param.IsReadOnly:
                                final_comments_param.Set(config["title"])
                            doc.Regenerate()

                            # v7.0.8: Criar tag do título FINAL na borda final
                            try:
                                if tag_symbol:
                                    # Criar tag final
                                    temp_tag_position = XYZ(border_left + inches_to_feet(1.0), border_top - inches_to_feet(0.5), 0)
                                    title_tag = IndependentTag.Create(
                                        doc,
                                        view.Id,
                                        Reference(final_border_region),
                                        False,
                                        TagMode.TM_ADDBY_CATEGORY,
                                        TagOrientation.Horizontal,
                                        temp_tag_position
                                    )
                                    title_tag.ChangeTypeId(tag_symbol.Id)
                                    doc.Regenerate()

                                    # v1.1: Centralizar tag usando BoundingBox
                                    # Primeiro posicionar em qualquer lugar para obter bbox
                                    title_tag.TagHeadPosition = XYZ(title_x, title_y, 0)
                                    doc.Regenerate()

                                    # Obter largura real da tag
                                    try:
                                        tag_bbox = title_tag.get_BoundingBox(view)
                                        if tag_bbox:
                                            tag_width = tag_bbox.Max.X - tag_bbox.Min.X
                                            # Calcular posição para centralizar: centro - metade da largura
                                            centered_x = title_x - (tag_width / 2.0)
                                            title_tag.TagHeadPosition = XYZ(centered_x, title_y, 0)
                                            doc.Regenerate()
                                    except:
                                        pass  # Se falhar, manter posição original

                                    title_region_created = True

                            except Exception as title_e:
                                print("ERRO ao criar tag final do título: {}".format(str(title_e)))

                            border_created = True

                        else:
                            print("ERRO: CS_Border_White não encontrado")

                    except Exception as e:
                        print("Erro ao criar borda: {}".format(str(e)))


            # Abrir a vista criada
            try:
                uidoc.ActiveView = view
            except Exception as e:
                print("Aviso: Não foi possível abrir vista automaticamente: {}".format(str(e)))

            self.txtStatus.Text = "v7.0: Legenda Criada! ({} itens)".format(len(checked_items))

            # v7.0.6: Mensagem de sucesso simplificada
            success_message = "Legenda '{}' criada com sucesso!".format(config["title"])
            forms.alert(success_message)

            # v7.0.5: Fechar janela de configuração e janela principal
            try:
                if hasattr(self, 'legend_config_window') and self.legend_config_window:
                    self.legend_config_window.Close()
                self.Close()
            except:
                pass

        except Exception as e:
            error_msg = "Erro ao criar legenda:\n{}\n\nDetalhes técnicos:\n{}".format(
                str(e), traceback.format_exc())
            forms.alert(error_msg)
            print(error_msg)
            self.txtStatus.Text = "ERRO ao criar legenda."

# ============================================================================
# RUN
# ============================================================================
if __name__ == '__main__':
    try:
        w = MainWindow()
        w.ShowDialog()
    except Exception as e:
        print(str(e))
        traceback.print_exc()
