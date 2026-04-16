# -*- coding: utf-8 -*-
"""
ParamForge v5.0
Ferramenta unificada de analise visual e documentacao por parametros.
Modo modeless: janela fica aberta enquanto o Revit e utilizavel.
Acoes de escrita usam External Events (Secao 2.9 CLAUDE.md).
"""
__title__ = "Param\nForge"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.0"

import os
import sys
import traceback

import clr
clr.AddReference("System")
clr.AddReference("System.Core")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("RevitAPIUI")

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

LIB_PATH = os.path.join(SCRIPT_DIR, '..', '..', '..', '..', 'lib')
LIB_PATH = os.path.normpath(LIB_PATH)
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from System import Action
from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, HOST_APP

doc     = revit.doc
uidoc   = revit.uidoc
rvt_year = int(HOST_APP.app.VersionNumber)


# ── Dispatcher helper ────────────────────────────────────────────────────────

def _dispatch(window, action):
    """Despacha action para o thread UI da janela WPF."""
    try:
        if window and window.Dispatcher:
            window.Dispatcher.BeginInvoke(Action(action))
    except Exception:
        pass


def _set_status(window, msg):
    _dispatch(window, lambda: setattr(window.txtStatus, 'Text', msg))


# ── External Event Handlers ──────────────────────────────────────────────────

class ApplyColorsHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref = None
        self.checked    = []
        self.all_views  = False

    def Execute(self, uiapp):
        try:
            import pf_actions
            from pf_helpers import ef_transaction
            d   = uiapp.ActiveUIDocument.Document
            u   = uiapp.ActiveUIDocument
            msg = pf_actions.apply_colors(d, u, self.checked, ef_transaction, self.all_views)
            _set_status(self.window_ref, msg)
        except Exception as e:
            _set_status(self.window_ref, "Erro: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_ApplyColors"


class ResetColorsHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref     = None
        self.current_values = []
        self.selected_cats  = []
        self.all_views      = False

    def Execute(self, uiapp):
        try:
            import pf_actions
            from pf_helpers import ef_transaction
            d   = uiapp.ActiveUIDocument.Document
            u   = uiapp.ActiveUIDocument
            msg = pf_actions.reset_colors(d, u, self.current_values,
                                          self.selected_cats, ef_transaction, self.all_views)
            _set_status(self.window_ref, msg)
        except Exception as e:
            _set_status(self.window_ref, "Erro: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_ResetColors"


class CreateFiltersHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref           = None
        self.checked              = []
        self.selected_param_names = []
        self.selected_cats        = []
        self.all_views            = False
        self.rvt_year             = 2026

    def Execute(self, uiapp):
        try:
            import pf_actions
            from pf_helpers import ef_transaction
            d   = uiapp.ActiveUIDocument.Document
            u   = uiapp.ActiveUIDocument
            msg = pf_actions.create_view_filters(
                d, u, self.checked, self.selected_param_names,
                self.selected_cats, self.all_views, self.rvt_year, ef_transaction)
            _set_status(self.window_ref, msg)
        except Exception as e:
            _set_status(self.window_ref, "Erro: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_CreateFilters"


class CreateLegendHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref = None
        self.checked    = []
        self.config     = {}

    def Execute(self, uiapp):
        try:
            import pf_actions
            from pf_helpers import ef_transaction
            d   = uiapp.ActiveUIDocument.Document
            u   = uiapp.ActiveUIDocument
            msg = pf_actions.create_legend(d, u, self.checked, self.config, ef_transaction)
            _set_status(self.window_ref, msg)
        except Exception as e:
            _set_status(self.window_ref, "Erro: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_CreateLegend"


class CreateSchedulesHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref  = None
        self.plano_final = []

    def Execute(self, uiapp):
        try:
            from pf_core import duplicar_e_filtrar
            from pf_helpers import nome_unico, sanitize_view_name, ef_transaction
            d = uiapp.ActiveUIDocument.Document
            u = uiapp.ActiveUIDocument
            criados = []
            for nome_item in self.plano_final:
                nome_ed  = nome_item.Nome.strip() or "Schedule"
                novo_nome = nome_unico(d, sanitize_view_name(nome_ed))
                sched_cat = (nome_item.ScheduleCategory.strip()
                             if nome_item.ScheduleCategory else "")
                novo = duplicar_e_filtrar(
                    d, nome_item.Template, nome_item.FiltroInfos,
                    novo_nome, sched_cat, ef_transaction)
                if novo:
                    criados.append(novo)

            n = len(criados)
            w = self.window_ref

            def _update_ui():
                if criados:
                    try:
                        u.ActiveView = criados[-1]
                        u.RefreshActiveView()
                    except Exception:
                        pass
                w.txtStatus.Text = ("{} schedule(s) criado(s).".format(n)
                                    if n else "Nenhum schedule criado.")

            _dispatch(w, _update_ui)
        except Exception as e:
            _set_status(self.window_ref, "Erro schedules: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_CreateSchedules"


class IsolateElementsHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref  = None
        self.element_ids = []

    def Execute(self, uiapp):
        try:
            from pf_helpers import ef_transaction
            d    = uiapp.ActiveUIDocument.Document
            u    = uiapp.ActiveUIDocument
            view = d.ActiveView
            ids  = List[ElementId](self.element_ids)
            with ef_transaction(d, "ParamForge: Isolar"):
                view.IsolateElementsTemporary(ids)
            u.RefreshActiveView()
            n = len(self.element_ids)
            _set_status(self.window_ref, "{} elementos isolados.".format(n))
        except Exception as e:
            _set_status(self.window_ref, "Erro ao isolar: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_Isolate"


class SectionBox3DHandler(IExternalEventHandler):
    def __init__(self):
        self.window_ref  = None
        self.element_ids = []

    def Execute(self, uiapp):
        try:
            from pf_helpers import ef_transaction
            from Snippets.views._view3d_helpers import (
                find_3d_view, compute_bounding_box, set_section_box)
            d  = uiapp.ActiveUIDocument.Document
            u  = uiapp.ActiveUIDocument
            w  = self.window_ref
            v3 = find_3d_view(d, u)
            if not v3:
                _set_status(w, "Nenhuma vista 3D encontrada.")
                return
            bbox = compute_bounding_box(d, self.element_ids)
            if not bbox:
                _set_status(w, "Elementos sem geometria.")
                return
            with ef_transaction(d, "ParamForge: Section Box 3D"):
                set_section_box(v3, bbox)
            u.ActiveView = v3
            u.RefreshActiveView()
            n = len(self.element_ids)
            _set_status(w, "Section Box 3D: {} elementos.".format(n))
        except Exception as e:
            _set_status(self.window_ref, "Erro 3D: {}".format(str(e)))

    def GetName(self):
        return "ParamForge_SectionBox3D"


class PickSelectionHandler(IExternalEventHandler):
    """Solicita selecao no modelo e repassa os elementos para a janela."""

    def __init__(self):
        self.window_ref = None

    def Execute(self, uiapp):
        u   = uiapp.ActiveUIDocument
        doc = u.Document
        w   = self.window_ref
        try:
            # Ocultar janela para usuario poder selecionar
            _dispatch(w, lambda: w.Hide())
            refs = u.Selection.PickObjects(
                ObjectType.Element,
                "Selecione elementos para ParamForge — ESC para cancelar")
            elements = [doc.GetElement(r.ElementId) for r in refs]

            def _done():
                w.set_selection(elements)
                w.Show()
                w.Activate()

            _dispatch(w, _done)
        except OperationCanceledException:
            _dispatch(w, lambda: [w.Show(), w.Activate()])
        except Exception:
            _dispatch(w, lambda: [w.Show(), w.Activate()])

    def GetName(self):
        return "ParamForge_PickSelection"


# ── main() ───────────────────────────────────────────────────────────────────

def main():
    try:
        # Instanciar handlers e ExternalEvents dentro do contexto de API
        apply_h     = ApplyColorsHandler()
        reset_h     = ResetColorsHandler()
        filters_h   = CreateFiltersHandler()
        filters_h.rvt_year = rvt_year
        legend_h    = CreateLegendHandler()
        schedules_h = CreateSchedulesHandler()
        isolate_h   = IsolateElementsHandler()
        section3d_h = SectionBox3DHandler()
        pick_h      = PickSelectionHandler()

        apply_evt     = ExternalEvent.Create(apply_h)
        reset_evt     = ExternalEvent.Create(reset_h)
        filters_evt   = ExternalEvent.Create(filters_h)
        legend_evt    = ExternalEvent.Create(legend_h)
        schedules_evt = ExternalEvent.Create(schedules_h)
        isolate_evt   = ExternalEvent.Create(isolate_h)
        section3d_evt = ExternalEvent.Create(section3d_h)
        pick_evt      = ExternalEvent.Create(pick_h)

        handlers = {
            "apply":     (apply_h,     apply_evt),
            "reset":     (reset_h,     reset_evt),
            "filters":   (filters_h,   filters_evt),
            "legend":    (legend_h,    legend_evt),
            "schedules": (schedules_h, schedules_evt),
            "isolate":   (isolate_h,   isolate_evt),
            "section3d": (section3d_h, section3d_evt),
            "pick":      (pick_h,      pick_evt),
        }

        from pf_window import ParamForgeWindow
        window = ParamForgeWindow(doc, uidoc, rvt_year, handlers)
        window.Show()   # Modeless — Revit permanece operacional

    except Exception:
        from pyrevit import forms
        forms.alert("Erro ao abrir ParamForge:\n{}".format(traceback.format_exc()))


if __name__ == '__main__':
    main()
