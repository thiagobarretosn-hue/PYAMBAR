# -*- coding: utf-8 -*-
"""
WBS → Unidade FINAL (ESTÁVEL)

VERSÃO: 5.0
"""

__title__ = "WBS → Unidade FINAL"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.0"

# ========================================
# IMPORTS
# ========================================

import os
import re
import traceback

import clr
clr.AddReference("PresentationFramework")

from Autodesk.Revit.DB import Transaction, StorageType
from pyrevit import revit, forms, script

# ========================================
# GLOBALS
# ========================================

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

# ========================================
# HELPERS
# ========================================

def extrair_andar(texto):
    if not texto:
        return None
    match = re.search(r"\d+", texto)
    return int(match.group()) if match else None


def gerar_numero(andar, sufixo):
    return (andar * 100) + sufixo


def get_param(element, nome):
    """Busca em instância e tipo"""

    # instância
    for p in element.Parameters:
        try:
            if p.Definition.Name == nome:
                return p
        except:
            pass

    # tipo
    try:
        tipo = element.Symbol
        if tipo:
            for p in tipo.Parameters:
                if p.Definition.Name == nome:
                    return p
    except:
        pass

    return None


def get_param_value(param):
    if not param:
        return None
    return param.AsString() or param.AsValueString()


def set_param_value(param, valor):
    if not param or param.IsReadOnly:
        return False

    try:
        if param.StorageType == StorageType.String:
            param.Set(str(valor))
        elif param.StorageType == StorageType.Integer:
            param.Set(int(valor))
        elif param.StorageType == StorageType.Double:
            param.Set(float(valor))
        else:
            return False
        return True
    except:
        return False


def get_all_params(elements):
    nomes = set()
    for el in elements:
        for p in el.Parameters:
            try:
                nomes.add(p.Definition.Name)
            except:
                pass
    return sorted(list(nomes))


def get_valid_targets(elements):
    nomes = set()
    for el in elements:
        for p in el.Parameters:
            try:
                if not p.IsReadOnly:
                    nomes.add(p.Definition.Name)
            except:
                pass
    return sorted(list(nomes))


# ========================================
# WPF WINDOW
# ========================================

class MainWindow(forms.WPFWindow):

    def __init__(self, elementos):
        xaml = os.path.join(PATH_SCRIPT, "ui.xaml")
        forms.WPFWindow.__init__(self, xaml)

        self.elementos = elementos

        # carregar parâmetros
        self.cmb_source.ItemsSource = get_all_params(elementos)
        self.cmb_target.ItemsSource = get_valid_targets(elementos)

        # default
        if "WBS Detail" in self.cmb_source.ItemsSource:
            self.cmb_source.SelectedItem = "WBS Detail"

        if "Mark" in self.cmb_target.ItemsSource:
            self.cmb_target.SelectedItem = "Mark"

        # EVENTOS (VERSÃO SEGURA)
        self.btn_preview.Click += self.on_preview_click
        self.btn_apply.Click += self.on_apply_click

        self.Show()

    # ========================================
    # EVENTOS WPF (ESTÁVEIS)
    # ========================================

    def on_preview_click(self, sender, args):
        self.preview()

    def on_apply_click(self, sender, args):
        self.apply()

    # ========================================
    # PREVIEW
    # ========================================

    def preview(self):

        try:
            source = self.cmb_source.SelectedItem
            sufixo = int(self.txt_suffix.Text)
            inc = self.chk_increment.IsChecked

            data = []
            atual = sufixo

            for el in self.elementos:

                p = get_param(el, source)
                valor = get_param_value(p)

                andar = extrair_andar(valor)

                if not andar:
                    continue

                numero = gerar_numero(andar, atual)

                data.append({
                    "Id": el.Id.IntegerValue,
                    "WBS": valor,
                    "Resultado": numero
                })

                if inc:
                    atual += 1

            self.grid_preview.ItemsSource = data

            forms.alert("Preview gerado: {} itens".format(len(data)))

        except Exception as e:
            forms.alert(str(e))


    # ========================================
    # APPLY
    # ========================================

    def apply(self):

        try:
            source = self.cmb_source.SelectedItem
            target = self.cmb_target.SelectedItem
            sufixo = int(self.txt_suffix.Text)
            inc = self.chk_increment.IsChecked

            atual = sufixo
            sucesso = 0
            erros = 0

            t = Transaction(doc, "WBS → Unidade FINAL")
            t.Start()

            for el in self.elementos:

                p_src = get_param(el, source)
                p_tgt = get_param(el, target)

                valor = get_param_value(p_src)

                if not valor:
                    erros += 1
                    continue

                andar = extrair_andar(valor)

                if not andar:
                    erros += 1
                    continue

                numero = gerar_numero(andar, atual)

                if set_param_value(p_tgt, numero):
                    sucesso += 1
                    output.print_md("✅ {} → {}".format(valor, numero))
                else:
                    erros += 1
                    output.print_md("❌ Falha ao escrever")

                if inc:
                    atual += 1

            t.Commit()

            forms.alert(
                "FINALIZADO\n\nSucesso: {}\nErros: {}".format(sucesso, erros)
            )

        except Exception as e:
            forms.alert(str(e))


# ========================================
# MAIN
# ========================================

def main():
    try:
        sel = uidoc.Selection.GetElementIds()

        if not sel:
            forms.alert("Selecione elementos.", exitscript=True)

        elementos = [doc.GetElement(i) for i in sel]

        MainWindow(elementos)

    except Exception as e:
        output.print_md("❌ {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


if __name__ == "__main__":
    main()
