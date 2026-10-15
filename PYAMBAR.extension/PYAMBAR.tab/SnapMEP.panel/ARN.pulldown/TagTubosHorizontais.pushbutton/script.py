# -*- coding: utf-8 -*-
"""
Tag Tubos Horizontais
Coloca a tag de cada tubo horizontal da vista ativa, na posicao que o Thiago
usa — medida em 62 tags reais das aranhas, nao arbitrada.

REGRA (ver lib/Snippets/_tag_layout.py):
  - a tag vai para o lado OPOSTO ao centro da rede (bateu em 82% das reais)
  - a distancia depende do comprimento do tubo: curto afasta mais
  - fica no meio do tubo, com leader

Idempotente: tubo que ja tem tag nesta vista e pulado. Na ARN TYP#V os 7 de 7
tubos horizontais ja estavam taggeados — rodar nao pode duplicar.

v1.1 (10/09/2026) — pelo Fluxo ARN, marca na VISTA DE DETALHE que o painel
passa; e o tipo de tag vem da config, sem perguntar. So pergunta quando o
tipo configurado nao existe no projeto.

VERSAO: 1.1
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Tag Tubos\nHorizontais"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.1"

import os
import sys
import traceback

from Autodesk.Revit.DB import (
    BuiltInCategory,
    Element,
    FamilySymbol,
    FilteredElementCollector,
    IndependentTag,
    Reference,
    TagOrientation,
    XYZ,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script

LIB_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from Snippets._tag_layout import (
    centroide,
    eh_horizontal,
    posicao_da_tag,
)
from Snippets._aranha_doc_config import TAG, carregar, casa_tag

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

#: Tipo de tag usado nas aranhas. So o padrao — a ferramenta pergunta.
TAG_PADRAO = 'PIPE - Desc/Size/Segment - ( 4mm)'

#: Escala em que as 62 tags foram medidas. Em outra escala a distancia e
#: reescalada para manter a MESMA aparencia no papel — isso e extrapolacao
#: geometrica, nao medicao, e a ferramenta avisa quando acontece.
ESCALA_DE_REFERENCIA = 12


def get_name(element):
    try:
        return Element.Name.GetValue(element)
    except Exception:
        return None


def pontas(pipe):
    """(p0, p1) como tuplas, ou None se o tubo nao tem curva."""
    loc = pipe.Location
    if loc is None or not hasattr(loc, 'Curve'):
        return None
    curva = loc.Curve
    a = curva.GetEndPoint(0)
    b = curva.GetEndPoint(1)
    return (a.X, a.Y, a.Z), (b.X, b.Y, b.Z)


def coletar_tipos_de_tag():
    """FamilySymbols da categoria Pipe Tags.

    Filtra por OfCategory em vez de comparar `Category.Id.Value` com o enum:
    converter BuiltInCategory para int e um atrito desnecessario em IronPython.
    """
    return list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_PipeTags)
        .OfClass(FamilySymbol)
        .ToElements()
    )


def tubos_ja_taggeados(view):
    """Ids dos elementos que ja tem tag nesta vista."""
    marcados = set()
    for tag in (FilteredElementCollector(doc, view.Id)
                .OfClass(IndependentTag)
                .WhereElementIsNotElementType()
                .ToElements()):
        try:
            for eid in tag.GetTaggedLocalElementIds():
                marcados.add(eid.Value)
        except Exception as erro:
            output.print_md(
                '- tag {} não respondeu quais elementos marca: {}'.format(
                    tag.Id, erro))
    return marcados


def vista_de_trabalho():
    """A vista de detalhe que o Fluxo ARN passou, ou a ativa.

    Desde a v2.4 do painel a chamada de detalhe vem ANTES das cotas e tags
    ("e melhor organizar na vista de detalhe" — o Thiago, 10/09/2026), e ela
    nao precisa estar aberta para receber o trabalho. Solta, a ferramenta
    trabalha na vista ativa, como sempre.
    """
    vid = globals().get('__arn_vista__')
    if vid is not None:
        vista = doc.GetElement(vid)
        if vista is not None:
            return vista
    return doc.ActiveView


def main():
    try:
        view = vista_de_trabalho()
        if view.IsTemplate:
            forms.alert('Rode numa vista, não num template.',
                        title='Tag Tubos Horizontais')
            return

        # ------------------------------------------------ o que ha na vista
        tubos = (FilteredElementCollector(doc, view.Id)
                 .OfClass(Pipe)
                 .WhereElementIsNotElementType()
                 .ToElements())
        if not tubos:
            forms.alert('Nenhum tubo visível nesta vista.',
                        title='Tag Tubos Horizontais')
            return

        horizontais = []
        for pipe in tubos:
            par = pontas(pipe)
            if par and eh_horizontal(par[0], par[1]):
                horizontais.append((pipe, par[0], par[1]))

        if not horizontais:
            forms.alert(
                'Há {} tubo(s) na vista, mas nenhum horizontal.\n\n'
                'Subidas de aparelho não entram nesta regra.'.format(
                    len(tubos)),
                title='Tag Tubos Horizontais')
            return

        ja_tem = tubos_ja_taggeados(view)
        pendentes = [t for t in horizontais if t[0].Id.Value not in ja_tem]

        if not pendentes:
            forms.alert(
                'Os {} tubos horizontais desta vista já tem tag.\n\n'
                'Nada a fazer.'.format(len(horizontais)),
                title='Tag Tubos Horizontais')
            return

        # ------------------------------------------------ tipo de tag
        tipos = coletar_tipos_de_tag()
        if not tipos:
            forms.alert('Nenhuma família de tag de tubo carregada no projeto.',
                        title='Tag Tubos Horizontais', warn_icon=True)
            return

        # a config do Fluxo ARN decide; so pergunta se ela nao casar
        config, erro_config = carregar()
        tipo_tag = None
        for t in tipos:
            if casa_tag(t.FamilyName, get_name(t), config[TAG]):
                tipo_tag = t
                break
        da_config = tipo_tag is not None

        if tipo_tag is None:
            nomes = sorted(set(get_name(t) or '?' for t in tipos))
            # o tipo das aranhas primeiro na lista — SelectFromList nao tem
            # pre-selecao, entao a ordem e o unico jeito de dar a dica
            if TAG_PADRAO in nomes:
                nomes.remove(TAG_PADRAO)
                nomes.insert(0, TAG_PADRAO)

            escolhido = forms.SelectFromList.show(
                nomes,
                title='Tipo de tag ({} tubo(s) sem tag)'.format(
                    len(pendentes)),
                multiselect=False,
                button_name='Usar este',
            )
            if not escolhido:
                return

            for t in tipos:
                if get_name(t) == escolhido:
                    tipo_tag = t
                    break
            if tipo_tag is None:
                forms.alert('Tipo de tag não resolvido.', warn_icon=True)
                return

        # ------------------------------------------------ centro da rede
        # O centro sai de TODOS os horizontais da vista, nao so dos pendentes:
        # senao o lado muda conforme o que ja foi taggeado antes.
        centro = centroide([
            ((p0[0] + p1[0]) / 2.0,
             (p0[1] + p1[1]) / 2.0,
             (p0[2] + p1[2]) / 2.0)
            for _, p0, p1 in horizontais
        ])

        fator = float(view.Scale) / ESCALA_DE_REFERENCIA

        # ------------------------------------------------ criar
        criadas = []
        falhas = []
        with revit.Transaction('Tag tubos horizontais'):
            if not tipo_tag.IsActive:
                tipo_tag.Activate()
                doc.Regenerate()

            for pipe, p0, p1 in pendentes:
                nome = get_name(pipe) or str(pipe.Id)
                alvo = posicao_da_tag(p0, p1, centro)
                if alvo is None:
                    falhas.append((nome, 'tubo degenerado, sem direção'))
                    continue

                # reescala o afastamento mantendo o meio do tubo no lugar
                meio_x = (p0[0] + p1[0]) / 2.0
                meio_y = (p0[1] + p1[1]) / 2.0
                ponto = XYZ(
                    meio_x + (alvo[0] - meio_x) * fator,
                    meio_y + (alvo[1] - meio_y) * fator,
                    alvo[2],
                )

                try:
                    tag = IndependentTag.Create(
                        doc, tipo_tag.Id, view.Id, Reference(pipe),
                        True, TagOrientation.Horizontal, ponto)
                except Exception as erro:
                    falhas.append((nome, str(erro)))
                    continue

                # IndependentTag.Create NAO respeita o ponto pedido — medido:
                # desvio de 0,15 a 0,31 ft. Setar depois zera o desvio.
                try:
                    tag.TagHeadPosition = ponto
                except Exception as erro:
                    falhas.append((nome, 'criada, mas não reposicionou: {}'
                                   .format(erro)))
                criadas.append((nome, tag))

        # ------------------------------------------------ relatorio
        output.print_md('## Tag Tubos Horizontais')
        output.print_md(
            'Vista **{}** · escala 1:{} · {} tubo(s) horizontal(is), '
            '{} já tinha(m) tag.'.format(
                get_name(view), view.Scale, len(horizontais),
                len(horizontais) - len(pendentes)))

        if abs(fator - 1.0) > 0.01:
            output.print_md(
                '**Atenção:** as distâncias foram medidas em vistas escala '
                '1:{}. Aqui a escala e 1:{}, então o afastamento foi '
                'multiplicado por {:.2f} para manter a mesma aparencia no '
                'papel. Isso e geometria, não medição — confira o '
                'resultado.'.format(
                    ESCALA_DE_REFERENCIA, view.Scale, fator))

        output.print_md('Tipo de tag: **{} : {}**{}.'.format(
            tipo_tag.FamilyName, get_name(tipo_tag),
            ' (da configuração)' if da_config else
            ' (escolhido na lista — o da configuração, "{}", não existe '
            'neste projeto)'.format(config[TAG])))
        if erro_config:
            output.print_md('- {}'.format(erro_config))

        output.print_md('**Tags criadas: {}**'.format(len(criadas)))
        for nome, tag in criadas:
            output.print_md('- {} · {}'.format(
                output.linkify(tag.Id), nome))

        if falhas:
            output.print_md('**Falhas ({}):**'.format(len(falhas)))
            for nome, motivo in falhas:
                output.print_md('- {} — {}'.format(nome, motivo))

        output.print_md(
            'A posição vem da regra medida (lado oposto ao centro da rede, '
            'afastamento por comprimento do tubo). Onde duas tags se '
            'encostarem, mova a mão — a ferramenta não detecta colisão entre '
            'textos.')

    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md('**Erro:** {}'.format(str(e)))
        output.print_md('```\n{}\n```'.format(traceback.format_exc()))


if __name__ == '__main__':
    main()
