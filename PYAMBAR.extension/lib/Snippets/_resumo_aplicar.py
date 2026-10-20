# -*- coding: utf-8 -*-
"""O que o Aplicar vai gravar, por parametro — puro (sem clr), com testes.

Pedido do Thiago em 16/09/2026, na auditoria: a ferramenta escreve em 2.500
elementos de uma vez e o unico aviso antes disso era a contagem no botao. Aqui
sai o resumo que a janela mostra ANTES da Transaction: quantos elementos cada
parametro recebe, os valores mais comuns, e o que esta bloqueado.
"""

#: valores diferentes mostrados por parametro antes de resumir o resto
EXEMPLOS = 3


def resumo_do_aplicar(itens):
    """[{'parametro', 'elementos', 'exemplos': [(valor, n)], 'outros',
    'bloqueados'}] ordenado por nome do parametro.

    `itens`: [{'valores': [(parametro, valor), ...],
               'bloqueios': {parametro: motivo}}] — um por elemento da preview.
    """
    contagem, bloqueados = {}, {}
    for item in itens or []:
        for parametro, valor in (item.get('valores') or []):
            if valor is None or valor == '':
                continue
            porvalor = contagem.setdefault(parametro, {})
            texto = u'{}'.format(valor)
            porvalor[texto] = porvalor.get(texto, 0) + 1
        for parametro in (item.get('bloqueios') or {}):
            bloqueados[parametro] = bloqueados.get(parametro, 0) + 1

    linhas = []
    for parametro in sorted(set(contagem) | set(bloqueados)):
        porvalor = contagem.get(parametro, {})
        ordenados = sorted(porvalor.items(), key=lambda par: (-par[1], par[0]))
        linhas.append({
            'parametro': parametro,
            'elementos': sum(porvalor.values()),
            'exemplos': ordenados[:EXEMPLOS],
            'outros': max(0, len(ordenados) - EXEMPLOS),
            'bloqueados': bloqueados.get(parametro, 0),
        })
    return linhas


def texto_do_resumo(linhas, elementos=0):
    """O texto da confirmacao. Sem linha nenhuma: diz que nao ha o que gravar."""
    if not linhas:
        return u'Nada a gravar.'
    partes = [u'{} elemento(s) na fila:'.format(elementos)] if elementos else []
    for linha in linhas:
        valores = u', '.join(u'"{}" ({})'.format(valor, quantos)
                             for valor, quantos in linha['exemplos'])
        if linha['outros']:
            valores += u' e mais {} valor(es)'.format(linha['outros'])
        texto = u'• {}: {} elemento(s)'.format(linha['parametro'],
                                               linha['elementos'])
        if valores:
            texto += u' — ' + valores
        if linha['bloqueados']:
            texto += u'  [{} bloqueado(s)]'.format(linha['bloqueados'])
        partes.append(texto)
    return u'\n'.join(partes)
