# -*- coding: utf-8 -*-
"""
Icon Downloader para pyRevit Buttons
Baixa ícones do Material Design Icons e converte para 96x96 PNG

USO:
    python icon_downloader.py "eye-off" "caminho/para/icon.png"
    python icon_downloader.py "hide" "caminho/para/icon.png" --dark

FONTES DE ÍCONES GRATUITAS:
    - Material Design Icons: https://materialdesignicons.com/
    - Simple Icons: https://simpleicons.org/
    - Remix Icon: https://remixicon.com/
    - Feather Icons: https://feathericons.com/
"""

import os
import sys
import urllib.request
import urllib.error

# URLs de APIs de ícones gratuitos
ICON_SOURCES = {
    'material': 'https://raw.githubusercontent.com/Templarian/MaterialDesign/master/svg/{}.svg',
    'feather': 'https://raw.githubusercontent.com/feathericons/feather/master/icons/{}.svg',
    'remix': 'https://raw.githubusercontent.com/Remix-Design/RemixIcon/master/icons/{}.svg',
}


def download_icon_svg(icon_name, source='material'):
    """Baixa ícone SVG da fonte especificada"""
    url = ICON_SOURCES.get(source, ICON_SOURCES['material']).format(icon_name)

    try:
        print("Baixando de: {}".format(url))
        response = urllib.request.urlopen(url)
        svg_content = response.read()
        print("✓ SVG baixado com sucesso!")
        return svg_content
    except urllib.error.HTTPError as e:
        print("✗ Erro HTTP {}: {}".format(e.code, e.reason))
        return None
    except Exception as e:
        print("✗ Erro ao baixar: {}".format(str(e)))
        return None


def convert_svg_to_png(svg_content, output_path, size=96):
    """Converte SVG para PNG usando PIL/Pillow"""
    try:
        from PIL import Image
        from io import BytesIO
        import cairosvg

        # Converter SVG para PNG com cairosvg
        png_data = cairosvg.svg2png(
            bytestring=svg_content,
            output_width=size,
            output_height=size
        )

        # Abrir com PIL e salvar
        img = Image.open(BytesIO(png_data))
        img.save(output_path, 'PNG')
        print("✓ Ícone salvo em: {}".format(output_path))
        return True

    except ImportError:
        print("✗ ERRO: Bibliotecas necessárias não instaladas")
        print("  Instale com: pip install Pillow cairosvg")
        return False
    except Exception as e:
        print("✗ Erro ao converter: {}".format(str(e)))
        return False


def copy_existing_icon(source_button, target_path):
    """Copia ícone de outro botão existente"""
    import shutil

    if not os.path.exists(source_button):
        print("✗ Botão de origem não encontrado: {}".format(source_button))
        return False

    source_icon = os.path.join(source_button, 'icon.png')
    if not os.path.exists(source_icon):
        print("✗ Ícone não encontrado em: {}".format(source_icon))
        return False

    try:
        shutil.copy2(source_icon, target_path)
        print("✓ Ícone copiado de: {}".format(source_button))

        # Copiar também o dark se existir
        source_dark = os.path.join(source_button, 'icon.dark.png')
        if os.path.exists(source_dark):
            target_dark = target_path.replace('icon.png', 'icon.dark.png')
            shutil.copy2(source_dark, target_dark)
            print("✓ Ícone dark copiado também")

        return True
    except Exception as e:
        print("✗ Erro ao copiar: {}".format(str(e)))
        return False


def list_available_buttons(extension_path):
    """Lista todos os botões disponíveis na extensão"""
    buttons = []

    for root, dirs, files in os.walk(extension_path):
        if 'icon.png' in files and '.pushbutton' in root:
            button_name = os.path.basename(root).replace('.pushbutton', '')
            has_dark = 'icon.dark.png' in files
            buttons.append((button_name, root, has_dark))

    return sorted(buttons, key=lambda x: x[0].lower())


def list_icons_only(extension_path):
    """Lista apenas os ícones disponíveis sem modo interativo"""
    print("\n" + "="*60)
    print("ICONES DISPONIVEIS NA EXTENSAO PYAMBAR LAB")
    print("="*60 + "\n")

    buttons = list_available_buttons(extension_path)

    if not buttons:
        print("Nenhum botao com icone encontrado na extensao")
        return

    # Agrupar por panel
    panels = {}
    for button_name, button_path, has_dark in buttons:
        # Extrair nome do panel do caminho
        parts = button_path.split(os.sep)
        panel_name = "Outros"
        for i, part in enumerate(parts):
            if '.panel' in part:
                panel_name = part.replace('.panel', '')
                break

        if panel_name not in panels:
            panels[panel_name] = []
        panels[panel_name].append((button_name, has_dark))

    # Imprimir agrupado
    total = 0
    for panel_name in sorted(panels.keys()):
        print("Panel: {}".format(panel_name))
        print("-" * 60)
        for button_name, has_dark in panels[panel_name]:
            dark_indicator = " [+ dark]" if has_dark else ""
            print("  * {}{}".format(button_name, dark_indicator))
            total += 1
        print("")

    print("="*60)
    print("Total: {} botoes com icones disponiveis".format(total))
    print("="*60 + "\n")

    print("Para copiar um icone:")
    print("  python lib/icon_downloader.py --copy \"NomeBotao\" \"MeuNovoBotao\"")
    print("\nPara modo interativo:")
    print("  python lib/icon_downloader.py --interactive")
    print("")


def interactive_mode(extension_path):
    """Modo interativo para selecionar e copiar ícone"""
    print("\n" + "="*60)
    print("MODO INTERATIVO - Copiar Ícone de Botão Existente")
    print("="*60 + "\n")

    buttons = list_available_buttons(extension_path)

    if not buttons:
        print("✗ Nenhum botão encontrado na extensão")
        return

    print("Botões disponíveis:\n")
    for i, (name, path, has_dark) in enumerate(buttons, 1):
        dark_indicator = " [+ dark]" if has_dark else ""
        print("  {}. {}{}".format(i, name, dark_indicator))

    print("\n" + "-"*60)
    choice = raw_input("\nEscolha o número do botão para copiar o ícone (ou 'q' para sair): ")

    if choice.lower() == 'q':
        print("Operação cancelada.")
        return

    try:
        index = int(choice) - 1
        if 0 <= index < len(buttons):
            source_name, source_path, has_dark = buttons[index]

            target_button = raw_input("\nNome do botão de destino: ")
            if not target_button:
                print("✗ Nome inválido")
                return

            # Construir caminho de destino
            target_path = os.path.join(
                extension_path,
                target_button + '.pushbutton',
                'icon.png'
            )

            # Criar pasta se não existir
            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
                print("✓ Pasta criada: {}".format(target_dir))

            # Copiar ícone
            copy_existing_icon(source_path, target_path)
        else:
            print("✗ Número inválido")
    except ValueError:
        print("✗ Entrada inválida")


def main():
    """Função principal"""
    print("\n" + "="*60)
    print("  PYAMBAR Lab - Icon Downloader para pyRevit")
    print("="*60 + "\n")

    if len(sys.argv) < 2:
        print("USO:")
        print("  1. Listar ícones disponíveis:")
        print("     python icon_downloader.py --list")
        print("")
        print("  2. Modo Interativo (copiar de botão existente):")
        print("     python icon_downloader.py --interactive")
        print("")
        print("  3. Copiar ícone específico:")
        print("     python icon_downloader.py --copy \"SourceButton\" \"TargetButton\"")
        print("")
        print("  4. Baixar da internet (requer Pillow + cairosvg):")
        print("     python icon_downloader.py --download \"icon-name\" \"output.png\"")
        print("")
        print("EXEMPLOS:")
        print("  python icon_downloader.py --list")
        print("  python icon_downloader.py --interactive")
        print("  python icon_downloader.py --copy \"ColorSplasher\" \"MeuBotao\"")
        print("  python icon_downloader.py --download \"eye-off\" \"icon.png\"")
        return

    mode = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    extension_path = os.path.dirname(script_dir)

    if mode == '--list':
        list_icons_only(extension_path)

    elif mode == '--interactive':
        interactive_mode(extension_path)

    elif mode == '--copy' and len(sys.argv) >= 4:
        source_button = sys.argv[2]
        target_button = sys.argv[3]

        # Encontrar botão de origem
        buttons = list_available_buttons(extension_path)
        source_path = None

        for name, path, has_dark in buttons:
            if name.lower() == source_button.lower():
                source_path = path
                break

        if not source_path:
            print("✗ Botão de origem não encontrado: {}".format(source_button))
            print("\nBotões disponíveis:")
            for name, _, _ in buttons:
                print("  - {}".format(name))
            print("\nUse --list para ver lista completa organizada por panel")
            return

        # Construir caminho de destino
        target_path = os.path.join(
            extension_path,
            target_button.replace('.pushbutton', '') + '.pushbutton',
            'icon.png'
        )

        # Criar pasta se não existir
        target_dir = os.path.dirname(target_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            print("✓ Pasta criada: {}".format(target_dir))

        copy_existing_icon(source_path, target_path)

    elif mode == '--download' and len(sys.argv) >= 4:
        icon_name = sys.argv[2]
        output_path = sys.argv[3]
        source = sys.argv[4] if len(sys.argv) > 4 else 'material'

        svg_content = download_icon_svg(icon_name, source)
        if svg_content:
            convert_svg_to_png(svg_content, output_path)

    else:
        print("✗ Modo inválido ou argumentos insuficientes")
        print("Use --help para ver as opções disponíveis")


if __name__ == '__main__':
    main()
