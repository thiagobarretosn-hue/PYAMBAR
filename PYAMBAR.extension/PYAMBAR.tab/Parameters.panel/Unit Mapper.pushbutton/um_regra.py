# -*- coding: utf-8 -*-
"""Editor de UMA regra de parametros — janela modal sobre o Unit Mapper.

Linhas montadas em codigo (o mesmo padrao dos "Parametros fixos"): cada
condicao e [campo] [parametro] [operador] [valor] [ate] [x], cada acao e
[parametro] [acao] [valor] [x]. O que a regra faz aparece por extenso embaixo,
atualizado a cada mudanca — a regra se le antes de ser salva.
"""
import os

from System.Windows import Thickness, Visibility
from System.Windows.Controls import Button, ComboBox, Orientation, StackPanel, TextBox

from pyrevit import forms
from pyrevit.forms import WPFWindow

from Snippets import _regras_param as rp

PASTA = os.path.dirname(__file__)

VALORES_FIXOS = {
    rp.ORIENTACAO: ['horizontal', 'vertical', 'inclinado'],
    rp.PAPEL: [rp.PAPEL_SOLTO, rp.PAPEL_GRUPO, rp.PAPEL_MEMBRO],
}

#: campo -> chave das opcoes lidas do modelo
OPCOES_DO_CAMPO = {
    rp.GRUPO: 'grupos', rp.SYSTEM: 'systems',
    rp.CLASSIFICACAO: 'classificacoes', rp.CATEGORIA: 'categorias',
    rp.FAMILIA: 'familias', rp.TIPO: 'tipos', rp.NIVEL: 'niveis',
    rp.FLOOR: 'floors',
}

MODELOS_DE_TEXTO = ['{Floor}-{Unit ID}', '{Floor}', '{Unit ID}', '{Type}',
                    '{nivel}', '{system}', '{categoria}']

_CHAVES_CAMPO = [c for c, _ in rp.CAMPOS]
_CHAVES_OPERADOR = [o for o, _ in rp.OPERADORES]
_CHAVES_ACAO = [a for a, _ in rp.ACOES]
_CHAVES_ONDE = [o for o, _ in rp.ONDES]
_CHAVES_COMBINAR = [c for c, _ in rp.COMBINACOES]


def _combo(largura, itens=None, editavel=False):
    combo = ComboBox()
    combo.Width = largura
    combo.Height = 24
    combo.Margin = Thickness(0, 0, 6, 0)
    combo.IsEditable = editavel
    for item in itens or []:
        combo.Items.Add(item)
    return combo


def _indice(chaves, chave, padrao=0):
    return chaves.index(chave) if chave in chaves else padrao


def _repor_itens(combo, itens):
    texto = combo.Text
    combo.Items.Clear()
    for item in itens:
        combo.Items.Add(item)
    combo.Text = texto


class EditorDeRegra(WPFWindow):

    def __init__(self, regra, opcoes):
        WPFWindow.__init__(self, os.path.join(PASTA, 'um_regra.xaml'))
        self.opcoes = opcoes or {}
        self.resultado = None
        self._condicoes = []    # (painel, campo, parametro, operador, valor, ate)
        self._acoes = []        # (painel, parametro, acao, valor)
        self._pronto = False

        regra = regra or {'nome': '', 'ativa': True, 'quando': [],
                          'entao': [], 'onde': rp.ONDE_AMBOS,
                          'so_vazio': False}
        self.NomeBox.Text = regra.get('nome') or ''
        self.AtivaChk.IsChecked = bool(regra.get('ativa', True))
        for _, rotulo in rp.ONDES:
            self.OndeCombo.Items.Add(rotulo)
        self.OndeCombo.SelectedIndex = _indice(_CHAVES_ONDE, regra.get('onde'))
        for _, rotulo in rp.COMBINACOES:
            self.CombinarCombo.Items.Add(rotulo)
        self.CombinarCombo.SelectedIndex = _indice(_CHAVES_COMBINAR,
                                                   regra.get('combinar'))
        self.SoVazioChk.IsChecked = bool(regra.get('so_vazio'))
        for condicao in regra.get('quando') or []:
            self._add_condicao(condicao)
        for acao in regra.get('entao') or []:
            self._add_acao(acao)
        if not self._acoes:
            self._add_acao(None)
        self._pronto = True
        self._atualizar()

    # ----------------------------------------------------------- condicoes

    def _add_condicao(self, condicao):
        condicao = condicao or {}
        painel = StackPanel()
        painel.Orientation = Orientation.Horizontal
        painel.Margin = Thickness(0, 3, 0, 3)

        campo = _combo(170, [r for _, r in rp.CAMPOS])
        campo.SelectedIndex = _indice(_CHAVES_CAMPO, condicao.get('campo'))
        parametro = _combo(140, self.opcoes.get('parametros'), True)
        parametro.Text = condicao.get('parametro') or ''
        parametro.ToolTip = u'nome do parâmetro a comparar'
        operador = _combo(115, [r for _, r in rp.OPERADORES])
        operador.SelectedIndex = _indice(_CHAVES_OPERADOR,
                                         condicao.get('operador'))
        valor = _combo(190, [], True)
        valor.Text = condicao.get('valor') or ''
        ate = TextBox()
        ate.Width = 60
        ate.Height = 24
        ate.Margin = Thickness(0, 0, 6, 0)
        ate.Text = condicao.get('ate') or ''
        ate.ToolTip = u'até'
        remover = Button()
        remover.Content = u'✕'
        remover.Width = 26
        remover.Height = 24
        remover.Tag = painel
        remover.Click += self._remover_condicao

        for controle in (campo, parametro, operador, valor, ate, remover):
            painel.Children.Add(controle)
        campo.SelectionChanged += self._mudou
        operador.SelectionChanged += self._mudou
        parametro.LostFocus += self._mudou
        valor.LostFocus += self._mudou
        valor.DropDownClosed += self._mudou
        ate.LostFocus += self._mudou

        linha = (painel, campo, parametro, operador, valor, ate)
        self.CondPanel.Children.Add(painel)
        self._condicoes.append(linha)
        self._ajustar_condicao(linha)

    def _ajustar_condicao(self, linha):
        _painel, campo, parametro, operador, valor, ate = linha
        chave = _CHAVES_CAMPO[max(campo.SelectedIndex, 0)]
        op = _CHAVES_OPERADOR[max(operador.SelectedIndex, 0)]
        parametro.Visibility = (Visibility.Visible if chave == rp.PARAMETRO
                                else Visibility.Collapsed)
        valor.Visibility = (Visibility.Collapsed if op in rp.SEM_VALOR
                            else Visibility.Visible)
        ate.Visibility = (Visibility.Visible if op == rp.ENTRE
                          else Visibility.Collapsed)
        _repor_itens(valor, VALORES_FIXOS.get(chave)
                     or self.opcoes.get(OPCOES_DO_CAMPO.get(chave), []))

    def _remover_condicao(self, sender, e):
        self._remover(sender.Tag, self._condicoes, self.CondPanel)

    # ---------------------------------------------------------------- acoes

    def _add_acao(self, acao):
        acao = acao or {}
        painel = StackPanel()
        painel.Orientation = Orientation.Horizontal
        painel.Margin = Thickness(0, 3, 0, 3)

        parametro = _combo(190, self.opcoes.get('parametros'), True)
        parametro.Text = acao.get('parametro') or ''
        parametro.ToolTip = u'parâmetro que recebe o valor'
        tipo = _combo(160, [r for _, r in rp.ACOES])
        tipo.SelectedIndex = _indice(_CHAVES_ACAO, acao.get('acao'))
        valor = _combo(260, [], True)
        valor.Text = acao.get('valor') or ''
        remover = Button()
        remover.Content = u'✕'
        remover.Width = 26
        remover.Height = 24
        remover.Tag = painel
        remover.Click += self._remover_acao

        for controle in (parametro, tipo, valor, remover):
            painel.Children.Add(controle)
        tipo.SelectionChanged += self._mudou
        parametro.LostFocus += self._mudou
        valor.LostFocus += self._mudou
        valor.DropDownClosed += self._mudou

        linha = (painel, parametro, tipo, valor)
        self.AcaoPanel.Children.Add(painel)
        self._acoes.append(linha)
        self._ajustar_acao(linha)

    def _ajustar_acao(self, linha):
        _painel, parametro, tipo, valor = linha
        chave = _CHAVES_ACAO[max(tipo.SelectedIndex, 0)]
        parametros = list(self.opcoes.get('parametros') or [])
        if chave == rp.FLOOR_MAIS:
            if not (parametro.Text or '').strip():
                parametro.Text = u'Floor'
            itens = ['+1', '+2', '+3', '-1']
            dica = (u'quantos níveis acima (+) ou abaixo (−) do Floor calculado, '
                    u'na ordem da aba Floors')
        elif chave == rp.FIXO:
            itens, dica = [], u'o valor gravado'
        elif chave == rp.COPIAR:
            itens = ['Floor', 'Unit ID', 'Type'] + parametros
            dica = u'de qual parâmetro copiar'
        elif chave == rp.MODELO:
            itens = MODELOS_DE_TEXTO
            dica = u'texto com campos entre chaves: {Floor}-{Unit ID}'
        elif chave == rp.DO_AMBIENTE_TOPO:
            itens = ['Unit ID', 'Type'] + parametros
            dica = (u'parâmetro do room que o TOPO da peça alcança — a aranha '
                    u'no forro pega a unidade de cima (vazio = o mesmo nome)')
        else:
            itens = parametros
            dica = u'parâmetro do ambiente (vazio = o mesmo nome)'
        _repor_itens(valor, itens)
        valor.ToolTip = dica

    def _remover_acao(self, sender, e):
        self._remover(sender.Tag, self._acoes, self.AcaoPanel)

    # ------------------------------------------------------------- comum

    def _remover(self, painel, linhas, container):
        for posicao, linha in enumerate(linhas):
            if linha[0] is painel:
                container.Children.Remove(painel)
                del linhas[posicao]
                break
        self._atualizar()

    def _mudou(self, sender, e):
        if not self._pronto:
            return
        self._pronto = False    # _repor_itens dispara eventos
        try:
            for linha in self._condicoes:
                if sender in (linha[1], linha[3]):
                    self._ajustar_condicao(linha)
            for linha in self._acoes:
                if sender is linha[2]:
                    self._ajustar_acao(linha)
        finally:
            self._pronto = True
        self._atualizar()

    def campo_mudou(self, sender, e):
        if self._pronto:
            self._atualizar()

    def coletar(self):
        quando = []
        for _p, campo, parametro, operador, valor, ate in self._condicoes:
            quando.append({
                'campo': _CHAVES_CAMPO[max(campo.SelectedIndex, 0)],
                'operador': _CHAVES_OPERADOR[max(operador.SelectedIndex, 0)],
                'parametro': (parametro.Text or '').strip(),
                'valor': (valor.Text or '').strip(),
                'ate': (ate.Text or '').strip()})
        entao = []
        for _p, parametro, tipo, valor in self._acoes:
            entao.append({
                'parametro': (parametro.Text or '').strip(),
                'acao': _CHAVES_ACAO[max(tipo.SelectedIndex, 0)],
                'valor': (valor.Text or '').strip()})
        return {'nome': (self.NomeBox.Text or '').strip(),
                'ativa': bool(self.AtivaChk.IsChecked),
                'quando': quando, 'entao': entao,
                'combinar': _CHAVES_COMBINAR[
                    max(self.CombinarCombo.SelectedIndex, 0)],
                'onde': _CHAVES_ONDE[max(self.OndeCombo.SelectedIndex, 0)],
                'so_vazio': bool(self.SoVazioChk.IsChecked)}

    def _atualizar(self):
        bruta = self.coletar()
        regra = rp.normalizar_regra(bruta)
        if regra is None:
            self.DescricaoLabel.Text = (u'Incompleta: falta ao menos uma ação '
                                        u'com parâmetro (e valor, quando a '
                                        u'ação pede).')
            return
        texto = rp.descrever_regra(regra)
        ignoradas = len(bruta['quando']) - len(regra['quando'])
        if ignoradas:
            texto += (u'\n{} condição(ões) incompleta(s) será(ão) '
                      u'ignorada(s).'.format(ignoradas))
        # 16/09/2026: regra que nunca casa aparece aqui, nao no resultado vazio
        for aviso in rp.avisos_da_regra(regra):
            texto += u'\n⚠ ' + aviso
        self.DescricaoLabel.Text = texto

    # ----------------------------------------------------------- botoes

    def btn_add_condicao(self, sender, e):
        self._add_condicao(None)
        self._atualizar()

    def btn_add_acao(self, sender, e):
        self._add_acao(None)
        self._atualizar()

    def btn_ok(self, sender, e):
        regra = rp.normalizar_regra(self.coletar())
        if regra is None:
            forms.alert(u'A regra precisa de ao menos uma ação completa.',
                        title=u'Regra de parâmetros')
            return
        if not regra['nome']:
            regra['nome'] = rp.descrever_regra(regra)[:60]
        self.resultado = regra
        self.Close()

    def btn_cancelar(self, sender, e):
        self.Close()
