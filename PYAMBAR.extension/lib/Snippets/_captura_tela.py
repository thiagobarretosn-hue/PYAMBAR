# -*- coding: utf-8 -*-
"""Captura de imagem: tela do Revit e clipboard. Devolve PNG (ou JPEG) em base64.

Copiado do `LogOcorrencias.pushbutton` em 24/09/2026 para o `lib`, sem mudar o
comportamento: a ferramenta LOG grava a imagem em DAT/LOG/img em vez de mandar
para o Drive (`gravar_em`, no fim do arquivo). O LogOcorrencias antigo segue
com a sua cópia até ser aposentado.

Depende de System.Drawing e System.Windows — so roda em IronPython dentro do Revit.

A imagem e reduzida a MAX_LARGURA antes de codificar e, se o base64 do PNG ainda
passar de LIMITE_BASE64, e recodificada em JPEG: o doPost do GAS tem limite de
tamanho, e um payload gigante viraria "sem conexao" e travaria a fila.
"""

import clr
clr.AddReference('System.Drawing')
clr.AddReference('System.Windows.Forms')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import Convert, Int64                                 # noqa: E402
from System.Diagnostics import Process                            # noqa: E402
from System.Drawing import Bitmap, Graphics, Point, Size          # noqa: E402
from System.Drawing.Drawing2D import InterpolationMode            # noqa: E402
from System.Drawing.Imaging import (                              # noqa: E402
    Encoder, EncoderParameter, EncoderParameters, ImageCodecInfo, ImageFormat
)
from System.IO import MemoryStream                                # noqa: E402
from System.Threading import Thread                               # noqa: E402
from System.Windows.Forms import Application, Control, Screen     # noqa: E402

MIME = 'image/png'
MIME_JPEG = 'image/jpeg'

MAX_LARGURA = 1920
LIMITE_BASE64 = int(3.5 * 1024 * 1024)
JPEG_QUALIDADE = 80

# --- recorte nativo do Windows (o mesmo do Win+Shift+S) ---

# Protocolo que abre a sobreposicao de recorte. Quem o registra e o Windows;
# nao ha executavel estavel para chamar direto, por isso o explorer.exe resolve.
URI_RECORTE = 'ms-screenclip:'

# Processos que hospedam a sobreposicao. Servem so para encurtar a espera quando
# o usuario cancela com Esc — se nenhum deles aparecer, o timeout resolve.
PROCESSOS_RECORTE = ('ScreenClippingHost', 'SnippingTool', 'ScreenSketch')

# Teto da espera. Escolher uma regiao leva segundos, nao minutos — e durante a
# espera o laco bombeia mensagens para o Revit (ver esperar_recorte), o que deixa
# o ribbon clicavel e permite iniciar outro comando pyRevit reentrante dentro
# deste. Quanto menor a janela de exposicao, melhor.
TIMEOUT_RECORTE_MS = 20000
INTERVALO_POLL_MS = 250

# Limpar o clipboard e disputado com outros processos: erra por instantes e
# resolve na volta seguinte.
TENTATIVAS_LIMPEZA = 5
ESPERA_LIMPEZA_MS = 120

# Depois que a sobreposicao fecha, o Windows ainda leva um instante para publicar
# a imagem no clipboard.
GRACA_POS_FECHAMENTO_MS = 1500


class ClipboardOcupado(RuntimeError):
    """O clipboard nao pode ser esvaziado antes do recorte.

    Nao e desistencia do usuario — e a unica situacao em que o recorte precisa
    parar e avisar, sob pena de anexar a imagem errada.
    """


def _para_base64(stream):
    """Convert.ToBase64String aceita o Byte[] direto — converter byte a byte no
    interpretador travaria a janela por segundos num screenshot de 4K."""
    return Convert.ToBase64String(stream.ToArray())


def _reduzir(bitmap):
    """Reduz proporcionalmente para MAX_LARGURA. Devolve (bitmap, foi_criado)."""
    if bitmap.Width <= MAX_LARGURA:
        return bitmap, False

    altura = int(round(bitmap.Height * (float(MAX_LARGURA) / float(bitmap.Width))))
    if altura < 1:
        altura = 1

    destino = Bitmap(MAX_LARGURA, altura)
    grafico = Graphics.FromImage(destino)
    try:
        grafico.InterpolationMode = InterpolationMode.HighQualityBicubic
        grafico.DrawImage(bitmap, 0, 0, MAX_LARGURA, altura)
    finally:
        grafico.Dispose()
    return destino, True


def _codificar_png(bitmap):
    stream = MemoryStream()
    try:
        bitmap.Save(stream, ImageFormat.Png)
        return _para_base64(stream)
    finally:
        stream.Dispose()


def _codificar_jpeg(bitmap, qualidade=JPEG_QUALIDADE):
    codec = None
    for item in ImageCodecInfo.GetImageEncoders():
        if item.MimeType == MIME_JPEG:
            codec = item
            break
    if codec is None:
        return None

    parametros = EncoderParameters(1)
    parametros.Param[0] = EncoderParameter(Encoder.Quality, Int64(qualidade))
    stream = MemoryStream()
    try:
        bitmap.Save(stream, codec, parametros)
        return _para_base64(stream)
    finally:
        stream.Dispose()
        parametros.Dispose()


def _resultado(bitmap, nome_base):
    """Reduz, codifica em PNG e cai para JPEG se o base64 passar do limite."""
    imagem, criada = _reduzir(bitmap)
    try:
        b64 = _codificar_png(imagem)
        if len(b64) <= LIMITE_BASE64:
            return {
                'filename': '{}.png'.format(nome_base),
                'mimeType': MIME,
                'base64': b64,
            }
        jpeg = _codificar_jpeg(imagem)
        if jpeg is None:
            return {
                'filename': '{}.png'.format(nome_base),
                'mimeType': MIME,
                'base64': b64,
            }
        return {
            'filename': '{}.jpg'.format(nome_base),
            'mimeType': MIME_JPEG,
            'base64': jpeg,
        }
    finally:
        if criada:
            imagem.Dispose()


def capturar_tela():
    """Captura o monitor onde esta o cursor — cobre setup de varios monitores."""
    tela = Screen.FromPoint(Control.MousePosition)
    limites = tela.Bounds

    bitmap = Bitmap(limites.Width, limites.Height)
    grafico = Graphics.FromImage(bitmap)
    try:
        grafico.CopyFromScreen(
            Point(limites.X, limites.Y),
            Point(0, 0),
            Size(limites.Width, limites.Height)
        )
    finally:
        grafico.Dispose()

    try:
        return _resultado(bitmap, 'screenshot')
    finally:
        bitmap.Dispose()


def tem_imagem_no_clipboard():
    from System.Windows import Clipboard
    try:
        return Clipboard.ContainsImage()
    except Exception:
        # O clipboard e um recurso disputado: outro processo pode te-lo aberto
        # neste instante. Nesse caso a proxima volta do poll tenta de novo.
        return False


def limpar_clipboard(tentativas=TENTATIVAS_LIMPEZA):
    """Esvazia o clipboard antes do recorte. False quando nao conseguiu.

    Sem isso, uma imagem que ja estivesse la seria lida como se fosse o recorte
    que o usuario acabou de fazer — inclusive quando ele cancelou.

    Confere o resultado em vez de confiar no Clear(): o clipboard e disputado,
    o Clear() pode estourar (ou nao valer) sem aviso, e quem chama precisa saber.
    """
    from System.Windows import Clipboard
    for _ in range(max(int(tentativas), 1)):
        try:
            Clipboard.Clear()
        except Exception:
            pass
        if not tem_imagem_no_clipboard():
            return True
        Thread.Sleep(ESPERA_LIMPEZA_MS)
    return not tem_imagem_no_clipboard()


def abrir_recorte():
    """Dispara a sobreposicao de recorte do Windows. A janela precisa ja estar
    fechada: a sobreposicao fotografa o que estiver na tela."""
    Process.Start('explorer.exe', URI_RECORTE)


def _recorte_ativo():
    """True enquanto a sobreposicao de recorte estiver de pe."""
    for nome in PROCESSOS_RECORTE:
        try:
            if Process.GetProcessesByName(nome).Length:
                return True
        except Exception:
            continue
    return False


def esperar_recorte(timeout_ms=TIMEOUT_RECORTE_MS, intervalo_ms=INTERVALO_POLL_MS):
    """Espera a imagem do recorte aparecer no clipboard. False quando nao veio.

    Cancelar com Esc e um caminho normal, nao um erro: o usuario simplesmente
    segue sem imagem.

    A espera termina cedo quando a sobreposicao ja apareceu e depois sumiu sem
    publicar nada — que e exatamente o Esc. Se nenhum dos processos conhecidos
    for visto (nome muda entre versoes do Windows), sobra o timeout.

    DoEvents a cada volta: sem bombear a fila de mensagens, a thread STA nao
    consegue ler o clipboard OLE de forma confiavel.
    """
    decorrido = 0
    viu_processo = False
    limite_apos_fechar = None

    while decorrido < timeout_ms:
        try:
            Application.DoEvents()
        except Exception:
            pass

        if tem_imagem_no_clipboard():
            return True

        if _recorte_ativo():
            viu_processo = True
            limite_apos_fechar = None
        elif viu_processo and limite_apos_fechar is None:
            limite_apos_fechar = decorrido + GRACA_POS_FECHAMENTO_MS
        elif limite_apos_fechar is not None and decorrido >= limite_apos_fechar:
            return False

        Thread.Sleep(intervalo_ms)
        decorrido += intervalo_ms

    return False


def capturar_recorte(timeout_ms=TIMEOUT_RECORTE_MS):
    """Limpa o clipboard, chama o recorte do Windows e devolve a imagem.

    None quando o usuario cancelou ou o tempo acabou — sem excecao: desistir do
    recorte nao e falha.

    Levanta ClipboardOcupado quando nao deu para esvaziar o clipboard. Aborta em
    vez de seguir porque a deteccao aqui e por PRESENCA de imagem: partindo de um
    clipboard sujo, o primeiro poll acha a imagem que ja estava la — o print que a
    pessoa copiou do Teams — e ela iria para a planilha rotulada como recorte,
    inclusive se o usuario tivesse cancelado. A alternativa, exigir MUDANCA de
    conteudo, precisaria de uma impressao digital da imagem anterior: dimensao e
    DPI colidem justamente no caso perigoso (print de tela cheia x recorte
    grande), e comparar pixel a pixel custaria decodificar uma imagem de 4K a cada
    volta do poll. Falhar o Clear() cinco vezes seguidas e raro; anexar a imagem
    errada num registro que vai para a planilha, nao.

    Quem chama tem que ter fechado a janela antes (ver o laco de main()): a
    sobreposicao captura a tela como ela estiver.
    """
    if not limpar_clipboard():
        raise ClipboardOcupado(
            'Nao foi possivel esvaziar o clipboard — outro programa esta '
            'segurando ele. Sem isso, a imagem que ja esta la seria anexada '
            'como se fosse o recorte.'
        )
    abrir_recorte()
    # O retorno da espera nao decide nada: uma imagem publicada logo depois da
    # janela de graca ainda serve, e capturar_clipboard ja devolve None quando nao
    # ha imagem nenhuma.
    esperar_recorte(timeout_ms)
    return capturar_clipboard()


def capturar_clipboard():
    """Converte a imagem do clipboard (BitmapSource do WPF) em PNG/JPEG base64."""
    from System.Windows import Clipboard
    from System.Windows.Media.Imaging import PngBitmapEncoder, BitmapFrame

    if not tem_imagem_no_clipboard():
        return None

    fonte = Clipboard.GetImage()
    if fonte is None:
        return None

    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(fonte))

    stream = MemoryStream()
    try:
        encoder.Save(stream)
        stream.Position = 0
        # Bitmap(stream) exige o stream vivo enquanto o bitmap existir — por isso
        # o Dispose do bitmap vem antes do Dispose do stream.
        bitmap = Bitmap(stream)
        try:
            return _resultado(bitmap, 'clipboard')
        finally:
            bitmap.Dispose()
    finally:
        stream.Dispose()


# --- gravar em arquivo (v1.8: a imagem vai para a DAT, nao para o Drive) ---

def gravar_em(resultado, pasta, nome_base):
    """base64 -> arquivo. -> nome do arquivo gravado, ou '' se nao havia
    imagem. O chamador ja garantiu a pasta."""
    if not resultado or not resultado.get('base64'):
        return ''
    from System.IO import File, Path
    extensao = Path.GetExtension(resultado.get('filename') or '.png')
    nome = '{}{}'.format(nome_base, extensao)
    File.WriteAllBytes(Path.Combine(pasta, nome),
                       Convert.FromBase64String(resultado['base64']))
    return nome
