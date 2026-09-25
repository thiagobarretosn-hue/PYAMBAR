# -*- coding: utf-8 -*-
"""Vincula varios DWG como CAD Link de uma vez, cada um na sua vista, com o
mesmo posicionamento, unidade, cores e camadas para todo o lote."""
__title__ = "Vincular\nCADs"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"

import os
import sys
import json
import codecs
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from Autodesk.Revit.DB import (
    Transaction, TransactionGroup, FilteredElementCollector,
    View, ViewType, ImportInstance, DWGImportOptions,
    ImportPlacement, ImportUnit, ImportColorMode,
    ModelPathUtils, ElementId
)
from pyrevit import revit, forms, script
from pyrevit.forms import WPFWindow

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)
from Snippets._cad_vista_match import sugerir_vista

doc = revit.doc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

_APPDATA_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'VincularCADs')
_APPDATA_CONFIG = os.path.join(_APPDATA_DIR, 'config.json')

# Ordem = ordem nos ComboBox; o primeiro e o padrao de fabrica
PLACEMENTS = [
    ("Origem para Origem", ImportPlacement.Origin),
    ("Centro para Centro", ImportPlacement.Centered),
    ("Coordenadas Compartilhadas", ImportPlacement.Shared),
]
UNIDADES = [
    ("Auto-detectar", ImportUnit.Default),
    ("Pes (ft)", ImportUnit.Foot),
    ("Polegadas (in)", ImportUnit.Inch),
    ("Metros", ImportUnit.Meter),
    ("Centimetros", ImportUnit.Centimeter),
    ("Milimetros", ImportUnit.Millimeter),
]
CORES = [
    ("Preservar", ImportColorMode.Preserved),
    ("Preto e branco", ImportColorMode.BlackAndWhite),
    ("Inverter", ImportColorMode.Inverted),
]
CAMADAS = [
    ("Todas", False),
    ("So as visiveis", True),
]

TIPOS_VISTA = {
    ViewType.FloorPlan: "Planta",
    ViewType.CeilingPlan: "Forro",
    ViewType.EngineeringPlan: "Estrutural",
    ViewType.AreaPlan: "Area",
    ViewType.Section: "Corte",
    ViewType.Elevation: "Elevacao",
    ViewType.Detail: "Detalhe",
    ViewType.DraftingView: "Desenho",
}


def get_element_id_value(elem_id):
    return elem_id.Value if hasattr(elem_id, 'Value') else elem_id.IntegerValue


def normalizar(caminho):
    try:
        return os.path.normcase(os.path.normpath(caminho))
    except Exception:
        return (caminho or "").lower()


# -- config --------------------------------------------------------------------

def load_config():
    if os.path.exists(_APPDATA_CONFIG):
        try:
            with codecs.open(_APPDATA_CONFIG, 'r', 'utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data):
    try:
        if not os.path.exists(_APPDATA_DIR):
            os.makedirs(_APPDATA_DIR)
        with codecs.open(_APPDATA_CONFIG, 'w', 'utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # preferencia perdida nao derruba o vinculo


# -- modelo --------------------------------------------------------------------

class VistaOpcao(object):
    def __init__(self, view, nome):
        self.View = view
        self.Name = nome


class CadItem(object):
    def __init__(self, caminho, vistas, vista_alvo):
        self.Caminho = caminho
        self.Arquivo = os.path.basename(caminho)
        self.Vistas = vistas        # lista compartilhada para o ComboBox
        self.VistaAlvo = vista_alvo


def vistas_elegiveis():
    vistas = []
    for view in FilteredElementCollector(doc).OfClass(View):
        if view.IsTemplate or view.ViewType not in TIPOS_VISTA:
            continue
        vistas.append(view)
    vistas.sort(key=lambda v: (TIPOS_VISTA[v.ViewType], v.Name))
    return vistas


def vista_sugerida(arquivo, vistas, fallback):
    """Tenta primeiro so as plantas (evita empate Planta x Forro de mesmo nome)."""
    plantas = [v for v in vistas if v.View.ViewType == ViewType.FloorPlan]
    for grupo in (plantas, vistas):
        idx = sugerir_vista(arquivo, [v.View.Name for v in grupo])
        if idx is not None:
            return grupo[idx]
    return fallback


def cads_ja_vinculados():
    """{(caminho normalizado, id da vista ou -1 se em todas as vistas)}."""
    existentes = set()
    for inst in FilteredElementCollector(doc).OfClass(ImportInstance):
        try:
            if not inst.IsLinked:
                continue
            tipo = doc.GetElement(inst.GetTypeId())
            if tipo is None or not tipo.IsExternalFileReference():
                continue
            ref = tipo.GetExternalFileReference()
            visivel = ModelPathUtils.ConvertModelPathToUserVisiblePath(ref.GetAbsolutePath())
            if not visivel:
                continue
            owner = inst.OwnerViewId
            vista_id = -1 if owner == ElementId.InvalidElementId else get_element_id_value(owner)
            existentes.add((normalizar(visivel), vista_id))
        except Exception:
            continue
    return existentes


# -- WPF -----------------------------------------------------------------------

class VincularCADsWindow(WPFWindow):
    def __init__(self, itens, config):
        WPFWindow.__init__(self, 'ui.xaml')
        self.result = None
        self.ScopeLabel.Content = "{} arquivo(s) DWG — confira a vista de cada um".format(len(itens))
        self.CadGrid.ItemsSource = itens

        for box, opcoes, chave in [
                (self.PlacementBox, PLACEMENTS, 'placement'),
                (self.UnitBox, UNIDADES, 'unidade'),
                (self.ColorBox, CORES, 'cores'),
                (self.LayerBox, CAMADAS, 'camadas')]:
            nomes = [nome for nome, _ in opcoes]
            box.ItemsSource = nomes
            salvo = config.get(chave)
            box.SelectedIndex = nomes.index(salvo) if salvo in nomes else 0

        self.ThisViewOnlyBox.IsChecked = config.get('somente_vista', True)

    def btn_apply_click(self, sender, e):
        self.CadGrid.CommitEdit()
        self.result = {
            'placement': self.PlacementBox.SelectedItem,
            'unidade': self.UnitBox.SelectedItem,
            'cores': self.ColorBox.SelectedItem,
            'camadas': self.LayerBox.SelectedItem,
            'somente_vista': bool(self.ThisViewOnlyBox.IsChecked),
        }
        self.Close()

    def btn_cancel_click(self, sender, e):
        self.Close()


# -- aplicacao -----------------------------------------------------------------

def montar_opcoes(escolha):
    opcoes = DWGImportOptions()
    opcoes.Placement = dict(PLACEMENTS)[escolha['placement']]
    opcoes.Unit = dict(UNIDADES)[escolha['unidade']]
    opcoes.ColorMode = dict(CORES)[escolha['cores']]
    opcoes.VisibleLayersOnly = dict(CAMADAS)[escolha['camadas']]
    opcoes.ThisViewOnly = escolha['somente_vista']
    return opcoes


def vincular_um(caminho, opcoes, view):
    """Cria o CAD Link na vista. Levanta excecao em falha."""
    # out ElementId volta como segundo item da tupla no IronPython
    ok, link_id = doc.Link(caminho, opcoes, view)
    if not ok or link_id is None or link_id == ElementId.InvalidElementId:
        raise Exception("o Revit recusou o vinculo (Link devolveu falso)")
    return link_id


def imprimir_relatorio(vinculados, pulados, falhos, escolha):
    output.print_md("# Vincular CADs — relatorio")
    output.print_md(
        "**Posicionamento:** {} &nbsp;|&nbsp; **Unidade:** {} &nbsp;|&nbsp; "
        "**Cores:** {} &nbsp;|&nbsp; **Camadas:** {} &nbsp;|&nbsp; **So na vista:** {}".format(
            escolha['placement'], escolha['unidade'], escolha['cores'],
            escolha['camadas'], "sim" if escolha['somente_vista'] else "nao"))

    if vinculados:
        output.print_md("## Vinculados ({})".format(len(vinculados)))
        for nome, vista_nome, inst_id in vinculados:
            output.print_md("- {} → {} {}".format(nome, vista_nome, output.linkify(inst_id)))

    if pulados:
        output.print_md("## Pulados ({})".format(len(pulados)))
        for nome, motivo in pulados:
            output.print_md("- {} — {}".format(nome, motivo))

    if falhos:
        output.print_md("## Falhos ({})".format(len(falhos)))
        for nome, motivo in falhos:
            output.print_md("- **{}** — {}".format(nome, motivo))

    if not vinculados and not falhos and not pulados:
        output.print_md("Nada a fazer.")


def main():
    arquivos = forms.pick_file(
        file_ext='dwg',
        multi_file=True,
        title="Selecione os DWG para vincular (Ctrl ou Shift para varios)")
    if not arquivos:
        return
    if isinstance(arquivos, str):
        arquivos = [arquivos]

    views = vistas_elegiveis()
    if not views:
        forms.alert("Nenhuma planta, corte, elevacao ou vista de desenho no modelo.", exitscript=True)

    nao_vincular = VistaOpcao(None, "— nao vincular —")
    opcoes_vista = [nao_vincular] + [
        VistaOpcao(v, "{}: {}".format(TIPOS_VISTA[v.ViewType], v.Name)) for v in views]

    ativa = next((o for o in opcoes_vista[1:] if o.View.Id == doc.ActiveView.Id), nao_vincular)
    itens = [CadItem(c, opcoes_vista, vista_sugerida(os.path.basename(c), opcoes_vista[1:], ativa))
             for c in sorted(arquivos, key=lambda p: os.path.basename(p).lower())]

    janela = VincularCADsWindow(itens, load_config())
    janela.ShowDialog()
    if not janela.result:
        return
    escolha = janela.result
    save_config(escolha)

    existentes = cads_ja_vinculados()
    vinculados, pulados, falhos = [], [], []

    opcoes = montar_opcoes(escolha)
    grupo = TransactionGroup(doc, "Vincular CADs em Lote")
    grupo.Start()
    try:
        for item in itens:
            if item.VistaAlvo is None or item.VistaAlvo.View is None:
                pulados.append((item.Arquivo, "marcado para nao vincular"))
                continue

            view = item.VistaAlvo.View
            chave = normalizar(item.Caminho)
            vista_id = get_element_id_value(view.Id)
            if (chave, -1) in existentes:
                pulados.append((item.Arquivo, "ja vinculado em todas as vistas"))
                continue
            if (chave, vista_id) in existentes:
                pulados.append((item.Arquivo, "ja vinculado em {}".format(item.VistaAlvo.Name)))
                continue

            transacao = Transaction(doc, "Vincular {}".format(item.Arquivo))
            transacao.Start()
            try:
                inst_id = vincular_um(item.Caminho, opcoes, view)
                transacao.Commit()
                existentes.add((chave, vista_id if escolha['somente_vista'] else -1))
                vinculados.append((item.Arquivo, item.VistaAlvo.Name, inst_id))
            except Exception as erro:
                if transacao.HasStarted() and not transacao.HasEnded():
                    transacao.RollBack()
                mensagem = str(erro)
                if not mensagem or len(mensagem) < 25:
                    mensagem = "{}: {}".format(type(erro).__name__, mensagem)
                falhos.append((item.Arquivo, mensagem))

        if vinculados:
            grupo.Assimilate()
        else:
            grupo.RollBack()
    except Exception:
        if grupo.HasStarted():
            grupo.RollBack()
        raise
    finally:
        opcoes.Dispose()

    imprimir_relatorio(vinculados, pulados, falhos, escolha)


if __name__ == "__main__":
    try:
        main()
    except Exception as erro_geral:
        output.print_md("**Erro:** {}".format(str(erro_geral)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
