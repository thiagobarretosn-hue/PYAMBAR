# -*- coding: utf-8 -*-
"""Distribui familias de conexao ao longo de tubulacoes selecionadas em intervalos regulares.
Altera temporariamente a preferencia de roteamento (Union) do PipeType,
usa BreakCurve + NewUnionFitting para inserir fittings corretamente orientados,
e restaura a configuracao original ao final."""
__title__ = "Distribuir\nFixtures"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0"

import os, sys, traceback
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
MIN_EDGE_DEFAULT = 0.5  # 6 polegadas em pes


def get_element_id_value(elem_id):
    return elem_id.Value if hasattr(elem_id, 'Value') else elem_id.IntegerValue


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
        except:
            return str(s.Id)

    return sorted(symbols, key=get_name)


def get_symbol_name(s):
    """Acessa Element.Name de forma segura no IronPython."""
    try:
        return s.Name
    except:
        return str(s.Id)


def format_symbol_name(s):
    """Retorna nome formatado: 'Family - Type'."""
    try:
        fam = s.Family.Name if s.Family else "?"
        return "{} - {}".format(fam, get_symbol_name(s))
    except:
        return str(s.Id)


def find_symbol_by_family_name(symbols, family_name):
    """Encontra o indice do symbol cuja Family.Name contem family_name.
    Retorna indice +1 (offset pelo NONE_OPTION no inicio da lista)."""
    for i, s in enumerate(symbols):
        try:
            if family_name.upper() in s.Family.Name.upper():
                return i + 1  # +1 por causa do NONE_OPTION
        except:
            pass
    return 0  # NONE_OPTION


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
            # Buscar parametro com mesmo nome no fitting
            p_dst = fitting.LookupParameter(p_src.Definition.Name)
            if p_dst and not p_dst.IsReadOnly and p_dst.StorageType == StorageType.String:
                p_dst.Set(val)
        except:
            pass


def distribute_on_single_pipe(pipe_id, spacing, min_edge, source_pipe=None, tolerance_pct=0):
    """Distribui fittings iterativamente em um unico pipe.
    A cada iteracao, re-le a curva do pipe atual e calcula o proximo ponto.
    Retorna (count, near_miss_info).
    near_miss_info = None ou dict com dados do pipe que quase coube."""
    count = 0
    near_miss = None

    while True:
        pipe = doc.GetElement(pipe_id)
        if not pipe or not isinstance(pipe.Location, DB.LocationCurve):
            break

        curve = pipe.Location.Curve
        length = curve.Length

        # Precisa de espaco: spacing + min_edge na ponta restante
        if length < spacing + min_edge:
            # Checar near-miss: tubo quase longo o suficiente
            if tolerance_pct > 0:
                threshold = spacing * (1.0 - tolerance_pct / 100.0)
                # Considerar min_edge: se o tubo >= threshold mas < spacing + min_edge
                if length >= threshold and length < spacing + min_edge:
                    deficit_pct = ((spacing + min_edge) - length) / spacing * 100.0
                    near_miss = {
                        "pipe_id": pipe_id,
                        "length": length,
                        "spacing": spacing,
                        "deficit_pct": deficit_pct,
                        "source_pipe": source_pipe
                    }
            break

        # Ponto exato na curva usando Evaluate (parametro normalizado)
        param = spacing / length
        break_pt = curve.Evaluate(param, True)

        # Verificar se sobra suficiente na outra ponta
        remaining = length - spacing
        if remaining < min_edge:
            break

        try:
            new_pipe_id = PlumbingUtils.BreakCurve(doc, pipe_id, break_pt)

            pipe_a = doc.GetElement(pipe_id)
            pipe_b = doc.GetElement(new_pipe_id)

            c1 = get_free_connector_near(pipe_a, break_pt)
            c2 = get_free_connector_near(pipe_b, break_pt)

            if c1 and c2:
                fitting = doc.Create.NewUnionFitting(c1, c2)
                if fitting:
                    copy_text_parameters(source_pipe, fitting)
                    count += 1

            # Continuar com o segmento MAIS LONGO (que tem espaco para mais breaks)
            len_a = pipe_a.Location.Curve.Length if isinstance(pipe_a.Location, DB.LocationCurve) else 0
            len_b = pipe_b.Location.Curve.Length if isinstance(pipe_b.Location, DB.LocationCurve) else 0
            pipe_id = pipe_id if len_a >= len_b else new_pipe_id

        except Exception as e:
            # Se falhou, nao insistir nesse pipe
            break

    return count, near_miss


def distribute_on_pipes(pipes, spacing_h, spacing_v, sym_horiz, sym_vert, min_edge, tolerance_pct=0):
    """Distribui fittings em todos os pipes.
    Agrupa por PipeType e orientacao para minimizar trocas de preferencia.
    Retorna (total_inseridos, lista_near_misses)."""
    # Separar pipes por orientacao
    horiz_pipes = []
    vert_pipes = []
    for pipe in pipes:
        if not isinstance(pipe.Location, DB.LocationCurve):
            continue
        if is_pipe_vertical(pipe):
            vert_pipes.append(pipe)
        else:
            horiz_pipes.append(pipe)

    total = 0
    all_near_misses = []

    # Processar horizontais
    if sym_horiz and horiz_pipes and spacing_h > 0:
        cnt, misses = _process_group(horiz_pipes, spacing_h, sym_horiz, min_edge, tolerance_pct)
        total += cnt
        for m in misses:
            m["orientation"] = "H"
            m["sym"] = sym_horiz
        all_near_misses.extend(misses)

    # Processar verticais
    if sym_vert and vert_pipes and spacing_v > 0:
        cnt, misses = _process_group(vert_pipes, spacing_v, sym_vert, min_edge, tolerance_pct)
        total += cnt
        for m in misses:
            m["orientation"] = "V"
            m["sym"] = sym_vert
        all_near_misses.extend(misses)

    return total, all_near_misses


def _process_group(pipes, spacing, sym, min_edge, tolerance_pct=0):
    """Processa um grupo de pipes (todos horiz ou todos vert) com mesmo symbol.
    Retorna (count, near_misses)."""
    # Agrupar por PipeType
    by_type = {}
    for pipe in pipes:
        type_id_val = get_element_id_value(pipe.GetTypeId())
        if type_id_val not in by_type:
            by_type[type_id_val] = {
                "type_id": pipe.GetTypeId(),
                "pipes": []
            }
        by_type[type_id_val]["pipes"].append(pipe)

    count = 0
    near_misses = []
    for group in by_type.values():
        pipe_type = doc.GetElement(group["type_id"])
        rpm = pipe_type.RoutingPreferenceManager

        original_id = swap_union_preference(rpm, sym.Id)
        try:
            for pipe in group["pipes"]:
                added, miss = distribute_on_single_pipe(
                    pipe.Id, spacing, min_edge, pipe, tolerance_pct)
                count += added
                if miss:
                    miss["type_id"] = group["type_id"]
                    near_misses.append(miss)
        finally:
            restore_union_preference(rpm, original_id)

    return count, near_misses


# ============================================================================
# 2) WPF
# ============================================================================

XAML_STRING = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Distribuir Fixtures" Height="490" Width="440"
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
        <TextBlock Grid.Row="8" Text="Evita segmentos muito curtos nas pontas do tubo"
                   Foreground="Gray" FontSize="10" Margin="0,0,0,5"/>

        <StackPanel Grid.Row="9" Orientation="Horizontal" Margin="0,0,0,5">
            <TextBlock Text="Tolerancia para tubos quase compativeis (%):" VerticalAlignment="Center"/>
            <TextBox x:Name="txt_tolerance" Text="15" Width="50" Margin="10,0,0,0"/>
        </StackPanel>
        <TextBlock Grid.Row="10" Text="Tubos dentro da tolerancia serao listados para aprovacao manual"
                   Foreground="Gray" FontSize="10" Margin="0,0,0,10"/>

        <!-- INFO -->
        <TextBlock Grid.Row="11" Text="Selecione '-- Nenhum (pular) --' para ignorar uma orientacao."
                   Foreground="DimGray" FontStyle="Italic" FontSize="10" Margin="0,0,0,5"/>

        <!-- BOTOES -->
        <StackPanel Grid.Row="13" Orientation="Horizontal" HorizontalAlignment="Right">
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
        self.resultado = None
        self.sym_horiz = None
        self.sym_vert = None
        self.spacing_h = 5.0
        self.spacing_v = 5.0
        self.min_edge = MIN_EDGE_DEFAULT
        self.tolerance_pct = 15.0
        self._symbols = symbols

        self.btn_cancel.Click += self.on_cancel
        self.btn_apply.Click += self.on_apply

        # Lista com opcao "Nenhum" no inicio
        names = [NONE_OPTION] + [format_symbol_name(s) for s in symbols]
        self.cmb_horiz.ItemsSource = names
        self.cmb_vert.ItemsSource = names

        self.cmb_horiz.SelectedIndex = default_horiz_idx
        self.cmb_vert.SelectedIndex = default_vert_idx

    def _parse_float(self, text, field_name):
        try:
            val = float(text.replace(',', '.'))
            if val <= 0:
                forms.alert("{} deve ser maior que zero.".format(field_name), exitscript=False)
                return None
            return val
        except:
            forms.alert("{}: valor invalido.".format(field_name), exitscript=False)
            return None

    def on_cancel(self, sender, e):
        self.resultado = None
        self.Close()

    def on_apply(self, sender, e):
        h_idx = self.cmb_horiz.SelectedIndex
        v_idx = self.cmb_vert.SelectedIndex

        # Pelo menos um deve ser selecionado
        if h_idx == 0 and v_idx == 0:
            forms.alert("Selecione pelo menos uma familia (horizontal ou vertical).",
                        exitscript=False)
            return

        # Parse espacamentos (so valida se familia selecionada)
        if h_idx > 0:
            sp_h = self._parse_float(self.txt_spacing_h.Text, "Espacamento horizontal")
            if sp_h is None:
                return
            self.spacing_h = sp_h
            self.sym_horiz = self._symbols[h_idx - 1]  # -1 pelo NONE_OPTION
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

        # Min edge
        me = self._parse_float(self.txt_min_edge.Text, "Distancia minima")
        if me is None:
            return
        self.min_edge = me

        # Tolerancia
        try:
            tol = float(self.txt_tolerance.Text.replace(',', '.'))
            if tol < 0:
                forms.alert("Tolerancia deve ser >= 0.", exitscript=False)
                return
            self.tolerance_pct = tol
        except:
            forms.alert("Tolerancia: valor invalido.", exitscript=False)
            return

        self.resultado = "ok"
        self.Close()


# ============================================================================
# 3) NEAR-MISS APPROVAL
# ============================================================================

class NearMissItem(object):
    """Wrapper para exibir near-miss no SelectFromList."""
    def __init__(self, miss_data, index):
        self._data = miss_data
        self._index = index
        orient = "Horiz" if miss_data["orientation"] == "H" else "Vert"
        self.name = "#{} [{}] Pipe {} - {:.2f} ft (faltam {:.1f}%)".format(
            index + 1,
            orient,
            get_element_id_value(miss_data["pipe_id"]),
            miss_data["length"],
            miss_data["deficit_pct"]
        )
        self.state = True  # pre-marcado

    @property
    def data(self):
        return self._data

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


def insert_fixture_on_near_miss(miss_data, min_edge):
    """Insere fixture no ponto medio do pipe near-miss.
    Retorna True se inseriu com sucesso."""
    pipe_id = miss_data["pipe_id"]
    pipe = doc.GetElement(pipe_id)
    if not pipe or not isinstance(pipe.Location, DB.LocationCurve):
        return False

    curve = pipe.Location.Curve
    length = curve.Length
    if length < min_edge * 2:
        return False

    # Inserir no ponto medio
    break_pt = curve.Evaluate(0.5, True)

    try:
        # Swap routing preference
        pipe_type = doc.GetElement(miss_data["type_id"])
        rpm = pipe_type.RoutingPreferenceManager
        sym = miss_data["sym"]
        original_id = swap_union_preference(rpm, sym.Id)

        try:
            new_pipe_id = PlumbingUtils.BreakCurve(doc, pipe_id, break_pt)
            pipe_a = doc.GetElement(pipe_id)
            pipe_b = doc.GetElement(new_pipe_id)
            c1 = get_free_connector_near(pipe_a, break_pt)
            c2 = get_free_connector_near(pipe_b, break_pt)

            if c1 and c2:
                fitting = doc.Create.NewUnionFitting(c1, c2)
                if fitting:
                    copy_text_parameters(miss_data.get("source_pipe"), fitting)
                    return True
        finally:
            restore_union_preference(rpm, original_id)
    except:
        pass

    return False


def show_near_miss_report(near_misses, min_edge):
    """Mostra relatorio de near-misses no output com links clicaveis,
    depois abre SelectFromList para aprovacao."""
    # Imprimir relatorio no output
    output.print_md("---")
    output.print_md("### Tubos quase compativeis ({})".format(len(near_misses)))
    output.print_md("Estes tubos ficaram curtos demais por uma margem "
                    "dentro da tolerancia configurada:\n")

    items = []
    for i, miss in enumerate(near_misses):
        orient = "Horiz" if miss["orientation"] == "H" else "Vert"
        pipe_link = output.linkify(miss["pipe_id"])
        output.print_md(
            "{}. {} [{}] - Comprimento: **{:.2f} ft** | "
            "Espacamento: {:.2f} ft | Deficit: **{:.1f}%**".format(
                i + 1, pipe_link, orient,
                miss["length"], miss["spacing"], miss["deficit_pct"]
            )
        )
        items.append(NearMissItem(miss, i))

    output.print_md("\n*Clique nos links acima para navegar ate cada tubo.*")

    # SelectFromList para aprovacao em lote
    selected = forms.SelectFromList.show(
        items,
        title="Aprovar fixtures em tubos quase compativeis",
        button_name="Inserir Selecionados",
        multiselect=True,
        name_attr="name"
    )

    if not selected:
        output.print_md("\nNenhum near-miss aprovado.")
        return 0

    # Inserir fixtures nos aprovados
    inserted = 0
    with revit.Transaction("Fixtures near-miss"):
        for item in selected:
            sym = item.data["sym"]
            if not sym.IsActive:
                sym.Activate()
            if insert_fixture_on_near_miss(item.data, min_edge):
                inserted += 1

    output.print_md("\n**{}/{}** fixtures near-miss inseridos.".format(
        inserted, len(selected)))
    return inserted


# ============================================================================
# 4) MAIN
# ============================================================================

def main():
    try:
        # Selecao de pipes
        sel_ids = uidoc.Selection.GetElementIds()
        pipes = []
        for eid in sel_ids:
            elem = doc.GetElement(eid)
            if isinstance(elem, Pipe):
                pipes.append(elem)

        if not pipes:
            forms.alert("Selecione tubulacoes (Pipes) antes de executar.",
                        exitscript=True)

        # Contagem por orientacao
        n_horiz = sum(1 for p in pipes if not is_pipe_vertical(p))
        n_vert = sum(1 for p in pipes if is_pipe_vertical(p))

        # Buscar familias disponiveis
        symbols = get_pipe_fittings()
        if not symbols:
            forms.alert("Nenhuma familia de Pipe Fitting carregada no projeto.",
                        exitscript=True)

        # Pre-selecionar Loop Hanger (horiz) e Riser Clamp (vert)
        idx_horiz = find_symbol_by_family_name(symbols, "LOOP HANGER")
        idx_vert = find_symbol_by_family_name(symbols, "Riser Clamp")

        # WPF modal - fecha ANTES da Transaction
        janela = ConfigWindow(symbols, idx_horiz, idx_vert)
        janela.ShowDialog()

        if janela.resultado != "ok":
            return

        s_horiz = janela.sym_horiz
        s_vert = janela.sym_vert
        spacing_h = janela.spacing_h
        spacing_v = janela.spacing_v
        min_edge = janela.min_edge
        tolerance_pct = janela.tolerance_pct

        # Transaction DEPOIS do ShowDialog
        with revit.Transaction("Distribuir Fixtures"):
            if s_horiz and not s_horiz.IsActive:
                s_horiz.Activate()
            if s_vert and not s_vert.IsActive:
                s_vert.Activate()

            total, near_misses = distribute_on_pipes(
                pipes, spacing_h, spacing_v, s_horiz, s_vert,
                min_edge, tolerance_pct)

        # Resumo
        msg = "**Concluido!** {} fixtures inseridos.\n\n".format(total)
        msg += "- {} tubos selecionados ({} horizontais, {} verticais)\n".format(
            len(pipes), n_horiz, n_vert)
        if s_horiz:
            msg += "- Horizontal: {} a cada {} ft\n".format(
                format_symbol_name(s_horiz), spacing_h)
        if s_vert:
            msg += "- Vertical: {} a cada {} ft\n".format(
                format_symbol_name(s_vert), spacing_v)
        msg += "- Distancia minima das extremidades: {} ft".format(min_edge)
        output.print_md(msg)

        # Near-misses: relatorio + aprovacao
        if near_misses:
            show_near_miss_report(near_misses, min_edge)

    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


if __name__ == "__main__":
    main()
