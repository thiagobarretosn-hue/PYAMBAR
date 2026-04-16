# -*- coding: utf-8 -*-
"""Distribui familias de conexao ao longo de tubulacoes selecionadas em intervalos regulares.
Altera temporariamente a preferencia de roteamento (Union) do PipeType,
usa BreakCurve + NewUnionFitting para inserir fittings corretamente orientados,
e restaura a configuracao original ao final.

ALGORITMO (v4.0 - equidistante):
  available = length - 2 * min_edge
  N = ceil(available / spacing)          -> minimo de fittings para step <= spacing
  step = available / (N + 1)             -> espacamento real, sempre <= spacing
  1a quebra: (min_edge + step) do inicio do tubo
  demais:    step do inicio do segmento atual (sempre o segmento "para o fim")
"""
__title__ = "Distribuir\nFixtures"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.0"

import os, sys, traceback, math
import traceback
import clr
clr.AddReference("System")
from System.Collections.Generic import List
from System import Int64

from Autodesk.Revit.DB import (
    Transaction, FilteredElementCollector, ElementId,
    FamilySymbol, BuiltInCategory, XYZ, StorageType,
    RoutingPreferenceRuleGroupType, RoutingPreferenceRule
)
from Autodesk.Revit.DB.Plumbing import Pipe, PlumbingUtils
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script, DB

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

NONE_OPTION = "-- Nenhum (pular) --"
MIN_EDGE_DEFAULT = 0.5  # pes


from pyrevit.compat import get_elementid_value_func
get_element_id_value = get_elementid_value_func()


# ============================================================================
# 1) HELPERS
# ============================================================================

def is_pipe_vertical(pipe):
    """Retorna True se o tubo e vertical (Z dominante)."""
    loc = pipe.Location
    if not isinstance(loc, DB.LocationCurve):
        return False
    curve = loc.Curve
    direction = (curve.GetEndPoint(1) - curve.GetEndPoint(0)).Normalize()
    return abs(direction.Z) > 0.95


def get_pipe_fittings():
    """Busca todos os FamilySymbol de PipeFitting ordenados por nome."""
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_PipeFitting)
                 .OfClass(FamilySymbol))
    symbols = list(collector)

    def get_name(s):
        try:
            fam = s.Family.Name if s.Family else "?"
            return "{} - {}".format(fam, get_symbol_name(s))
        except Exception:
            return str(s.Id)

    return sorted(symbols, key=get_name)


def get_symbol_name(s):
    try:
        return s.Name
    except Exception:
        return str(s.Id)


def format_symbol_name(s):
    try:
        fam = s.Family.Name if s.Family else "?"
        return "{} - {}".format(fam, get_symbol_name(s))
    except Exception:
        return str(s.Id)


def find_symbol_by_family_name(symbols, family_name):
    """Retorna indice +1 (offset pelo NONE_OPTION) do symbol cuja Family.Name
    contem family_name, ou 0 se nao encontrado."""
    for i, s in enumerate(symbols):
        try:
            if family_name.upper() in s.Family.Name.upper():
                return i + 1
        except Exception:
            pass
    return 0


def get_free_connector_near(elem, point):
    """Retorna o conector livre mais proximo do ponto."""
    best = None
    best_dist = float('inf')
    for c in elem.ConnectorManager.Connectors:
        if not c.IsConnected:
            dist = c.Origin.DistanceTo(point)
            if dist < best_dist:
                best_dist = dist
                best = c
    return best


def swap_union_preference(rpm, new_symbol_id):
    """Troca a regra Union no RoutingPreferenceManager.
    Retorna o MEPPartId original para restaurar depois."""
    union_group = RoutingPreferenceRuleGroupType.Unions
    n_rules = rpm.GetNumberOfRules(union_group)

    original_id = None
    if n_rules > 0:
        original_id = rpm.GetRule(union_group, 0).MEPPartId
        rpm.RemoveRule(union_group, 0)

    new_rule = RoutingPreferenceRule(new_symbol_id, "PYAMBAR temp")
    rpm.AddRule(union_group, new_rule, 0)
    return original_id


def restore_union_preference(rpm, original_id):
    """Restaura a regra Union original."""
    union_group = RoutingPreferenceRuleGroupType.Unions
    n_rules = rpm.GetNumberOfRules(union_group)
    if n_rules > 0:
        rpm.RemoveRule(union_group, 0)

    if original_id is not None:
        restore_rule = RoutingPreferenceRule(original_id, "restored")
        rpm.AddRule(union_group, restore_rule, 0)


def copy_text_parameters(source_pipe, fitting):
    """Copia parametros de texto (String) editaveis do pipe para o fitting."""
    if not source_pipe or not fitting:
        return
    for p_src in source_pipe.Parameters:
        try:
            if p_src.StorageType != StorageType.String:
                continue
            if p_src.IsReadOnly:
                continue
            val = p_src.AsString()
            if not val:
                continue
            p_dst = fitting.LookupParameter(p_src.Definition.Name)
            if p_dst and not p_dst.IsReadOnly and p_dst.StorageType == StorageType.String:
                p_dst.Set(val)
        except Exception:
            pass


def distribute_on_single_pipe(pipe_id, spacing, min_edge, source_pipe=None):
    """Distribui N fittings equidistantes em um unico pipe.

    Algoritmo:
      available = length - 2 * min_edge
      N    = ceil(available / spacing)    -- minimo para step <= spacing
      step = available / (N + 1)          -- espacamento real (<= spacing)

      1a iteracao: quebra em (min_edge + step) do inicio
      demais:      quebra em step do inicio do segmento atual
      Apos cada quebra, continua sempre com o segmento de break_pt ate o fim.

    Retorna count (int).
    """
    pipe = doc.GetElement(pipe_id)
    if not pipe or not isinstance(pipe.Location, DB.LocationCurve):
        return 0

    curve = pipe.Location.Curve
    length = curve.Length
    available = length - 2.0 * min_edge

    if available <= 0.0:
        return 0

    N = int(math.ceil(available / spacing))
    if N == 0:
        return 0

    step = available / float(N + 1)
    count = 0
    current_id = pipe_id
    first = True

    for _ in range(N):
        seg = doc.GetElement(current_id)
        if not seg or not isinstance(seg.Location, DB.LocationCurve):
            break

        seg_curve  = seg.Location.Curve
        seg_length = seg_curve.Length

        # 1a quebra: margem inicial + 1 step; demais: apenas 1 step
        break_dist = (min_edge + step) if first else step
        first = False

        # Seguranca: ponto deve ficar estritamente dentro do segmento
        if break_dist + min_edge > seg_length + 1e-6:
            break

        param = break_dist / seg_length
        if not (0.0 < param < 1.0):
            break

        break_pt = seg_curve.Evaluate(param, True)

        try:
            new_id = PlumbingUtils.BreakCurve(doc, current_id, break_pt)
            if new_id == ElementId.InvalidElementId:
                break

            seg_a = doc.GetElement(current_id)
            seg_b = doc.GetElement(new_id)

            c1 = get_free_connector_near(seg_a, break_pt)
            c2 = get_free_connector_near(seg_b, break_pt)

            if c1 and c2:
                fitting = doc.Create.NewUnionFitting(c1, c2)
                if fitting:
                    copy_text_parameters(source_pipe, fitting)
                    count += 1

            # Sempre continuar com o segmento "break_pt -> fim"
            current_id = new_id

        except Exception:
            break

    return count


def _process_group(pipes, spacing, sym, min_edge):
    """Processa um grupo de pipes (todos horiz ou todos vert) com mesmo symbol.
    Agrupa por PipeType para minimizar trocas de preferencia.
    Retorna count total."""
    by_type = {}
    for pipe in pipes:
        type_id_val = get_element_id_value(pipe.GetTypeId())
        if type_id_val not in by_type:
            by_type[type_id_val] = {"type_id": pipe.GetTypeId(), "pipes": []}
        by_type[type_id_val]["pipes"].append(pipe)

    count = 0
    for group in by_type.values():
        pipe_type = doc.GetElement(group["type_id"])
        rpm = pipe_type.RoutingPreferenceManager

        original_id = swap_union_preference(rpm, sym.Id)
        try:
            for pipe in group["pipes"]:
                count += distribute_on_single_pipe(
                    pipe.Id, spacing, min_edge, pipe)
        finally:
            restore_union_preference(rpm, original_id)

    return count


def distribute_on_pipes(pipes, spacing_h, spacing_v, sym_horiz, sym_vert, min_edge):
    """Distribui fittings em todos os pipes, separando por orientacao.
    Retorna total inserido."""
    horiz_pipes = []
    vert_pipes  = []
    for pipe in pipes:
        if not isinstance(pipe.Location, DB.LocationCurve):
            continue
        if is_pipe_vertical(pipe):
            vert_pipes.append(pipe)
        else:
            horiz_pipes.append(pipe)

    total = 0

    if sym_horiz and horiz_pipes and spacing_h > 0:
        total += _process_group(horiz_pipes, spacing_h, sym_horiz, min_edge)

    if sym_vert and vert_pipes and spacing_v > 0:
        total += _process_group(vert_pipes, spacing_v, sym_vert, min_edge)

    return total


# ============================================================================
# 2) WPF
# ============================================================================

XAML_STRING = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Distribuir Fixtures" Height="420" Width="440"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
    <Grid Margin="15">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- HORIZONTAIS -->
        <TextBlock Grid.Row="0" Text="TUBOS HORIZONTAIS" FontWeight="Bold" FontSize="13" Margin="0,0,0,5"/>
        <Grid Grid.Row="1" Margin="0,0,0,5">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="100"/>
            </Grid.ColumnDefinitions>
            <ComboBox x:Name="cmb_horiz" Grid.Column="0" Margin="0,0,10,0"/>
            <TextBox x:Name="txt_spacing_h" Grid.Column="1" Text="5.0"/>
        </Grid>
        <TextBlock Grid.Row="2" Text="Familia                                                                  Espacamento (ft)"
                   Foreground="Gray" FontSize="10" Margin="0,0,0,10"/>

        <!-- VERTICAIS -->
        <TextBlock Grid.Row="3" Text="TUBOS VERTICAIS" FontWeight="Bold" FontSize="13" Margin="0,5,0,5"/>
        <Grid Grid.Row="4" Margin="0,0,0,5">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="100"/>
            </Grid.ColumnDefinitions>
            <ComboBox x:Name="cmb_vert" Grid.Column="0" Margin="0,0,10,0"/>
            <TextBox x:Name="txt_spacing_v" Grid.Column="1" Text="5.0"/>
        </Grid>
        <TextBlock Grid.Row="5" Text="Familia                                                                  Espacamento (ft)"
                   Foreground="Gray" FontSize="10" Margin="0,0,0,10"/>

        <!-- CONFIGURACAO -->
        <TextBlock Grid.Row="6" Text="CONFIGURACAO" FontWeight="Bold" FontSize="13" Margin="0,5,0,5"/>
        <StackPanel Grid.Row="7" Orientation="Horizontal" Margin="0,0,0,5">
            <TextBlock Text="Distancia minima das extremidades (ft):" VerticalAlignment="Center"/>
            <TextBox x:Name="txt_min_edge" Text="0.5" Width="60" Margin="10,0,0,0"/>
        </StackPanel>
        <TextBlock Grid.Row="8" Text="Fittings distribuidos equidistantemente com step = available / (N+1)"
                   Foreground="Gray" FontStyle="Italic" FontSize="10" Margin="0,0,0,5"/>
        <TextBlock Grid.Row="9" Text="Selecione '-- Nenhum (pular) --' para ignorar uma orientacao."
                   Foreground="DimGray" FontStyle="Italic" FontSize="10" Margin="0,0,0,5"/>

        <!-- BOTOES -->
        <StackPanel Grid.Row="10" Orientation="Horizontal" HorizontalAlignment="Right">
            <Button x:Name="btn_cancel" Content="Cancelar" Width="80" Margin="0,0,10,0"/>
            <Button x:Name="btn_apply" Content="Executar" Width="90" IsDefault="True"/>
        </StackPanel>
    </Grid>
</Window>
"""


class ConfigWindow(forms.WPFWindow):
    """Janela modal para configuracao."""

    def __init__(self, symbols, default_horiz_idx, default_vert_idx):
        forms.WPFWindow.__init__(self, XAML_STRING, literal_string=True)
        self.resultado  = None
        self.sym_horiz  = None
        self.sym_vert   = None
        self.spacing_h  = 5.0
        self.spacing_v  = 5.0
        self.min_edge   = MIN_EDGE_DEFAULT
        self._symbols   = symbols

        self.btn_cancel.Click += self.on_cancel
        self.btn_apply.Click  += self.on_apply

        names = [NONE_OPTION] + [format_symbol_name(s) for s in symbols]
        self.cmb_horiz.ItemsSource = names
        self.cmb_vert.ItemsSource  = names

        self.cmb_horiz.SelectedIndex = default_horiz_idx
        self.cmb_vert.SelectedIndex  = default_vert_idx

    def _parse_float(self, text, field_name):
        try:
            val = float(text.replace(',', '.'))
            if val <= 0:
                forms.alert("{} deve ser maior que zero.".format(field_name), exitscript=False)
                return None
            return val
        except Exception:
            forms.alert("{}: valor invalido.".format(field_name), exitscript=False)
            return None

    def on_cancel(self, sender, e):
        self.resultado = None
        self.Close()

    def on_apply(self, sender, e):
        h_idx = self.cmb_horiz.SelectedIndex
        v_idx = self.cmb_vert.SelectedIndex

        if h_idx == 0 and v_idx == 0:
            forms.alert("Selecione pelo menos uma familia (horizontal ou vertical).",
                        exitscript=False)
            return

        if h_idx > 0:
            sp_h = self._parse_float(self.txt_spacing_h.Text, "Espacamento horizontal")
            if sp_h is None:
                return
            self.spacing_h = sp_h
            self.sym_horiz = self._symbols[h_idx - 1]
        else:
            self.sym_horiz = None

        if v_idx > 0:
            sp_v = self._parse_float(self.txt_spacing_v.Text, "Espacamento vertical")
            if sp_v is None:
                return
            self.spacing_v = sp_v
            self.sym_vert = self._symbols[v_idx - 1]
        else:
            self.sym_vert = None

        me = self._parse_float(self.txt_min_edge.Text, "Distancia minima")
        if me is None:
            return
        self.min_edge = me

        self.resultado = "ok"
        self.Close()


# ============================================================================
# 3) MAIN
# ============================================================================

def main():
    try:
        global doc, uidoc
        doc = revit.doc
        uidoc = revit.uidoc

        try:
            sel_ids = uidoc.Selection.GetElementIds()
            pipes = []
            for eid in sel_ids:
                elem = doc.GetElement(eid)
                if isinstance(elem, Pipe):
                    pipes.append(elem)

            if not pipes:
                forms.alert("Selecione tubulacoes (Pipes) antes de executar.",
                            exitscript=True)

            n_horiz = sum(1 for p in pipes if not is_pipe_vertical(p))
            n_vert  = sum(1 for p in pipes if is_pipe_vertical(p))

            symbols = get_pipe_fittings()
            if not symbols:
                forms.alert("Nenhuma familia de Pipe Fitting carregada no projeto.",
                            exitscript=True)

            idx_horiz = find_symbol_by_family_name(symbols, "LOOP HANGER")
            idx_vert  = find_symbol_by_family_name(symbols, "Riser Clamp")

            # WPF modal -- fecha ANTES da Transaction
            janela = ConfigWindow(symbols, idx_horiz, idx_vert)
            janela.ShowDialog()

            if janela.resultado != "ok":
                return

            s_horiz   = janela.sym_horiz
            s_vert    = janela.sym_vert
            spacing_h = janela.spacing_h
            spacing_v = janela.spacing_v
            min_edge  = janela.min_edge

            # Transaction DEPOIS do ShowDialog
            with revit.Transaction("Distribuir Fixtures"):
                if s_horiz and not s_horiz.IsActive:
                    s_horiz.Activate()
                if s_vert and not s_vert.IsActive:
                    s_vert.Activate()

                total = distribute_on_pipes(
                    pipes, spacing_h, spacing_v, s_horiz, s_vert, min_edge)

            msg = "**Concluido!** {} fixtures inseridos.\n\n".format(total)
            msg += "- {} tubos selecionados ({} horizontais, {} verticais)\n".format(
                len(pipes), n_horiz, n_vert)
            if s_horiz:
                msg += "- Horizontal: {} | espacamento: {} ft\n".format(
                    format_symbol_name(s_horiz), spacing_h)
            if s_vert:
                msg += "- Vertical: {} | espacamento: {} ft\n".format(
                    format_symbol_name(s_vert), spacing_v)
            msg += "- Distancia minima das extremidades: {} ft\n".format(min_edge)
            msg += "- Algoritmo: equidistante (step = available / (N+1))"
            output.print_md(msg)

        except OperationCanceledException:
            return
        except Exception as e:
            output.print_md("**Erro:** {}".format(str(e)))
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
if __name__ == "__main__":
    main()
