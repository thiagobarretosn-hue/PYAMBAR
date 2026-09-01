# -*- coding: utf-8 -*-
"""
_mep_connect_log.py — registro automatico das execucoes do Conectar Em Lote.

Grava cada execucao num JSON em APPDATA, com tudo que apareceria no balao e no
output: contadores, escolhas do usuario, recusas com motivo, pendencias e o
diagnostico. Assim a analise nao depende de copiar e colar texto — nem do
Revit continuar aberto.

    %APPDATA%\\pyRevit\\PYAMBAR\\ConectarEmLote\\runs\\run_AAAAMMDD_HHMMSS.json

Na bancada de testes (Y=200, Z=10) o cenario e reconhecido pela coordenada X
dos elementos selecionados, entao cada arquivo ja vem etiquetado com C1..C12.

IronPython: usar codecs.open (o open() nativo ignora encoding e grava cp1252)
e int() nos ElementId (Int64 do .NET nao e serializavel em JSON).
"""

import codecs
import json
import os
from datetime import datetime

PASTA = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                     'ConectarEmLote', 'runs')

# Bancada de testes: X do cenario -> etiqueta. Tolerancia de 6 ft cobre a
# largura de cada montagem sem invadir a vizinha (elas distam 10 ft ou mais).
BANCADA_Y = 200.0
BANCADA_TOL = 6.0
BANCADA = [
    (200.0, "C1  Fase 1 - conectores coincidentes"),
    (210.0, "C2  Fase 1 - desalinhado 20 mm"),
    (220.0, "C3  Fase 2 - vao de 2 ft"),
    (230.0, "C4  Fase 0b - TE (ramal 90)"),
    (240.0, "C5  Fase 0b - WYE (ramal 45)"),
    (250.0, "C6  Fase 0b - JOELHO (canto)"),
    (260.0, "C7  Fase 0d - DESVIO offset 200 mm"),
    (270.0, "C8  Fase 0e - DERIVACAO tronco continuo"),
    (285.0, "C9  Fase 0e - mesmo sentido 748 mm"),
    (300.0, "C10 FUSAO - ja conectados"),
    (315.0, "C11 ANTI-SALTO - 3 em linha"),
    (330.0, "C12 REDUCAO - diametros 3x2"),
    (348.75, "C13 INCLINACAO - vao axial com 1/8in por ft"),
    (364.50, "C14 TE em tronco INCLINADO"),
    (375.60, "C15 ramal a 22.5 graus"),
    (391.20, "C16 ramal a 60 graus"),
    (409.05, "C17 CADEIA - 5 segmentos com folga"),
    (422.00, "C18 REDE EXISTENTE - nao pode quebrar"),
    (436.00, "C19 MARGEM - cruzamento rente a ponta"),
    (450.40, "C20 ESCOLHA - 4 troncos candidatos"),
    (470.60, "C21 MULTIPLO - prumada com 4 ramais"),
    (493.00, "C22 MALHA - 2 prumadas ligadas por 2 ramais"),
    (515.50, "C23 MISTO - vao + bucha + cruzamento juntos"),
    (533.50, "C24 CADEIA EM L - 6 segmentos e um canto"),
    (550.00, "C25 Fase 0 - TE SOLTO sobre prumada"),
    (574.00, "C26 DOIS TES espacados no mesmo tubo"),
    (591.00, "C27 REDUCAO no cruzamento (3 x 2)"),
    (606.50, "C28 CONTROLE - nada a fazer"),
    (626.00, "C29 FORA DO PLANO - ramal em 3D"),
    (666.00, "C30 DOIS TES juntos no mesmo tubo"),
]


VISTA_BANCADA = "Section 74"
MARCA_AUTO = "=== RESULTADO (automatico) ==="
MARCA_OBS = "=== MINHAS OBS ==="


def _ponto_medio(elements):
    """(x, y) medio dos elementos, para reconhecer o cenario da bancada."""
    xs, ys = [], []
    for elem in elements:
        try:
            bb = elem.get_BoundingBox(None)
            if bb is None:
                continue
            xs.append((bb.Min.X + bb.Max.X) / 2.0)
            ys.append((bb.Min.Y + bb.Max.Y) / 2.0)
        except Exception:
            pass
    if not xs:
        return None, None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def detectar_cenario(elements):
    """Etiqueta do cenario da bancada, ou None se a selecao esta noutro lugar."""
    x, y = _ponto_medio(elements)
    if x is None:
        return None
    if abs(y - BANCADA_Y) > 20.0:
        return None                      # fora da bancada
    melhor, dist = None, BANCADA_TOL
    for bx, nome in BANCADA:
        d = abs(x - bx)
        if d < dist:
            melhor, dist = nome, d
    return melhor


def _ids(elements):
    saida = []
    for elem in elements:
        try:
            valor = elem.Id.Value if hasattr(elem.Id, 'Value') else elem.Id.IntegerValue
            saida.append(int(valor))
        except Exception:
            pass
    return saida


def _limpar(valor):
    """Deixa o valor serializavel: ElementId do .NET vira int."""
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    if isinstance(valor, dict):
        return dict((str(k), _limpar(v)) for k, v in valor.items())
    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor
    if isinstance(valor, str):
        return valor
    for attr in ('Value', 'IntegerValue'):
        if hasattr(valor, attr):
            try:
                return int(getattr(valor, attr))
            except Exception:
                pass
    return str(valor)


def registrar(doc, elements, resultado, escolhas=None, resumo="",
              diagnostico=None, vizinhos=None):
    """Grava a execucao e devolve o caminho do arquivo (ou None se falhar).

    Nunca levanta: registro e apoio, nao pode derrubar a ferramenta.
    """
    try:
        if not os.path.exists(PASTA):
            os.makedirs(PASTA)

        agora = datetime.now()
        dados = {
            'quando': agora.strftime('%Y-%m-%d %H:%M:%S'),
            'documento': getattr(doc, 'Title', ''),
            'cenario': detectar_cenario(elements),
            'selecao': _ids(elements),
            'n_selecionados': len(elements),
            'escolhas': _limpar(escolhas or {}),
            # 'menu_aberto'/'menu_cancelado' vem junto das escolhas: sem eles
            # nao da para separar "a busca nao achou par" de "o menu foi
            # fechado", e a analise do cenario empaca.
            'resumo': resumo,
            'contadores': dict(
                (k, _limpar(resultado.get(k, 0))) for k in
                ('tees', 'wyes', 'elbows', 'jogs', 'takeoffs', 'splits',
                 'reducers', 'girados', 'series', 'connected', 'merged',
                 'failed', 'no_tee')),
            'fases_com_erro': _limpar(resultado.get('fases_com_erro') or []),
            'recusas_fusao': _limpar(resultado.get('merge_recusas') or []),
            'pulados_desvio': _limpar(resultado.get('jog_skips') or []),
            'pulados_derivacao': _limpar(resultado.get('takeoff_skips') or []),
            'recusas_bucha': _limpar(resultado.get('reducer_recusas') or []),
            'angulo_sem_peca': _limpar(resultado.get('no_tee_planos') or []),
            'ajuste_recusado': _limpar(resultado.get('girar_recusas') or []),
            'tubos_apagados': _limpar(resultado.get('tubos_perdidos') or []),
            'avisos_inclinacao': _limpar(resultado.get('slope_avisos') or []),
            'vizinhos_fora_da_selecao': _limpar(vizinhos or []),
            'diagnostico': _limpar(diagnostico or []),
        }

        nome = 'run_{}.json'.format(agora.strftime('%Y%m%d_%H%M%S'))
        caminho = os.path.join(PASTA, nome)
        with codecs.open(caminho, 'w', encoding='utf-8') as arquivo:
            json.dump(dados, arquivo, indent=2, ensure_ascii=False)

        # Alem do JSON, escrever o resultado na nota do proprio cenario: assim
        # o que aconteceu fica ao lado do que era esperado, sem copiar texto.
        escrever_no_modelo(doc, dados['cenario'], resultado, escolhas, agora,
                           nome)
        return caminho
    except Exception:
        return None


def _x_do_cenario(nome):
    """X da montagem cujo rotulo e ``nome``, ou None."""
    for bx, rotulo in BANCADA:
        if rotulo == nome:
            return bx
    return None


def _resumo_curto(resultado, escolhas, agora):
    """Bloco de texto que a ferramenta escreve na nota do cenario."""
    ct = resultado or {}
    feitos = []
    for chave, rot in (('tees', 'te'), ('wyes', 'wye'), ('elbows', 'joelho'),
                       ('jogs', 'desvio'), ('takeoffs', 'derivacao'),
                       ('splits', 'dividido'), ('series', 'em serie'),
                       ('connected', 'conectado'), ('merged', 'fundido'),
                       ('reducers', 'bucha'), ('girados', 'girado')):
        try:
            n = int(ct.get(chave, 0) or 0)
        except Exception:
            n = 0
        if n:
            feitos.append("{} {}".format(n, rot))
    falhas = int(ct.get('failed', 0) or 0)

    linhas = [agora.strftime('%d/%m %H:%M') + "  " +
              (" | ".join(feitos) if feitos else "NADA FEITO") +
              ("  ({} falha(s))".format(falhas) if falhas else "")]

    esc = escolhas or {}
    escolhido = esc.get('derivacao') or (
        "desvio {:g} graus".format(esc['desvio_graus'])
        if esc.get('desvio_graus') else None)
    if escolhido:
        linhas.append("escolha: " + str(escolhido))
    if esc.get('ajustes_de_angulo'):
        linhas.append("ajuste de angulo: " + ", ".join(
            "{} {}".format(k, v)
            for k, v in esc['ajustes_de_angulo'].items()))
    if esc.get('menu_cancelado'):
        linhas.append("MENU FECHADO sem escolher")
    elif esc.get('sem_opcao'):
        linhas.append("sem opcao: " + str(esc['sem_opcao']))

    for campo, rot in (('takeoff_skips', 'derivacao pulada'),
                       ('jog_skips', 'desvio pulado'),
                       ('reducer_recusas', 'bucha recusada'),
                       ('tubos_perdidos', 'TUBO APAGADO'),
                       ('no_tee_planos', 'angulo sem peca'),
                       ('fases_com_erro', 'FASE COM ERRO')):
        itens = ct.get(campo) or []
        for item in itens[:2]:
            if isinstance(item, (list, tuple)) and len(item) > 1:
                linhas.append("{}: {}".format(rot, item[1]))
            else:
                linhas.append("{}: {}".format(rot, item))
    return "\n".join(linhas)


def escrever_no_modelo(doc, cenario, resultado, escolhas, agora, arquivo=""):
    """Escreve o resultado na nota do cenario, dentro do proprio modelo.

    So reescreve o bloco entre ``MARCA_AUTO`` e ``MARCA_OBS`` — o titulo, o
    esperado e as observacoes escritas a mao ficam intactos. Assim o texto do
    teste nao precisa ser copiado a mao a cada rodada.

    Devolve True se gravou. Nunca levanta.
    """
    if not cenario:
        return False
    bx = _x_do_cenario(cenario)
    if bx is None:
        return False
    try:
        from Autodesk.Revit.DB import (FilteredElementCollector, TextNote,
                                       Transaction, View)

        vista = None
        for v in FilteredElementCollector(doc).OfClass(View):
            try:
                if not v.IsTemplate and v.Name == VISTA_BANCADA:
                    vista = v
                    break
            except Exception:
                pass
        if vista is None:
            return False

        alvo, melhor = None, BANCADA_TOL
        for nota in FilteredElementCollector(doc, vista.Id).OfClass(TextNote):
            try:
                d = abs(nota.Coord.X - bx)
                # a nota de resultado e a de baixo; a de titulo fica no alto
                if d < melhor and MARCA_AUTO in nota.Text:
                    alvo, melhor = nota, d
            except Exception:
                pass
        if alvo is None:
            return False

        texto = alvo.Text
        i = texto.index(MARCA_AUTO)
        j = texto.find(MARCA_OBS)
        cabeca = texto[:i]
        cauda = texto[j:] if j > i else ("\n" + MARCA_OBS + "\n")
        miolo = "{}\n{}\n{}\n".format(MARCA_AUTO,
                                      _resumo_curto(resultado, escolhas, agora),
                                      arquivo)

        t = Transaction(doc, "Bancada: gravar resultado")
        t.Start()
        alvo.Text = cabeca + miolo + cauda
        t.Commit()
        return True
    except Exception:
        return False
