"""
generate_files_wxs.py
Gera Files.wxs enumerando todos os arquivos de PYAMBAR.extension
Substitui o comando 'wix harvest' removido no WiX v6

Usa 'Subdirectory' no Component (WiX v4+) evitando arvore de Directory aninhada.

Uso:
    python generate_files_wxs.py <extensao_dir> <output_wxs>
"""
import os
import sys
import uuid
import re

def make_id(rel_path):
    """Converte caminho relativo em ID valido para WiX"""
    s = re.sub(r'[^A-Za-z0-9_]', '_', rel_path)
    if s and s[0].isdigit():
        s = "f_" + s
    # Limitar tamanho (WiX max ~72 chars)
    if len(s) > 60:
        s = s[:60] + "_" + format(abs(hash(rel_path)), 'x')[:6]
    return s

def generate_files_wxs(extension_dir, output_file):
    extension_dir = os.path.abspath(extension_dir)

    components = []
    for root, dirs, files in os.walk(extension_dir):
        # Ignorar pastas ocultas e cache Python
        dirs[:] = sorted([d for d in dirs
                          if not d.startswith(".") and d != "__pycache__"])

        for fname in sorted(files):
            # Ignorar arquivos temporarios/compilados/ocultos
            if fname.endswith((".pyc", ".pyo", ".bak", ".tmp")):
                continue
            if fname.startswith("."):
                continue

            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, extension_dir)
            rel_dir  = os.path.dirname(rel_path)

            comp_id = "comp_" + make_id(rel_path)
            file_id = "file_" + make_id(rel_path)

            components.append({
                "comp_id": comp_id,
                "file_id": file_id,
                "source":  full_path,
                "name":    fname,
                "rel_dir": rel_dir,   # "" se na raiz de INSTALLDIR
                "guid":    str(uuid.uuid4()).upper()
            })

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">',
        '',
        '  <Fragment>',
        '    <ComponentGroup Id="PyAMBARFiles">',
    ]

    for comp in components:
        # Subdirectory so se nao esta na raiz
        subdir_attr = ""
        if comp["rel_dir"]:
            # WiX usa barras invertidas no Subdirectory
            subdir_attr = ' Subdirectory="{}"'.format(comp["rel_dir"])

        source_esc = comp["source"].replace("\\", "\\\\")

        lines.append('      <Component Id="{}" Directory="INSTALLDIR" Guid="{}"{}>'
                     .format(comp["comp_id"], comp["guid"], subdir_attr))
        lines.append('        <File Id="{}" Source="{}" Name="{}" KeyPath="yes" />'
                     .format(comp["file_id"], comp["source"], comp["name"]))
        lines.append('      </Component>')

    lines += [
        '    </ComponentGroup>',
        '  </Fragment>',
        '',
        '</Wix>',
    ]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("[OK] Files.wxs gerado com {} componentes".format(len(components)))
    return len(components)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python generate_files_wxs.py <extensao_dir> <output_wxs>")
        sys.exit(1)
    generate_files_wxs(sys.argv[1], sys.argv[2])
