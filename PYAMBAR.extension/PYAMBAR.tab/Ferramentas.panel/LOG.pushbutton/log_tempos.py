# -*- coding: utf-8 -*-
"""Cronometro do LOG — DESLIGADO, a menos que exista o arquivo-chave.

Auditoria de lentidao (05/10/2026: "o botao de atualizar tem sido um pouco
lento"). Medir antes de corrigir ([[win-instrumentar-antes-de-corrigir]]):
com `%APPDATA%\\pyRevit\\PYAMBAR\\Interferencias\\MEDIR_TEMPOS` presente, os
metodos da janela e as funcoes de disco sao embrulhados e cada chamada
grava `tempos.log` ao lado, aninhado pela profundidade. Sem o arquivo, nada
e embrulhado e o custo e zero.
"""
import io
import os
import time

_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                    'Interferencias')
CHAVE = os.path.join(_DIR, 'MEDIR_TEMPOS')
SAIDA = os.path.join(_DIR, 'tempos.log')

_profundidade = [0]

JANELA = ('carregar', 'carregar_log', 'montar_lista', 'preencher_para',
          'atualizar_repositorio', 'mostrar_relatorios', 'escolher_primeiro',
          'mostrar_detalhe', 'mostrar_recado', 'mostrar_imagem',
          'ler_apontamentos', 'apresentar_se', 'avisar_novidades', 'ler',
          'para_o_repositorio', 'mostrar_projeto', 'ir_para_aba',
          'montar_resumo', 'mostrar_rotulos', 'ao_recarregar')
DISCO = ('ler_registro', 'gravar_registro', 'listar', 'migrar_antigos',
         'ler_status_do_projeto', 'gravar_status_do_projeto', 'ler_html',
         'gravar_preferencias')
LOG_DISCO = ('ler', 'ler_equipe', 'marcar_visto', 'visto_em',
             'precisa_se_apresentar', 'nome_do_usuario')


def ligado():
    return os.path.exists(CHAVE)


def _gravar(linha):
    with io.open(SAIDA, 'a', encoding='utf-8') as arquivo:
        arquivo.write(linha + u'\n')


def _embrulhar(funcao, nome):
    def medida(*args, **kwargs):
        _profundidade[0] += 1
        inicio = time.time()
        try:
            return funcao(*args, **kwargs)
        finally:
            gasto = (time.time() - inicio) * 1000.0
            _profundidade[0] -= 1
            _gravar(u'{}{:<34} {:>8.0f} ms'.format(
                u'  ' * _profundidade[0], nome, gasto))
    medida.__name__ = getattr(funcao, '__name__', nome)
    return medida


def instrumentar(classe, ifr_disco, log_disco):
    """Embrulha so quando a chave existe. -> quantos foram embrulhados."""
    if not ligado():
        return 0
    _gravar(u'==== {} ===='.format(time.strftime('%H:%M:%S')))
    quantos = 0
    for nome in JANELA:
        if hasattr(classe, nome):
            setattr(classe, nome, _embrulhar(getattr(classe, nome),
                                              u'janela.' + nome))
            quantos += 1
    for modulo, nomes, prefixo in ((ifr_disco, DISCO, u'disco.'),
                                   (log_disco, LOG_DISCO, u'log_disco.')):
        for nome in nomes:
            if hasattr(modulo, nome):
                setattr(modulo, nome, _embrulhar(getattr(modulo, nome),
                                                 prefixo + nome))
                quantos += 1
    return quantos
