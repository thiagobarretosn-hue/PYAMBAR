# -*- coding: utf-8 -*-
"""Botao de UM template da Tags Organizadas, num menu curto (23/10/2026).

Tag Installation Plans (plantas) e Tag Wall FAC (cortes) sao o mesmo
codigo: o menu mostra so o TIPO de tag de cada categoria ativa no template e
Executar; o resto e o template. O motor e o script.py da Tags Organizadas,
carregado como modulo (main() dela nao roda) — nada duplicado.

Saida silenciosa (regra da distribuicao): deu certo = balao com o placar;
deu errado = balao curto + traceback em %APPDATA%/pyRevit/PYAMBAR/<pasta>/
erros.log. O botao chama `rodar(...)` dentro de try e `falhou(...)` no except.
"""
import io
import json
import os
import sys
import time
import traceback
import types

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import GridLength, Thickness, VerticalAlignment
from System.Windows.Controls import ComboBox, RowDefinition, TextBlock
from System.Windows.Controls import Grid

from Autodesk.Revit.DB import TransactionGroup

from pyrevit import forms

PASTA = os.path.dirname(os.path.abspath(__file__))


class Botao(object):
    """titulo: nome no balao e no menu; pasta_appdata: subpasta em
    %APPDATA%/pyRevit/PYAMBAR (config e erros.log)."""

    def __init__(self, titulo, pasta_appdata):
        self.titulo = titulo
        self.dir = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', pasta_appdata)
        self.config = os.path.join(self.dir, 'config.json')
        self.erros = os.path.join(self.dir, 'erros.log')
        self.pasta_appdata = pasta_appdata

    def load_config(self):
        if os.path.exists(self.config):
            try:
                with io.open(self.config, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, data):
        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
        with io.open(self.config, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))

    def balao(self, texto):
        try:
            forms.show_balloon(self.titulo, texto)
        except Exception:
            pass

    def falhou(self, erro):
        """Balao curto; o detalhe vai para o erros.log (nunca para a tela)."""
        try:
            if not os.path.isdir(self.dir):
                os.makedirs(self.dir)
            with io.open(self.erros, 'a', encoding='utf-8') as f:
                f.write(u'{} {}\n{}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'), erro, traceback.format_exc()))
            self.balao(u'Não deu certo: {} — detalhe em {}\\erros.log'.format(erro, self.pasta_appdata))
        except Exception:
            self.balao(u'Não deu certo: {}'.format(erro))


def carregar_tags_organizadas(globais_do_botao):
    """Executa o script.py da Tags Organizadas num modulo novo, SEM rodar o
    main() dela (__name__ != '__main__'). O proprio script descarta e
    reimporta coleta/motor do disco a cada carga."""
    if PASTA not in sys.path:
        sys.path.insert(0, PASTA)
    caminho = os.path.join(PASTA, 'script.py')
    with io.open(caminho, 'r', encoding='utf-8') as f:
        fonte = f.read()
    modulo = types.ModuleType('tags_organizadas_motor')
    espaco = modulo.__dict__
    for nome, valor in globais_do_botao.items():
        # __revit__ e afins que o pyRevit pos no escopo do botao
        if nome.startswith('__') and nome.endswith('__') and nome not in ('__name__', '__file__', '__doc__'):
            espaco[nome] = valor
    espaco['__name__'] = 'tags_organizadas_motor'
    espaco['__file__'] = caminho
    exec(compile(fonte, caminho, 'exec'), espaco)
    return modulo


class Menu(forms.WPFWindow):
    """linhas: [(chave, rotulo, [nomes de tipo], nome escolhido)]."""

    def __init__(self, titulo, nome_vista, linhas, refazer, texto_refazer, setas=(), seta=None):
        """setas: [(valor, texto)] da caixa de seta (vale para todas as tags);
        seta: valor escolhido da ultima vez."""
        forms.WPFWindow.__init__(self, os.path.join(PASTA, 'menu.xaml'))
        self.Title = titulo
        self.txt_titulo.Text = titulo
        self.txt_vista.Text = nome_vista
        self.txt_refazer.Text = texto_refazer
        self.chk_refazer.IsChecked = refazer
        self.valores_seta = [v for v, _t in setas]
        for _v, texto in setas:
            self.cmb_seta.Items.Add(texto)
        if self.valores_seta:
            self.cmb_seta.SelectedIndex = self.valores_seta.index(seta) if seta in self.valores_seta else 0
        self.combos = {}
        self.resultado = None
        for i, (chave, rotulo, nomes, atual) in enumerate(linhas):
            self.grd_tipos.RowDefinitions.Add(RowDefinition(Height=GridLength.Auto))
            txt = TextBlock(Text=rotulo, VerticalAlignment=VerticalAlignment.Center, Margin=Thickness(0, 4, 8, 4))
            Grid.SetRow(txt, i)
            Grid.SetColumn(txt, 0)
            cmb = ComboBox(Margin=Thickness(0, 4, 0, 4), MinHeight=28)
            for n in nomes:
                cmb.Items.Add(n)
            if atual in nomes:
                cmb.SelectedItem = atual
            elif nomes:
                cmb.SelectedIndex = 0
            Grid.SetRow(cmb, i)
            Grid.SetColumn(cmb, 1)
            self.grd_tipos.Children.Add(txt)
            self.grd_tipos.Children.Add(cmb)
            self.combos[chave] = cmb
        self.btn_executar.IsEnabled = bool(linhas)

    def executar_click(self, sender, args):
        i = self.cmb_seta.SelectedIndex
        self.resultado = {'tipos': dict((k, c.SelectedItem) for k, c in self.combos.items() if c.SelectedItem),
                          'refazer': bool(self.chk_refazer.IsChecked),
                          'seta': self.valores_seta[i] if 0 <= i < len(self.valores_seta) else None}
        self.Close()

    def cancelar_click(self, sender, args):
        self.resultado = None
        self.Close()


def rodar(botao, doc, template, vista_ok, aviso_vista, globais_do_botao,
          texto_refazer=u'Apagar e refazer as tags que o botão coloca', rotulos=None):
    """vista_ok(view) -> bool; aviso_vista: balao quando a vista nao serve.
    rotulos: {chave: nome} no lugar do rotulo da categoria (no corte, 'passe'
    e 'Acessórios de tubo' — Thiago, 23/10/2026)."""
    rotulos = rotulos or {}
    view = doc.ActiveView
    if view is None or view.IsTemplate or not vista_ok(view):
        botao.balao(aviso_vista)
        return
    tags = carregar_tags_organizadas(globais_do_botao)
    modelo = tags.tag_templates.todos(tags._APPDATA_TEMPLATES)[template]
    # so os TIPOS de tag (rapido): a coleta da vista roda no executar
    info = dict((c['chave'], {'tipos': tags.coleta.tipos_de_tag(doc, c['tag_bic'])}) for c in tags.reg.CATEGORIAS)
    cfg = botao.load_config()
    salvos = cfg.get('tipos') or {}
    linhas = []
    for c in tags.reg.CATEGORIAS:
        tc = modelo['categorias'].get(c['chave']) or {}
        if not tc.get('ativo'):
            continue
        nomes = sorted(info[c['chave']]['tipos'])
        if not nomes:
            continue
        atual = salvos.get(c['chave']) or tc.get('tipo') or c.get('tipo_padrao')
        linhas.append((c['chave'], rotulos.get(c['chave'], c['rotulo']), nomes, atual))
    if not linhas:
        botao.balao(u'Nenhuma família de tag carregada para as categorias do template.')
        return

    # seta: uma escolha para TODAS as tags (Thiago, 23/10/2026); grava no
    # proprio tipo de tag, como a coluna de seta da Tags Organizadas
    setas = tags.coleta.listar_setas(doc)
    opcoes_seta = ([(tags.MANTER, u'Manter a de cada tipo'), (tags.NENHUMA, u'Sem seta')]
                   + [(n, n) for n, _i in setas])
    menu = Menu(botao.titulo, u'{}  ·  escala 1:{}'.format(view.Name, view.Scale), linhas,
                cfg.get('refazer', True), texto_refazer, opcoes_seta, cfg.get('seta'))
    menu.ShowDialog()
    escolha_menu = menu.resultado
    if not escolha_menu:
        return
    botao.save_config(escolha_menu)

    # depois de fechar a janela (modal): so agora as Transactions
    R, U = view.RightDirection, view.UpDirection
    del tags.coleta.AVISOS[:]
    escolha = tags._escolha_do_template(info, template, escolha_menu['tipos'])
    escolha['arranjo']['refazer'] = escolha_menu['refazer']
    if escolha_menu.get('seta'):
        for esc in escolha['categorias'].values():
            esc['seta'] = escolha_menu['seta']
    # o executar refaz o levantamento com 'refazer' ou na trama; so sem os
    # dois ele usa o daqui (pula o que ja tem tag)
    dados = None
    if not escolha['arranjo']['refazer'] and not escolha['arranjo'].get('so_trama'):
        _info, dados = tags.levantar(view, R, U)
    # estilo margem (cortes): alinhamento do texto de cada tipo. Abre a
    # familia so para ler e o EditFamily nao roda com o grupo aberto
    alinhamentos = {}
    if escolha['arranjo'].get('estilo_arranjo') == 'margem':
        for c in tags.reg.CATEGORIAS:
            esc = escolha['categorias'][c['chave']]
            if esc['ativo']:
                alinhamentos[c['chave']] = tags.coleta.alinhamento_do_texto(
                    doc, info[c['chave']]['tipos'][esc['tipo']])
    grupo = TransactionGroup(doc, botao.titulo)
    grupo.Start()
    try:
        r = tags.executar(view, R, U, info, dados, setas, escolha, alinhamentos, auto=True) or {}
    except tags.Cancelado:
        if grupo.HasStarted() and not grupo.HasEnded():
            grupo.RollBack()
        botao.balao(u'Cancelado — a vista ficou como estava.')
        return
    except Exception:
        if grupo.HasStarted() and not grupo.HasEnded():
            grupo.RollBack()
        raise
    if grupo.HasStarted() and not grupo.HasEnded():
        grupo.Assimilate()

    if r.get('nada'):
        botao.balao(u'Nada a etiquetar nesta vista.')
        return
    por = r.get('por_categoria') or {}
    partes = [u'{} {}'.format(n, rotulos.get(k, tags.reg.por_chave(k)['rotulo']).lower())
              for k, n in sorted(por.items())]
    texto = u'{} tags criadas ({}).'.format(r.get('criadas', 0), u', '.join(partes))
    aud = r.get('auditoria') or {}
    if aud.get('com_conflito'):
        texto += u' {} para revisar.'.format(aud['com_conflito'])
    if r.get('sem_lugar'):
        texto += u' {} sem lugar.'.format(len(r['sem_lugar']))
    botao.balao(texto)
