# -*- coding: utf-8 -*-
"""Exporta schedules para CSV UTF-8 com BOM.
Batch: schedules concatenados com linha em branco separando.
include_headers: bool global OU lido por schedule em sched['include_header'].
"""

import csv
import io


def export_csv(schedules_data, file_path, include_headers=True):
    """
    schedules_data: list de dict com chaves name, headers, rows e
                    opcionalmente include_header (bool, sobrescreve global).
    """
    with io.open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        for i, sched in enumerate(schedules_data):
            if i > 0:
                writer.writerow([])  # linha em branco entre schedules
            inc_hdr = sched.get('include_header', include_headers)
            if inc_hdr and sched.get('headers'):
                writer.writerow([str(h).strip() for h in sched['headers']])
            for row in sched.get('rows', []):
                writer.writerow([str(v).strip() for v in row])
