# -*- coding: utf-8 -*-
"""
Exporta schedules como .csv para importacao no Google Sheets e abre a pasta.
CSV e o formato universal de importacao para Google Sheets (Arquivo > Importar).
"""

import os
from ExportPro import csv_exporter


def export_sheets(schedules_data, file_path, include_headers=True):
    """
    Gera .csv (para importar no Google Sheets) e abre a pasta no Explorer.
    file_path deve ter extensao csv
    """
    csv_exporter.export_csv(schedules_data, file_path, include_headers=include_headers)
    folder = os.path.dirname(file_path)
    if folder and os.path.exists(folder):
        os.startfile(folder)
