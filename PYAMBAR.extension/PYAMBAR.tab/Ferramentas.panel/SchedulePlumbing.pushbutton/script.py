# -*- coding: utf-8 -*-
"""
Schedule Plumbing v4.1
Interface visual para criar schedules filtradas a partir de templates.

MODO SELECAO:
  Clique "Selecao" na janela para selecionar elementos MEP no modelo.
  Varre parametros com valores variados DENTRO da selecao.

MODO PROJETO:
  Clique "Projeto" para varrer TODOS os elementos MEP do projeto.
  Mostra parametros com valores variados no projeto inteiro.

RE-SELECAO: clicar o botao "Selecao (N el.)" dentro da janela
  fecha a janela, abre o picker do Revit, e reabre com nova selecao.

FLUXO:
  1. Escolher modo / selecionar elementos
  2. Selecionar 1 ou mais parametros de agrupamento (Ctrl+click)
  3. Ver combinacoes Tipo x Valor(es) — escolher quais criar
  4. Escolher template por tipo MEP
  5. Clicar "Criar" -> Dialog de confirmacao com nomes editaveis
  6. Confirmar -> schedules criadas

VERSAO: 4.1
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Schedule\nPlumbing"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.1"

# ============================================================================
# IMPORTS
# ============================================================================
import os
import sys
import json
import traceback

import clr
clr.AddReference("System")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Windows.Forms")

import System
from System.Collections.ObjectModel import ObservableCollection
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows import (
    RoutedEventHandler, Window, WindowStartupLocation, ResizeMode, Thickness
)
from System.Windows.Controls.Primitives import ToggleButton
from System.Windows.Forms import Application as WinFormsApp
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from System.Collections.Generic import List as DotNetList

from Autodesk.Revit.DB import (
    Transaction, FilteredElementCollector,
    ViewSchedule, ViewDuplicateOption,
    ScheduleFilter, ScheduleFilterType,
    BuiltInCategory, StorageType,
    CategorySet, InstanceBinding,
    SharedParameterElement, SpecTypeId,
    ExternalDefinitionCreationOptions,
    NamingUtils, View3D, ElementId
)

from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script, HOST_APP
from Snippets.core._revit_version_helpers import get_id_value

doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
output = script.get_output()

# ============================================================================
# CONFIG
# ============================================================================

FILTER_PARAM_NAME = "Filter-1"
FILTER_PARAM_GUID = "9dabaa61-9699-4408-bc33-9c1473ccfac9"
_GUID_FILTER1 = System.Guid(FILTER_PARAM_GUID)

GRUPOS = [
    {
        "nome": "Tubos",
        "categorias": [BuiltInCategory.OST_PipeCurves, BuiltInCategory.OST_FlexPipeCurves],
        "cat_schedule": BuiltInCategory.OST_PipeCurves,
        "cor": "#3B82F6",
    },
    {
        "nome": "Conexoes",
        "categorias": [BuiltInCategory.OST_PipeFitting],
        "cat_schedule": BuiltInCategory.OST_PipeFitting,
        "cor": "#10B981",
    },
    {
        "nome": "Acessorios",
        "categorias": [BuiltInCategory.OST_PipeAccessory],
        "cat_schedule": BuiltInCategory.OST_PipeAccessory,
        "cor": "#F59E0B",
    },
    {
        "nome": "Pecas",
        "categorias": [BuiltInCategory.OST_PlumbingFixtures],
        "cat_schedule": BuiltInCategory.OST_PlumbingFixtures,
        "cor": "#8B5CF6",
    },
]

TODAS_CATS_MEP = [
    BuiltInCategory.OST_PipeCurves, BuiltInCategory.OST_FlexPipeCurves,
    BuiltInCategory.OST_PipeFitting, BuiltInCategory.OST_PipeAccessory,
    BuiltInCategory.OST_PlumbingFixtures,
]

_CAT_PARA_GRUPO = {}
for _g in GRUPOS:
    for _c in _g["categorias"]:
        _CAT_PARA_GRUPO[int(_c)] = _g["nome"]

_GRUPO_COR = {g["nome"]: g["cor"] for g in GRUPOS}

# Estado persistente entre sessoes (restaurar apos Isolar/Vista3D)
STATE_FILE = os.path.join(os.path.dirname(__file__), "sp_state.json")


def _save_state(param_nomes, combinacoes_checked):
    """Salva estado atual (params e combos marcadas) em JSON."""
    try:
        state = {
            "param_nomes": param_nomes,
            "checked_combos": [
                {"grupo": c.Grupo, "valores": [list(v) for v in c.ValoresTuple]}
                for c in combinacoes_checked
            ],
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _load_state():
    """Carrega estado salvo. Retorna dict ou None."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _clear_state():
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass


# ============================================================================
# SELECTION FILTER
# ============================================================================

class MepSelectionFilter(ISelectionFilter):
    """Restringe picking apenas a elementos MEP (tubos, conexoes, acessorios)."""

    def AllowElement(self, element):
        try:
            cat_int = get_id_value(element.Category.Id)
            return cat_int in _CAT_PARA_GRUPO
        except Exception:
            return False

    def AllowReference(self, reference, point):
        return True


def _detectar_sel_mep():
    """Retorna elementos MEP da selecao atual do Revit."""
    sel_mep = []
    try:
        for elem_id in uidoc.Selection.GetElementIds():
            try:
                el = doc.GetElement(elem_id)
                if el and el.Category:
                    cat_int = get_id_value(el.Category.Id)
                    if cat_int in _CAT_PARA_GRUPO:
                        sel_mep.append(el)
            except Exception:
                continue
    except Exception:
        pass
    return sel_mep


def _pick_elementos_mep():
    """
    Abre picker do Revit para selecao de elementos MEP.
    Retorna lista de elementos (pode ser vazia) ou None se cancelado.
    """
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            MepSelectionFilter(),
            "Selecione tubos, conexoes e acessorios MEP  (Enter para confirmar)"
        )
        elementos = []
        for r in refs:
            try:
                el = doc.GetElement(r.ElementId)
                if el:
                    elementos.append(el)
            except Exception:
                continue
        return elementos
    except OperationCanceledException:
        return None  # Sinal: manter selecao anterior


def _isolar_em_vista(ids):
    """Isola elementos na vista ativa. ids = lista de ElementId."""
    try:
        view = uidoc.ActiveView
        id_list = DotNetList[ElementId](ids)
        t = Transaction(doc, "SP - Isolar preview")
        t.Start()
        try:
            view.IsolateElementsTemporary(id_list)
            t.Commit()
        except Exception as e:
            t.RollBack()
            output.print_md("ERRO ao isolar: {}".format(str(e)))
            return False
        uidoc.RefreshActiveView()
        return True
    except Exception as e:
        output.print_md("ERRO ao isolar na vista: {}".format(str(e)))
        return False


def _abrir_vista3d(ids):
    """Abre a vista 3D ativa (ou default {3D}) e isola os elementos."""
    try:
        # Prioridade: vista 3D ativa > {3D} > qualquer View3D
        view3d = None
        active = uidoc.ActiveView
        if isinstance(active, View3D) and not active.IsTemplate:
            view3d = active
        if view3d is None:
            for v in FilteredElementCollector(doc).OfClass(View3D):
                if not v.IsTemplate and v.Name == "{3D}":
                    view3d = v
                    break
        if view3d is None:
            for v in FilteredElementCollector(doc).OfClass(View3D):
                if not v.IsTemplate:
                    view3d = v
                    break
        if view3d is None:
            output.print_md("Nenhuma vista 3D encontrada no projeto.")
            return False

        id_list = DotNetList[ElementId](ids)
        t = Transaction(doc, "SP - Vista 3D preview")
        t.Start()
        try:
            view3d.IsolateElementsTemporary(id_list)
            t.Commit()
        except Exception as e:
            t.RollBack()
            output.print_md("ERRO ao isolar em 3D: {}".format(str(e)))
            return False

        try:
            uidoc.ActiveView = view3d
            uidoc.RefreshActiveView()
        except Exception:
            pass
        return True
    except Exception as e:
        output.print_md("ERRO ao abrir vista 3D: {}".format(str(e)))
        return False


# ============================================================================
# DATA MODELS
# ============================================================================

class CombinacaoItem(object):
    """Par (Tipo x ValoresCombinados) — linha na ListView de combinacoes."""
    def __init__(self, grupo, valores_tuple, valor_display, count):
        self.Grupo = grupo
        self.ValoresTuple = valores_tuple   # tuple of (param_nome, valor_str)
        self.Valor = valor_display          # "Apt 101 | CIVIL"
        self.Count = count
        self.IsChecked = False              # desativado por padrao


class ParamItem(object):
    """Parametro de agrupamento com preview de valores."""
    def __init__(self, nome, guid, valores):
        self.Nome = nome
        self.Guid = guid
        self.Valores = valores
        qtd = len(valores)
        sample = sorted(valores)[:3]
        sample_str = ", ".join(sample)
        if qtd > 3:
            sample_str = sample_str + "..."
        self.Preview = "[{} val.]  {}".format(qtd, sample_str)


class NomeItem(object):
    """Item no dialog de confirmacao — nome editavel."""
    def __init__(self, grupo, filtro_display, nome, template, filtro_infos):
        self.Grupo = grupo
        self.FiltroDisplay = filtro_display
        self.Nome = nome                    # editavel via WPF TwoWay binding
        self.Template = template
        self.FiltroInfos = filtro_infos     # list of {nome, guid, valor}


# ============================================================================
# XAML - JANELA PRINCIPAL
# ============================================================================

XAML_SCHEDULE = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Grid.Resources>
        <Style TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe UI"/>
            <Setter Property="Foreground" Value="#111827"/>
        </Style>
        <Style TargetType="Button">
            <Setter Property="Height" Value="28"/>
            <Setter Property="Margin" Value="2"/>
            <Setter Property="Background" Value="White"/>
            <Setter Property="BorderBrush" Value="#D1D5DB"/>
            <Setter Property="FontFamily" Value="Segoe UI"/>
            <Setter Property="Cursor" Value="Hand"/>
        </Style>
        <Style x:Key="BtnPrimary" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Background" Value="#4F46E5"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
        </Style>
        <Style x:Key="BtnSmall" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Height" Value="24"/>
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="Padding" Value="6,0"/>
        </Style>
        <Style x:Key="BtnModeActive" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Background" Value="#4F46E5"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Height" Value="28"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
            <Setter Property="FontSize" Value="11"/>
        </Style>
        <Style x:Key="BtnModeInactive" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Background" Value="White"/>
            <Setter Property="Foreground" Value="#4F46E5"/>
            <Setter Property="BorderBrush" Value="#4F46E5"/>
            <Setter Property="BorderThickness" Value="1.5"/>
            <Setter Property="Height" Value="28"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
            <Setter Property="FontSize" Value="11"/>
        </Style>
    </Grid.Resources>

    <Grid.RowDefinitions>
        <RowDefinition Height="4"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <Border Grid.Row="0" Background="#4F46E5"/>

    <Grid Grid.Row="1" Margin="12">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="272"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>

        <!-- ====== PAINEL ESQUERDO ====== -->
        <Grid Grid.Column="0">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <!-- Modo toggle + contagens -->
            <Border Grid.Row="0" Background="#EEF2FF" CornerRadius="6"
                    Padding="10,8" Margin="0,0,0,10">
                <StackPanel>
                    <!-- Mode toggle buttons -->
                    <Grid Margin="0,0,0,6">
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="6"/>
                            <ColumnDefinition Width="*"/>
                        </Grid.ColumnDefinitions>
                        <Button x:Name="btnModoSelecao"
                                Style="{StaticResource BtnModeActive}"
                                Content="Selecao" Margin="0"/>
                        <Button Grid.Column="2" x:Name="btnModoProjeto"
                                Style="{StaticResource BtnModeInactive}"
                                Content="Projeto" Margin="0"/>
                    </Grid>
                    <!-- Subtitle -->
                    <TextBlock x:Name="lblModo" Text=""
                               FontSize="10" Foreground="#6B7280"
                               HorizontalAlignment="Center" Margin="0,0,0,4"/>
                    <!-- Element counts -->
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="*"/>
                        </Grid.ColumnDefinitions>
                        <StackPanel HorizontalAlignment="Center">
                            <TextBlock Text="Tubos" FontSize="10" Foreground="#6B7280"
                                       HorizontalAlignment="Center"/>
                            <TextBlock x:Name="lblTubos" Text="0" FontSize="16"
                                       FontWeight="Bold" Foreground="#3B82F6"
                                       HorizontalAlignment="Center"/>
                        </StackPanel>
                        <StackPanel Grid.Column="1" HorizontalAlignment="Center">
                            <TextBlock Text="Conexoes" FontSize="10" Foreground="#6B7280"
                                       HorizontalAlignment="Center"/>
                            <TextBlock x:Name="lblConexoes" Text="0" FontSize="16"
                                       FontWeight="Bold" Foreground="#10B981"
                                       HorizontalAlignment="Center"/>
                        </StackPanel>
                        <StackPanel Grid.Column="2" HorizontalAlignment="Center">
                            <TextBlock Text="Acessorios" FontSize="10" Foreground="#6B7280"
                                       HorizontalAlignment="Center"/>
                            <TextBlock x:Name="lblAcessorios" Text="0" FontSize="16"
                                       FontWeight="Bold" Foreground="#F59E0B"
                                       HorizontalAlignment="Center"/>
                        </StackPanel>
                        <StackPanel Grid.Column="3" HorizontalAlignment="Center">
                            <TextBlock Text="Pecas" FontSize="10" Foreground="#6B7280"
                                       HorizontalAlignment="Center"/>
                            <TextBlock x:Name="lblPecas" Text="0" FontSize="16"
                                       FontWeight="Bold" Foreground="#8B5CF6"
                                       HorizontalAlignment="Center"/>
                        </StackPanel>
                    </Grid>
                </StackPanel>
            </Border>

            <!-- Heading params -->
            <DockPanel Grid.Row="1" Margin="2,0,0,4">
                <TextBlock Text="1. Agrupar por:" FontWeight="SemiBold"
                           VerticalAlignment="Center" DockPanel.Dock="Left"/>
                <TextBlock Text="Ctrl+click = multi" FontSize="10" Foreground="#9CA3AF"
                           VerticalAlignment="Center" HorizontalAlignment="Right"/>
            </DockPanel>

            <!-- Search box -->
            <TextBox x:Name="txtSearch" Grid.Row="2"
                     Text="Buscar parametro..." Foreground="#9CA3AF"
                     Height="24" FontSize="11" Padding="5,2"
                     Margin="0,0,0,4"
                     BorderBrush="#D1D5DB"/>

            <!-- Param ListBox - Extended multi-select -->
            <Border Grid.Row="3" BorderBrush="#E5E7EB" BorderThickness="1" Margin="0,0,0,10">
                <ListBox x:Name="lbParams" BorderThickness="0"
                         SelectionMode="Extended"
                         ScrollViewer.HorizontalScrollBarVisibility="Disabled"
                         Background="White">
                    <ListBox.ItemTemplate>
                        <DataTemplate>
                            <StackPanel Margin="4,3">
                                <TextBlock Text="{Binding Nome}" FontSize="12"
                                           FontWeight="SemiBold"/>
                                <TextBlock Text="{Binding Preview}" FontSize="10"
                                           Foreground="#6B7280"/>
                            </StackPanel>
                        </DataTemplate>
                    </ListBox.ItemTemplate>
                </ListBox>
            </Border>

            <!-- Templates -->
            <StackPanel Grid.Row="4">
                <TextBlock Text="2. Templates:" FontWeight="SemiBold" Margin="2,0,0,6"/>

                <StackPanel x:Name="rowTubos" Margin="0,0,0,5">
                    <TextBlock Text="Tubos:" FontSize="11" Foreground="#6B7280"/>
                    <ComboBox x:Name="cmbTubos" Height="24" FontSize="11"/>
                </StackPanel>

                <StackPanel x:Name="rowConexoes" Margin="0,0,0,5">
                    <TextBlock Text="Conexoes:" FontSize="11" Foreground="#6B7280"/>
                    <ComboBox x:Name="cmbConexoes" Height="24" FontSize="11"/>
                </StackPanel>

                <StackPanel x:Name="rowAcessorios" Margin="0,0,0,5">
                    <TextBlock Text="Acessorios:" FontSize="11" Foreground="#6B7280"/>
                    <ComboBox x:Name="cmbAcessorios" Height="24" FontSize="11"/>
                </StackPanel>

                <StackPanel x:Name="rowPecas" Margin="0,0,0,5">
                    <TextBlock Text="Pecas Hidrossanitarias:" FontSize="11" Foreground="#6B7280"/>
                    <ComboBox x:Name="cmbPecas" Height="24" FontSize="11"/>
                </StackPanel>

                <CheckBox x:Name="chkVerTodos"
                          Content="Ver todos os schedules do projeto"
                          Margin="2,4,0,0" FontSize="11"/>
            </StackPanel>
        </Grid>

        <!-- ====== PAINEL DIREITO ====== -->
        <Grid Grid.Column="2">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <!-- Header -->
            <DockPanel Margin="0,0,0,6">
                <StackPanel DockPanel.Dock="Right" Orientation="Horizontal">
                    <Button x:Name="btnInvert" Content="&#8646; Inverter"
                            Style="{StaticResource BtnSmall}" Width="76"/>
                    <Button x:Name="btnSelectAll" Content="&#10003; Todos"
                            Style="{StaticResource BtnSmall}" Width="72"/>
                    <Button x:Name="btnDeselectAll" Content="&#9744; Nenhum"
                            Style="{StaticResource BtnSmall}" Width="76"/>
                </StackPanel>
                <TextBlock x:Name="lblCombTitle"
                           Text="&lt;-- Selecione 1 ou mais parametros"
                           FontWeight="SemiBold" VerticalAlignment="Center"
                           Foreground="#9CA3AF" FontSize="13"/>
            </DockPanel>

            <!-- Combinacoes ListView -->
            <Border Grid.Row="1" BorderBrush="#E5E7EB" BorderThickness="1" Background="White">
                <ListView x:Name="lvCombinacoes" BorderThickness="0" FontSize="12">
                    <ListView.View>
                        <GridView>
                            <GridViewColumn Header="" Width="38">
                                <GridViewColumn.CellTemplate>
                                    <DataTemplate>
                                        <CheckBox IsChecked="{Binding IsChecked, Mode=TwoWay}"
                                                  HorizontalAlignment="Center"
                                                  VerticalAlignment="Center"/>
                                    </DataTemplate>
                                </GridViewColumn.CellTemplate>
                            </GridViewColumn>
                            <GridViewColumn Header="Tipo" Width="100"
                                            DisplayMemberBinding="{Binding Grupo}"/>
                            <GridViewColumn Header="Valor(es)" Width="260"
                                            DisplayMemberBinding="{Binding Valor}"/>
                            <GridViewColumn Header="Elem." Width="65"
                                            DisplayMemberBinding="{Binding Count}"/>
                        </GridView>
                    </ListView.View>
                </ListView>
            </Border>

            <!-- Footer -->
            <DockPanel Grid.Row="2" Margin="0,8,0,0">
                <!-- Verificacao (esquerda) -->
                <StackPanel Orientation="Horizontal" DockPanel.Dock="Left"
                            VerticalAlignment="Center">
                    <TextBlock x:Name="lblSelecionadas" Text=""
                               VerticalAlignment="Center" FontSize="11"
                               Foreground="#6B7280" Margin="0,0,10,0"/>
                    <Button x:Name="btnSelecionar"
                            Content="&#9654; Selecionar"
                            Style="{StaticResource BtnSmall}"
                            Width="90" IsEnabled="False"
                            ToolTip="Selecionar elementos no modelo (janela permanece aberta)"/>
                    <Button x:Name="btnIsolar"
                            Content="&#9670; Isolar"
                            Style="{StaticResource BtnSmall}"
                            Width="72" IsEnabled="False"
                            ToolTip="Isolar na vista ativa e fechar janela"/>
                    <Button x:Name="btnVer3D"
                            Content="&#9671; 3D"
                            Style="{StaticResource BtnSmall}"
                            Width="52" IsEnabled="False"
                            ToolTip="Abrir vista 3D e isolar elementos"/>
                </StackPanel>
                <!-- Acoes principais (direita) -->
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right"
                            DockPanel.Dock="Right">
                    <Button x:Name="btnCancel" Content="Cancelar"
                            Width="90" Height="34" Margin="0,0,8,0"/>
                    <Button x:Name="btnCriar" Content="Criar Schedules"
                            Style="{StaticResource BtnPrimary}"
                            Width="185" Height="34" IsEnabled="False" FontSize="13"/>
                </StackPanel>
            </DockPanel>
        </Grid>
    </Grid>

    <Border Grid.Row="2" Background="#F3F4F6" Padding="10,4" Margin="0,6,0,0">
        <TextBlock x:Name="txtStatus" Text="Pronto."
                   FontSize="11" Foreground="#6B7280"/>
    </Border>
</Grid>
"""

# ============================================================================
# XAML - DIALOG DE CONFIRMACAO
# ============================================================================

XAML_CONFIRM = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- Header -->
    <Border Grid.Row="0" Background="#4F46E5" Padding="16,10">
        <StackPanel>
            <TextBlock x:Name="lblHeader"
                       Text="Confirmar criacao de schedules"
                       Foreground="White" FontSize="14" FontWeight="Bold"
                       FontFamily="Segoe UI"/>
            <TextBlock Text="Edite os nomes antes de confirmar"
                       Foreground="#C7D2FE" FontSize="11"
                       FontFamily="Segoe UI" Margin="0,2,0,0"/>
        </StackPanel>
    </Border>

    <!-- Column headers -->
    <Border Grid.Row="1" Background="#F9FAFB" BorderBrush="#E5E7EB"
            BorderThickness="0,0,0,1" Padding="8,5">
        <Grid>
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="90"/>
                <ColumnDefinition Width="200"/>
                <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <TextBlock Text="TIPO" FontSize="10" FontWeight="Bold"
                       Foreground="#6B7280" FontFamily="Segoe UI"/>
            <TextBlock Grid.Column="1" Text="AGRUPAMENTO" FontSize="10"
                       FontWeight="Bold" Foreground="#6B7280" FontFamily="Segoe UI"/>
            <TextBlock Grid.Column="2" Text="NOME DO SCHEDULE  (editavel)"
                       FontSize="10" FontWeight="Bold"
                       Foreground="#6B7280" FontFamily="Segoe UI"/>
        </Grid>
    </Border>

    <!-- Items -->
    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto">
        <ItemsControl x:Name="itemsList">
            <ItemsControl.ItemTemplate>
                <DataTemplate>
                    <Border BorderBrush="#F3F4F6" BorderThickness="0,0,0,1" Padding="8,4">
                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="90"/>
                                <ColumnDefinition Width="200"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <Border CornerRadius="3" Padding="5,2"
                                    Background="{Binding GrupoCor}"
                                    HorizontalAlignment="Left" VerticalAlignment="Center">
                                <TextBlock Text="{Binding Grupo}" FontSize="10"
                                           FontWeight="Bold" Foreground="White"
                                           FontFamily="Segoe UI"/>
                            </Border>
                            <TextBlock Grid.Column="1"
                                       Text="{Binding FiltroDisplay}"
                                       FontSize="11" Foreground="#374151"
                                       VerticalAlignment="Center" Margin="4,0"
                                       FontFamily="Segoe UI"/>
                            <TextBox Grid.Column="2"
                                     Text="{Binding Nome, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                                     FontSize="11" Height="26" Padding="5,2"
                                     BorderBrush="#D1D5DB" FontFamily="Segoe UI"
                                     VerticalContentAlignment="Center"/>
                        </Grid>
                    </Border>
                </DataTemplate>
            </ItemsControl.ItemTemplate>
        </ItemsControl>
    </ScrollViewer>

    <!-- Footer -->
    <Border Grid.Row="3" Background="#F9FAFB" BorderBrush="#E5E7EB"
            BorderThickness="0,1,0,0" Padding="12,10">
        <DockPanel>
            <TextBlock x:Name="lblConfirmInfo" Text=""
                       VerticalAlignment="Center" FontSize="11"
                       Foreground="#6B7280" FontFamily="Segoe UI"
                       DockPanel.Dock="Left"/>
            <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
                <Button x:Name="btnCancelar" Content="Cancelar"
                        Width="90" Height="34" Margin="0,0,8,0"
                        FontFamily="Segoe UI" Cursor="Hand"/>
                <Button x:Name="btnConfirmar" Content="Criar Schedules"
                        Width="160" Height="34"
                        Background="#4F46E5" Foreground="White"
                        BorderThickness="0" FontWeight="Bold"
                        FontFamily="Segoe UI Semibold" Cursor="Hand"/>
            </StackPanel>
        </DockPanel>
    </Border>
</Grid>
"""

# ============================================================================
# HELPERS - PARAMETROS
# ============================================================================

def _ler_valor_param(param):
    try:
        if not param or not param.HasValue:
            return None
        if param.StorageType != StorageType.String:
            return None
        val = param.AsString()
        if not val or not val.strip():
            return None
        val = val.strip()
        if val.lower() in ("<varies>", "<varia>", "<varies...>"):
            return None
        return val
    except Exception:
        return None


def _get_guid_de_param(param):
    try:
        param_el = doc.GetElement(param.Definition.Id)
        if isinstance(param_el, SharedParameterElement):
            return param_el.GuidValue
    except Exception:
        pass
    return None


# ============================================================================
# HELPERS - COLETORES
# ============================================================================

def coletar_todos_mep():
    grupos = {}
    for cfg in GRUPOS:
        elementos = []
        for cat_bic in cfg["categorias"]:
            col = (FilteredElementCollector(doc)
                   .OfCategory(cat_bic)
                   .WhereElementIsNotElementType())
            elementos.extend(list(col))
        if elementos:
            grupos[cfg["nome"]] = elementos
    return grupos


def identificar_grupos_de_lista(elementos):
    resultado = {}
    for el in elementos:
        try:
            cat_int = get_id_value(el.Category.Id)
            nome = _CAT_PARA_GRUPO.get(cat_int)
            if nome:
                resultado.setdefault(nome, []).append(el)
        except Exception:
            continue
    return resultado


# ============================================================================
# HELPERS - SCAN DE PARAMETROS
# ============================================================================

def escanear_params_projeto(grupos_elementos):
    """Retorna {nome: {guid, valores: set}} para params TEXT com 2+ valores unicos."""
    param_data = {}
    for elementos in grupos_elementos.values():
        for el in elementos:
            try:
                for param in el.Parameters:
                    try:
                        val = _ler_valor_param(param)
                        if not val:
                            continue
                        nome = param.Definition.Name
                        if nome not in param_data:
                            guid = _get_guid_de_param(param)
                            param_data[nome] = {"guid": guid, "valores": set()}
                        param_data[nome]["valores"].add(val)
                    except Exception:
                        continue
            except Exception:
                continue
    return {n: d for n, d in param_data.items() if len(d["valores"]) >= 2}


# ============================================================================
# HELPERS - COMBINACOES (produto cartesiano multi-param)
# ============================================================================

def construir_combinacoes_multi(grupos_elementos, param_nomes):
    """
    Constroi combinacoes como produto cartesiano de N parametros.
    ValoresTuple = tuple de (param_nome, valor_str).
    """
    grupos_contagem = {}
    for cfg in GRUPOS:
        nome_grupo = cfg["nome"]
        elementos = grupos_elementos.get(nome_grupo, [])
        if not elementos:
            continue
        contagem = {}
        for el in elementos:
            try:
                vals = []
                valid = True
                for param_nome in param_nomes:
                    p = el.LookupParameter(param_nome)
                    val = _ler_valor_param(p) if p else None
                    if val:
                        vals.append((param_nome, val))
                    else:
                        valid = False
                        break
                if valid and vals:
                    key = tuple(vals)
                    contagem[key] = contagem.get(key, 0) + 1
            except Exception:
                continue
        if contagem:
            grupos_contagem[nome_grupo] = contagem

    items = []
    for cfg in GRUPOS:
        nome_grupo = cfg["nome"]
        contagem = grupos_contagem.get(nome_grupo, {})
        for vals_tuple in sorted(contagem.keys()):
            valor_display = " | ".join(v for _, v in vals_tuple)
            items.append(CombinacaoItem(
                nome_grupo, vals_tuple, valor_display, contagem[vals_tuple]))
    return items


# ============================================================================
# HELPERS - SCHEDULES
# ============================================================================

def buscar_schedules_por_categoria(cat_bic):
    cat_val = int(cat_bic)
    resultado = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if not s.IsTemplate and get_id_value(s.Definition.CategoryId) == cat_val:
                resultado.append(s)
        except Exception:
            continue
    return sorted(resultado, key=lambda x: x.Name)


def buscar_todos_schedules():
    resultado = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if not s.IsTemplate:
                resultado.append(s)
        except Exception:
            continue
    return sorted(resultado, key=lambda x: x.Name)


def sanitize_view_name(name):
    """
    Remove/substitui caracteres proibidos em nomes de views do Revit.
    Revit proibe: / \\ : * ? \" < > | { } [ ] e caracteres de controle.
    Usa NamingUtils.IsValidName() para validacao final.
    """
    _PROHIBITED = ['/', '\\', ':', '*', '?', '"', '<', '>', '|',
                   '{', '}', '[', ']', ';', '~', '`']
    result = name
    for ch in _PROHIBITED:
        result = result.replace(ch, '-')
    while '--' in result:
        result = result.replace('--', '-')
    result = result.strip('-. ')
    if not result:
        result = "Schedule"
    try:
        if not NamingUtils.IsValidName(result):
            cleaned = ""
            for ch in result:
                if ch.isalnum() or ch in (' ', '-', '_'):
                    cleaned += ch
            result = cleaned.strip() or "Schedule"
    except Exception:
        pass
    return result


def nome_unico(base):
    existentes = {s.Name for s in FilteredElementCollector(doc).OfClass(ViewSchedule)}
    if base not in existentes:
        return base
    i = 2
    while "{} ({})".format(base, i) in existentes:
        i += 1
    return "{} ({})".format(base, i)


# ============================================================================
# HELPERS - SHARED PARAM FILTER-1
# ============================================================================

def _filter1_existe():
    return SharedParameterElement.Lookup(doc, _GUID_FILTER1) is not None


def _criar_filter1():
    original_sp = app.SharedParametersFilename
    try:
        temp_path = os.path.join(
            os.environ.get("TEMP", os.environ.get("TMP", "C:/Temp")),
            "pyambar_shared_params.txt"
        )
        if not os.path.exists(temp_path):
            with open(temp_path, "w") as f:
                f.write("# This is a Revit shared parameter file.\n# Do not edit manually.\n")
                f.write("*META\tVERSION\tMINVERSION\nMETA\t2\t1\n")
                f.write("*GROUP\tID\tNAME\n")
                f.write("*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n")
        app.SharedParametersFilename = temp_path
        sp_file = app.OpenSharedParameterFile()
        if not sp_file:
            return False, "Nao foi possivel abrir shared parameters file"
        grupo = sp_file.Groups.get_Item("PYAMBAR")
        if not grupo:
            grupo = sp_file.Groups.Create("PYAMBAR")
        definition = grupo.Definitions.get_Item(FILTER_PARAM_NAME)
        if not definition:
            opts = ExternalDefinitionCreationOptions(FILTER_PARAM_NAME, SpecTypeId.String.Text)
            opts.GUID = _GUID_FILTER1
            opts.Visible = True
            definition = grupo.Definitions.Create(opts)
        cat_set = CategorySet()
        for cat_bic in TODAS_CATS_MEP:
            cat = doc.Settings.Categories.get_Item(cat_bic)
            if cat:
                cat_set.Insert(cat)
        binding = InstanceBinding(cat_set)
        t = Transaction(doc, "SP - Criar {}".format(FILTER_PARAM_NAME))
        t.Start()
        try:
            ok = doc.ParameterBindings.Insert(definition, binding)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            return False, str(ex)
        return (True, None) if ok else (False, "ParameterBindings.Insert retornou False")
    except Exception as ex:
        return False, str(ex)
    finally:
        app.SharedParametersFilename = original_sp


# ============================================================================
# HELPERS - CRIAR SCHEDULE COM MULTIPLOS FILTROS
# ============================================================================

def _obter_ou_adicionar_field(schedule_def, filtro_info):
    guid = filtro_info.get("guid")
    nome = filtro_info["nome"]

    def _match(field):
        try:
            param_el = doc.GetElement(field.ParameterId)
            if guid and isinstance(param_el, SharedParameterElement):
                return param_el.GuidValue == guid
            if param_el and hasattr(param_el, "GetDefinition"):
                defn = param_el.GetDefinition()
                return defn and defn.Name == nome
        except Exception:
            pass
        return False

    for i in range(schedule_def.GetFieldCount()):
        if _match(schedule_def.GetField(i)):
            return schedule_def.GetField(i)

    for schedulable in schedule_def.GetSchedulableFields():
        try:
            param_el = doc.GetElement(schedulable.ParameterId)
            matched = False
            if guid and isinstance(param_el, SharedParameterElement):
                matched = param_el.GuidValue == guid
            elif param_el and hasattr(param_el, "GetDefinition"):
                defn = param_el.GetDefinition()
                matched = defn and defn.Name == nome
            if matched:
                field = schedule_def.AddField(schedulable)
                field.IsHidden = True
                return field
        except Exception:
            continue
    return None


def duplicar_e_filtrar_multi(template, filtro_infos, novo_nome):
    """
    Duplica template e aplica N filtros em AND logico.
    - ClearFilters() remove filtros herdados do template
    - AddFilter() chamado N vezes = AND entre todos os filtros
    - ScheduleFilterType.Equal para params STRING (StorageType.String)
    """
    t = Transaction(doc, "SP - Criar {}".format(novo_nome))
    t.Start()
    try:
        novo_id = template.Duplicate(ViewDuplicateOption.Duplicate)
        novo = doc.GetElement(novo_id)

        schedule_def = novo.Definition

        # Limpar filtros herdados do template (AND logic exige partida limpa)
        schedule_def.ClearFilters()

        # Aplicar N filtros — cada AddFilter adiciona condicao AND
        for filtro_info in filtro_infos:
            campo = _obter_ou_adicionar_field(schedule_def, filtro_info)
            if not campo:
                output.print_md("  AVISO: '{}' nao disponivel no template '{}'".format(
                    filtro_info["nome"], template.Name))
                t.RollBack()
                return None
            filtro = ScheduleFilter(campo.FieldId, ScheduleFilterType.Equal, filtro_info["valor"])
            schedule_def.AddFilter(filtro)

        # Renomear apos configurar filtros (nome ja sanitizado)
        novo.Name = novo_nome

        t.Commit()
        return novo

    except Exception as e:
        if t.HasStarted():
            t.RollBack()
        output.print_md("  ERRO ao duplicar '{}': {}".format(template.Name, str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        return None


# ============================================================================
# DIALOG DE CONFIRMACAO
# ============================================================================

class ConfirmDialog(Window):
    """Mostra lista de schedules a criar com nomes editaveis."""

    def __init__(self, plano_items):
        self._items = plano_items
        self.plano_final = None

        self.Title = "Confirmar criacao de schedules"
        n = len(plano_items)
        self.Height = max(300, min(120 + n * 38 + 80, 580))
        self.Width = 720
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = BrushConverter().ConvertFrom("#FFFFFF")

        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_CONFIRM))
        self.Content = XamlReader.Load(stream)

        self.lblHeader      = self.Content.FindName("lblHeader")
        self.lblConfirmInfo = self.Content.FindName("lblConfirmInfo")
        self.itemsList      = self.Content.FindName("itemsList")
        self.btnConfirmar   = self.Content.FindName("btnConfirmar")
        self.btnCancelar    = self.Content.FindName("btnCancelar")

        self.lblHeader.Text = "Criar {} schedule{}".format(
            n, "s" if n != 1 else "")
        self.lblConfirmInfo.Text = "Edite os nomes e confirme."

        _CORES = {"Tubos": "#3B82F6", "Conexoes": "#10B981", "Acessorios": "#F59E0B", "Pecas": "#8B5CF6"}
        for item in plano_items:
            item.GrupoCor = _CORES.get(item.Grupo, "#6B7280")

        col = ObservableCollection[object]()
        for item in plano_items:
            col.Add(item)
        self.itemsList.ItemsSource = col

        self.btnConfirmar.Click += self._on_confirmar
        self.btnCancelar.Click  += self._on_cancelar

    def _on_confirmar(self, sender, args):
        self.plano_final = self._items
        self.Close()

    def _on_cancelar(self, sender, args):
        self.Close()


# ============================================================================
# JANELA PRINCIPAL
# ============================================================================

class SchedulePlumbingWindow(Window):

    def __init__(self, sel_mep):
        # State
        self._sel_mep = sel_mep
        self._modo = "selecao" if sel_mep else "projeto"
        self.grupos_elementos = {}
        self.param_scan = {}
        self.resultado = None

        self._combinacoes = []
        self._comb_col = ObservableCollection[object]()
        self._all_param_items = []
        self._todos_schedules = []
        self._schedules_por_grupo = {}
        self._current_param_nomes = []
        self._current_param_scan_slice = {}
        self._suppressing_selection = False   # evita reentrada durante restore
        self._saved_state = _load_state()     # estado da sessao anterior

        # Window setup
        self.Title = "Schedule Plumbing  v4.1"
        self.Height = 660
        self.Width = 1000
        self.MinWidth = 780
        self.MinHeight = 500
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = BrushConverter().ConvertFrom("#F9FAFB")

        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_SCHEDULE))
        self.Content = XamlReader.Load(stream)

        # Controls
        self.btnModoSelecao  = self.Content.FindName("btnModoSelecao")
        self.btnModoProjeto  = self.Content.FindName("btnModoProjeto")
        self.lblModo         = self.Content.FindName("lblModo")
        self.lblTubos        = self.Content.FindName("lblTubos")
        self.lblConexoes     = self.Content.FindName("lblConexoes")
        self.lblAcessorios   = self.Content.FindName("lblAcessorios")
        self.txtSearch       = self.Content.FindName("txtSearch")
        self.lbParams        = self.Content.FindName("lbParams")
        self.rowTubos        = self.Content.FindName("rowTubos")
        self.rowConexoes     = self.Content.FindName("rowConexoes")
        self.rowAcessorios   = self.Content.FindName("rowAcessorios")
        self.rowPecas        = self.Content.FindName("rowPecas")
        self.cmbTubos        = self.Content.FindName("cmbTubos")
        self.cmbConexoes     = self.Content.FindName("cmbConexoes")
        self.cmbAcessorios   = self.Content.FindName("cmbAcessorios")
        self.cmbPecas        = self.Content.FindName("cmbPecas")
        self.lblPecas        = self.Content.FindName("lblPecas")
        self.chkVerTodos     = self.Content.FindName("chkVerTodos")
        self.lvCombinacoes   = self.Content.FindName("lvCombinacoes")
        self.lblCombTitle    = self.Content.FindName("lblCombTitle")
        self.lblSelecionadas = self.Content.FindName("lblSelecionadas")
        self.btnInvert       = self.Content.FindName("btnInvert")
        self.btnSelectAll    = self.Content.FindName("btnSelectAll")
        self.btnDeselectAll  = self.Content.FindName("btnDeselectAll")
        self.btnSelecionar   = self.Content.FindName("btnSelecionar")
        self.btnIsolar       = self.Content.FindName("btnIsolar")
        self.btnVer3D        = self.Content.FindName("btnVer3D")
        self.btnCriar        = self.Content.FindName("btnCriar")
        self.btnCancel       = self.Content.FindName("btnCancel")
        self.txtStatus       = self.Content.FindName("txtStatus")

        self.lvCombinacoes.ItemsSource = self._comb_col

        # Button labels — Selecao SEMPRE habilitado (fecha e abre picker)
        n_sel = len(sel_mep)
        if n_sel > 0:
            self.btnModoSelecao.Content = "Selecao ({} el.)".format(n_sel)
        else:
            self.btnModoSelecao.Content = "Selecionar..."

        # Events
        self.btnModoSelecao.Click               += self._on_modo_selecao_click
        self.btnModoProjeto.Click               += self._on_modo_projeto_click
        self.lbParams.SelectionChanged          += self._on_param_selected
        self.txtSearch.GotFocus                 += self._on_search_focus
        self.txtSearch.LostFocus                += self._on_search_blur
        self.txtSearch.TextChanged              += self._on_search_changed
        self.btnInvert.Click                    += self._on_invert
        self.btnSelectAll.Click                 += self._on_select_all
        self.btnDeselectAll.Click               += self._on_deselect_all
        self.btnSelecionar.Click                += self._on_selecionar_click
        self.btnIsolar.Click                    += self._on_isolar_click
        self.btnVer3D.Click                     += self._on_ver3d_click
        self.chkVerTodos.Checked                += self._on_ver_todos_changed
        self.chkVerTodos.Unchecked              += self._on_ver_todos_changed
        self.btnCriar.Click                     += self._on_criar
        self.btnCancel.Click                    += self._on_cancel

        # Routed: checkbox changes inside ListView
        self.lvCombinacoes.AddHandler(
            ToggleButton.CheckedEvent,
            RoutedEventHandler(self._on_check_changed))
        self.lvCombinacoes.AddHandler(
            ToggleButton.UncheckedEvent,
            RoutedEventHandler(self._on_check_changed))

        # Init
        self._preload_schedules()
        self._ativar_modo(self._modo)

    # -----------------------------------------------------------------------
    # MODE TOGGLE
    # -----------------------------------------------------------------------

    def _on_modo_selecao_click(self, sender, args):
        # Sempre fecha a janela e volta ao Revit para (re)selecionar elementos.
        # main() detecta "__RESELECT__", abre o picker e reabre a janela.
        self.resultado = "__RESELECT__"
        self.Close()

    def _on_modo_projeto_click(self, sender, args):
        if self._modo != "projeto":
            self._ativar_modo("projeto")

    def _ativar_modo(self, modo):
        self._modo = modo
        self._style_modo_buttons()
        self.txtStatus.Text = "Carregando dados..."
        WinFormsApp.DoEvents()

        if modo == "selecao":
            self.grupos_elementos = identificar_grupos_de_lista(self._sel_mep)
        else:
            self.grupos_elementos = coletar_todos_mep()

        self.param_scan = escanear_params_projeto(self.grupos_elementos)
        self._refresh_data_ui()
        # Restaurar estado salvo (apos Isolar/Vista3D da sessao anterior)
        if self._saved_state:
            self._try_restore_state()

    def _style_modo_buttons(self):
        _c = BrushConverter()
        _act_bg  = _c.ConvertFrom("#4F46E5")
        _act_fg  = _c.ConvertFrom("#FFFFFF")
        _inact_bg = _c.ConvertFrom("#FFFFFF")
        _inact_fg = _c.ConvertFrom("#4F46E5")
        _inact_bd = _c.ConvertFrom("#4F46E5")
        _t0  = Thickness(0)
        _t15 = Thickness(1.5)

        if self._modo == "selecao":
            self.btnModoSelecao.Background    = _act_bg
            self.btnModoSelecao.Foreground    = _act_fg
            self.btnModoSelecao.BorderThickness = _t0
            self.btnModoProjeto.Background    = _inact_bg
            self.btnModoProjeto.Foreground    = _inact_fg
            self.btnModoProjeto.BorderBrush   = _inact_bd
            self.btnModoProjeto.BorderThickness = _t15
        else:
            self.btnModoSelecao.Background    = _inact_bg
            self.btnModoSelecao.Foreground    = _inact_fg
            self.btnModoSelecao.BorderBrush   = _inact_bd
            self.btnModoSelecao.BorderThickness = _t15
            self.btnModoProjeto.Background    = _act_bg
            self.btnModoProjeto.Foreground    = _act_fg
            self.btnModoProjeto.BorderThickness = _t0

    # -----------------------------------------------------------------------
    # DATA REFRESH
    # -----------------------------------------------------------------------

    def _preload_schedules(self):
        self._todos_schedules = buscar_todos_schedules()
        for cfg in GRUPOS:
            self._schedules_por_grupo[cfg["nome"]] = buscar_schedules_por_categoria(
                cfg["cat_schedule"])

    def _refresh_data_ui(self):
        """Atualiza contagens, lista de params e limpa combinacoes."""
        total = sum(len(els) for els in self.grupos_elementos.values())
        modo_label = "Selecao" if self._modo == "selecao" else "Projeto"
        self.lblModo.Text = "{} - {} elementos MEP".format(modo_label, total)

        self.lblTubos.Text      = str(len(self.grupos_elementos.get("Tubos", [])))
        self.lblConexoes.Text   = str(len(self.grupos_elementos.get("Conexoes", [])))
        self.lblAcessorios.Text = str(len(self.grupos_elementos.get("Acessorios", [])))
        self.lblPecas.Text      = str(len(self.grupos_elementos.get("Pecas", [])))

        # Reset search box
        self.txtSearch.Text = "Buscar parametro..."
        self.txtSearch.Foreground = BrushConverter().ConvertFrom("#9CA3AF")

        # Populate params
        param_items = []
        for nome in sorted(self.param_scan.keys()):
            data = self.param_scan[nome]
            param_items.append(ParamItem(nome, data["guid"], data["valores"]))
        self._all_param_items = param_items
        self.lbParams.ItemsSource = param_items

        # Clear combinations
        self._combinacoes = []
        self._comb_col.Clear()
        self._current_param_nomes = []
        self._current_param_scan_slice = {}
        self.lblCombTitle.Text = "<-- Selecione 1 ou mais parametros"
        self.lblCombTitle.Foreground = BrushConverter().ConvertFrom("#9CA3AF")
        self._update_ui()

        # Refresh templates
        self._populate_templates(bool(self.chkVerTodos.IsChecked))

        n_params = len(param_items)
        if n_params == 0:
            self.txtStatus.Text = (
                "Nenhum parametro TEXT com 2+ valores encontrado. "
                "Verifique se os elementos possuem parametros texto preenchidos."
            )
        else:
            self.txtStatus.Text = "{} parametros. Ctrl+click para multi-selecao.".format(n_params)

    def _populate_templates(self, ver_todos):
        _COLLAPSED = System.Windows.Visibility.Collapsed
        _VISIBLE   = System.Windows.Visibility.Visible
        rows = {
            "Tubos":      (self.rowTubos,      self.cmbTubos),
            "Conexoes":   (self.rowConexoes,    self.cmbConexoes),
            "Acessorios": (self.rowAcessorios,  self.cmbAcessorios),
            "Pecas":      (self.rowPecas,       self.cmbPecas),
        }
        for cfg in GRUPOS:
            nome = cfg["nome"]
            row, cmb = rows[nome]
            if nome not in self.grupos_elementos:
                row.Visibility = _COLLAPSED
                continue
            row.Visibility = _VISIBLE
            cmb.Items.Clear()
            schedules = self._todos_schedules if ver_todos else (
                self._schedules_por_grupo.get(nome) or self._todos_schedules)
            for s in schedules:
                cmb.Items.Add(s.Name)
            if cmb.Items.Count > 0:
                cmb.SelectedIndex = 0

    # -----------------------------------------------------------------------
    # SEARCH
    # -----------------------------------------------------------------------

    def _on_search_focus(self, sender, args):
        if self.txtSearch.Text == "Buscar parametro...":
            self.txtSearch.Text = ""
            self.txtSearch.Foreground = BrushConverter().ConvertFrom("#111827")

    def _on_search_blur(self, sender, args):
        if not self.txtSearch.Text:
            self.txtSearch.Text = "Buscar parametro..."
            self.txtSearch.Foreground = BrushConverter().ConvertFrom("#9CA3AF")

    def _on_search_changed(self, sender, args):
        text = self.txtSearch.Text.lower()
        if not text or text == "buscar parametro...":
            self.lbParams.ItemsSource = self._all_param_items
            return
        filtered = [p for p in self._all_param_items if text in p.Nome.lower()]
        self.lbParams.ItemsSource = filtered

    # -----------------------------------------------------------------------
    # PARAM SELECTION -> COMBINATIONS
    # -----------------------------------------------------------------------

    def _on_param_selected(self, sender, args):
        if self._suppressing_selection:
            return
        selected_items = list(self.lbParams.SelectedItems)
        if not selected_items:
            return
        param_nomes = [item.Nome for item in selected_items]
        self._update_combinations(param_nomes)

    def _update_combinations(self, param_nomes, restore_combos=None):
        """Constroi combinacoes para os params dados. Opcionalmente restaura checked."""
        self.txtStatus.Text = "Calculando combinacoes..."
        WinFormsApp.DoEvents()

        self._current_param_nomes = param_nomes
        self._current_param_scan_slice = {
            n: self.param_scan[n] for n in param_nomes if n in self.param_scan}

        if len(param_nomes) == 1:
            self.lblCombTitle.Text = "Combinacoes para:  {}".format(param_nomes[0])
        else:
            self.lblCombTitle.Text = "Combinacoes para:  {}".format(
                " + ".join(param_nomes))
        self.lblCombTitle.Foreground = BrushConverter().ConvertFrom("#111827")

        self._combinacoes = construir_combinacoes_multi(self.grupos_elementos, param_nomes)

        self._comb_col.Clear()
        for item in self._combinacoes:
            self._comb_col.Add(item)

        # Restaurar estado de checked (apos Isolar/Vista3D)
        if restore_combos:
            restore_set = set()
            for rc in restore_combos:
                key = (rc["grupo"], tuple(tuple(v) for v in rc["valores"]))
                restore_set.add(key)
            for item in self._combinacoes:
                if (item.Grupo, item.ValoresTuple) in restore_set:
                    item.IsChecked = True
            self.lvCombinacoes.Items.Refresh()

        self._update_ui()
        self.txtStatus.Text = "{} combinacoes para '{}'.".format(
            len(self._combinacoes),
            " + ".join(param_nomes) if len(param_nomes) > 1 else param_nomes[0])

    # -----------------------------------------------------------------------
    # STATE RESTORE
    # -----------------------------------------------------------------------

    def _try_restore_state(self):
        """Restaura params e combos marcadas do estado salvo."""
        if not self._saved_state:
            return
        param_nomes = self._saved_state.get("param_nomes", [])
        restore_combos = self._saved_state.get("checked_combos", [])
        if not param_nomes:
            return
        valid_params = [n for n in param_nomes if n in self.param_scan]
        if not valid_params:
            return

        self._suppressing_selection = True
        try:
            self._update_combinations(valid_params, restore_combos=restore_combos)
        finally:
            self._suppressing_selection = False

        # Selecionar visualmente os params no ListBox
        try:
            param_set = set(valid_params)
            for i in range(self.lbParams.Items.Count):
                item = self.lbParams.Items.GetItemAt(i)
                container = self.lbParams.ItemContainerGenerator.ContainerFromIndex(i)
                if container is not None and item.Nome in param_set:
                    container.IsSelected = True
        except Exception:
            pass

        n_checked = sum(1 for c in self._combinacoes if c.IsChecked)
        self.txtStatus.Text = "Estado restaurado: {} params, {} combos marcadas.".format(
            len(valid_params), n_checked)

    # -----------------------------------------------------------------------
    # VERIFICATION ACTIONS (Selecionar / Isolar / Vista 3D)
    # -----------------------------------------------------------------------

    def _elementos_de_combinacao(self, combo):
        """Retorna elementos que correspondem exatamente a uma combinacao."""
        grupo_els = self.grupos_elementos.get(combo.Grupo, [])
        matching = []
        for el in grupo_els:
            try:
                all_match = True
                for param_nome, valor in combo.ValoresTuple:
                    p = el.LookupParameter(param_nome)
                    if _ler_valor_param(p) != valor:
                        all_match = False
                        break
                if all_match:
                    matching.append(el)
            except Exception:
                continue
        return matching

    def _get_ids_checked(self):
        """Coleta ElementIds de todas as combinacoes marcadas."""
        ids = []
        seen = set()
        for combo in self._combinacoes:
            if not combo.IsChecked:
                continue
            for el in self._elementos_de_combinacao(combo):
                eid = el.Id
                val = eid.Value if hasattr(eid, 'Value') else eid.IntegerValue
                if val not in seen:
                    seen.add(val)
                    ids.append(eid)
        return ids

    def _on_selecionar_click(self, sender, args):
        """Seleciona elementos no modelo SEM fechar a janela."""
        ids = self._get_ids_checked()
        if not ids:
            self.txtStatus.Text = "Nenhum elemento para selecionar."
            return
        try:
            id_list = DotNetList[ElementId](ids)
            uidoc.Selection.SetElementIds(id_list)
            self.txtStatus.Text = "{} elemento(s) selecionado(s) no modelo.".format(len(ids))
        except Exception as e:
            self.txtStatus.Text = "Erro ao selecionar: {}".format(str(e))

    def _on_isolar_click(self, sender, args):
        """Salva estado, fecha janela -> main() isola na vista ativa."""
        ids = self._get_ids_checked()
        if not ids:
            return
        checked = [c for c in self._combinacoes if c.IsChecked]
        _save_state(self._current_param_nomes, checked)
        self.resultado = ("__ISOLATE__", ids)
        self.Close()

    def _on_ver3d_click(self, sender, args):
        """Salva estado, fecha janela -> main() abre vista 3D com isolacao."""
        ids = self._get_ids_checked()
        if not ids:
            return
        checked = [c for c in self._combinacoes if c.IsChecked]
        _save_state(self._current_param_nomes, checked)
        self.resultado = ("__VISTA3D__", ids)
        self.Close()

    # -----------------------------------------------------------------------
    # CHECKBOX CONTROLS
    # -----------------------------------------------------------------------

    def _on_check_changed(self, sender, args):
        self._update_ui()

    def _on_select_all(self, sender, args):
        for item in self._combinacoes:
            item.IsChecked = True
        self.lvCombinacoes.Items.Refresh()
        self._update_ui()

    def _on_deselect_all(self, sender, args):
        for item in self._combinacoes:
            item.IsChecked = False
        self.lvCombinacoes.Items.Refresh()
        self._update_ui()

    def _on_invert(self, sender, args):
        for item in self._combinacoes:
            item.IsChecked = not item.IsChecked
        self.lvCombinacoes.Items.Refresh()
        self._update_ui()

    # -----------------------------------------------------------------------
    # TEMPLATE TOGGLE
    # -----------------------------------------------------------------------

    def _on_ver_todos_changed(self, sender, args):
        self._populate_templates(bool(self.chkVerTodos.IsChecked))

    # -----------------------------------------------------------------------
    # CRIAR -> CONFIRM DIALOG
    # -----------------------------------------------------------------------

    def _on_criar(self, sender, args):
        try:
            if not self._current_param_nomes:
                forms.alert("Selecione um ou mais parametros de agrupamento.")
                return

            selecionadas = [item for item in self._combinacoes if item.IsChecked]
            if not selecionadas:
                forms.alert(
                    "Nenhuma combinacao selecionada.\n\n"
                    "Dica: marque as combinacoes desejadas na lista.")
                return

            # Collect templates
            templates_por_grupo = {}
            grupos_necessarios = set(c.Grupo for c in selecionadas)
            cmb_map = {
                "Tubos":      self.cmbTubos,
                "Conexoes":   self.cmbConexoes,
                "Acessorios": self.cmbAcessorios,
                "Pecas":      self.cmbPecas,
            }

            for cfg in GRUPOS:
                nome_grupo = cfg["nome"]
                if nome_grupo not in grupos_necessarios:
                    continue
                cmb = cmb_map[nome_grupo]
                if not cmb or cmb.SelectedItem is None:
                    forms.alert("Template para '{}' nao selecionado.".format(nome_grupo))
                    return
                template_nome = cmb.SelectedItem
                template = next(
                    (s for s in self._todos_schedules if s.Name == template_nome), None)
                if not template:
                    forms.alert("Template '{}' nao encontrado.".format(template_nome))
                    return
                templates_por_grupo[nome_grupo] = template

            # Build NomeItems for ConfirmDialog
            plano_items = []
            for comb in selecionadas:
                template = templates_por_grupo.get(comb.Grupo)
                if not template:
                    continue

                filtro_infos = []
                for param_nome, valor in comb.ValoresTuple:
                    data = self._current_param_scan_slice.get(param_nome, {})
                    filtro_infos.append({
                        "nome": param_nome,
                        "guid": data.get("guid"),
                        "valor": valor,
                    })

                nome_base = sanitize_view_name(
                    "{} - {}".format(template.Name, comb.Valor))
                nome_proposto = nome_unico(nome_base)
                plano_items.append(NomeItem(
                    comb.Grupo, comb.Valor, nome_proposto, template, filtro_infos))

            if not plano_items:
                forms.alert("Nenhum schedule configurado.")
                return

            # Show confirm dialog
            confirm = ConfirmDialog(plano_items)
            confirm.ShowDialog()

            if not confirm.plano_final:
                return  # User cancelled

            self.resultado = confirm.plano_final
            self.Close()

        except Exception as e:
            forms.alert("Erro ao preparar schedules: {}".format(str(e)))

    def _on_cancel(self, sender, args):
        self.Close()

    # -----------------------------------------------------------------------
    # UI UPDATE
    # -----------------------------------------------------------------------

    def _update_ui(self):
        count = sum(1 for item in self._combinacoes if item.IsChecked)
        has_checked = count > 0
        if has_checked:
            label = "schedules" if count != 1 else "schedule"
            self.btnCriar.Content = "Revisar e Criar  {}  {}  >>>".format(count, label)
            self.btnCriar.IsEnabled = True
            self.lblSelecionadas.Text = "{} selecionada(s)".format(count)
        else:
            self.btnCriar.Content = "Criar Schedules"
            self.btnCriar.IsEnabled = False
            self.lblSelecionadas.Text = ""
        # Botoes de verificacao: so ativos quando ha combinacoes marcadas
        self.btnSelecionar.IsEnabled = has_checked
        self.btnIsolar.IsEnabled = has_checked
        self.btnVer3D.IsEnabled = has_checked


# ============================================================================
# MAIN
# ============================================================================

def main():
    output.print_md("## Schedule Plumbing v4.1")
    output.print_md("---")

    # Detectar pre-selecao MEP
    sel_mep = _detectar_sel_mep()
    if sel_mep:
        output.print_md("**{} elementos MEP pre-selecionados** (modo Selecao)".format(
            len(sel_mep)))
    else:
        output.print_md("**Sem pre-selecao** (modo Projeto ativo)")

    # Loop: janela pode solicitar re-selecao via resultado == "__RESELECT__"
    while True:
        janela = SchedulePlumbingWindow(sel_mep)
        janela.ShowDialog()

        res = janela.resultado

        # --- Re-selecionar elementos ---
        if res == "__RESELECT__":
            output.print_md("Aguardando selecao no modelo...")
            novos = _pick_elementos_mep()
            if novos is None:
                output.print_md("Selecao cancelada. Reabrindo janela.")
            elif len(novos) == 0:
                output.print_md("Nenhum elemento MEP. Reabrindo em modo Projeto.")
                sel_mep = []
            else:
                sel_mep = novos
                output.print_md("**{} elemento(s) MEP selecionado(s)**".format(len(sel_mep)))
            continue

        # --- Isolar na vista ativa ---
        if isinstance(res, tuple) and res[0] == "__ISOLATE__":
            ids = res[1]
            output.print_md("Isolando {} elemento(s) na vista ativa...".format(len(ids)))
            ok = _isolar_em_vista(ids)
            if ok:
                output.print_md(
                    "Isolamento aplicado. Feche o isolamento com **Esc** ou o icone de olho."
                    "\n\n*Execute a ferramenta novamente para continuar de onde parou.*")
            break  # Nao reabre — usuario fica livre no modelo

        # --- Abrir Vista 3D + isolar ---
        if isinstance(res, tuple) and res[0] == "__VISTA3D__":
            ids = res[1]
            output.print_md("Abrindo vista 3D com {} elemento(s)...".format(len(ids)))
            ok = _abrir_vista3d(ids)
            if ok:
                output.print_md(
                    "Vista 3D aberta com isolamento aplicado."
                    "\n\n*Execute a ferramenta novamente para continuar de onde parou.*")
            break  # Nao reabre

        # --- Cancelamento normal ---
        if not res:
            break

        # --- Criar schedules (fora do contexto WPF — API disponivel) ---
        output.print_md("\n### Criando schedules")
        criados = []
        for nome_item in res:
            nome_editado = nome_item.Nome.strip() or "Schedule"
            novo_nome = nome_unico(sanitize_view_name(nome_editado))
            novo = duplicar_e_filtrar_multi(
                nome_item.Template,
                nome_item.FiltroInfos,
                novo_nome
            )
            if novo:
                criados.append(novo)
                output.print_md("  OK **{}**".format(novo.Name))

        if criados:
            try:
                uidoc.ActiveView = criados[-1]
                uidoc.RefreshActiveView()
            except Exception:
                pass

        # Limpar estado salvo apos criacao bem-sucedida
        _clear_state()

        output.print_md("\n---")
        output.print_md("## {} schedule(s) criado(s)".format(len(criados)))
        if len(criados) > 1:
            output.print_md("*Os demais estao disponiveis no Project Browser.*")
        break


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        output.print_md("\n## Erro inesperado")
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
