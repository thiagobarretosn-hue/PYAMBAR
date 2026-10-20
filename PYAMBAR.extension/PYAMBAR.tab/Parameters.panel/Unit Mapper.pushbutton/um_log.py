# -*- coding: utf-8 -*-
"""Log de sessao do Unit Mapper no disco — a camada IronPython de
`Snippets._um_log` (o formato, puro e testado).

Pedido do Thiago em 15/09/2026, para o Claude analisar depois "todas as
escolhas e tudo que vai acontecer".

Arquivo: %APPDATA%\\pyRevit\\PYAMBAR\\WBS\\unit_mapper.log — uma linha JSON
por evento, todas as sessoes em sequencia (campo `sessao`). Passou de 20 MB,
vira `unit_mapper.log.1`. Falha de disco NUNCA derruba a janela: fica contada
em SAUDE (o padrao do diario do Fluxo ARN, `af_diario`).
"""
import codecs
import os

from System.IO import File

from Snippets import _um_log as ulog

_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'WBS')
CAMINHO = os.path.join(_DIR, 'unit_mapper.log')
_ANTERIOR = CAMINHO + '.1'

SAUDE = {'falhas': 0, 'ultimo_erro': None}


def _escrever(linhas):
    try:
        if not os.path.exists(_DIR):
            os.makedirs(_DIR)
        if os.path.exists(CAMINHO) and ulog.precisa_girar(os.path.getsize(CAMINHO)):
            # os.replace nao existe no IronPython ([[ironpython-os-replace-nao-existe]])
            if File.Exists(_ANTERIOR):
                File.Delete(_ANTERIOR)
            File.Move(CAMINHO, _ANTERIOR)
        with codecs.open(CAMINHO, 'a', encoding='utf-8') as arquivo:
            for texto in linhas:
                arquivo.write(texto + '\n')
    except Exception as erro:
        SAUDE['falhas'] += 1
        SAUDE['ultimo_erro'] = str(erro)


class LogDeSessao(object):
    """Um por abertura da janela."""

    def __init__(self):
        self.sessao = ulog.novo_id_de_sessao()
        self._config = None
        self._preview = None

    def registrar(self, tipo, **dados):
        try:
            _escrever([ulog.linha(self.sessao, tipo, dados)])
        except Exception as erro:
            SAUDE['falhas'] += 1
            SAUDE['ultimo_erro'] = str(erro)

    def registrar_lote(self, tipo, registros):
        """Muitas linhas numa abertura so do arquivo (os elementos do Aplicar)."""
        try:
            _escrever([ulog.linha(self.sessao, tipo, dados) for dados in registros])
        except Exception as erro:
            SAUDE['falhas'] += 1
            SAUDE['ultimo_erro'] = str(erro)

    def configuracao(self, atual):
        """A primeira vai inteira; depois, so o que mudou."""
        atual = ulog.para_json(atual)
        if self._config is None:
            self.registrar('configuracao', inicial=True, valores=atual)
        else:
            mudancas = ulog.diferencas(self._config, atual)
            if not mudancas:
                return
            self.registrar('configuracao_mudou', mudancas=mudancas)
        self._config = atual

    def preview(self, resumo):
        """So quando o resultado da preview muda — cada tecla recalcula."""
        assinatura = ulog.assinatura(resumo)
        if assinatura == self._preview:
            return
        self._preview = assinatura
        self.registrar('preview', **resumo)
