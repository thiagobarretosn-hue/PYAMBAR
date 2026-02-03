# PYAMBAR

**Extensão pyRevit para workflows BIM e MEP no Revit 2026**

[![GitHub release](https://img.shields.io/github/v/release/thiagobarretosn-hue/PYAMBAR)](https://github.com/thiagobarretosn-hue/PYAMBAR/releases)
[![Python](https://img.shields.io/badge/Python-IronPython%203-blue)](https://ironpython.net/)
[![Revit](https://img.shields.io/badge/Revit-2026-orange)](https://www.autodesk.com/products/revit)

---

## Instalação

### Opção 1: pyRevit CLI (Recomendado - com atualização automática)

Abra o terminal e execute:

```cmd
pyrevit extend ui PYAMBAR https://github.com/thiagobarretosn-hue/PYAMBAR.git --branch=main
```

Reinicie o Revit. A extensão aparecerá no Extension Manager e pode ser atualizada a qualquer momento.

### Opção 2: Instalador Gráfico

1. Baixe o instalador: [PYAMBAR_Installer.exe](https://github.com/thiagobarretosn-hue/PYAMBAR/releases/latest)
2. Execute o instalador
3. Escolha a pasta de instalação
4. Clique em "Instalar"
5. Reinicie o Revit

### Opção 3: Manual

1. Baixe o [ZIP do repositório](https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip)
2. Extraia a pasta `PYAMBAR.extension` para:
   - `%APPDATA%\pyRevit-Master\Extensions\`
   - Ou qualquer pasta de extensões do pyRevit
3. Reinicie o Revit

---

## Ferramentas Incluídas

### Ferramentas.panel

| Ferramenta | Descrição |
|------------|-----------|
| **CoordenadasXYZ** | Exporta coordenadas de elementos para CSV |
| **Color-FiLL Forge** | Aplica cores por parâmetro em vistas |
| **Find and Replace** | Busca e substitui texto em folhas |
| **Isolate BY Parameters** | Isola elementos por valor de parâmetro |
| **MapViewGenerator** | Gera vistas de mapa automaticamente |
| **OcultarPorParametro** | Oculta elementos por valor de parâmetro |
| **RevitSheet Pro** | Gerenciador avançado de folhas |
| **SomarComprimentos** | Soma comprimentos de tubulações |
| **ToggleGridBubbles** | Liga/desliga bolhas de grid |
| **ViewFiltersCopy** | Copia filtros entre vistas |

### Parameters.panel

| Ferramenta | Descrição |
|------------|-----------|
| **Config Parameters** | Configura parâmetros de projeto |
| **Copy Parameters** | Copia parâmetros entre elementos |
| **ParameterPalette** | Paleta rápida de edição de parâmetros |

### SnapMEP.panel

| Ferramenta | Descrição |
|------------|-----------|
| **Connect No Rotate** | Conecta sem rotacionar |
| **Disconnect** | Desconecta elementos MEP |
| **Move Connect** | Move e conecta em um passo |
| **Rotacionar** | Rotaciona elementos MEP |
| **SlabPasses** | Gera furações em lajes |

---

## Requisitos

- **Revit**: 2026
- **pyRevit**: 5.0+
- **Python**: IronPython 3 (incluso no pyRevit)

---

## Atualização

### Se instalou via pyRevit CLI (Opção 1):

**Via terminal:**
```cmd
pyrevit extensions update PYAMBAR
```

**Ou via Extension Manager no Revit:**
1. pyRevit > Extensions > Manage Extensions
2. Selecione PYAMBAR
3. Clique em "Update"

### Se instalou via Instalador (Opção 2):

Execute o instalador novamente - ele detectará a versão instalada e fará a atualização automaticamente.

---

## Desenvolvimento

### Estrutura do Repositório

```
PYAMBAR/
├── PYAMBAR.extension/    # Extensão pyRevit
│   ├── extension.json
│   ├── lib/              # Bibliotecas compartilhadas
│   └── PYAMBAR.tab/      # Ferramentas
├── installer/            # Código do instalador
│   ├── pyambar_installer.py
│   └── build.bat
├── releases/             # Executáveis compilados
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

## Licença

MIT License - Veja [LICENSE](LICENSE) para detalhes.
