# -*- coding: utf-8 -*-
"""Verificação de passes de laje: coletar no Revit, perguntar, verificar.

Roda INTEIRA dentro do ExternalEvent (`ifr_evento`, pedido 'passes'): só lê
o modelo, sem Transaction. O diálogo é modal e abre ali mesmo — o Revit já
está parado esperando o evento.

O QUE COLETA (medido no CIQ-PLB-SLAB PASSES por MCP, 18/09/2026)
---------------------------------------------------------------
- Passes: acessórios de tubo do PROJETO ABERTO cujo tipo tem `Size Diameter`
  (a família WPS da AMBAR). Eixo = `LocationPoint`; faixa Z = a caixa.
- Tubos: verticais (|dir.Z| >= 0,99) do projeto e dos vínculos marcados, já
  em coordenadas do projeto (`GetTotalTransform`).
- Pisos (v1.6): do projeto e de todos os vínculos carregados — topo da caixa
  e `FLOOR_ATTR_THICKNESS_PARAM` — para a espessura de laje sem passe. O CIQ
  não tem piso em nenhum vínculo; esse caminho NÃO foi conferido em modelo.
- Lajes: os níveis do projeto; espessura por laje em
  `Snippets._passes_laje.espessura_por_nivel`.

A regra está em `Snippets._passes_laje` — aqui não se decide nada.
"""
import os
from datetime import datetime

import clr
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')

from System.Windows import Thickness
from System.Windows.Controls import CheckBox

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FamilyInstance,
    FilteredElementCollector,
    Level,
    LocationCurve,
    LocationPoint,
    RevitLinkInstance,
    XYZ,
)

from pyrevit.forms import WPFWindow

from Snippets._comprimento_texto import POLEGADAS, texto_para_pes
from Snippets._passes_laje import (
    ESP_PADRAO,
    ESP_PASSES,
    ESP_PISO,
    INVENTARIO,
    PADRAO,
    TODAS_AS_REGRAS,
    eh_vertical,
    espessura_por_nivel,
    lajes_com_passe,
    montar_relatorio,
    polegadas_texto,
    resumo,
    verificar,
)

import ifr_disco

SCRIPT_DIR = os.path.dirname(__file__)
ESTE_PROJETO = u'(este projeto)'
ORIGEM_DA_ESPESSURA = {ESP_PASSES: u'dos passes', ESP_PISO: u'do piso',
                       ESP_PADRAO: u'padrão'}


def _id(eid):
    return int(eid.Value if hasattr(eid, 'Value') else eid.IntegerValue)


def _nome(elemento):
    try:
        return elemento.Name
    except Exception:
        return ''


def _polegadas(parametro):
    return parametro.AsDouble() * 12.0 if parametro is not None else None


def _vinculos(documento):
    """[(nome do arquivo, doc, transform)] — uma instância por arquivo."""
    vistos = set()
    resultado = []
    for instancia in FilteredElementCollector(documento) \
            .OfClass(RevitLinkInstance):
        doc_vinculo = instancia.GetLinkDocument()
        nome = _nome(instancia).split(' : ')[0].strip()
        if doc_vinculo is None or nome in vistos:
            continue
        vistos.add(nome)
        resultado.append((nome, doc_vinculo, instancia.GetTotalTransform()))
    return resultado


# ------------------------------------------------------------------ coleta

def coletar_passes(documento):
    passes = []
    for fi in FilteredElementCollector(documento) \
            .OfCategory(BuiltInCategory.OST_PipeAccessory) \
            .WhereElementIsNotElementType():
        if not isinstance(fi, FamilyInstance):
            continue
        diametro = fi.Symbol.LookupParameter('Size Diameter')
        local = fi.Location
        caixa = fi.get_BoundingBox(None)
        if diametro is None or not isinstance(local, LocationPoint) or \
                caixa is None:
            continue
        passes.append({
            'id': _id(fi.Id), 'tipo': _nome(fi.Symbol),
            'categoria': fi.Category.Name if fi.Category else u'Passe',
            'diametro': diametro.AsDouble() * 12.0,
            'x': local.Point.X, 'y': local.Point.Y,
            'zmin': caixa.Min.Z, 'zmax': caixa.Max.Z,
        })
    return passes


def _tubos_do_documento(documento, vinculo, transform):
    tubos = []
    for tubo in FilteredElementCollector(documento) \
            .OfCategory(BuiltInCategory.OST_PipeCurves) \
            .WhereElementIsNotElementType():
        local = tubo.Location
        if not isinstance(local, LocationCurve):
            continue
        a = local.Curve.GetEndPoint(0)
        b = local.Curve.GetEndPoint(1)
        if transform is not None:
            a, b = transform.OfPoint(a), transform.OfPoint(b)
        p0, p1 = (a.X, a.Y, a.Z), (b.X, b.Y, b.Z)
        if not eh_vertical(p0, p1):
            continue
        nominal = _polegadas(tubo.get_Parameter(
            BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)) or 0.0
        externo = _polegadas(tubo.get_Parameter(
            BuiltInParameter.RBS_PIPE_OUTER_DIAMETER)) or nominal
        tamanho = tubo.get_Parameter(BuiltInParameter.RBS_CALCULATED_SIZE)
        tubos.append({
            'vinculo': vinculo, 'id': _id(tubo.Id), 'p0': p0, 'p1': p1,
            'nominal': nominal, 'externo': externo,
            'categoria': tubo.Category.Name if tubo.Category else u'Tubo',
            'descricao': u'{} {}'.format(
                _nome(tubo), tamanho.AsString() if tamanho else '').strip(),
        })
    return tubos


def coletar_tubos(documento):
    """{origem: [tubo vertical]} — '' = este projeto; vínculo pelo arquivo."""
    por_origem = {}
    locais = _tubos_do_documento(documento, '', None)
    if locais:
        por_origem[''] = locais
    for nome, doc_vinculo, transform in _vinculos(documento):
        tubos = _tubos_do_documento(doc_vinculo, nome, transform)
        if tubos:
            por_origem[nome] = tubos
    return por_origem


def _pisos_do_documento(documento, transform):
    pisos = []
    for piso in FilteredElementCollector(documento) \
            .OfCategory(BuiltInCategory.OST_Floors) \
            .WhereElementIsNotElementType():
        caixa = piso.get_BoundingBox(None)
        espessura = _polegadas(piso.get_Parameter(
            BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM))
        if caixa is None or not espessura:
            continue
        topo = caixa.Max.Z
        if transform is not None:
            topo = transform.OfPoint(XYZ(caixa.Max.X, caixa.Max.Y,
                                         caixa.Max.Z)).Z
        pisos.append({'topo': topo, 'espessura': espessura})
    return pisos


def coletar_pisos(documento):
    """Pisos do projeto e de todos os vínculos carregados (topo, espessura)."""
    pisos = _pisos_do_documento(documento, None)
    for _, doc_vinculo, transform in _vinculos(documento):
        pisos.extend(_pisos_do_documento(doc_vinculo, transform))
    return pisos


def coletar_niveis(documento):
    return sorted(({'nivel': _nome(n), 'topo': n.Elevation}
                   for n in FilteredElementCollector(documento)
                   .OfClass(Level)), key=lambda n: n['topo'])


# ----------------------------------------------------------------- diálogo

class DialogoPasses(WPFWindow):
    """Lajes, origens dos tubos, medidas e regras. `resultado` = config."""

    def __init__(self, niveis, passes, tubos_por_origem, espessuras, salvo):
        WPFWindow.__init__(self, os.path.join(SCRIPT_DIR, 'passes.xaml'))
        self.resultado = None
        sugeridas = set(salvo.get('lajes') or lajes_com_passe(passes, niveis))
        self._lajes = []
        for nivel in niveis:
            espessura, origem, n = espessuras[nivel['nivel']]
            detalhe = u'{} passes · '.format(n) if n else u''
            self._lajes.append((dict(nivel, espessura=espessura), self._caixa(
                self.LajesPanel, u'{}  ({}laje {} {})'.format(
                    nivel['nivel'], detalhe, polegadas_texto(espessura),
                    ORIGEM_DA_ESPESSURA[origem]),
                nivel['nivel'] in sugeridas)))

        marcados = salvo.get('vinculos')
        self._origens = [
            (origem, self._caixa(
                self.VinculosPanel, u'{}  ({})'.format(
                    origem or ESTE_PROJETO, len(tubos_por_origem[origem])),
                origem in marcados if marcados is not None else True))
            for origem in sorted(tubos_por_origem)]

        ligadas = salvo.get('regras')
        self._regras = []
        for regra in TODAS_AS_REGRAS:
            if ligadas is not None:
                marcada = regra in ligadas
            else:
                # o inventário nasce DESLIGADO: numa laje com 400 passes são
                # 400 linhas, e quem abre quer ver o que está errado
                marcada = regra != INVENTARIO
            texto = regra
            if regra == INVENTARIO:
                texto = u'{}  (lista para navegar, não acusa erro)'.format(
                    regra)
            self._regras.append((regra, self._caixa(self.RegrasPanel, texto,
                                                    marcada)))

        self.ToleranciaBox.Text = polegadas_texto(
            salvo.get('tolerancia', PADRAO['tolerancia']))
        self.RaioBox.Text = polegadas_texto(salvo.get('raio', PADRAO['raio']))

    def _caixa(self, painel, texto, marcada):
        caixa = CheckBox()
        caixa.Content = texto
        caixa.IsChecked = marcada
        caixa.Margin = Thickness(0, 2, 0, 2)
        painel.Children.Add(caixa)
        return caixa

    def _medida(self, caixa, nome):
        pes = texto_para_pes(caixa.Text, POLEGADAS)
        if pes is None or pes <= 0:
            raise ValueError(u'{}: "{}" não é uma medida (ex.: 1/4", 0.25, '
                             u'12")'.format(nome, caixa.Text))
        return pes * 12.0

    def ao_verificar(self, sender, args):
        try:
            config = {
                'lajes': [n for n, c in self._lajes if c.IsChecked],
                'vinculos': [o for o, c in self._origens if c.IsChecked],
                'regras': [r for r, c in self._regras if c.IsChecked],
                'tolerancia': self._medida(self.ToleranciaBox, u'Tolerância'),
                'raio': self._medida(self.RaioBox, u'Raio'),
            }
        except ValueError as erro:
            self.ErroLabel.Text = str(erro)
            return
        for chave, falta in (('lajes', u'uma laje'),
                             ('vinculos', u'um modelo com tubos'),
                             ('regras', u'uma regra')):
            if not config[chave]:
                self.ErroLabel.Text = u'Marque ao menos {}.'.format(falta)
                return
        self.resultado = config
        self.Close()

    def ao_cancelar(self, sender, args):
        self.Close()


# ---------------------------------------------------------------- executar

def executar(uiapp, janela):
    """Coleta, pergunta, verifica, grava e abre na janela. -> texto p/ rodapé."""
    documento = uiapp.ActiveUIDocument.Document
    passes = coletar_passes(documento)
    niveis = coletar_niveis(documento)
    tubos_por_origem = coletar_tubos(documento)
    if not tubos_por_origem:
        return u'Nenhum tubo vertical no projeto nem nos vínculos carregados.'
    espessuras = espessura_por_nivel(niveis, passes, coletar_pisos(documento))

    salvo = janela.prefs.get('passes') or {}
    dialogo = DialogoPasses(niveis, passes, tubos_por_origem, espessuras,
                            salvo)
    dialogo.ShowDialog()
    config = dialogo.resultado
    if config is None:
        return u'Verificação de passes cancelada.'

    lajes = config['lajes']
    tubos = []
    for origem in config['vinculos']:
        tubos.extend(tubos_por_origem.get(origem, []))
    achados = verificar(passes, tubos, lajes, config['tolerancia'],
                        config['raio'], config['regras'])

    parametros = {
        'tolerancia': config['tolerancia'], 'raio': config['raio'],
        'regras': config['regras'],
        'espessuras': dict((l['nivel'], l['espessura']) for l in lajes),
        'vinculos': [o or ESTE_PROJETO for o in config['vinculos']],
        'passes': len(passes), 'tubos': len(tubos),
    }
    modelo = janela.caminho_do_modelo()
    relatorio = montar_relatorio(achados, modelo,
                                 datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                                 lajes, parametros)
    caminho = ifr_disco.caminho_relatorio_passes(modelo, documento.Title)
    # verificar de novo, depois de corrigir o modelo, é o uso NORMAL: o
    # relatório é sempre o mesmo arquivo, reescrito. O que muda é o que a
    # ferramenta diz depois (v2.3, Thiago 25/09/2026: "faltou um aviso
    # falando que o relatório foi atualizado").
    ja_existia = os.path.exists(caminho)
    ifr_disco.gravar_relatorio(caminho, relatorio)

    janela.prefs['passes'] = {
        'lajes': [l['nivel'] for l in lajes],
        'vinculos': config['vinculos'], 'regras': config['regras'],
        'tolerancia': config['tolerancia'], 'raio': config['raio'],
    }
    ifr_disco.gravar_preferencias(janela.prefs)
    janela.carregar(caminho)
    partes = [u'{} {}'.format(n, r.lower()) for r, n in resumo(achados)]
    achado = u', '.join(partes) if partes else u'nada a apontar'
    quando = datetime.now().strftime('%H:%M')
    if not ja_existia:
        janela.NovidadesLabel.Text = u'Relatório criado às {}.'.format(quando)
        return u'Verificação feita às {}: {} passe(s), {} tubo(s) em {} ' \
               u'laje(s) — {}.'.format(quando, len(passes), len(tubos),
                                       len(lajes), achado)
    # re-verificação: o que MUDOU desde a anterior é a notícia
    delta = getattr(janela, '_delta', {}) or {}
    mudou = []
    if delta.get('novos'):
        mudou.append(u'{} novo(s)'.format(delta['novos']))
    if delta.get('sairam'):
        mudou.append(u'{} sumiu(ram) do modelo'.format(delta['sairam']))
    if delta.get('voltaram'):
        # o que voltou depois de resolvido foi reaberto pela sincronização
        mudou.append(u'{} voltou(aram) a aparecer'.format(delta['voltaram']))
    resumo_mudanca = u', '.join(mudou) if mudou else u'nada mudou desde a ' \
                                                     u'verificação anterior'
    janela.NovidadesLabel.Text = u'Relatório REFEITO às {} — {}.'.format(
        quando, resumo_mudanca)
    return u'Relatório de passes ATUALIZADO às {} ({} passe(s), {} tubo(s) ' \
           u'em {} laje(s)): {} — agora {}.'.format(
               quando, len(passes), len(tubos), len(lajes), resumo_mudanca,
               achado)
