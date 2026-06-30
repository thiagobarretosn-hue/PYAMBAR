# -*- coding: utf-8 -*-
"""Divide tubulacoes em secoes de comprimento comercial inserindo unioes.

ALGORITMO:
  Cortes a partir do INICIO do segmento atual em multiplos do comprimento comercial.
  O residuo fica ao final. Um corte e pulado se:
    - residuo < tolerancia * comprimento_comercial  (evita treco pequeno no final)
    - ponto de corte esta a menos de min_edge_ft de qualquer conector
"""
__title__ = "Secoes\nComerciais"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.2"

import os, sys, traceback
import clr
clr.AddReference("System")
from System import Int64
from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    Transaction, FilteredElementCollector, ElementId,
    FamilySymbol, BuiltInCategory, XYZ,
    StorageType, BuiltInParameter,
    RoutingPreferenceRuleGroupType, RoutingPreferenceRule
)
from Autodesk.Revit.DB.Plumbing import Pipe, PlumbingUtils
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script, DB

doc   = revit.doc
uidoc = revit.uidoc

PRESET_CPVC_FT    = 10.0   # 10 feet = 3048 mm
PRESET_PVC_FT     = 20.0   # 20 feet = 6096 mm
RPM_DEFAULT_LABEL = "-- RPM padrao --"


from pyrevit.compat import get_elementid_value_func
get_element_id_value = get_elementid_value_func()


def xml_escape(text):
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


# ============================================================================
# 1) HELPERS
# ============================================================================

def format_symbol_name(s):
    """Retorna nome legivel para FamilySymbol. Tenta Family.Name : Symbol.Name."""
    if s is None:
        return "N/A"
    fam_name = ""
    sym_name = ""
    try:
        fam = s.Family
        if fam is not None:
            fam_name = fam.Name or ""
    except Exception:
        pass
    try:
        sym_name = s.Name or ""
    except Exception:
        pass
    if fam_name and sym_name and fam_name != sym_name:
        return "{} : {}".format(fam_name, sym_name)
    if fam_name:
        return fam_name
    if sym_name:
        return sym_name
    return "ID {}".format(get_element_id_value(s.Id))


def get_pipe_type_name(pipe_type, tid_val):
    """Retorna nome legivel para PipeType com fallback para parametro do sistema."""
    try:
        n = pipe_type.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = pipe_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p:
            n = p.AsString()
            if n:
                return n
    except Exception:
        pass
    return "ID {}".format(tid_val)


def get_union_from_rpm(pipe_type):
    """Retorna elemento da primeira regra Union no RPM do PipeType, ou None."""
    try:
        rpm    = pipe_type.RoutingPreferenceManager
        grp    = RoutingPreferenceRuleGroupType.Unions
        if rpm.GetNumberOfRules(grp) == 0:
            return None
        sym_id = rpm.GetRule(grp, 0).MEPPartId
        if sym_id == ElementId.InvalidElementId:
            return None
        return doc.GetElement(sym_id)
    except Exception:
        return None


def get_pipe_fitting_symbols():
    """Busca todos os FamilySymbol de PipeFitting ordenados por nome."""
    symbols = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_PipeFitting)
        .OfClass(FamilySymbol)
    )
    return sorted(symbols, key=lambda s: format_symbol_name(s))


def get_free_connector_near(elem, point):
    """Retorna o conector livre mais proximo do ponto."""
    best      = None
    best_dist = float('inf')
    for c in elem.ConnectorManager.Connectors:
        if not c.IsConnected:
            dist = c.Origin.DistanceTo(point)
            if dist < best_dist:
                best_dist = dist
                best      = c
    return best


def point_near_connector(pipe, point, min_dist):
    """Retorna True se o ponto esta a menos de min_dist de qualquer conector do pipe."""
    for c in pipe.ConnectorManager.Connectors:
        if c.Origin.DistanceTo(point) < min_dist:
            return True
    return False


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


def swap_union_preference(rpm, new_symbol_id):
    """Troca a regra Union no RPM. Retorna o MEPPartId original."""
    grp     = RoutingPreferenceRuleGroupType.Unions
    orig_id = None
    if rpm.GetNumberOfRules(grp) > 0:
        orig_id = rpm.GetRule(grp, 0).MEPPartId
        rpm.RemoveRule(grp, 0)
    rpm.AddRule(grp, RoutingPreferenceRule(new_symbol_id, "PYAMBAR temp"), 0)
    return orig_id


def restore_union_preference(rpm, original_id):
    """Restaura a regra Union original."""
    grp = RoutingPreferenceRuleGroupType.Unions
    if rpm.GetNumberOfRules(grp) > 0:
        rpm.RemoveRule(grp, 0)
    if original_id is not None:
        rpm.AddRule(grp, RoutingPreferenceRule(original_id, "restored"), 0)


# ============================================================================
# 2) ALGORITMO
# ============================================================================

def divide_single_pipe(pipe_id, commercial_ft, min_edge_ft, tolerance):
    """Divide um pipe em secoes de comprimento comercial.

    A cada iteracao lemos o comprimento REAL do segmento atual para evitar
    acumulo de erro de ponto flutuante. Copia parametros de texto do pipe
    para cada uniao inserida.

    Retorna o numero de unioes inseridas.
    """
    count      = 0
    current_id = pipe_id

    while True:
        seg = doc.GetElement(current_id)
        if not seg or not isinstance(seg.Location, DB.LocationCurve):
            break

        seg_curve  = seg.Location.Curve
        seg_length = seg_curve.Length

        if seg_length <= commercial_ft + 1e-6:
            break

        residuo = seg_length - commercial_ft
        if residuo < tolerance * commercial_ft:
            break

        param = commercial_ft / seg_length
        if not (0.001 < param < 0.999):
            break

        break_pt = seg_curve.Evaluate(param, True)

        if point_near_connector(seg, break_pt, min_edge_ft):
            break

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
                    copy_text_parameters(seg, fitting)
                    count += 1

            current_id = new_id

        except Exception:
            break

    return count


def process_pipes(pipes, type_lengths, min_edge_ft, tolerance, type_overrides):
    """Processa todos os pipes agrupados por PipeType.

    type_lengths:   {type_id_val -> commercial_ft}
    type_overrides: {type_id_val -> FamilySymbol}
      Chave ausente = usar RPM configurado no PipeType (sem troca).

    Retorna (total, per_type_counts {tid_val -> count}).
    """
    by_type = {}
    for pipe in pipes:
        if not isinstance(pipe.Location, DB.LocationCurve):
            continue
        tid_val = get_element_id_value(pipe.GetTypeId())
        if tid_val not in by_type:
            by_type[tid_val] = {"type_id": pipe.GetTypeId(), "pipes": []}
        by_type[tid_val]["pipes"].append(pipe)

    total           = 0
    per_type_counts = {}

    for tid_val, group in by_type.items():
        pipe_type     = doc.GetElement(group["type_id"])
        rpm           = pipe_type.RoutingPreferenceManager
        override      = type_overrides.get(tid_val)
        commercial_ft = type_lengths.get(tid_val, PRESET_CPVC_FT)

        if override is not None:
            original_id = swap_union_preference(rpm, override.Id)
        else:
            original_id = None

        count = 0
        try:
            for pipe in group["pipes"]:
                count += divide_single_pipe(
                    pipe.Id, commercial_ft, min_edge_ft, tolerance)
        finally:
            if override is not None:
                restore_union_preference(rpm, original_id)

        total += count
        per_type_counts[tid_val] = count

    return total, per_type_counts


# ============================================================================
# 3) WPF  -  XAML gerado dinamicamente
# ============================================================================

XAML_BASE = """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Secoes Comerciais" SizeToContent="Height" Width="570"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
    <StackPanel Margin="14">

        <!-- COMPRIMENTO COMERCIAL -->
        <TextBlock Text="COMPRIMENTO COMERCIAL" FontWeight="Bold" FontSize="13" Margin="0,0,0,6"/>
        <StackPanel Orientation="Horizontal" Margin="0,0,0,2">
            <TextBlock Text="Predefinir todos:" VerticalAlignment="Center" Margin="0,0,8,0"/>
            <Button x:Name="btn_cpvc" Content="CPVC 10&apos;" Width="76" Margin="0,0,6,0"/>
            <Button x:Name="btn_pvc"  Content="PVC 20&apos;"  Width="76"/>
        </StackPanel>
        <TextBlock Text="Ajuste individualmente por tipo na tabela abaixo."
                   Foreground="Gray" FontSize="10" FontStyle="Italic" Margin="0,2,0,12"/>

        <!-- CONFIGURACAO -->
        <TextBlock Text="CONFIGURACAO" FontWeight="Bold" FontSize="13" Margin="0,0,0,6"/>
        <Grid Margin="0,0,0,12">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto"/>
                <ColumnDefinition Width="65"/>
                <ColumnDefinition Width="16"/>
                <ColumnDefinition Width="Auto"/>
                <ColumnDefinition Width="55"/>
            </Grid.ColumnDefinitions>
            <TextBlock Grid.Column="0" Text="Distancia de seguranca (ft):"
                       VerticalAlignment="Center" Margin="0,0,8,0"/>
            <TextBox x:Name="txt_min_edge"  Grid.Column="1" Text="0.5"/>
            <TextBlock Grid.Column="2"/>
            <TextBlock Grid.Column="3" Text="Tolerancia (%):"
                       VerticalAlignment="Center" Margin="0,0,8,0"/>
            <TextBox x:Name="txt_tolerance" Grid.Column="4" Text="10"/>
        </Grid>

        <!-- MATERIAIS -->
        <TextBlock Text="MATERIAIS / UNIAO" FontWeight="Bold" FontSize="13" Margin="0,0,0,4"/>
        <Grid Margin="0,0,0,4">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="145"/>
                <ColumnDefinition Width="135"/>
                <ColumnDefinition Width="65"/>
                <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <TextBlock Grid.Column="0" Text="Tipo de tubo"        Foreground="Gray" FontSize="10"/>
            <TextBlock Grid.Column="1" Text="Uniao (RPM)"         Foreground="Gray" FontSize="10"/>
            <TextBlock Grid.Column="2" Text="Compr. (ft)"         Foreground="Gray" FontSize="10"/>
            <TextBlock Grid.Column="3" Text="Override (opcional)" Foreground="Gray" FontSize="10"/>
        </Grid>
        <ScrollViewer MaxHeight="220" VerticalScrollBarVisibility="Auto" Margin="0,0,0,12">
            <StackPanel>
{material_rows}
            </StackPanel>
        </ScrollViewer>

        <!-- BOTOES -->
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
            <Button x:Name="btn_cancel" Content="Cancelar" Width="80" Margin="0,0,10,0"/>
            <Button x:Name="btn_apply"  Content="Executar"  Width="90" IsDefault="True"/>
        </StackPanel>

    </StackPanel>
</Window>"""

ROW_TEMPLATE = """                <Grid Margin="0,0,0,5">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="145"/>
                        <ColumnDefinition Width="135"/>
                        <ColumnDefinition Width="65"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>
                    <TextBlock Grid.Column="0" Text="{type_name}"
                               VerticalAlignment="Center" TextWrapping="Wrap"/>
                    <TextBlock Grid.Column="1" Text="{rpm_text}"
                               VerticalAlignment="Center" TextWrapping="Wrap"
                               Foreground="{rpm_color}"/>
                    <TextBox x:Name="txt_len_{idx}" Grid.Column="2"
                             Text="{default_len}" VerticalAlignment="Center"/>
                    <ComboBox x:Name="cmb_type_{idx}" Grid.Column="3"/>
                </Grid>"""


def build_xaml(type_info):
    rows = []
    for i, (_, info) in enumerate(type_info.items()):
        rpm_sym   = info["rpm_sym"]
        rpm_text  = xml_escape(format_symbol_name(rpm_sym)) if rpm_sym else "Nao detectado"
        rpm_color = "#005A00" if rpm_sym else "#CC0000"
        rows.append(ROW_TEMPLATE.format(
            type_name   = xml_escape(info["name"]),
            rpm_text    = rpm_text,
            rpm_color   = rpm_color,
            default_len = str(PRESET_CPVC_FT),
            idx         = i,
        ))
    return XAML_BASE.format(material_rows="\n".join(rows))


class ConfigWindow(forms.WPFWindow):
    """Janela modal para configuracao de secoes comerciais."""

    def __init__(self, pipes):
        # 1) Coletar tipos ANTES de construir o XAML
        self._type_info = self._collect_type_info(pipes)

        # 2) Symbols para override
        self._symbols        = get_pipe_fitting_symbols()
        self._override_names = [RPM_DEFAULT_LABEL] + [
            format_symbol_name(s) for s in self._symbols]

        # 3) Inicializar WPF com XAML dinamico
        forms.WPFWindow.__init__(self, build_xaml(self._type_info), literal_string=True)

        # 4) Preencher ComboBoxes de override
        self._combos = {}   # tid_val -> ComboBox
        for i, tid_val in enumerate(self._type_info.keys()):
            cmb = self.FindName("cmb_type_{}".format(i))
            if cmb is not None:
                cmb.ItemsSource   = self._override_names
                cmb.SelectedIndex = 0
                self._combos[tid_val] = cmb

        # 5) Resultados
        self.resultado      = None
        self.min_edge_ft    = 0.5
        self.tolerance      = 0.10
        self.type_lengths   = {}
        self.type_overrides = {}

        # 6) Eventos
        self.btn_cpvc.Click   += self._on_cpvc
        self.btn_pvc.Click    += self._on_pvc
        self.btn_cancel.Click += self._on_cancel
        self.btn_apply.Click  += self._on_apply

    def _collect_type_info(self, pipes):
        info = {}
        seen = set()
        for pipe in pipes:
            tid_val = get_element_id_value(pipe.GetTypeId())
            if tid_val in seen:
                continue
            seen.add(tid_val)
            pipe_type = doc.GetElement(pipe.GetTypeId())
            info[tid_val] = {
                "type_id": pipe.GetTypeId(),
                "name":    get_pipe_type_name(pipe_type, tid_val),
                "rpm_sym": get_union_from_rpm(pipe_type),
            }
        return info

    def _set_all_lengths(self, ft_str):
        for i in range(len(self._type_info)):
            txt = self.FindName("txt_len_{}".format(i))
            if txt is not None:
                txt.Text = ft_str

    def _on_cpvc(self, sender, e):
        self._set_all_lengths(str(PRESET_CPVC_FT))

    def _on_pvc(self, sender, e):
        self._set_all_lengths(str(PRESET_PVC_FT))

    def _on_cancel(self, sender, e):
        self.resultado = None
        self.Close()

    def _parse_float_pos(self, text, field_name):
        try:
            val = float(text.strip().replace(',', '.'))
            if val <= 0:
                forms.alert("{} deve ser maior que zero.".format(field_name),
                            exitscript=False)
                return None
            return val
        except Exception:
            forms.alert("{}: valor invalido.".format(field_name), exitscript=False)
            return None

    def _on_apply(self, sender, e):
        min_edge = self._parse_float_pos(self.txt_min_edge.Text, "Distancia de seguranca")
        if min_edge is None:
            return

        tol_pct = self._parse_float_pos(self.txt_tolerance.Text, "Tolerancia")
        if tol_pct is None:
            return

        # Comprimento por tipo
        type_lengths = {}
        for i, tid_val in enumerate(self._type_info.keys()):
            txt = self.FindName("txt_len_{}".format(i))
            if txt is not None:
                val = self._parse_float_pos(
                    txt.Text,
                    "Comprimento ({})".format(self._type_info[tid_val]["name"])
                )
                if val is None:
                    return
                type_lengths[tid_val] = val
            else:
                type_lengths[tid_val] = PRESET_CPVC_FT

        # Override por tipo
        overrides = {}
        for tid_val, cmb in self._combos.items():
            idx = cmb.SelectedIndex
            if idx > 0:
                overrides[tid_val] = self._symbols[idx - 1]

        self.min_edge_ft    = min_edge
        self.tolerance      = tol_pct / 100.0
        self.type_lengths   = type_lengths
        self.type_overrides = overrides
        self.resultado      = "ok"
        self.Close()


# ============================================================================
# 4) MAIN
# ============================================================================

def main():
    try:
        sel_ids = uidoc.Selection.GetElementIds()
        pipes   = []
        for eid in sel_ids:
            elem = doc.GetElement(eid)
            if isinstance(elem, Pipe):
                pipes.append(elem)

        if not pipes:
            forms.alert("Selecione tubulacoes (Pipes) antes de executar.",
                        exitscript=True)

        # WPF modal -- fecha ANTES da Transaction
        janela = ConfigWindow(pipes)
        janela.ShowDialog()

        if janela.resultado != "ok":
            return

        min_edge_ft    = janela.min_edge_ft
        tolerance      = janela.tolerance
        type_lengths   = janela.type_lengths
        type_overrides = janela.type_overrides
        type_info      = janela._type_info

        # Transaction DEPOIS do ShowDialog
        with revit.Transaction("Secoes Comerciais"):
            for sym in type_overrides.values():
                if sym and not sym.IsActive:
                    sym.Activate()

            total, per_type = process_pipes(
                pipes, type_lengths, min_edge_ft, tolerance, type_overrides)

        msg = "**Concluido!** {} unioes inseridas.\n\n".format(total)
        msg += "- {} tubos processados\n".format(len(pipes))
        msg += "- Distancia de seguranca: {} ft\n".format(min_edge_ft)
        msg += "- Tolerancia: {}%\n\n".format(int(tolerance * 100))
        msg += "**Por tipo:**\n"
        for tid_val, count in per_type.items():
            name = type_info[tid_val]["name"]
            ft   = type_lengths.get(tid_val, PRESET_CPVC_FT)
            mm   = int(round(ft * 304.8))
            msg += "- {}: {} unioes | {} ft ({} mm)\n".format(name, count, ft, mm)
        forms.alert(msg.replace("**", ""))

    except OperationCanceledException:
        return
    except Exception as e:
        forms.alert("Erro: {}".format(str(e)))


if __name__ == "__main__":
    main()
