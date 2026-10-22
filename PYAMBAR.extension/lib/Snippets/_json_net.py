# -*- coding: utf-8 -*-
"""
Nome: _json_net.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
JSON pelo .NET (System.Text.Json) dentro do IronPython — o `json` do
IronPython e Python puro: medido em 22/10/2026 no status do clash do NEW
SAXUM (1,5 MB, 1.214 itens), LER levou 6,3 s e GRAVAR 22,8 s; o .NET le o
mesmo arquivo em 0,1 s. Cada "Resolvido" congelava o Revit ~29 s na maquina
do colega. Mesmo formato no disco (UTF-8 sem BOM, acentos legiveis, chaves
em ordem): quem le com o `json` do Python continua lendo.

Se o .NET falhar por qualquer motivo, cai no `json` do Python — o
comportamento de antes, so mais lento.

Diferenca conhecida: float inteiro (1.0) volta como int (1). Nenhum codigo do
LOG distingue os dois (1 == 1.0).

Autor: Thiago Barreto Sobral Nunes
"""
import codecs
import json

import clr
clr.AddReference('System.Text.Json')
clr.AddReference('System.Text.Encodings.Web')
from System import Boolean, Double, Int64, Object, String  # noqa: E402
from System.Collections.Generic import Dictionary, List  # noqa: E402
from System.IO import File  # noqa: E402
from System.Text import UTF8Encoding  # noqa: E402
from System.Text.Encodings.Web import JavaScriptEncoder  # noqa: E402
from System.Text.Json import (  # noqa: E402
    JsonDocument,
    JsonDocumentOptions,
    JsonSerializer,
    JsonSerializerOptions,
    JsonValueKind,
)

_UTF8 = UTF8Encoding(False)
_OBJ = JsonValueKind.Object
_ARR = JsonValueKind.Array
_STR = JsonValueKind.String
_NUM = JsonValueKind.Number
# True/False sao palavras reservadas no Python 3: so por getattr
_VERDADE = getattr(JsonValueKind, 'True')
_FALSO = getattr(JsonValueKind, 'False')

_OPCOES = JsonSerializerOptions()
# compacto: o status do clash do NEW SAXUM cai de 1,8 MB (indentado) para
# ~1,1 MB — menos a gravar e menos para o Drive enviar a cada clique
_OPCOES.WriteIndented = False
# acento legivel no arquivo, como o ensure_ascii=False de antes
_OPCOES.Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping

#: a primeira falha do .NET fica aqui (diagnostico); o resto segue no Python
falha = None


def _py(elemento):
    tipo = elemento.ValueKind
    if tipo == _OBJ:
        return dict((p.Name, _py(p.Value)) for p in elemento.EnumerateObject())
    if tipo == _ARR:
        return [_py(x) for x in elemento.EnumerateArray()]
    if tipo == _STR:
        return elemento.GetString()
    if tipo == _NUM:
        bruto = elemento.GetRawText()
        if '.' in bruto or 'e' in bruto or 'E' in bruto:
            return elemento.GetDouble()
        try:
            return int(elemento.GetInt64())
        except Exception:
            return elemento.GetDouble()
    if tipo == _VERDADE:
        return True
    if tipo == _FALSO:
        return False
    return None


def _net(valor):
    if valor is None or isinstance(valor, (bool, str)):
        return valor
    if isinstance(valor, int):
        return Int64(valor)
    if isinstance(valor, float):
        return Double(valor)
    if isinstance(valor, dict):
        saida = Dictionary[String, Object]()
        # chaves em ordem: o mesmo arquivo do sort_keys de antes
        for chave in sorted(valor, key=lambda k: str(k)):
            saida[str(chave)] = _net(valor[chave])
        return saida
    if isinstance(valor, (list, tuple)):
        saida = List[Object]()
        for item in valor:
            saida.Add(_net(item))
        return saida
    raise TypeError(u'tipo sem JSON: {}'.format(type(valor).__name__))


def de_texto(texto):
    """Texto JSON -> objetos Python."""
    global falha
    try:
        documento = JsonDocument.Parse(texto, JsonDocumentOptions())
        try:
            return _py(documento.RootElement)
        finally:
            documento.Dispose()
    except Exception as erro:
        falha = falha or u'ler: {}'.format(erro)
        return json.loads(texto)


def ler_arquivo(caminho):
    """Arquivo UTF-8 (com ou sem BOM) -> objetos Python."""
    texto = File.ReadAllText(caminho)
    return de_texto(texto)


def para_texto(dados):
    """Objetos Python -> texto JSON compacto, chaves em ordem."""
    global falha
    try:
        return JsonSerializer.Serialize(_net(dados), Object, _OPCOES)
    except Exception as erro:
        falha = falha or u'gravar: {}'.format(erro)
        return json.dumps(dados, indent=1, ensure_ascii=False, sort_keys=True)


def gravar_arquivo(caminho, dados):
    """Grava UTF-8 sem BOM (como o codecs.open de antes)."""
    texto = para_texto(dados)
    try:
        File.WriteAllText(caminho, texto, _UTF8)
    except Exception:
        with codecs.open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write(texto)
