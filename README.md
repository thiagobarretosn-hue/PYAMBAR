# PYAMBAR

Extensao pyRevit para workflows BIM e MEP no Revit 2026

[![Versao](https://img.shields.io/badge/versao-2.7.0-blue)](https://github.com/thiagobarretosn-hue/PYAMBAR/releases)
[![Python](https://img.shields.io/badge/Python-IronPython%203-blue)](https://ironpython.net/)
[![Revit](https://img.shields.io/badge/Revit-2026-orange)](https://www.autodesk.com/products/revit)
[![License](https://img.shields.io/github/license/thiagobarretosn-hue/PYAMBAR)](LICENSE)

---

## O que e o PYAMBAR?

PYAMBAR e uma extensao para o **pyRevit** que adiciona um conjunto de ferramentas de automacao voltadas para profissionais de **BIM e MEP** que trabalham com o Autodesk Revit 2026.

O objetivo e eliminar tarefas repetitivas e manuais do dia a dia — copiar parametros, aplicar filtros visuais, conectar elementos MEP, exportar dados — substituindo-as por operacoes de um unico clique diretamente no ribbon do Revit.

---

## Principais Funcoes

### Gestao de Parametros

- **ParameterPalette** — paleta flutuante que exibe e edita parametros de elementos selecionados em tempo real, sem abrir propriedades
- **Copy Parameters** — copia valores de parametros de um elemento para multiplos outros em lote
- **SyncPipeParams** — sincroniza parametros de tubulacoes com base em um elemento de referencia
- **Config Parameters** — define quais parametros as ferramentas PYAMBAR devem ler e escrever por projeto

### Visualizacao e Filtros

- **ParamForge** — ferramenta unificada de analise visual e documentacao por parametros: cores, filtros de vista, legendas e schedules num unico pipeline
- **Color-FiLL Forge** — aplica esquemas de cores a elementos de uma vista com base em qualquer parametro, com suporte a regras customizadas
- **ByParam** — pulldown com 4 acoes rapidas por parametro: Isolar, Ocultar, Selecionar e Vista 3D
- **ViewFiltersCopy** — copia todos os filtros configurados de uma vista para uma ou mais vistas de destino

### Automacao de Vistas e Folhas

- **Export Pro** — exporta schedules (tabelas) do Revit em CSV ou Excel com agrupamento avancado, suporte a multiplas tabelas e presets de projeto
- **Find and Replace** — localiza e substitui texto em titulos de folhas, nomes de vistas e outros campos de texto
- **RevitSheet Pro** — gerenciador avancado para organizacao e renomeacao em lote de folhas
- **MapViewGenerator** — gera automaticamente vistas de mapa a partir de regioes definidas no modelo
- **RegiaoNaCropBox** — ajusta a crop box de uma vista com base em uma regiao selecionada no modelo

### MEP — Snap e Conexoes

- **Connect No Rotate** — conecta elementos MEP ao conector mais proximo sem alterar a rotacao do elemento
- **Move Connect** — move um elemento e reconecta automaticamente os conectores em uma unica operacao
- **Disconnect** — desconecta conectores MEP selecionados de forma rapida
- **Rotacionar** — menu com rotacoes pre-definidas (22.5°, 90°, 180°, 270°) e entrada livre para elementos MEP
- **Nivelar Tubos Verticais** — nivela tubulacoes verticais alinhando-as ao ponto de referencia selecionado
- **DistribuirFixtures** — distribui fixtures MEP uniformemente ao longo de uma linha ou entre dois pontos
- **SecoesComerciais** — gera secoes comerciais padronizadas automaticamente a partir de elementos selecionados
- **SlabPasses** — gera furacoes parametricas em lajes para passagens de tubulacoes e dutos

### Utilidades

- **SomarComprimentos** — soma o comprimento total de tubulacoes ou canaletas selecionadas e exibe o resultado formatado
- **CoordenadasXYZ** — exporta as coordenadas X, Y e Z de elementos selecionados para um arquivo CSV

---

## Requisitos

| Componente | Versao Minima |
| ---------- | ------------- |
| Autodesk Revit | 2026 |
| pyRevit | 6.0+ |
| Windows | 10 versao 1803+ |

> Python (IronPython 3) e incluido automaticamente com o pyRevit 6+. Nao e necessario instalar separadamente.

---

## Instalacao

Escolha o metodo mais adequado ao seu ambiente:

---

### Opcao 1 — Instalador CMD (.bat) *(Recomendado)*

Sem dependencias. Funciona em qualquer Windows 10 1803+ com curl e tar nativos.
Sempre baixa a versao mais recente diretamente do GitHub.

1. Baixe: [Install-PYAMBAR.bat](https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.bat)
2. Duplo clique no arquivo
3. Escolha a opcao no menu: `[1]` Instalar / Atualizar — `[2]` Desinstalar
4. Confirme com `S`
5. Reinicie o Revit

---

### Opcao 2 — Script PowerShell

Sem interface grafica. Recomendado para usuarios com acesso ao PowerShell.

**Metodo rapido — cole no PowerShell:**

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
Invoke-WebRequest -Uri "https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1" -OutFile "$env:TEMP\Install-PYAMBAR.ps1"
& "$env:TEMP\Install-PYAMBAR.ps1"
```

**Ou baixe e execute manualmente:**

1. Baixe: [Install-PYAMBAR.ps1](https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1)
2. Clique com botao direito -> **"Executar com PowerShell"**
3. Se solicitado, confirme com `S`
4. Reinicie o Revit

**Parametros avancados:**

```powershell
# Instalacao em caminho personalizado
.\Install-PYAMBAR.ps1 -InstallPath "D:\MinhasExtensoes"

# Instalacao silenciosa (sem confirmacoes)
.\Install-PYAMBAR.ps1 -Silent

# Sem registro automatico no pyRevit
.\Install-PYAMBAR.ps1 -SkipRegistration
```

---

### Opcao 3 — pyRevit CLI

Ideal para quem ja usa o terminal e quer atualizacoes via Extension Manager.

```cmd
pyrevit extend ui PYAMBAR https://github.com/thiagobarretosn-hue/PYAMBAR.git --branch=main
```

Reinicie o Revit. A extensao aparecera no ribbon.

---

### Opcao 4 — Instalacao Manual

Para ambientes sem acesso a internet ou com restricoes corporativas.

1. Baixe o [ZIP do repositorio](https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip)
2. Extraia o conteudo
3. Copie a pasta `PYAMBAR.extension` para:

   ```text
   %APPDATA%\pyRevit\Extensions\
   ```

4. Abra o pyRevit Extension Manager e adicione o caminho da pasta acima
5. Reinicie o Revit

---

### Nota sobre o instalador .exe

Existe um instalador grafico (`PYAMBAR_Installer.exe`) disponivel em releases, mas o **Windows SmartScreen bloqueia executaveis sem assinatura digital** — que e cara e voltada para software comercial. Para contornar o bloqueio, clique em **"Mais informacoes"** -> **"Executar assim mesmo"**, ou prefira as opcoes .bat, PowerShell ou CLI acima, que nao tem esse problema.

---

## Atualizacao

| Metodo de Instalacao | Como Atualizar |
| -------------------- | -------------- |
| CMD .bat (Opcao 1) | Execute o .bat novamente e escolha `[1]` |
| PowerShell (Opcao 2) | Execute o script novamente |
| pyRevit CLI (Opcao 3) | `pyrevit extensions update PYAMBAR` ou pelo Extension Manager no Revit |
| Manual (Opcao 4) | Baixe o ZIP novamente e substitua a pasta |

---

## Desinstalacao

| Metodo | Como Desinstalar |
| ------ | ---------------- |
| CMD .bat | Execute o .bat e escolha `[2]` |
| PowerShell | Nao suportado — exclua manualmente |
| pyRevit CLI | `pyrevit extensions remove PYAMBAR` |
| Manual | Exclua `%APPDATA%\pyRevit\Extensions\PYAMBAR.extension` |

Reinicie o Revit apos remover.

---

## Ferramentas Disponíveis

### Ferramentas.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **Export Pro** | Exporta schedules em CSV ou Excel com agrupamento avancado e presets por projeto |
| **ParamForge** | Analise visual por parametros: cores, filtros, legendas e schedules num unico pipeline |
| **Color-FiLL Forge** | Aplica cores a elementos por valor de parametro em vistas |
| **ByParam** | Pulldown: Isolar, Ocultar, Selecionar e Vista 3D por parametro |
| **ViewFiltersCopy** | Copia filtros de vista entre vistas do projeto |
| **RevitSheet Pro** | Gerenciador avancado de folhas e organizacao de projeto |
| **Find and Replace** | Busca e substitui texto em folhas e vistas |
| **MapViewGenerator** | Gera vistas de mapa a partir de regioes definidas |
| **RegiaoNaCropBox** | Ajusta crop box de vista com base em regiao selecionada |
| **SomarComprimentos** | Soma comprimentos de tubulacoes e canaletas selecionadas |
| **CoordenadasXYZ** | Exporta coordenadas X, Y, Z de elementos selecionados para CSV |

### Parameters.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **ParameterPalette** | Paleta flutuante para leitura e edicao rapida de parametros |
| **Copy Parameters** | Copia valores de parametros entre elementos |
| **SyncPipeParams** | Sincroniza parametros de tubulacoes a partir de um elemento de referencia |
| **Config Parameters** | Configura quais parametros serao usados pelas ferramentas PYAMBAR |

### SnapMEP.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **Connect No Rotate** | Conecta elementos MEP sem alterar a rotacao |
| **Move Connect** | Move e reconecta elementos MEP em uma unica operacao |
| **Disconnect** | Desconecta conectores de elementos MEP |
| **Rotacionar** | Rotacoes rapidas: 22.5°, 90°, 180°, 270° e entrada livre |
| **Nivelar Tubos Verticais** | Nivela tubulacoes verticais ao ponto de referencia |
| **DistribuirFixtures** | Distribui fixtures MEP uniformemente ao longo de uma linha |
| **SecoesComerciais** | Gera secoes comerciais padronizadas a partir de elementos selecionados |
| **SlabPasses** | Gera furacoes automaticas em lajes para passagens MEP |

---

## Estrutura do Repositorio

```text
PYAMBAR/
├── PYAMBAR.extension/           # Extensao pyRevit
│   ├── extension.json           # Metadados e versao da extensao
│   ├── lib/                     # Bibliotecas e snippets compartilhados
│   └── PYAMBAR.tab/
│       ├── Ferramentas.panel/   # 11 ferramentas gerais + updater
│       ├── Parameters.panel/    # 4 ferramentas de parametros
│       └── SnapMEP.panel/       # 8 ferramentas MEP
├── installer/
│   ├── Install-PYAMBAR.bat      # Instalador CMD (recomendado)
│   ├── Install-PYAMBAR.ps1      # Instalador PowerShell
│   ├── pyambar_installer.py     # Codigo-fonte do instalador .exe
│   ├── build.bat                # Script de build do .exe
│   └── requirements.txt         # Dependencias do build
├── CHANGELOG.md
├── LICENSE
└── README.md
```

---

## Suporte

- **Reportar bug:** [github.com/thiagobarretosn-hue/PYAMBAR/issues](https://github.com/thiagobarretosn-hue/PYAMBAR/issues)
- **Discussoes:** [github.com/thiagobarretosn-hue/PYAMBAR/discussions](https://github.com/thiagobarretosn-hue/PYAMBAR/discussions)

---

## Autor

**Thiago Barreto Sobral Nunes**
[thiagobarretosn@gmail.com](mailto:thiagobarretosn@gmail.com)

---

## Licenca

MIT License — veja [LICENSE](LICENSE) para detalhes.
