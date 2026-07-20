# -*- coding: utf-8 -*-
"""
Motor de agrupamento — port do SummaryAll.gs (_groupAndAggregate + _sortRows).
Puro Python: sem imports Revit.
"""

import locale
import functools


def apply_filters(headers, rows, rules):
    """
    Filtro por valores (estilo Excel) — remove linhas cujo valor da coluna esta
    na lista 'filter_excluded' da regra. Roda ANTES de apply_grouping; e
    independente da action (ate colunas 'ignore' filtram linhas).

    Retorna nova lista de linhas (ou a original se nenhum filtro ativo).
    """
    if not rows:
        return rows

    col_map = {name: idx for idx, name in enumerate(headers)}
    active  = []
    for rule in rules:
        excluded = rule.get('filter_excluded')
        if not excluded:
            continue
        idx = col_map.get(rule.get('name', ''))
        if idx is None:
            continue
        active.append((idx, set(str(v) for v in excluded)))

    if not active:
        return rows

    out = []
    for row in rows:
        keep = True
        for idx, excl in active:
            val = str(row[idx]) if idx < len(row) else ''
            if val in excl:
                keep = False
                break
        if keep:
            out.append(row)
    return out


def apply_grouping(headers, rows, rules):
    """
    Agrupa e agrega linhas conforme regras por coluna.

    headers: list[str]
    rows:    list[list[str]]
    rules:   list[dict] com chaves: name, action, sort_order, sort_dir
             action: 'group' | 'sum' | 'count' | 'copy_first' | 'ignore'

    Retorna (output_headers: list[str], grouped_rows: list[list[str]])
    """
    if rows is None or len(rows) == 0:
        out_headers = _build_output_headers(headers, rules)
        return out_headers, []

    col_map = {name: idx for idx, name in enumerate(headers)}

    group_indices      = []
    sum_indices        = []
    count_indices      = []
    copy_first_indices = []
    manter_indices     = []
    sort_keys          = []

    for rule in rules:
        name   = rule.get('name', '')
        action = rule.get('action', 'ignore')
        idx    = col_map.get(name)
        if idx is None:
            continue

        if action == 'group':
            group_indices.append(idx)
        elif action == 'sum':
            sum_indices.append(idx)
        elif action == 'count':
            count_indices.append(idx)
        elif action == 'copy_first':
            copy_first_indices.append(idx)
        elif action == 'manter':
            manter_indices.append(idx)

        order = rule.get('sort_order')
        if order is not None:
            try:
                sort_keys.append({
                    'col_idx':   idx,
                    'ascending': str(rule.get('sort_dir', 'ASC')).upper() != 'DESC',
                    'priority':  int(order),
                })
            except (TypeError, ValueError):
                pass

    sort_keys.sort(key=lambda k: k['priority'])

    # Colunas que aparecem na saida (nao ignoradas)
    active_indices = (set(group_indices)
                      | set(sum_indices)
                      | set(count_indices)
                      | set(copy_first_indices)
                      | set(manter_indices))
    output_col_order = [i for i in range(len(headers)) if i in active_indices]

    # --- Agrupar ---
    group_map    = {}  # key -> stored row (list, mesmo comprimento de headers)
    group_order  = []  # insercao para preservar ordem de aparicao
    manter_sets  = {}  # key -> {col_idx: set de valores distintos}

    for row_num, row in enumerate(rows):
        key = ('||'.join(str(row[i]) if i < len(row) else '' for i in group_indices)
               if group_indices else str(row_num))

        if key not in group_map:
            stored = [str(row[i]) if i < len(row) else '' for i in range(len(headers))]
            for ci in count_indices:
                stored[ci] = '1'
            group_map[key]  = stored
            group_order.append(key)
            manter_sets[key] = {ci: {str(row[ci]) if ci < len(row) else ''} for ci in manter_indices}
        else:
            stored = group_map[key]
            for ci in sum_indices:
                prev = stored[ci]
                curr = str(row[ci]) if ci < len(row) else '0'
                try:
                    stored[ci] = str(float(prev) + float(curr))
                except (ValueError, TypeError):
                    pass
            for ci in count_indices:
                try:
                    stored[ci] = str(int(float(stored[ci])) + 1)
                except (ValueError, TypeError):
                    stored[ci] = '1'
            for ci in manter_indices:
                val = str(row[ci]) if ci < len(row) else ''
                manter_sets[key][ci].add(val)

    # Resolver colunas "manter": valor unico ou <varia>
    _VARIA = u'<varia>'
    for k in group_order:
        for ci, vals in manter_sets[k].items():
            group_map[k][ci] = next(iter(vals)) if len(vals) == 1 else _VARIA

    result = [group_map[k] for k in group_order]

    # --- Ordenar ---
    if sort_keys:
        def _sort_key_fn(row):
            parts = []
            for sk in sort_keys:
                val = str(row[sk['col_idx']]) if sk['col_idx'] < len(row) else ''
                try:
                    parts.append((0, float(val), '', sk['ascending']))
                except (ValueError, TypeError):
                    parts.append((1, 0.0, locale.strxfrm(val), sk['ascending']))
            return parts

        def _cmp_rows(a, b):
            ka = _sort_key_fn(a)
            kb = _sort_key_fn(b)
            for (ta, na, sa, asc_a), (tb, nb, sb, _) in zip(ka, kb):
                if ta != tb:
                    diff = ta - tb
                elif ta == 0:
                    diff = (na - nb) if na != nb else 0
                else:
                    diff = (0 if sa == sb else (1 if sa > sb else -1))
                if diff != 0:
                    return int(diff) if asc_a else -int(diff)
            return 0

        result = sorted(result, key=functools.cmp_to_key(_cmp_rows))

    # --- Formatar saida ---
    out_headers = _build_output_headers(headers, rules)
    sum_set     = set(sum_indices)
    out_rows    = []
    for row in result:
        out_row = []
        for idx in output_col_order:
            val = row[idx] if idx < len(row) else ''
            if idx in sum_set:
                try:
                    fval = float(val)
                    val  = str(int(fval)) if fval == int(fval) else str(round(fval, 6))
                except (ValueError, TypeError):
                    pass
            out_row.append(val)
        out_rows.append(out_row)

    return out_headers, out_rows


def _build_output_headers(headers, rules):
    """Constroi lista de headers de saida: exclui 'ignore', prefixo '# ' em 'count'."""
    col_map       = {name: idx for idx, name in enumerate(headers)}
    count_indices = set()
    active        = set()

    for rule in rules:
        action = rule.get('action', 'ignore')
        idx    = col_map.get(rule.get('name', ''))
        if idx is None:
            continue
        if action != 'ignore':
            active.add(idx)
        if action == 'count':
            count_indices.add(idx)

    out = []
    for i, h in enumerate(headers):
        if i not in active:
            continue
        out.append(('# ' + h) if i in count_indices else h)
    return out
