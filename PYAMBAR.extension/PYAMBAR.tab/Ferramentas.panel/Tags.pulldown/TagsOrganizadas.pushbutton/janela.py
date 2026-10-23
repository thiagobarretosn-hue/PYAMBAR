# -*- coding: utf-8 -*-
"""Janela da Tags Organizadas (modal: fecha ANTES de qualquer Transaction).

As linhas de categoria sao montadas em codigo a partir de `categorias.py` —
categoria nova no registro aparece aqui sem mexer no XAML. Os estilos visuais
(Interruptor, Marca, Linha, Selo*) moram no ui.xaml e sao buscados com
FindResource: a aparencia fica num lugar so (janela nova, 13/10/2026).

Unidades: a janela MOSTRA no sistema do projeto (imperial: polegada de papel
e pe; metrico: mm de papel e metro) e GUARDA sempre em mm de papel e pes, que
e o que o motor usa (pedido do Thiago, 08/10/2026: "mm no papel nao quer dizer
nada para quem trabalha em polegadas").
"""
import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import (FontWeights, GridLength, GridUnitType, HorizontalAlignment, SystemParameters,
                            TextTrimming, TextWrapping, Thickness, VerticalAlignment, Visibility)
from System.Windows.Controls import (Border, CheckBox, ColumnDefinition, ComboBox, StackPanel, TextBlock,
                                     TextBox, ToolTipService, WrapPanel)
from System.Windows.Controls import Grid

from pyrevit import forms

from Snippets._tag_regras import ler_numero, resumo_escolha
from Snippets._tag_templates import gravar as gravar_template

PATH = os.path.dirname(__file__)

#: estilo das tags unidas (chave -> texto na janela)
ESTILOS = {'ramos': u'Ramificações ortogonais', 'leque': u'Leque (um cotovelo só)'}

#: larguras das colunas da tabela de categorias (None = o resto). As MESMAS
#: do cabecalho no ui.xaml — mudar uma, mudar a outra. Fixas somam 494: com a
#: janela de 1240 a CATEGORIA fica com ~280 px (com 542 fixas e 1080 de
#: janela ficava com ~70 e o nome sumia — revisao 13/10/2026)
COLUNAS = (44, None, 190, 140, 48, 72)

#: o que a nota embaixo do arranjo diz em cada estilo
NOTA_ARRANJO = {
    'perto': u'Ombro sempre horizontal. Medido no CIQ: 45° + 90° deixa as tags mais perto; 60° é opcional.',
    'margem': u'Calibrado nos cortes do F10: chamada a 90° (60° só quando a reta cortaria um tubo), '
              u'água quente à esquerda e fria à direita.',
}

#: primeiro item do combo de templates: o que foi usado da ultima vez
ULTIMO = u'— último uso —'

#: valores especiais da coluna de seta
MANTER = u'__manter__'
NENHUMA = u'__nenhuma__'

def _num(txt, padrao, marca=None):
    """Numero > 0 do campo (aceita fracao; marca de pe/pol so a do campo), ou o padrao."""
    v = ler_numero(txt, marca)
    return padrao if v is None else v


def _fmt(v, casas=2):
    s = (u'{:.' + str(casas) + u'f}').format(v)
    return s.rstrip(u'0').rstrip(u'.') if u'.' in s else s


class Unidades(object):
    """Conversao entre o que a janela mostra e o que o config guarda."""

    def __init__(self, imperial):
        self.imperial = imperial
        self.papel = u'POL' if imperial else u'MM'
        self.modelo = u'FT' if imperial else u'M'
        # marca de unidade que cada campo aceita no fim (1/32", 25')
        self.marca_papel = u'"' if imperial else None
        self.marca_modelo = u"'" if imperial else None

    def papel_mostrar(self, mm):
        return _fmt(mm / 25.4, 3) if self.imperial else _fmt(mm, 1)

    def papel_ler(self, txt, padrao_mm):
        v = _num(txt, None, self.marca_papel)
        if v is None:
            return padrao_mm
        return v * 25.4 if self.imperial else v

    def modelo_mostrar(self, pes):
        return _fmt(pes, 1) if self.imperial else _fmt(pes * 0.3048, 2)

    def modelo_ler(self, txt, padrao_pes):
        v = _num(txt, None, self.marca_modelo)
        if v is None:
            return padrao_pes
        return v if self.imperial else v / 0.3048


class Janela(forms.WPFWindow):
    """cats: lista do registro; info: {chave: {'tipos': {nome: sym},
    'seta_atual': {nome_tipo: nome_seta}, 'contagem': texto}}; setas: [nomes];
    cfg: config salvo; imperial: unidades do projeto."""

    def __init__(self, cats, info, setas, cfg, nome_vista, imperial=True, arranjo_padrao='perto',
                 templates=None, caminho_templates=None, template_inicial=None):
        forms.WPFWindow.__init__(self, os.path.join(PATH, 'ui.xaml'))
        # cabe na tela: a 150% num monitor 1920x1080 a area util tem 672 de
        # altura e a janela de 780 nascia com a barra de titulo fora da tela
        area = SystemParameters.WorkArea
        self.Height = min(self.Height, area.Height - 8)
        self.Width = min(self.Width, area.Width - 8)
        self.MinHeight = min(self.MinHeight, self.Height)
        self.MinWidth = min(self.MinWidth, self.Width)
        self._ajustar_coluna_lista()
        # o monitor do Revit pode nao ser o principal (WorkArea e do principal)
        self.SourceInitialized += self._caber_no_monitor
        # a lista rola sempre com barra; o cabecalho desconta a largura REAL
        # dela (o tema do pyRevit 7 tem barra de 10 px, o sistema 17)
        self.grd_cabecalho.Margin = Thickness(6, 0, 6 + SystemParameters.VerticalScrollBarWidth, 6)
        self.sv_categorias.ScrollChanged += self._casar_cabecalho
        self.cats = cats
        self.info = info
        self.setas = setas
        self.cfg = cfg
        self.un = Unidades(imperial)
        self.resultado = None
        self.linhas = {}
        self.txt_vista.Text = nome_vista
        self.txt_col_x.Text = u'A CADA ({})'.format(self.un.modelo)
        self.txt_rot_espaco.Text = u'AJUSTE FINO ({} NO PAPEL)'.format(self.un.papel)

        salvo = cfg.get('categorias', {})
        for cat in cats:
            self._linha(cat, salvo.get(cat['chave'], {}))

        self._carregar_arranjo(cfg.get('arranjo', {}), arranjo_padrao)
        # o estilo decide o que aparece (margem ignora angulos e alcance)
        self.rb_perto.Checked += lambda s, e: self._arranjo_mudou()
        self.rb_margem.Checked += lambda s, e: self._arranjo_mudou()
        self.chk_refazer.Checked += lambda s, e: self._resumo()
        self.chk_refazer.Unchecked += lambda s, e: self._resumo()
        self._arranjo_mudou()
        # templates de atuacao: o primeiro item e o ultimo uso (config salvo)
        self.caminho_templates = caminho_templates
        self.templates = templates or {}
        self._popular_templates(ULTIMO)
        if template_inicial in self.templates:
            self._aplicar_template(self.templates[template_inicial])
            self._popular_templates(template_inicial)
            self._mostrar_nota(self.templates[template_inicial])
        # o 'ultimo uso' e o estado em que a janela ABRIU (ja com o template
        # inicial do primeiro uso): voltar o combo para ele desfaz o template
        # escolhido depois (antes so a nota sumia)
        self._ultimo = self._coletar()
        self.cmb_template.SelectionChanged += self._template_escolhido
        self._resumo()

    # -------------------------------------------------------------- tela
    def _ajustar_coluna_lista(self):
        """A coluna direita (320) fica sempre inteira: abaixo de ~1076 de
        janela o aperto vai para a lista, onde o titulo encurta ou quebra.
        16 moldura + 44 margens + 16 vao + 320 = 396."""
        col = self.FindName('col_lista')
        if col is not None:
            col.MinWidth = max(0.0, min(680.0, self.Width - 396.0))

    def _caber_no_monitor(self, sender, args):
        """Limita a janela a area util do monitor ONDE ela abre (o do Revit) e
        centraliza nele. SystemParameters.WorkArea e so o monitor principal:
        com o Revit num notebook a 150% como secundario, a janela nascia
        maior que a tela, com a barra de titulo fora (revisao 13/10/2026)."""
        try:
            clr.AddReference('System.Windows.Forms')
            from System.Windows.Forms import Screen
            from System.Windows.Interop import WindowInteropHelper
            from System.Windows import PresentationSource, Point
            wa = Screen.FromHandle(WindowInteropHelper(self).Handle).WorkingArea
            m = PresentationSource.FromVisual(self).CompositionTarget.TransformFromDevice
            a = m.Transform(Point(wa.Left, wa.Top))
            b = m.Transform(Point(wa.Right, wa.Bottom))
            w, h = b.X - a.X, b.Y - a.Y
            self.Width = min(self.Width, w - 8)
            self.Height = min(self.Height, h - 8)
            self.MinWidth = min(self.MinWidth, self.Width)
            self.MinHeight = min(self.MinHeight, self.Height)
            self.Left = a.X + (w - self.Width) / 2.0
            self.Top = a.Y + (h - self.Height) / 2.0
            self._ajustar_coluna_lista()
        except Exception:
            pass                # fica o limite do monitor principal (__init__)

    def _casar_cabecalho(self, sender, args):
        barra = max(0.0, sender.ActualWidth - sender.ViewportWidth)
        self.grd_cabecalho.Margin = Thickness(6, 0, 6 + barra, 6)

    # ----------------------------------------------------------- templates
    def _popular_templates(self, selecionar):
        self._sem_evento = True
        self.cmb_template.ItemsSource = [ULTIMO] + sorted(self.templates.keys())
        self.cmb_template.SelectedItem = selecionar
        self._sem_evento = False

    def _template_escolhido(self, sender, args):
        if getattr(self, '_sem_evento', False):
            return
        sel = self.cmb_template.SelectedItem
        t = self._ultimo if sel == ULTIMO else self.templates.get(sel)
        if t is not None:
            self._aplicar_template(t)
        self._mostrar_nota(t)

    def _mostrar_nota(self, t):
        """Template ainda nao conferido contra o projeto avisa (Installation Plans)."""
        nota = (t or {}).get('nota')
        self.txt_nota_template.Text = nota or u''
        self.txt_nota_template.Visibility = Visibility.Visible if nota else Visibility.Collapsed

    def _aplicar_template(self, t):
        for cat in self.cats:
            l = self.linhas[cat['chave']]
            c = t['categorias'].get(cat['chave'])
            if not l['tipo'].IsEnabled:
                continue                     # sem tipo de tag carregado no projeto
            l['chk'].IsChecked = bool(c and c.get('ativo'))
            if not c:
                continue
            if c.get('tipo') and c['tipo'] in list(l['tipo'].ItemsSource or []):
                l['tipo'].SelectedItem = c['tipo']
            seta = c.get('seta', MANTER)
            if seta == NENHUMA:
                l['seta'].SelectedIndex = 1
            elif seta in self.setas:
                l['seta'].SelectedItem = seta
            else:
                l['seta'].SelectedIndex = 0
            if l['unir'].IsEnabled:
                l['unir'].IsChecked = bool(c.get('unir', True))
            if l['x'] is not None and c.get('x_pes'):
                l['x'].Text = self.un.modelo_mostrar(c['x_pes'])
        arr = t.get('arranjo', {})
        self._carregar_arranjo(arr, arr.get('estilo_arranjo', 'perto'))
        self._arranjo_mudou()
        self._resumo()

    def salvar_template_click(self, sender, args):
        atual = self.cmb_template.SelectedItem
        nome = forms.ask_for_string(
            default=atual if atual and atual != ULTIMO else u'',
            prompt=u'Nome do template (com o nome de um que já existe, ele é substituído):',
            title=u'Salvar template de tags')
        if not nome or not nome.strip():
            return
        nome = nome.strip()
        try:
            gravar_template(self.caminho_templates, nome, self._coletar())
        except Exception as ex:
            forms.alert(u'Não gravou o template: {}'.format(ex), title=u'Tags Organizadas')
            return
        self.templates[nome] = self._coletar()
        self._popular_templates(nome)
        self._mostrar_nota(None)               # o template gravado e do usuario

    # ------------------------------------------------------------- arranjo
    def _carregar_arranjo(self, arr, arranjo_padrao):
        angs = arr.get('angulos', [90, 45])
        self.chk_a45.IsChecked = 45 in angs
        self.chk_a60.IsChecked = 60 in angs
        self.chk_refazer.IsChecked = False      # nunca vem ligado: apaga tags
        self.txt_alcance.Text = self.un.papel_mostrar(arr.get('alcance_mm', 22.0))
        self.txt_folga.Text = self.un.papel_mostrar(arr.get('folga_mm', 0.8))
        self.txt_raio.Text = self.un.papel_mostrar(arr.get('raio_mm', 8.0))
        # v0.8 tinha um maximo so ('max_pente') para os dois; o Thiago quer pente
        # de 8 e uniao de 12 (08/10/2026) — o valor antigo vira o da uniao
        if 'max_uniao' in arr:
            max_uniao, max_pente = arr['max_uniao'], arr.get('max_pente', 8)
        else:
            max_uniao, max_pente = arr.get('max_pente', 12), 8
        self.txt_max_uniao.Text = str(int(max_uniao))
        self.txt_max_pente.Text = str(int(max_pente))
        # arranjo: o padrao vem do TIPO de vista (corte -> margem), nao do config
        # — o mesmo usuario alterna entre slab passes (planta) e cortes
        if arranjo_padrao == 'margem':
            self.rb_margem.IsChecked = True
        else:
            self.rb_perto.IsChecked = True
        self.cmb_estilo.ItemsSource = [ESTILOS[k] for k in ('ramos', 'leque')]
        self.cmb_estilo.SelectedItem = ESTILOS.get(arr.get('estilo_uniao', 'ramos'), ESTILOS['ramos'])
        if arr.get('modo') == 'rapido':
            self.rb_rapido.IsChecked = True
        else:
            self.rb_completo.IsChecked = True

    def _margem(self):
        return bool(self.rb_margem.IsChecked)

    def _arranjo_mudou(self):
        """Mostra so o que vale no estilo escolhido: angulos no Perto, busca
        Completa/Rapida na Margem. Margem ignora angulos e distancia maxima
        (calibracao fixa, ver cfg_margem) — antes a janela deixava mexer
        neles sem efeito nenhum (auditoria 12/10/2026)."""
        margem = self._margem()
        self.pnl_angulos.Visibility = Visibility.Collapsed if margem else Visibility.Visible
        self.pnl_modo.Visibility = Visibility.Visible if margem else Visibility.Collapsed
        self.txt_alcance.IsEnabled = not margem
        # TextBlock desabilitado nao muda de cor e esconde o tooltip que
        # explica por que: so esmaecer
        self.txt_lbl_alcance.Opacity = 0.45 if margem else 1.0
        self.txt_nota_arranjo.Text = NOTA_ARRANJO['margem' if margem else 'perto']

    # ------------------------------------------------------------- linhas
    def _linha(self, cat, salvo):
        chave = cat['chave']
        inf = self.info.get(chave, {})
        tipos = inf.get('tipos', {})

        grade = Grid()
        for largura in COLUNAS:
            col = ColumnDefinition()
            col.Width = GridLength(largura) if largura else GridLength(1, GridUnitType.Star)
            grade.ColumnDefinitions.Add(col)

        chk = CheckBox()
        chk.Style = self.FindResource('Interruptor')
        chk.HorizontalAlignment = HorizontalAlignment.Left
        chk.ToolTip = u'Etiquetar {}'.format(cat['rotulo'].lower())
        Grid.SetColumn(chk, 0)
        grade.Children.Add(chk)

        # titulo + selo com a contagem: o selo desce para baixo do titulo
        # quando a coluna aperta (WrapPanel), em vez de esconder o nome;
        # descricao embaixo
        textos = StackPanel()
        topo = WrapPanel()
        titulo = TextBlock()
        titulo.Text = cat['rotulo']
        titulo.FontWeight = FontWeights.SemiBold
        titulo.FontSize = 13
        titulo.VerticalAlignment = VerticalAlignment.Center
        titulo.TextTrimming = TextTrimming.CharacterEllipsis
        titulo.ToolTip = cat['rotulo']
        titulo.Margin = Thickness(0, 0, 8, 0)
        topo.Children.Add(titulo)
        selo, txt_selo = self._selo(cat, inf, tipos)
        selo.Margin = Thickness(0, 1, 0, 1)
        topo.Children.Add(selo)
        desc = TextBlock()
        desc.Text = cat['descricao']
        desc.FontSize = 11
        desc.Margin = Thickness(0, 2, 8, 0)
        desc.Foreground = self.FindResource('Texto2')
        desc.TextWrapping = TextWrapping.Wrap
        textos.Children.Add(topo)
        textos.Children.Add(desc)
        Grid.SetColumn(textos, 1)
        grade.Children.Add(textos)

        cmb_tipo = ComboBox()
        cmb_tipo.Margin = Thickness(8, 0, 0, 0)
        nomes = sorted(tipos.keys())
        cmb_tipo.ItemsSource = nomes
        escolhido = salvo.get('tipo') or cat.get('tipo_padrao')
        if escolhido in tipos:
            cmb_tipo.SelectedItem = escolhido
        elif nomes:
            cmb_tipo.SelectedIndex = 0
        Grid.SetColumn(cmb_tipo, 2)
        grade.Children.Add(cmb_tipo)

        cmb_seta = ComboBox()
        cmb_seta.Margin = Thickness(8, 0, 0, 0)
        Grid.SetColumn(cmb_seta, 3)
        grade.Children.Add(cmb_seta)

        chk_unir = CheckBox()
        chk_unir.Style = self.FindResource('Marca')
        chk_unir.HorizontalAlignment = HorizontalAlignment.Center
        chk_unir.IsChecked = bool(salvo.get('unir', cat.get('unir', True)))
        chk_unir.ToolTip = (u'Uma tag por feixe de conduítes paralelos lado a lado'
                            if cat['modo'] == 'linear' else
                            u'Uma tag só para vizinhos com texto 100% igual')
        if cat['modo'] == 'tubo':
            # o script nunca une tubo (cada um traz o comprimento no texto):
            # a caixa clicavel prometia o que nao fazia
            chk_unir.IsChecked = False
            chk_unir.IsEnabled = False
            chk_unir.ToolTip = u'Tubo não une: cada tubo traz o próprio comprimento no texto.'
            ToolTipService.SetShowOnDisabled(chk_unir, True)
        Grid.SetColumn(chk_unir, 4)
        grade.Children.Add(chk_unir)

        x_box = None
        if cat['modo'] == 'linear':
            x_box = TextBox()
            x_box.Margin = Thickness(8, 0, 0, 0)
            x_box.Text = self.un.modelo_mostrar(salvo.get('x_pes', cat.get('x_pes', 25.0)))
            x_box.ToolTip = u'Uma tag no mínimo por trecho e mais uma a cada X'
            Grid.SetColumn(x_box, 5)
            grade.Children.Add(x_box)
        else:
            traco = TextBlock()
            traco.Text = u'—'
            traco.Foreground = self.FindResource('Texto3')
            traco.HorizontalAlignment = HorizontalAlignment.Center
            traco.VerticalAlignment = VerticalAlignment.Center
            Grid.SetColumn(traco, 5)
            grade.Children.Add(traco)

        borda = Border()
        borda.Style = self.FindResource('Linha')
        borda.Child = grade
        self.pnl_categorias.Children.Add(borda)

        if not tipos:
            for c in (chk, cmb_tipo, cmb_seta, chk_unir):
                c.IsEnabled = False
            chk.IsChecked = False
            chk.ToolTip = u'Nenhum tipo de tag desta categoria carregado no projeto.'
            ToolTipService.SetShowOnDisabled(chk, True)
        else:
            # categoria nova (tubo, conexao) vem DESMARCADA: rodar no CIQ nao
            # pode sair etiquetando tubo que ninguem pediu
            chk.IsChecked = bool(salvo.get('ativo', cat.get('ativo_padrao', True)))

        linha = {'chk': chk, 'tipo': cmb_tipo, 'seta': cmb_seta, 'unir': chk_unir, 'x': x_box,
                 'seta_salva': salvo.get('seta', MANTER), 'titulo': titulo}
        self.linhas[chave] = linha
        self._popular_setas(chave)
        self._realce(chave)
        cmb_tipo.SelectionChanged += lambda s, e, k=chave: self._popular_setas(k)
        cmb_tipo.SelectionChanged += lambda s, e: self._resumo()
        chk.Checked += lambda s, e, k=chave: self._ligou(k)
        chk.Unchecked += lambda s, e, k=chave: self._ligou(k)

    def _selo(self, cat, inf, tipos):
        """Selo ao lado do nome: quanto falta etiquetar (azul), nada (cinza)
        ou o aviso de que o projeto nao tem o tipo de tag (laranja)."""
        selo = Border()
        txt = TextBlock()
        txt.FontSize = 11
        txt.FontWeight = FontWeights.SemiBold
        n = int(inf.get('n') or 0)
        if not tipos:
            selo.Style = self.FindResource('SeloAlerta')
            txt.Text = u'sem tipo de tag'
            txt.Foreground = self.FindResource('Alerta')
            selo.ToolTip = u'Carregue uma família de tag desta categoria no projeto para poder etiquetar.'
        elif n:
            selo.Style = self.FindResource('SeloAzul')
            txt.Text = (u'{} trecho(s)' if cat['modo'] == 'linear' else u'{} sem tag').format(n)
            txt.Foreground = self.FindResource('Acento')
            selo.ToolTip = inf.get('contagem') or None
        else:
            selo.Style = self.FindResource('SeloCinza')
            txt.Text = u'nada a etiquetar'
            txt.Foreground = self.FindResource('Texto2')
            selo.ToolTip = inf.get('contagem') or None
        txt.TextTrimming = TextTrimming.CharacterEllipsis
        selo.Child = txt
        return selo, txt

    def _ligou(self, chave):
        self._realce(chave)
        self._resumo()

    def _realce(self, chave):
        """Categoria desligada fica com o nome apagado: o olho bate no que vai rodar."""
        l = self.linhas[chave]
        l['titulo'].Foreground = self.FindResource('Texto' if l['chk'].IsChecked else 'Texto3')

    def _popular_setas(self, chave):
        """Primeiro item mostra a seta ATUAL do tipo escolhido."""
        linha = self.linhas[chave]
        tipo = linha['tipo'].SelectedItem
        atual = self.info.get(chave, {}).get('seta_atual', {}).get(tipo, u'?')
        itens = [u'Manter ({})'.format(atual), u'Nenhuma'] + list(self.setas)
        anterior = linha['seta'].SelectedItem
        linha['seta'].ItemsSource = itens
        salva = linha.pop('seta_salva', None)
        if salva is not None:
            if salva == NENHUMA:
                linha['seta'].SelectedIndex = 1
            elif salva in self.setas:
                linha['seta'].SelectedItem = salva
            else:
                linha['seta'].SelectedIndex = 0
        elif anterior in self.setas:
            linha['seta'].SelectedItem = anterior
        else:
            linha['seta'].SelectedIndex = 0

    def _resumo(self):
        if len(self.linhas) < len(self.cats):
            return                              # janela ainda montando
        contagens = dict((k, v.get('n', 0)) for k, v in self.info.items())
        escolha = self._coletar()
        self.txt_resumo.Text = resumo_escolha(escolha, contagens, self._ja(escolha))
        # sem categoria ligada nao ha o que rodar: o botao principal apaga
        self.btn_ok.IsEnabled = any(c['ativo'] for c in escolha['categorias'].values())

    # ------------------------------------------------------------ botoes
    def cancelar_click(self, sender, args):
        self.resultado = None
        self.Close()

    def _coletar(self):
        """O que esta na janela, no formato do config/template (sem validar)."""
        cats = {}
        for cat in self.cats:
            l = self.linhas[cat['chave']]
            idx = l['seta'].SelectedIndex
            if idx <= 0:
                seta = MANTER
            elif idx == 1:
                seta = NENHUMA
            else:
                seta = l['seta'].SelectedItem
            cats[cat['chave']] = {
                'ativo': bool(l['chk'].IsChecked) and l['tipo'].SelectedItem is not None,
                'tipo': l['tipo'].SelectedItem,
                'seta': seta,
                'unir': bool(l['unir'].IsChecked),
                'x_pes': (self.un.modelo_ler(l['x'].Text, cat.get('x_pes', 25.0))
                          if l['x'] is not None else None),
            }
        angulos = [90]
        if self.chk_a45.IsChecked:
            angulos.append(45)
        if self.chk_a60.IsChecked:
            angulos.append(60)
        return {
            'categorias': cats,
            'arranjo': {
                'angulos': angulos,
                'refazer': bool(self.chk_refazer.IsChecked),
                'alcance_mm': self.un.papel_ler(self.txt_alcance.Text, 22.0),
                'folga_mm': self.un.papel_ler(self.txt_folga.Text, 0.8),
                'raio_mm': self.un.papel_ler(self.txt_raio.Text, 8.0),
                'max_pente': max(2, int(_num(self.txt_max_pente.Text, 8))),
                'max_uniao': max(2, int(_num(self.txt_max_uniao.Text, 12))),
                'estilo_uniao': 'leque' if self.cmb_estilo.SelectedItem == ESTILOS['leque'] else 'ramos',
                'estilo_arranjo': 'margem' if self._margem() else 'perto',
                'modo': 'rapido' if self.rb_rapido.IsChecked else 'completo',
            },
        }

    def _ja(self, escolha):
        """{categoria: quantos ja tem tag} para o Refazer. Trecho de conduite
        segurado por um stub etiquetado so entra se Stubs tambem for refeito."""
        stub = escolha['categorias'].get('stub', {}).get('ativo')
        return dict((k, int(v.get('ja') or 0) + (int(v.get('ja_conexao') or 0) if stub else 0))
                    for k, v in self.info.items())

    def _campos_invalidos(self):
        """Nomes dos campos com texto que nao e numero > 0. Antes o valor
        invalido virava o padrao em silencio e o campo continuava mostrando o
        que foi digitado (revisao 13/10/2026)."""
        papel, modelo = self.un.marca_papel, self.un.marca_modelo
        campos = [(self.txt_folga, u'Folga mínima entre tags', papel),
                  (self.txt_raio, u'Raio para unir tags iguais', papel),
                  (self.txt_max_uniao, u'Máx. elementos por tag unida', None),
                  (self.txt_max_pente, u'Máx. conduítes por pente', None)]
        if self.txt_alcance.IsEnabled:
            campos.append((self.txt_alcance, u'Distância máxima ao elemento', papel))
        ruins = [nome for caixa, nome, marca in campos if ler_numero(caixa.Text, marca) is None]
        for cat in self.cats:
            l = self.linhas[cat['chave']]
            if l['x'] is not None and l['chk'].IsChecked and ler_numero(l['x'].Text, modelo) is None:
                ruins.append(u'A cada — {}'.format(cat['rotulo']))
        return ruins

    def _setas_que_mudam(self, escolha):
        """[(tipo, seta atual, seta nova)] das categorias ligadas cuja ponta de
        seta vai mudar NO TIPO (vale para o projeto inteiro)."""
        mud = []
        for cat in self.cats:
            c = escolha['categorias'][cat['chave']]
            if not c['ativo'] or c['seta'] == MANTER:
                continue
            nova = u'Nenhuma' if c['seta'] == NENHUMA else c['seta']
            atual = self.info.get(cat['chave'], {}).get('seta_atual', {}).get(c['tipo'])
            if atual is not None and atual != nova:
                mud.append((c['tipo'], atual, nova))
        return mud

    def ok_click(self, sender, args):
        escolha = self._coletar()
        if not any(c['ativo'] for c in escolha['categorias'].values()):
            forms.alert(u'Marque pelo menos uma categoria.', title=u'Tags Organizadas')
            return
        ruins = self._campos_invalidos()
        if ruins:
            self.exp_ajuste.IsExpanded = True
            forms.alert(u'Valor inválido (use um número maior que zero, ex.: 0.03 ou 1/32):\n\n'
                        + u'\n'.join(u'• ' + r for r in ruins), title=u'Tags Organizadas')
            return
        mud = self._setas_que_mudam(escolha)
        if mud and not forms.alert(
                u'A ponta de seta é gravada no TIPO de tag: muda TODAS as tags desse tipo, em todas '
                u'as vistas e folhas do projeto.\n\n'
                + u'\n'.join(u'• {}: {} → {}'.format(*m) for m in mud) + u'\n\nContinuar?',
                title=u'Tags Organizadas', yes=True, no=True):
            return
        if escolha['arranjo']['refazer']:
            ja_cat = self._ja(escolha)
            ja = sum(ja_cat.get(k, 0) for k, c in escolha['categorias'].items() if c['ativo'])
            if not forms.alert(
                    u'Até {} elemento(s)/trecho(s) que já têm tag nas categorias marcadas terão a tag '
                    u'apagada e criada de novo. Tag manual em elemento que o botão não etiqueta fica. '
                    u'Ajustes manuais nas refeitas se perdem (um Ctrl+Z desfaz tudo).\n\nContinuar?'.format(ja),
                    title=u'Tags Organizadas', yes=True, no=True):
                return
        self.resultado = escolha
        self.Close()
