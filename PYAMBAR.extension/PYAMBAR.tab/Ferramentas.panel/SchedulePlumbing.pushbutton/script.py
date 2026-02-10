# -*- coding: utf-8 -*-
__title__ = "Schedule\nPlumbing"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.1"
__doc__ = """Cria planilha interna com tubulações/conexões selecionadas"""

import clr
import sys
import os
clr.AddReference("System")

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List
from pyrevit import forms, script, revit, HOST_APP
from datetime import datetime

from Snippets.core._revit_version_helpers import get_id_value

doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
rvt_year = int(app.VersionNumber)
output = script.get_output()

PARAMETROS = [
    "Ambiente", "Stage", "Tipologia UH", "Módulo Montagem",
    "WBS", "WBS Detail", "WBS Detail Instance", "WBS Instance"
]

CATEGORIAS_MEP = [
    BuiltInCategory.OST_PipeCurves,
    BuiltInCategory.OST_PipeFitting,
    BuiltInCategory.OST_FlexPipeCurves,
    BuiltInCategory.OST_PipeAccessory
]

def selecionar_elementos_plumbing():
    try:
        with forms.WarningBar(title="Selecione tubos, conexões e acessórios"):
            refs = uidoc.Selection.PickObjects(ObjectType.Element, "Selecione MEP")
        
        if not refs:
            forms.alert("Nenhum elemento selecionado!", exitscript=True)
        
        elementos = [doc.GetElement(ref.ElementId) for ref in refs]
        elementos_validos = []
        
        for el in elementos:
            if el.Category:
                cat_id = get_id_value(el.Category.Id)
                for cat in CATEGORIAS_MEP:
                    if cat_id == int(cat):
                        elementos_validos.append(el)
                        break
        
        if not elementos_validos:
            forms.alert("Nenhum elemento válido!\n\nSelecione: Tubos, Conexões, Acessórios", exitscript=True)
        
        return elementos_validos
    
    except Exception as e:
        output.print_md("❌ Erro: {}".format(str(e)))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        return None

def marcar_elementos(elementos):
    try:
        marca = "PLUMB_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
        t = Transaction(doc, "Marcar Elementos")
        t.Start()
        
        for el in elementos:
            param = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if param and not param.IsReadOnly:
                param.Set(marca)
        
        t.Commit()
        return marca
    
    except Exception as e:
        if t.HasStarted():
            t.RollBack()
        output.print_md("❌ Erro ao marcar: {}".format(str(e)))
        return None

def criar_schedule_multicategoria(marca_filtro):
    try:
        t = Transaction(doc, "Criar Schedule")
        t.Start()
        
        schedule_name = "Plumbing - {}".format(datetime.now().strftime("%d.%m.%Y %Hh%M"))
        schedule = ViewSchedule.CreateSchedule(doc, ElementId.InvalidElementId)
        schedule.Name = schedule_name
        schedule_def = schedule.Definition
        campos_disponiveis = schedule_def.GetSchedulableFields()
        
        # Campo Comments OCULTO para filtro
        campo_comments = None
        for campo in campos_disponiveis:
            param_id = get_id_value(campo.ParameterId)
            if param_id == int(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS):
                campo_comments = schedule_def.AddField(campo)
                campo_comments.IsHidden = True
                break
        
        if campo_comments:
            filtro = ScheduleFilter(campo_comments.FieldId, ScheduleFilterType.Equal, marca_filtro)
            schedule_def.AddFilter(filtro)
        
        # Campo fórmula Project Name
        try:
            campo_formula = schedule_def.AddField(ScheduleFieldType.Formula)
            campo_formula.SetFormulaValue("\"Plumbing -\"")
            campo_formula.ColumnHeading = "Project Name"
        except:
            pass
        
        # Adicionar 8 parâmetros
        parametros_adicionados = []
        parametros_nao_encontrados = []
        
        for param_nome in PARAMETROS:
            encontrado = False
            for campo in campos_disponiveis:
                try:
                    nome_campo = campo.GetName(doc) if hasattr(campo, 'GetName') else None
                    if nome_campo == param_nome:
                        field = schedule_def.AddField(campo)
                        field.ColumnHeading = param_nome
                        parametros_adicionados.append(param_nome)
                        encontrado = True
                        break
                except:
                    continue
            
            if not encontrado:
                parametros_nao_encontrados.append(param_nome)
        
        output.print_md("\n**Parâmetros adicionados:** {}".format(len(parametros_adicionados)))
        for p in parametros_adicionados:
            output.print_md("  ✅ {}".format(p))
        
        if parametros_nao_encontrados:
            output.print_md("\n**⚠️ Parâmetros NÃO encontrados:** {}".format(len(parametros_nao_encontrados)))
            for p in parametros_nao_encontrados:
                output.print_md("  ❌ {}".format(p))
        
        t.Commit()
        return schedule
    
    except Exception as e:
        if t.HasStarted():
            t.RollBack()
        output.print_md("❌ Erro criar schedule: {}".format(str(e)))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        return None

# MAIN
try:
    output.print_md("## 🔧 Schedule Plumbing")
    output.print_md("---")
    
    output.print_md("### 1️⃣ Seleção")
    elementos = selecionar_elementos_plumbing()
    if not elementos:
        script.exit()
    output.print_md("✅ {} elementos".format(len(elementos)))
    
    output.print_md("\n### 2️⃣ Marcação")
    marca = marcar_elementos(elementos)
    if not marca:
        script.exit()
    output.print_md("✅ Marca: `{}`".format(marca))
    
    output.print_md("\n### 3️⃣ Criando Schedule")
    schedule = criar_schedule_multicategoria(marca)
    if not schedule:
        script.exit()
    output.print_md("\n✅ Schedule: **{}**".format(schedule.Name))
    
    output.print_md("\n### 4️⃣ Abrindo")
    uidoc.ActiveView = schedule
    uidoc.RefreshActiveView()
    
    output.print_md("\n---\n## ✅ Concluído!")
    
except Exception as e:
    output.print_md("\n---\n## ❌ Erro:")
    output.print_md("```\n{}\n```".format(str(e)))
    import traceback
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
