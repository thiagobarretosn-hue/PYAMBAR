# -*- coding: utf-8 -*-
"""
Envia dados de schedules para um GAS web app via HTTP POST JSON.
Usa System.Net.WebClient (.NET) — disponivel em IronPython no Revit.
NAO testavel em CPython puro (dependencia de System.Net).
"""

import json
import re

_GAS_ENDPOINT = (
    'https://script.google.com/a/macros/ambar-technologies.com/s/'
    'AKfycbwmbXHS_TMX7AUWBETXAA3SGwFZVwRVB0CxvsyqJWjBlklRbBgd9NeQx7Jb2d-gKj0l/exec'
)


def extract_spreadsheet_id(spreadsheet_url):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', spreadsheet_url or '')
    return m.group(1) if m else None


def _try_number(v):
    s = str(v).strip()
    try:
        f = float(s)
        return int(f) if (f == int(f) and '.' not in s) else f
    except (ValueError, TypeError):
        return s


def post_to_gas(spreadsheet_url, schedules_data, project_name, mode='separate', tab_name=None):
    """
    Envia schedules para um Google Apps Script web app deployado.

    url           : str  — URL do GAS web app (formato .../exec)
    schedules_data: list — cada item e dict com chaves name, headers, rows,
                          e opcionalmente include_header (bool)
    project_name  : str  — doc.Title (identificador do projeto Revit)
    mode          : 'separate' | 'stacked' | 'append'
    tab_name      : str  — para mode='append': nome exato da aba de destino

    Retorna dict {'status': 'ok', 'sheets': N} em sucesso.
    Levanta RuntimeError em caso de falha de rede ou resposta invalida.
    """
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url)
    if not spreadsheet_id:
        raise RuntimeError(
            'URL da planilha invalida. Cole a URL completa do Google Sheets.\n'
            'Exemplo: https://docs.google.com/spreadsheets/d/1BxiM.../edit'
        )

    payload = {
        'projectName': project_name,
        'spreadsheetId': spreadsheet_id,
        'mode': mode,
        'schedules': [
            {
                'name': s['name'],
                'headers': [str(h).strip() for h in s.get('headers', [])],
                'rows': [[_try_number(v) for v in row] for row in s.get('rows', [])],
                'includeHeader': bool(s.get('include_header', True)),
            }
            for s in schedules_data
        ],
    }
    if tab_name:
        payload['tabName'] = tab_name
    payload_json = json.dumps(payload, ensure_ascii=False)

    try:
        import clr
        clr.AddReference('System')
        from System.Net import WebClient
        from System.Text import Encoding

        client = WebClient()
        client.Encoding = Encoding.UTF8
        client.Headers.Add('Content-Type', 'application/json; charset=utf-8')
        response = client.UploadString(_GAS_ENDPOINT, 'POST', payload_json)
    except Exception as e:
        msg = str(e)
        if '401' in msg or 'Unauthorized' in msg:
            raise RuntimeError(
                'GAS retornou 401 (acesso negado).\n\n'
                'No Apps Script:\n'
                '  Deploy > Manage deployments > Edit (icone lapis)\n'
                '  Who has access: Anyone\n'
                '  Deploy'
            )
        raise RuntimeError('Falha ao conectar com GAS web app: {}'.format(msg))

    try:
        result = json.loads(response)
    except Exception:
        raise RuntimeError('Resposta invalida do GAS web app: {}'.format(response[:200]))

    if result.get('status') != 'ok':
        raise RuntimeError('GAS retornou erro: {}'.format(result.get('message', response)))

    return result
