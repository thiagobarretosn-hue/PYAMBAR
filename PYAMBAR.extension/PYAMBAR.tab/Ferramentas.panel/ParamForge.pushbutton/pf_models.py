# -*- coding: utf-8 -*-
"""
ParamForge - Modelos de dados.
"""
import random

from System.Windows.Media import SolidColorBrush
from System.Windows.Media import Color as WpfColor
from Autodesk.Revit.DB import Color


class ValueItem(object):
    """Item de valor com cor para ListView."""

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
        self.WpfColor = WpfColor.FromRgb(self.R, self.G, self.B)
        self.ColorBrush = SolidColorBrush(self.WpfColor)

    def GetRevitColor(self):
        return Color(self.R, self.G, self.B)


class ScheduleTemplateItem(object):
    """Template de schedule com categoria associada."""

    def __init__(self, schedule, cat_id_val):
        self.Schedule = schedule
        self.Name = schedule.Name
        self.CatIdVal = cat_id_val

    def __str__(self):
        return self.Name


class NomeItem(object):
    """Item no dialog de confirmacao de schedule."""

    def __init__(self, cat_name, filtro_display, nome, template, filtro_infos, schedule_category=""):
        self.CatName = cat_name
        self.FiltroDisplay = filtro_display
        self.Nome = nome
        self.Template = template
        self.FiltroInfos = filtro_infos
        self.IsChecked = True
        self.ScheduleCategory = schedule_category
