# -*- coding: utf-8 -*-
__title__ = "Conectar\nEm Lote"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.30"

import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
from System import Int64
from Autodesk.Revit.DB import (
    Color, ElementId, FillPatternElement, FillPatternTarget,
    FilteredElementCollector, OverrideGraphicSettings, Transaction
)
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from pyrevit import revit, forms, script

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

# Descartar os snippets ja carregados ANTES de importar.
#
# O pyRevit mantem os modulos em memoria entre execucoes: salvar o .py nao
# recarrega nada. Enquanto a ferramenta esta em desenvolvimento isso mente com
# autoridade — um teste roda com a versao anterior e o resultado parece dizer
# que a correcao nao funcionou. Ja aconteceu duas vezes aqui: uma varredura
# inteira e um teste manual, ambos medindo codigo velho.
#
# O custo e reimportar alguns .py por clique. Na distribuicao, onde o codigo
# nao muda entre execucoes, este bloco pode sair.
for _mod in [m for m in list(sys.modules)
             if m == 'Snippets' or m.startswith('Snippets.')]:
    try:
        del sys.modules[_mod]
    except Exception:
        pass

from Snippets._mep_batch_connect import (
    connect_batch, format_summary, did_anything, has_connectors, diagnose,
    vizinhos_fora_da_selecao, detectar_angulos_fora, AXIAL_MAX, PULL_DIST
)
from Snippets._mep_offset_jog import (
    find_offset_pairs, available_angles, advance_for, feasibility
)
from Snippets._mep_branch_takeoff import (
    find_takeoff_pairs, feasibility as takeoff_feasibility,
    avanco_estrategia, ESTRATEGIAS, tem_ambiguidade
)
from Snippets._mep_fill_gap import find_stub_targets
from Snippets._mep_connect_log import registrar as registrar_execucao
from Snippets._slope_repair import (
    coletar_trechos_afetados, descrever_trechos, formatar_resultado,
    reinclinar_trechos
)

doc = revit.doc
uidoc = revit.uidoc

# Verbosidade do output.
#
# LIGADO: a janela mostra o raciocinio — o que a ferramenta entendeu da
# selecao, a medida de cada criterio, o diagnostico das pendencias. Foi isso
# que permitiu achar os defeitos desta ferramenta, e continua ligado no lab.
#
# DESLIGADO (distribuicao): o engenheiro quer o resultado, nao o raciocinio.
# Fica so o que exige decisao dele — o que nao foi feito e por que, pecas
# encostadas fora da selecao, e erro.
DIAGNOSTICO = False

# Gravacao do registro em APPDATA (pyRevit/PYAMBAR/ConectarEmLote/runs).
#
# No lab e o que permite reconstruir uma execucao depois — geometria, escolhas,
# motivo de cada recusa. Na distribuicao fica DESLIGADO: escrever arquivo por
# execucao na maquina de quem so quer usar a ferramenta e coleta que ninguem
# pediu. Se um caso estranho aparecer em obra, e so pedir ao usuario para
# ligar as duas chaves e repetir.
REGISTRO = False


def _detalhe(texto):
    """Mensagem de diagnostico — some quando DIAGNOSTICO esta desligado."""
    if DIAGNOSTICO:
        output.print_md(texto)
output = script.get_output()


def _link(eid):
    """Link clicavel a partir de ElementId OU do valor inteiro do id.

    Os relatorios guardam o id como int (ler .Id de elemento ja deletado
    levanta InvalidObjectException), mas linkify so aceita ElementId.
    """
    try:
        if isinstance(eid, (int, long)):
            eid = ElementId(Int64(eid))
    except NameError:          # IronPython 3 nao tem long
        if isinstance(eid, int):
            eid = ElementId(Int64(eid))
    try:
        return output.linkify(eid)
    except Exception:
        return str(eid)


# Preenchido por _escolher_estrategia: o que a busca achou e o que o usuario
# fez com o menu. Sem isso, "nada a conectar" com zero pares e "nada a
# conectar" porque o menu foi fechado ficam identicos no registro — foi
# exatamente essa duvida que travou a analise do cenario C9.
RELATO_ESCOLHA = {}


# Paleta da escolha visual. Ler "tubo 10805260, 14.00 ft" e ter de procurar
# qual e na tela e lento e da erro; ver VERMELHO ligando no AZUL e imediato.
COR_ORIGEM = ("VERMELHO", 220, 30, 30)
CORES_DESTINO = [
    ("AZUL", 20, 90, 235),
    ("VERDE", 0, 155, 60),
    ("LARANJA", 240, 140, 0),
    ("ROXO", 150, 40, 190),
    ("CIANO", 0, 170, 190),
    ("ROSA", 235, 60, 150),
]


def _zoom_em(elem):
    """Enquadra o elemento na vista ativa e o deixa selecionado."""
    try:
        from System.Collections.Generic import List as _NetList
        ids = _NetList[ElementId]()
        ids.Add(elem.Id)
        uidoc.ShowElements(ids)
        uidoc.Selection.SetElementIds(ids)
    except Exception:
        pass


def _padrao_solido():
    """FillPatternElement solido, para o tubo aparecer preenchido na cor."""
    try:
        for fp in FilteredElementCollector(doc).OfClass(FillPatternElement):
            padrao = fp.GetFillPattern()
            if padrao.IsSolidFill and padrao.Target == FillPatternTarget.Drafting:
                return fp.Id
    except Exception:
        pass
    return None


def _override(r, g, b, solido):
    """Realce de linha grossa + superficie na cor."""
    ogs = OverrideGraphicSettings()
    cor = Color(r, g, b)
    try:
        ogs.SetProjectionLineColor(cor)
        ogs.SetProjectionLineWeight(8)
        ogs.SetCutLineColor(cor)
        if solido is not None:
            ogs.SetSurfaceForegroundPatternId(solido)
            ogs.SetSurfaceForegroundPatternColor(cor)
            ogs.SetSurfaceForegroundPatternVisible(True)
            ogs.SetCutForegroundPatternId(solido)
            ogs.SetCutForegroundPatternColor(cor)
    except Exception:
        pass
    return ogs


def _pintar(mapa_cores):
    """Pinta {elemento: (nome, r, g, b)} na vista ativa. Devolve os ids pintados.

    Precisa de Transaction propria — e a escolha acontece ANTES da Transaction
    principal, entao abrir uma aqui e seguro (dialogo dentro de Transaction e
    erro fatal no Revit 2026).
    """
    pintados = []
    solido = _padrao_solido()
    t = Transaction(doc, "Destacar tubos da escolha")
    try:
        t.Start()
        for elem, (_nome, r, g, b) in mapa_cores.items():
            try:
                doc.ActiveView.SetElementOverrides(elem.Id,
                                                   _override(r, g, b, solido))
                pintados.append(elem.Id)
            except Exception:
                pass
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
    return pintados


def _despintar(ids):
    """Devolve os elementos a aparencia normal. Sempre chamar no fim."""
    if not ids:
        return
    t = Transaction(doc, "Limpar destaque")
    try:
        t.Start()
        limpo = OverrideGraphicSettings()
        for eid in ids:
            try:
                doc.ActiveView.SetElementOverrides(eid, limpo)
            except Exception:
                pass
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass


def _rotulo_tronco(cand, i):
    """Uma linha descrevendo o tronco candidato, pela COR que ele esta na tela."""
    nome = CORES_DESTINO[i % len(CORES_DESTINO)][0]
    try:
        tid = cand['tronco'].Id
        tid = tid.Value if hasattr(tid, 'Value') else tid.IntegerValue
    except Exception:
        tid = "?"
    return "{}  —  tubo {} · {:.1f} ft · entrada a {:.1f} ft".format(
        nome, tid, cand.get('comp_tronco', 0.0), cand.get('dist_entrada', 0.0))


class _SoEstes(ISelectionFilter):
    """Deixa clicar apenas nos tubos candidatos — o resto fica inerte."""

    def __init__(self, ids):
        self.ids = set(ids)

    def AllowElement(self, elem):
        try:
            valor = (elem.Id.Value if hasattr(elem.Id, 'Value')
                     else elem.Id.IntegerValue)
            return int(valor) in self.ids
        except Exception:
            return False

    def AllowReference(self, ref, ponto):
        return False


def _enquadrar(elems):
    """Enquadra o conjunto todo, para os candidatos caberem na tela juntos."""
    try:
        from System.Collections.Generic import List as _NetList
        ids = _NetList[ElementId]()
        for elem in elems:
            ids.Add(elem.Id)
        uidoc.ShowElements(ids)
        uidoc.Selection.SetElementIds(_NetList[ElementId]())   # sem realce azul
    except Exception:
        pass


def _escolher_tronco(pares):
    """Deixa apontar EM QUAL tronco derivar, clicando no proprio modelo.

    A escolha e feita NA VISTA, nao numa janela: uma lista modal cobre
    justamente os tubos que ela esta descrevendo, e casar "tubo 10806512" com
    um tubo na tela e o que tornava a decisao uma adivinhacao. Aqui o ramal
    fica VERMELHO, cada tronco possivel ganha uma cor, a tela enquadra todos e
    o Revit pede um clique — com o filtro deixando clicar so nos candidatos.

    So pergunta quando ha mais de um tronco possivel. Roda ANTES da Transaction
    principal: PickObject e dialogo dentro dela sao erro fatal no Revit 2026.
    """
    for par in pares:
        alternativas = par.get('alternativas') or []
        if len(alternativas) < 2:
            continue

        mapa = {par['ramal']: COR_ORIGEM}
        for i, cand in enumerate(alternativas):
            mapa[cand['tronco']] = CORES_DESTINO[i % len(CORES_DESTINO)]
        pintados = _pintar(mapa)
        _enquadrar([par['ramal']] + [c['tronco'] for c in alternativas])

        escolhido = None
        try:
            ids_validos = []
            for cand in alternativas:
                try:
                    tid = cand['tronco'].Id
                    ids_validos.append(int(tid.Value if hasattr(tid, 'Value')
                                           else tid.IntegerValue))
                except Exception:
                    pass
            try:
                ref = uidoc.Selection.PickObject(
                    ObjectType.Element, _SoEstes(ids_validos),
                    "Clique no tronco onde derivar o ramal VERMELHO "
                    "(ESC para nao derivar)")
                alvo = doc.GetElement(ref.ElementId)
                alvo_id = int(alvo.Id.Value if hasattr(alvo.Id, 'Value')
                              else alvo.Id.IntegerValue)
                for cand in alternativas:
                    tid = cand['tronco'].Id
                    if int(tid.Value if hasattr(tid, 'Value')
                           else tid.IntegerValue) == alvo_id:
                        escolhido = cand
                        break
            except Exception:
                # ESC, ou a vista nao aceita selecao: cai para a lista
                escolhido = _escolher_tronco_por_lista(par, alternativas)
                if escolhido is False:
                    return False
        finally:
            # a pintura nunca pode sobrar no modelo, nem se o usuario desistir
            _despintar(pintados)

        if not escolhido:
            return False

        for chave in ('tronco', 'comp_tronco', 'p0t', 'p1t', 'eixo_tronco',
                      'offset', 'lado', 't_livre'):
            if chave in escolhido:
                par[chave] = escolhido[chave]
        # marca a decisao: o motor nao troca de tronco pelas costas de quem
        # apontou um na tela — se nao couber, ele diz por que
        par['escolha_do_usuario'] = True
    return True


def _escolher_tronco_por_lista(par, alternativas):
    """Reserva para quando nao da para clicar na vista (ESC, vista sem 3D).

    Devolve o candidato, None se nao decidiu, ou False se desistiu de tudo.
    """
    opcoes = [_rotulo_tronco(c, i) for i, c in enumerate(alternativas)]
    resp = forms.CommandSwitchWindow.show(
        opcoes, message="Derivar o ramal VERMELHO em qual tronco?")
    if isinstance(resp, tuple):
        resp = resp[0]
    if not resp:
        return False
    return alternativas[opcoes.index(resp)]


def _explicar_selecao(elements):
    """Diz o que a ferramenta ENTENDEU da selecao, antes de agir.

    A seleccao carrega significado oculto: com dois tubos a Fase 0e ve um par,
    com tres ela pode eleger outro tronco e mudar todo o resultado. Sem esse
    aviso o usuario nao tinha como saber o que ia acontecer nem por que o
    resultado mudava ao incluir mais um tubo — "nao esta claro o que
    selecionar" e exatamente isso.
    """
    tubos = [e for e in elements if e is not None and e.IsValidObject]
    linhas = ["**{} elemento(s) na selecao.**".format(len(tubos))]

    try:
        pares_deriv = find_takeoff_pairs(tubos)
    except Exception:
        pares_deriv = []
    try:
        pares_desvio = [p for p in find_offset_pairs(tubos)
                        if p.get('dist_pontas', 0) >= PULL_DIST]
    except Exception:
        pares_desvio = []

    def _id(elem):
        try:
            v = elem.Id
            return int(v.Value if hasattr(v, 'Value') else v.IntegerValue)
        except Exception:
            return "?"

    for par in pares_deriv:
        alternativas = par.get('alternativas') or []
        linhas.append(
            "- derivacao: ramal `{}` -> tronco `{}`{}".format(
                _id(par['ramal']), _id(par['tronco']),
                "  (ha {} tronco(s) possivel(is); vai perguntar qual)".format(
                    len(alternativas)) if len(alternativas) > 1 else ""))
    for par in pares_desvio:
        linhas.append("- desvio: `{}` + `{}`  (offset {:.0f} mm)".format(
            _id(par['pipe_a']), _id(par['pipe_b']), par['offset'] * 304.8))

    try:
        alvos_toco, _ = find_stub_targets(
            [e for e in elements if e is not None and e.IsValidObject])
    except Exception:
        alvos_toco = []
    for alvo in alvos_toco:
        linhas.append(
            "- toco: a conexao `{}` ganha tubo para derivar no tronco `{}` "
            "(offset {:.0f} mm)".format(_id(alvo['fitting']),
                                        _id(alvo['tronco']),
                                        alvo['lateral'] * 304.8))

    if not pares_deriv and not pares_desvio and not alvos_toco:
        linhas.append("- nenhuma peca a criar; so as ligacoes diretas")
    return linhas


def _perguntar_rotacoes(elements):
    """{id_do_ramal: plano} para os cruzamentos sem peca no angulo.

    Um ramal que cruza a 22,5 ou a 60 graus nao tem juncao: o wye so aceita 45
    e o te so 90. Duas saidas, nesta ordem:

      1. JOELHO de ajuste — recua o ramal e emenda um trecho que chega no
         angulo certo. O tubo desenhado fica onde esta.
      2. GIRAR o ramal — so quando nenhuma dobra do catalogo resolve. Mexe no
         desenho do projetista, entao nunca acontece sem autorizacao.

    Roda ANTES da Transaction principal. Medir o angulo das familias exige
    Transaction ativa (instancia num SubTransaction revertido), entao abre-se
    uma so para medir, sem alterar nada.
    """
    achados = []
    t = Transaction(doc, "Medir angulos das juncoes")
    try:
        t.Start()
        achados = detectar_angulos_fora(elements)
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        return {}

    try:
        from Snippets._mep_angle_fix import peca_para
    except Exception:
        peca_para = None

    autorizados = {}
    for caso in achados:
        planos = caso.get('planos') or []
        if not planos:
            continue

        # Fora da faixa de duvida a peca esta decidida pelo angulo: perto de
        # 45 e wye, perto de 90 e te. Perguntar ali so atrasa quem ja sabe a
        # resposta — e um tronco com inclinacao de esgoto caia nessa pergunta
        # por 0,6 grau. So a faixa do meio e escolha de verdade.
        if peca_para is not None:
            _pedida, perguntar = peca_para(caso['theta'])
            if not perguntar:
                autorizados[caso['id']] = planos[0]
                continue

        # O rotulo diz a PECA e o preco de usa-la. Quem le e engenheiro: o
        # que importa e "que peca vai entrar" e "o que muda no desenho".
        opcoes, mapa = [], {}
        for plano in planos:
            peca = "Te" if plano['alvo'] >= 89.0 else "Wye"
            if plano['tipo'] == 'joelho':
                rotulo = "{} de {:g} com joelho de {:g}  ·  tubo fica no lugar"                    .format(peca, plano['alvo'], plano['dobra'])
            elif plano['tipo'] == 'rotacao':
                rotulo = "{} de {:g}  ·  gira o ramal {:+.0f}".format(
                    peca, plano['alvo'], plano['rotacao'])
            else:
                continue
            if rotulo in mapa:
                continue
            opcoes.append(rotulo)
            mapa[rotulo] = plano
        if not opcoes:
            continue

        _zoom_em(caso['branch'])
        pintados = _pintar({caso['branch']: COR_ORIGEM,
                            caso['main']: CORES_DESTINO[0]})
        try:
            resp = forms.CommandSwitchWindow.show(
                opcoes + ["Nao alterar"],
                message="Ramal a {:.0f} graus do tronco — sem peca nesse "
                        "angulo. Como conectar?".format(caso['theta']))
            if isinstance(resp, tuple):
                resp = resp[0]
        finally:
            _despintar(pintados)
        if resp in mapa:
            autorizados[caso['id']] = mapa[resp]
    return autorizados


def _escolher_estrategia(elements):
    """(angulo_do_desvio, estrategia_da_derivacao) — menu de dois niveis.

    As situacoes sao parecidas demais para caber numa lista so: primeiro
    escolhe-se COMO resolver (Te, Wye ou so joelhos), e a segunda janela mostra
    apenas as combinacoes daquela familia, com quanto cada uma sobe.
    """
    pipes = [e for e in elements if e is not None and e.IsValidObject]
    try:
        pares_desvio = [p for p in find_offset_pairs(pipes)
                        if p.get('dist_pontas', 0) >= PULL_DIST]
    except Exception:
        pares_desvio = []
    try:
        pares_deriv = find_takeoff_pairs(pipes)
    except Exception:
        pares_deriv = []
    # Uma via livre de FITTING vira ramal assim que a fase 0h lhe der o tubo.
    # Sem contar esses alvos aqui, a estrategia sai None e a derivacao fica
    # desligada — o toco nasceria para nada, porque a decisao de "nao ha peca
    # a criar" e tomada ANTES de ele existir.
    try:
        alvos_toco, _ = find_stub_targets(pipes)
    except Exception:
        alvos_toco = []

    RELATO_ESCOLHA.clear()
    RELATO_ESCOLHA.update({'pares_desvio': len(pares_desvio),
                           'pares_derivacao': len(pares_deriv),
                           'alvos_toco': len(alvos_toco),
                           'menu_aberto': False,
                           'menu_cancelado': False})

    if not pares_desvio and not pares_deriv and not alvos_toco:
        return None, None

    # ---- nivel 1: com o que resolver
    familias = []
    if pares_deriv or alvos_toco:
        familias.append("Te")
        familias.append("Wye")
    if pares_desvio:
        familias.append("Joelhos (desvio entre duas pontas)")

    if len(familias) == 1:
        escolha1 = familias[0]
    else:
        quantos = []
        if pares_deriv or alvos_toco:
            quantos.append("{} derivacao(oes)".format(
                len(pares_deriv) + len(alvos_toco)))
        if pares_desvio:
            quantos.append("{} desvio(s)".format(len(pares_desvio)))
        RELATO_ESCOLHA['menu_aberto'] = True
        # "So conectar" existia escondido no ESC: fechar a janela ja pulava as
        # fases que criam peca. Escondido nao e opcao — quem quer so juntar o
        # que existe precisa ver isso escrito.
        SO_CONECTAR = "So conectar o que existe (nao criar peca)"
        escolha1 = forms.CommandSwitchWindow.show(
            familias + [SO_CONECTAR],
            message="Como resolver?  ({})".format(" · ".join(quantos)))
        if isinstance(escolha1, tuple):
            escolha1 = escolha1[0]
        if escolha1 == SO_CONECTAR:
            RELATO_ESCOLHA['so_conectar'] = True
            return None, None
    if not escolha1:
        RELATO_ESCOLHA['menu_cancelado'] = True
        return None, None

    # ---- nivel 2: qual combinacao
    if escolha1.startswith("Joelhos"):
        offset_max = max(p['offset'] for p in pares_desvio)
        opcoes, mapa = [], {}
        for ang in available_angles(pares_desvio[0]['pipe_a']):
            if ang >= 59.0 and ang < 89.0:
                continue          # 60 graus e raro em obra: fora da lista
            cabem = sum(1 for p in pares_desvio if feasibility(p, ang)[0])
            if not cabem:
                continue
            rotulo = "2 joelhos de {:g}  (avanca {:.0f} mm)".format(
                ang, advance_for(offset_max, ang) * 304.8)
            if cabem < len(pares_desvio):
                rotulo += "  {}/{}".format(cabem, len(pares_desvio))
            opcoes.append(rotulo)
            mapa[rotulo] = ang
        if not opcoes:
            output.print_md("**Nenhum angulo cabe** para os {} desvio(s).".format(
                len(pares_desvio)))
            RELATO_ESCOLHA['sem_opcao'] = 'nenhum angulo de desvio cabe'
            return None, None
        RELATO_ESCOLHA['menu_aberto'] = True
        escolha2 = forms.CommandSwitchWindow.show(
            opcoes,
            message="Desvio — offset {:.0f} mm · {} par(es):".format(
                offset_max * 304.8, len(pares_desvio)),
            switches={"Encurtar tubos se precisar": True})
        switches = {}
        if isinstance(escolha2, tuple):
            escolha2, switches = escolha2
        if not escolha2:
            RELATO_ESCOLHA['menu_cancelado'] = True
            return None, None
        ang = mapa.get(escolha2)
        if ang and not switches.get("Encurtar tubos se precisar", True):
            if not all(feasibility(p, ang)[0] for p in pares_desvio):
                forms.alert("Precisaria encurtar tubo e a opcao esta "
                            "desmarcada. Nenhum desvio foi criado.",
                            title="Desvio")
                RELATO_ESCOLHA['sem_opcao'] = 'precisaria encurtar e a opcao esta desmarcada'
                return None, None
        return ang, None

    chave = 'te' if escolha1 == "Te" else 'wye'

    # Antes de perguntar COMO derivar, deixar apontar EM QUE tronco: com mais
    # de um candidato a escolha automatica (menor offset) pode cair no tubo
    # errado, e a derivacao sai num lugar que nao era o pretendido.
    if not _escolher_tronco(pares_deriv):
        RELATO_ESCOLHA['menu_cancelado'] = True
        return None, None

    # O alvo de toco ainda NAO e um par de derivacao — o ramal dele so nasce
    # na fase 0h. Ele entra aqui pelo offset (para dimensionar as opcoes) e
    # como candidato; a viabilidade real e medida no motor, e a recusa, se
    # houver, sai no relatorio.
    offsets = ([p['offset'] for p in pares_deriv] +
               [a['lateral'] for a in alvos_toco])
    offset_max = max(offsets) if offsets else 0.0
    total_deriv = len(pares_deriv) + len(alvos_toco)

    opcoes, mapa = [], {}
    for rotulo_base, ang_j, n_j, ang_e in ESTRATEGIAS[chave]:
        estrategia = (rotulo_base, ang_j, n_j, ang_e)
        cabem = sum(1 for p in pares_deriv
                    if takeoff_feasibility(p, estrategia)[0])
        cabem += len(alvos_toco)
        if not cabem:
            continue
        sobe = avanco_estrategia(offset_max, ang_j, n_j)
        rotulo = "{}  (sobe {:.0f} mm)".format(
            rotulo_base, (sobe or 0.0) * 304.8)
        if cabem < total_deriv:
            rotulo += "  {}/{}".format(cabem, total_deriv)
        opcoes.append(rotulo)
        mapa[rotulo] = estrategia
    if not opcoes:
        output.print_md(
            "**Nenhuma combinacao de {} cabe** para as {} derivacao(oes) "
            "(offset ate {:.0f} mm).".format(
                escolha1, total_deriv, offset_max * 304.8))
        RELATO_ESCOLHA['sem_opcao'] = 'nenhuma combinacao de {} cabe'.format(escolha1)
        return None, None

    # "por cima ou por baixo" so quando algum ramal tem as DUAS pontas livres
    switches = {}
    try:
        ambiguo = tem_ambiguidade(pipes)
    except Exception:
        ambiguo = False
    if ambiguo:
        switches = {"Sair pela ponta de baixo": False}

    RELATO_ESCOLHA['menu_aberto'] = True
    escolha2 = forms.CommandSwitchWindow.show(
        opcoes,
        message="Derivacao com {} — offset {:.0f} mm · {} par(es):".format(
            escolha1, offset_max * 304.8, total_deriv),
        switches=switches)
    resp = {}
    if isinstance(escolha2, tuple):
        escolha2, resp = escolha2
    if not escolha2:
        RELATO_ESCOLHA['menu_cancelado'] = True
        return None, None
    estrategia = mapa.get(escolha2)
    if estrategia and resp.get("Sair pela ponta de baixo"):
        estrategia = estrategia + (True,)     # sinaliza preferir a ponta baixa
    return None, estrategia


# Guardada para o registro de falha: sem ela, um erro nao registra nada — e
# a execucao que quebrou e justamente a que mais precisa ficar gravada.
SELECAO_ATUAL = []


def main():
    ids = list(uidoc.Selection.GetElementIds())
    if not ids:
        forms.alert("Nenhum elemento selecionado.", exitscript=True)

    elements = [doc.GetElement(eid) for eid in ids]
    elements = [e for e in elements if has_connectors(e)]
    del SELECAO_ATUAL[:]
    SELECAO_ATUAL.extend(elements)

    if len(elements) < 2:
        forms.alert("Selecione pelo menos 2 elementos MEP.", exitscript=True)

    # Desvio (jog): tubos paralelos desalinhados nao emendam reto — precisam
    # de dois joelhos. A escolha do angulo e feita ANTES da Transaction
    # (dialogo aberto dentro dela e erro fatal no Revit 2026).
    # O que a ferramenta entendeu da selecao, antes de mexer em nada.
    for linha in _explicar_selecao(elements):
        _detalhe(linha)

    # Angulo sem peca: avisar e perguntar ANTES de qualquer Transaction.
    rotacoes = _perguntar_rotacoes(elements)

    jog_angle, takeoff_angle = _escolher_estrategia(elements)
    escolhas = {'desvio_graus': jog_angle,
                'derivacao': takeoff_angle[0] if takeoff_angle else None,
                'ponta_baixa': bool(takeoff_angle and len(takeoff_angle) > 4)}
    escolhas.update(RELATO_ESCOLHA)
    if rotacoes:
        escolhas['ajustes_de_angulo'] = dict(
            (str(k), "{} -> {:g}".format(v.get('tipo'), v.get('alvo'))
             if isinstance(v, dict) else str(v))
            for k, v in rotacoes.items())

    # Fechar o menu deixava a ferramenta dizer "nada a conectar", como se nao
    # houvesse caso — indistinguivel de uma falha de deteccao.
    if RELATO_ESCOLHA.get('menu_cancelado'):
        _detalhe(
            "> Menu fechado sem escolher: as fases que **criam** peca "
            "(desvio e derivacao) ficaram de fora. As demais rodaram "
            "normalmente.")
    if jog_angle:
        _detalhe("Estrategia escolhida: **desvio com 2 joelhos de "
                 "{:g} graus**.".format(jog_angle))
    elif takeoff_angle:
        _detalhe("Estrategia escolhida: **{}**.".format(takeoff_angle[0]))

    with revit.Transaction("Conectar Em Lote"):
        res = connect_batch(elements, jog_angle=jog_angle,
                            takeoff_angle=takeoff_angle, rotacoes=rotacoes)

    if not did_anything(res):
        # Diagnostico no output: qual limite estourou, com os numeros medidos.
        # O alerta sozinho nao dizia nada util para achar a causa.
        _detalhe("### Conectar Em Lote — nada a conectar")
        _detalhe(
            "Criterios: conectores a menos de 1\", tubo alinhado no eixo com "
            "conector livre a ate {} ft, te/cruzeta livre sobre o eixo de um "
            "tubo selecionado, ou ponta livre de ramal cruzando outro tubo "
            "selecionado.".format(int(AXIAL_MAX)))
        linhas_diag = diagnose(elements)
        for linha in linhas_diag:
            _detalhe(linha)
        if REGISTRO:
            registrar_execucao(doc, elements, res, escolhas=escolhas,
                               resumo="(nada a conectar)",
                               diagnostico=linhas_diag)
        # Fase que ABORTOU nao e "nada a conectar": o motivo real e a
        # excecao, e ela morria aqui — este return vem antes do bloco que
        # relata fases_com_erro, la embaixo.
        abortadas = res.get('fases_com_erro') or []
        perdidos = res.get('tubos_perdidos') or []
        for texto in abortadas:
            _detalhe("- **fase abortada:** {}".format(texto))
        for texto in perdidos:
            _detalhe("- **tubo perdido:** {}".format(texto))

        if abortadas:
            forms.alert(
                "{} fase(s) abortaram — por isso nada foi conectado.\n\n"
                "{}\n\nO detalhe esta na janela de output."
                .format(len(abortadas), "\n".join(abortadas)))
        else:
            forms.alert(
                "Nenhum par compativel encontrado.\n\n"
                "O diagnostico com as medidas de cada criterio foi impresso "
                "na janela de output.")
        return

    resumo = format_summary(res)

    # Cruzamento reconhecido, mas sem familia de juncao para aquele angulo nas
    # routing preferences do tipo de tubo (te de 90 e wye de 45 nao cobrem 22.5
    # nem 60). Recusar e o certo — calar sobre o motivo, nao.
    if res.get('no_tee'):
        output.print_md(
            "**{} cruzamento(s) sem peca no angulo** — os tubos ficaram "
            "intactos.".format(res['no_tee']))
        for _bid, texto in (res.get('no_tee_planos') or [])[:6]:
            _detalhe("  - `{}` {}".format(_bid, texto))
    try:
        forms.show_balloon("Conectar Em Lote", resumo)
    except Exception:
        pass

    # Remover tubo e a acao mais dificil de perceber e a mais cara de desfazer:
    # aparece SEMPRE, mesmo com o output enxuto.
    duplicados = res.get('redundantes') or []
    if duplicados:
        output.print_md(
            "**{} tubo(s) duplicado(s) removido(s)** (outro tubo passava "
            "direto por eles):".format(len(duplicados)))
        for eid, motivo in duplicados[:10]:
            output.print_md("- {} — {}".format(_link(eid), motivo))
    for eid, motivo in (res.get('redundante_avisos') or [])[:6]:
        output.print_md("- {} — {}".format(_link(eid), motivo))

    # Recusa por elemento ja ligado: aparece SEMPRE. Sem isso o caso vira
    # "nao fez nada", indistinguivel de "nao havia o que fazer".
    criados = res.get('tubos_criados') or 0
    if criados:
        output.print_md(
            "**{} tubo(s) criado(s)** onde faltava so o tubo entre duas "
            "conexoes ja alinhadas.".format(criados))

    tocos = res.get('tocos') or 0
    if tocos:
        output.print_md(
            "**{} toco(s) criado(s)** para dar ramal a uma conexao que "
            "estava sem tubo.".format(tocos))

    cantos = res.get('cantos') or 0
    if cantos:
        output.print_md(
            "**{} canto(s) fechado(s)** com dois joelhos e um trecho — as "
            "pontas foram esticadas, nada ligado saiu do lugar.".format(cantos))

    recusas = ((res.get('split_recusas') or []) +
               (res.get('junction_recusas') or []) +
               (res.get('canto_recusas') or []) +
               (res.get('fill_recusas') or []) +
               (res.get('stub_recusas') or []) +
               (res.get('reducer_recusas') or []) +
               (res.get('series_recusas') or []) +
               (res.get('girar_recusas') or []) +
               (res.get('pair_recusas') or []))
    if recusas:
        output.print_md(
            "**{} caso(s) que a ferramenta recusou** (o motivo traz a "
            "medida):".format(len(recusas)))
        for eid, motivo in recusas[:10]:
            output.print_md("- {} — {}".format(_link(eid), motivo))

    avisos = res.get('slope_avisos') or []

    if res['failed'] > 0 or res['no_tee'] > 0 or avisos:
        output.print_md("**" + resumo + ".**")
    if avisos:
        output.print_md(
            "{} conexao(oes) onde o Revit **nao respeitou a inclinacao** "
            "gravada. Quase sempre e o conector do fitting alvo (sem Allow "
            "Slope Adjustments):".format(len(avisos)))
        for aviso in avisos:
            output.print_md("- " + aviso)
    if res['no_tee'] > 0:
        output.print_md(
            "{} cruzamento(s) dividido(s) **sem fitting** — o angulo do ramal "
            "nao serve para te e nao ha, nas routing preferences do tipo, "
            "familia de juncao com esse angulo (o Wye de 45 cobre so 45). "
            "O tubo principal ficou religado e o ramal encostado no eixo."
            .format(res['no_tee']))

    erros = res.get('fases_com_erro') or []
    if erros:
        output.print_md(
            "**{} fase(s) abortaram** (as demais rodaram normalmente): {}"
            .format(len(erros), ", ".join(erros)))

    recusas = res.get('merge_recusas') or []
    if recusas:
        output.print_md(
            "**{} par(es) ligado(s) que NAO fundiram** (continuam conectados, "
            "so nao viraram um tubo so):".format(len(recusas)))
        for eid, motivo in recusas:
            output.print_md("- {} — {}".format(_link(eid), motivo))

    derivacoes = res.get('takeoff_skips') or []
    if derivacoes:
        output.print_md("**{} derivacao(oes) nao feita(s):**".format(
            len(derivacoes)))
        for eid, motivo in derivacoes:
            output.print_md("- {} — {}".format(_link(eid), motivo))

    # Diagnostico tambem quando a execucao fez ALGUMA coisa mas deixou
    # pendencia. Antes ele so saia se nada tivesse acontecido, e voce ficava
    # sem explicacao no caso mais comum: "fez 1, recusou 5".
    houve_pendencia = bool(res['failed'] or res['no_tee'] or recusas or
                           erros or (res.get('takeoff_skips') or []) or
                           (res.get('jog_skips') or []))
    if houve_pendencia:
        _detalhe("---")
        _detalhe("### Diagnostico das pendencias")
        if DIAGNOSTICO:
            for linha in diagnose(elements):
                output.print_md(linha)

    pulados = res.get('jog_skips') or []
    if pulados:
        output.print_md("**{} desvio(s) nao feito(s):**".format(len(pulados)))
        for eid, motivo in pulados:
            output.print_md("- {} — {}".format(_link(eid), motivo))


    # Conector livre encostado em algo que ficou FORA da selecao produz o
    # mesmo sintoma de um bug — some sem explicacao. Avisar e mais util do
    # que conectar por conta propria em elemento que ninguem escolheu.
    try:
        faltantes = vizinhos_fora_da_selecao(elements)
    except Exception:
        faltantes = []
    if faltantes:
        output.print_md("---")
        output.print_md(
            "**{} conexao(oes) possivel(is) com elementos FORA da selecao.** "
            "Selecione-os junto e rode de novo:".format(len(faltantes)))
        for meu, dele, dist in sorted(faltantes, key=lambda x: x[2])[:15]:
            output.print_md("- {} esta a **{:.1f} mm** de {} (nao selecionado)"
                            .format(_link(meu), dist * 304.8, _link(dele)))

    # Registro automatico: tudo que apareceu no balao e no output vai para
    # %APPDATA%/pyRevit/PYAMBAR/ConectarEmLote/runs/, ja etiquetado com o
    # cenario da bancada quando a selecao esta nela.
    diag_log = []
    if houve_pendencia:
        try:
            diag_log = diagnose(elements)
        except Exception:
            diag_log = []
    caminho_log = None
    if REGISTRO:
        caminho_log = registrar_execucao(doc, elements, res, escolhas=escolhas,
                                         resumo=resumo, diagnostico=diag_log,
                                         vizinhos=faltantes)
    if caminho_log:
        _detalhe("_registro: {}_".format(os.path.basename(caminho_log)))

    # Correcao dos trechos que a conexao desinclinou. Fora da Transaction do
    # connect_batch: se o usuario recusar, o que ele ja tem continua valido.
    ids = res.get('slope_ids') or []
    if ids:
        achados = coletar_trechos_afetados(doc, ids)
        pergunta = descrever_trechos(achados)
        if pergunta and forms.alert(pergunta, title="Inclinacao alterada",
                                    yes=True, no=True, warn_icon=True):
            with revit.Transaction("Reinclinar Trechos"):
                rep = reinclinar_trechos(achados)
            output.print_md("**Reinclinacao:** " + formatar_resultado(rep))
            if rep['falhas']:
                for eid, motivo in rep['falhas'][:8]:
                    output.print_md("- id {}: {}".format(eid, motivo))


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        # A execucao que quebra e a que mais interessa analisar: registrar o
        # traceback antes de mostra-lo, senao o caso se perde ao fechar a aba.
        output.print_md("**Erro:** {}".format(erro))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        try:
            registrar_execucao(
                doc, SELECAO_ATUAL,
                {'fases_com_erro': ["EXCECAO: {}".format(erro)]},
                escolhas=dict(RELATO_ESCOLHA),
                resumo="(a ferramenta levantou excecao)",
                diagnostico=traceback.format_exc().split("\n"))
        except Exception:
            pass
        raise
