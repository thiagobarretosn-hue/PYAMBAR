# -*- coding: utf-8 -*-
"""Trecho horizontal de tubulacao — puro (sem clr), com testes.

Pedido do Thiago em 16/09/2026, depois da auditoria do MIIQLUX: "quando a
gente tem um pequeno espaco de tubos horizontais a gente nao considera como
colgante, considera como riser". O desvio nao se reconhece pelo comprimento
de UMA peca:

    10933832 (0,77 ft) + conexoes + 10933836 (0,72 ft) = trecho de 1,5 ft
    10858820 (0,51) + 10858887 (3,82) + 10859792 (0,54)  = trecho de 4,9 ft

O tubo de 3,82 ft sozinho passa de qualquer corte pequeno; o TRECHO inteiro,
entre dois verticais, e que diz que aquilo e um desvio de riser. E a conexao,
que nao tem comprimento nenhum, herda os numeros do trecho — sem isso a regra
deixava toda conexao em branco (o que aconteceu no 1o uso).

O trecho vai de tubo horizontal a tubo horizontal, passando por conexoes e
acessorios, e PARA no tubo vertical/inclinado (que vira "ponta"), em peca de
outra categoria (louca, equipamento) e na fronteira do grupo.
"""

HORIZONTAL = 'horizontal'

TUBO = 'tubo'
CONEXAO = 'conexao'     # conexao ou acessorio: entra no trecho, sem comprimento
OUTRO = 'outro'         # louca, equipamento: fecha o trecho e nao conta ponta

#: rede doente (tudo ligado em tudo) nao pode travar a preview
LIMITE_PECAS = 400


def trecho_de(inicio, peca_de, vizinhos_de, limite=LIMITE_PECAS):
    """{'pecas', 'comprimento', 'pontas'} do trecho horizontal de `inicio`.

    `peca_de(id)` -> {'tipo', 'orientacao', 'comprimento', 'grupo'} ou None.
    `vizinhos_de(id)` -> ids ligados fisicamente.

    None quando o trecho nao tem nenhum tubo horizontal: peca vertical, ou
    conexao entre dois verticais (essa ja herda a orientacao do tubo).
    """
    base = peca_de(inicio)
    if base is None:
        return None
    if base['tipo'] == OUTRO:
        return None
    if base['tipo'] == TUBO and base.get('orientacao') != HORIZONTAL:
        return None

    grupo = base.get('grupo')
    pecas, pontas = [], set()
    comprimento = 0.0
    tem_tubo = False
    vistos = set([inicio])
    fila = [inicio]
    while fila and len(pecas) < limite:
        atual = fila.pop()
        dados = peca_de(atual)
        if dados is None:
            continue
        pecas.append(atual)
        if dados['tipo'] == TUBO:
            tem_tubo = True
            comprimento += dados.get('comprimento') or 0.0
        for vizinho in vizinhos_de(atual) or []:
            if vizinho in vistos:
                continue
            outro = peca_de(vizinho)
            if outro is None or outro['tipo'] == OUTRO:
                continue
            # o grupo e uma unidade: o trecho da aranha nao vira o do tubo solto
            if outro.get('grupo') != grupo:
                continue
            if outro['tipo'] == TUBO and outro.get('orientacao') != HORIZONTAL:
                pontas.add(vizinho)
                continue
            vistos.add(vizinho)
            fila.append(vizinho)
    if not tem_tubo:
        return None
    return {'pecas': pecas, 'comprimento': comprimento, 'pontas': len(pontas)}
