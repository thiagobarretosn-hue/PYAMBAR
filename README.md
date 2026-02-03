# PYAMBAR

**Extensao pyRevit para workflows BIM e MEP no Revit 2026**

[![GitHub release](https://img.shields.io/github/v/release/thiagobarretosn-hue/PYAMBAR)](https://github.com/thiagobarretosn-hue/PYAMBAR/releases)
[![Python](https://img.shields.io/badge/Python-IronPython%203-blue)](https://ironpython.net/)
[![Revit](https://img.shields.io/badge/Revit-2026-orange)](https://www.autodesk.com/products/revit)

---

## Instalacao

### Opcao 1: pyRevit CLI (Recomendado - com atualizacao automatica)

Abra o terminal e execute:

```cmd
pyrevit extend ui PYAMBAR https://github.com/thiagobarretosn-hue/PYAMBAR.git --branch=main
```

Reinicie o Revit. A extensao aparecera no Extension Manager e pode ser atualizada a qualquer momento.

### Opcao 2: Instalador Grafico

1. Baixe o instalador: [PYAMBAR_Installer.exe](https://github.com/thiagobarretosn-hue/PYAMBAR/releases/latest)
2. Execute o instalador
3. Escolha a pasta de instalacao
4. Clique em "Instalar"
5. Reinicie o Revit

### Opcao 3: Manual

1. Baixe o [ZIP do repositorio](https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip)
2. Extraia a pasta `PYAMBAR.extension` para:
   - `%APPDATA%\pyRevit-Master\Extensions\`
   - Ou qualquer pasta de extensoes do pyRevit
3. Reinicie o Revit

---

## Ferramentas Incluidas

### Ferramentas.panel

| Ferramenta | Descricao |
|------------|-----------|
| **CoordenadasnXYZ** | Exporta coordenadas de elementos para CSV |
| **Color-FiLL Forge** | Aplica cores por parametro em vistas |
| **Find and Replace** | Busca e substitui texto em folhas |
| **Isalate BY Parameters** | Isola elementos por valor de parametro |
| **MapViewGenerator** | Gera vistas de mapa automaticamente |
| **OcultarPorParametro** | Oculta elementos por valor de parametro |
| **RevitSheet Pro** | Gerenciador avancado de folhas |
| **SomarComprimentos** | Soma comprimentos de tubulacoes |
| **ToggleGridBubbles** | Liga/desliga bolhas de grid |
| **ViewFiltersCopy** | Copia filtros entre vistas |

### Parameters.panel

| Ferramenta | Descricao |
|------------|-----------|
| **Config Parameters** | Configura parametros de projeto |
| **Copy Parameters** | Copia parametros entre elementos |
| **ParameterPalette** | Paleta rapida de edicao de parametros |

### SnapMEP.panel

| Ferramenta | Descricao |
|------------|-----------|
| **Connect No Rotate** | Conecta sem rotacionar |
| **Disconnect** | Desconecta elementos MEP |
| **Move Connect** | Move e conecta em um passo |
| **Rotacionar** | Rotaciona elementos MEP |
| **SlabPasses** | Gera furacoes em lajes |

---

## Requisitos

- **Revit**: 2026
- **pyRevit**: 5.0+
- **Python**: IronPython 3 (incluso no pyRevit)

---

## Atualizacao

### Se instalou via pyRevit CLI (Opcao 1):

**Via terminal:**
```cmd
pyrevit extensions update PYAMBAR
```

**Ou via Extension Manager no Revit:**
1. pyRevit > Extensions > Manage Extensions
2. Selecione PYAMBAR
3. Clique em "Update"

### Se instalou via Instalador (Opcao 2):

Execute o instalador novamente - ele detectara a versao instalada e fara a atualizacao automaticamente.

---

## Desenvolvimento

### Estrutura do Repositorio

```
PYAMBAR/
├── PYAMBAR.extension/    # Extensao pyRevit
│   ├── extension.json
│   ├── lib/              # Bibliotecas compartilhadas
│   └── PYAMBAR.tab/      # Ferramentas
├── installer/            # Codigo do instalador
│   ├── pyambar_installer.py
│   └── build.bat
├── releases/             # Executaveis compilados
└── README.md
```

### Build do Instalador

```bash
cd installer
pip install -r requirements.txt
build.bat
```

---

## Autor

**Thiago Barreto Sobral Nunes**
thiagobarretosn@gmail.com

---

## Licenca

MIT License - Veja [LICENSE](LICENSE) para detalhes.
