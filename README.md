# PYAMBAR

Extensao pyRevit para workflows BIM e MEP no Revit 2026

[![GitHub release](https://img.shields.io/github/v/release/thiagobarretosn-hue/PYAMBAR)](https://github.com/thiagobarretosn-hue/PYAMBAR/releases)
[![Python](https://img.shields.io/badge/Python-IronPython%203-blue)](https://ironpython.net/)
[![Revit](https://img.shields.io/badge/Revit-2026-orange)](https://www.autodesk.com/products/revit)
[![License](https://img.shields.io/github/license/thiagobarretosn-hue/PYAMBAR)](LICENSE)

---

## O que e o PYAMBAR?

PYAMBAR e uma extensao para o **pyRevit** que adiciona um conjunto de ferramentas de automacao voltadas para profissionais de **BIM e MEP** que trabalham com o Autodesk Revit 2026.

O objetivo e eliminar tarefas repetitivas e manuais do dia a dia — como copiar parametros, aplicar filtros visuais, conectar elementos MEP e gerenciar vistas — substituindo-as por operacoes de um unico clique diretamente no ribbon do Revit.

---

## Principais Funcoes

### Gestao de Parametros

- **ParameterPalette** — paleta flutuante que exibe e edita parametros de elementos selecionados em tempo real, sem abrir propriedades
- **Copy Parameters** — copia valores de parametros de um elemento para multiplos outros em lote
- **Config Parameters** — define quais parametros as ferramentas PYAMBAR devem ler e escrever por projeto

### Visualizacao e Filtros

- **Color-FiLL Forge** — aplica esquemas de cores a elementos de uma vista com base em qualquer parametro, com suporte a regras customizadas
- **Isolate BY Parameters** — isola elementos na vista com base em combinacoes de valores de parametro (AND/OR)
- **OcultarPorParametro** — oculta elementos que correspondam a um valor de parametro especifico
- **ViewFiltersCopy** — copia todos os filtros configurados de uma vista para uma ou mais vistas de destino

### Automacao de Vistas e Folhas

- **Find and Replace** — localiza e substitui texto em titulos de folhas, nomes de vistas e outros campos de texto
- **MapViewGenerator** — gera automaticamente vistas de mapa a partir de regioes definidas no modelo
- **RevitSheet Pro** — gerenciador avancado para organizacao e renomeacao em lote de folhas
- **ToggleGridBubbles** — liga e desliga a exibicao de bolhas de eixos em vistas com um clique

### MEP — Snap e Conexoes

- **Connect No Rotate** — conecta elementos MEP ao conector mais proximo sem alterar a rotacao do elemento
- **Move Connect** — move um elemento e reconecta automaticamente os conectores em uma unica operacao
- **Disconnect** — desconecta conectores MEP selecionados de forma rapida
- **Rotacionar** — menu com rotacoes pre-definidas (22.5°, 90°, 180°, 270°) e entrada livre para elementos MEP
- **SlabPasses** — gera furacoes parametricas em lajes para passagens de tubulacoes e dutos

### Utilidades

- **SomarComprimentos** — soma o comprimento total de tubulacoes ou canaletas selecionadas e exibe o resultado formatado
- **CoordenadasXYZ** — exporta as coordenadas X, Y e Z de elementos selecionados para um arquivo CSV

---

## Requisitos

| Componente | Versao Minima |
| ---------- | ------------- |
| Autodesk Revit | 2026 |
| pyRevit | 5.0+ |
| Windows | 10 versao 1803+ |

> Python (IronPython 3) e incluido automaticamente com o pyRevit. Nao e necessario instalar separadamente.

---

## Instalacao

Escolha o metodo mais adequado ao seu ambiente:

---

### Opcao 1 — pyRevit CLI *(Recomendado)*

Ideal para quem ja usa o terminal e quer atualizacoes automaticas via Extension Manager.

```cmd
pyrevit extend ui PYAMBAR https://github.com/thiagobarretosn-hue/PYAMBAR.git --branch=main
```

Reinicie o Revit. A extensao aparecera no ribbon e pode ser atualizada a qualquer momento pelo Extension Manager.

---

### Opcao 2 — Instalador Grafico (.exe)

Interface grafica com progresso visual. Suporta instalacao, atualizacao e desinstalacao.

1. Baixe o instalador na [pagina de releases](https://github.com/thiagobarretosn-hue/PYAMBAR/releases/latest): `PYAMBAR_Installer.exe`
2. Execute o arquivo
3. Se o Windows SmartScreen alertar, clique em **"Mais informacoes"** → **"Executar assim mesmo"** *(veja [Avisos do Windows](#avisos-do-windows))*
4. Escolha a pasta de instalacao (ou mantenha o padrao)
5. Clique em **"Instalar / Atualizar"**
6. Reinicie o Revit

Para desinstalar: abra o instalador novamente e clique em **"Desinstalar"**.

---

### Opcao 3 — Script PowerShell

Sem interface grafica. Recomendado para usuarios que nao conseguem executar o `.exe`.

**Metodo rapido — cole no PowerShell:**

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
Invoke-WebRequest -Uri "https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1" -OutFile "$env:TEMP\Install-PYAMBAR.ps1"
& "$env:TEMP\Install-PYAMBAR.ps1"
```

**Ou baixe e execute manualmente:**

1. Baixe: [Install-PYAMBAR.ps1](https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1)
2. Clique com botao direito → **"Executar com PowerShell"**
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

### Opcao 4 — Instalador CMD (.bat) *(sem PowerShell)*

Para usuarios sem acesso ao PowerShell ou com restricoes de politica de execucao de scripts.

**Requisito:** Windows 10 versao 1803 ou superior (curl e tar nativos).

1. Baixe: [Install-PYAMBAR.bat](https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.bat)
2. Duplo clique no arquivo
3. Escolha a opcao no menu: `[1]` Instalar / Atualizar — `[2]` Desinstalar
4. Confirme com `S`
5. Reinicie o Revit

---

### Opcao 5 — Pacote MSI *(Ambientes Corporativos)*

Recomendado para empresas com politicas de seguranca (GPO) que bloqueiam `.exe` de fontes externas.
O MSI e instalado nativamente pelo Windows Installer, aparece em **Programas e Recursos** e suporta desinstalacao por GPO.

1. Baixe o instalador na [pagina de releases](https://github.com/thiagobarretosn-hue/PYAMBAR/releases/latest): `PYAMBAR_Installer.msi`
2. Duplo clique e siga o assistente (2 cliques: Aceitar → Instalar)
3. Reinicie o Revit

**Instalacao silenciosa (GPO / linha de comando):**

```cmd
msiexec /i PYAMBAR_Installer.msi /quiet /norestart
```

**Desinstalacao silenciosa:**

```cmd
msiexec /x PYAMBAR_Installer.msi /quiet /norestart
```

> O MSI instala a extensao em `%APPDATA%\pyRevit-Master\Extensions\PYAMBAR.extension\`
> e registra automaticamente no pyRevit se o CLI estiver disponivel.

---

### Opcao 6 — Instalacao Manual

Para ambientes sem acesso a internet ou com restricoes corporativas.

1. Baixe o [ZIP do repositorio](https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip)
2. Extraia o conteudo
3. Copie a pasta `PYAMBAR.extension` para:

   ```text
   %APPDATA%\pyRevit-Master\Extensions\
   ```

4. Abra o pyRevit Extension Manager e adicione o caminho da pasta acima
5. Reinicie o Revit

---

## Atualizacao

| Metodo de Instalacao | Como Atualizar |
| -------------------- | -------------- |
| pyRevit CLI (Opcao 1) | `pyrevit extensions update PYAMBAR` ou pelo Extension Manager no Revit |
| Instalador .exe (Opcao 2) | Execute o instalador novamente — detecta a versao e atualiza |
| PowerShell (Opcao 3) | Execute o script novamente |
| CMD .bat (Opcao 4) | Execute o .bat novamente e escolha `[1]` |
| MSI (Opcao 5) | Baixe o novo MSI e execute — detecta e substitui a versao anterior |
| Manual (Opcao 6) | Baixe o ZIP novamente e substitua a pasta |

---

## Desinstalacao

| Metodo | Como Desinstalar |
| ------ | ---------------- |
| pyRevit CLI | `pyrevit extensions remove PYAMBAR` |
| Instalador .exe | Abra o instalador e clique em **"Desinstalar"** |
| CMD .bat | Execute o .bat e escolha `[2]` |
| MSI | Painel de Controle → Programas e Recursos → PYAMBAR → Desinstalar |
| Manual | Exclua a pasta `%APPDATA%\pyRevit-Master\Extensions\PYAMBAR.extension` |

Reinicie o Revit apos remover.

---

## Ferramentas Incluidas

### Ferramentas.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **Color-FiLL Forge** | Aplica cores a elementos por valor de parametro em vistas |
| **CoordenadasXYZ** | Exporta coordenadas X, Y, Z de elementos selecionados para CSV |
| **Find and Replace** | Busca e substitui texto em folhas e vistas |
| **Isolate BY Parameters** | Isola elementos na vista com base em valores de parametro |
| **MapViewGenerator** | Gera vistas de mapa a partir de regioes definidas |
| **OcultarPorParametro** | Oculta elementos na vista por valor de parametro |
| **RevitSheet Pro** | Gerenciador avancado de folhas e organizacao de projeto |
| **SomarComprimentos** | Soma comprimentos de tubulacoes e canaletas selecionadas |
| **ToggleGridBubbles** | Liga e desliga bolhas de eixos rapidamente |
| **ViewFiltersCopy** | Copia filtros de vista entre vistas do projeto |

### Parameters.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **Config Parameters** | Configura quais parametros serao usados pelas ferramentas PYAMBAR |
| **Copy Parameters** | Copia valores de parametros entre elementos |
| **ParameterPalette** | Paleta flutuante para leitura e edicao rapida de parametros |

### SnapMEP.panel

| Ferramenta | Descricao |
| ---------- | --------- |
| **Connect No Rotate** | Conecta elementos MEP sem alterar a rotacao |
| **Disconnect** | Desconecta conectores de elementos MEP |
| **Move Connect** | Move e conecta elementos em uma unica operacao |
| **Rotacionar** | Menu com rotacoes rapidas: 22.5°, 90°, 180°, 270° e livre |
| **SlabPasses** | Gera furacoes automaticas em lajes para passagens MEP |

---

## Avisos do Windows

### Windows SmartScreen

O instalador `.exe` e gerado com PyInstaller e nao possui assinatura digital paga. Isso e comum em ferramentas open-source. O codigo e auditavel neste repositorio.

**Para prosseguir:**

1. Na tela de alerta, clique em **"Mais informacoes"**
2. Clique em **"Executar assim mesmo"**

**Alternativa sem alerta:** use as opcoes 1, 3 ou 4 (CLI, PowerShell ou CMD).

### Antivirus / Windows Defender

Se o antivirus bloquear o arquivo:

1. Abra **Seguranca do Windows** → **Protecao contra virus e ameacas**
2. Va em **Historico de protecao**
3. Localize o item bloqueado → **Acoes** → **Permitir no dispositivo**

---

## Estrutura do Repositorio

```text
PYAMBAR/
├── PYAMBAR.extension/          # Extensao pyRevit
│   ├── extension.json          # Metadados da extensao
│   ├── lib/                    # Bibliotecas e snippets compartilhados
│   └── PYAMBAR.tab/
│       ├── Ferramentas.panel/  # 10 ferramentas gerais
│       ├── Parameters.panel/   # 3 ferramentas de parametros
│       └── SnapMEP.panel/      # 5 ferramentas MEP
├── installer/
│   ├── pyambar_installer.py    # Codigo-fonte do instalador .exe
│   ├── Install-PYAMBAR.ps1     # Instalador PowerShell
│   ├── Install-PYAMBAR.bat     # Instalador CMD (sem PowerShell)
│   ├── build.bat               # Script de build do .exe
│   └── requirements.txt        # Dependencias do build
├── releases/                   # Executaveis compilados
├── CHANGELOG.md
├── LICENSE
└── README.md
```

---

## Build do Instalador

Para compilar o `.exe` a partir do codigo-fonte:

```cmd
cd installer
pip install -r requirements.txt
build.bat
```

O executavel sera gerado em `installer/dist/` e copiado automaticamente para `releases/`.

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
