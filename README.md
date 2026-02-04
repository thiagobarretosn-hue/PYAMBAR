# PYAMBAR

**Extensao pyRevit para workflows BIM e MEP no Revit 2026**

[![GitHub release](https://img.shields.io/github/v/release/thiagobarretosn-hue/PYAMBAR)](https://github.com/thiagobarretosn-hue/PYAMBAR/releases)
[![Python](https://img.shields.io/badge/Python-IronPython%203-blue)](https://ironpython.net/)
[![Revit](https://img.shields.io/badge/Revit-2026-orange)](https://www.autodesk.com/products/revit)

---

## Instalacao

### Opcao 1: pyRevit CLI (Recomendado)

Abra o terminal e execute:

```cmd
pyrevit extend ui PYAMBAR https://github.com/thiagobarretosn-hue/PYAMBAR.git --branch=main
```

Reinicie o Revit. A extensao aparecera no Extension Manager e pode ser atualizada a qualquer momento.

---

### Opcao 2: Script PowerShell (Sem bloqueio do Windows)

**Metodo mais simples - sem bloqueios de antivirus:**

1. Baixe o script: [Install-PYAMBAR.ps1](https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1)
2. Clique com botao direito no arquivo → **"Executar com PowerShell"**
3. Se aparecer aviso de politica de execucao, digite `S` para confirmar
4. Siga as instrucoes na tela
5. Reinicie o Revit

**Ou execute diretamente no PowerShell:**

```powershell
# Execucao direta (copia e cola no PowerShell)
Set-ExecutionPolicy Bypass -Scope Process -Force
Invoke-WebRequest -Uri "https://github.com/thiagobarretosn-hue/PYAMBAR/raw/main/installer/Install-PYAMBAR.ps1" -OutFile "$env:TEMP\Install-PYAMBAR.ps1"
& "$env:TEMP\Install-PYAMBAR.ps1"
```

**Opcoes avancadas:**

```powershell
# Instalacao silenciosa
.\Install-PYAMBAR.ps1 -Silent

# Caminho personalizado
.\Install-PYAMBAR.ps1 -InstallPath "D:\MinhasExtensoes"

# Sem registro automatico no pyRevit
.\Install-PYAMBAR.ps1 -SkipRegistration
```

---

### Opcao 3: Instalador Grafico (.exe)

> **Nota:** O Windows SmartScreen pode bloquear o instalador por ser um executavel nao assinado. Veja a secao [Resolvendo Bloqueio do Windows](#resolvendo-bloqueio-do-windows) abaixo.

1. Baixe o instalador: [PYAMBAR_Installer.exe](https://github.com/thiagobarretosn-hue/PYAMBAR/releases/latest)
2. Execute o instalador
3. Escolha a pasta de instalacao
4. Clique em "Instalar"
5. Reinicie o Revit

---

### Opcao 4: Manual

1. Baixe o [ZIP do repositorio](https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip)
2. Extraia a pasta `PYAMBAR.extension` para:
   - `%APPDATA%\pyRevit-Master\Extensions\`
   - Ou qualquer pasta de extensoes do pyRevit
3. Reinicie o Revit

---

## Resolvendo Bloqueio do Windows

### Windows SmartScreen

Se o Windows bloquear o instalador .exe:

1. Na tela de aviso, clique em **"Mais informacoes"**
2. Clique em **"Executar assim mesmo"**

![SmartScreen](https://user-images.githubusercontent.com/placeholder/smartscreen.png)

### Windows Defender / Antivirus

Se o antivirus bloquear:

1. Abra **Seguranca do Windows** → **Protecao contra virus e ameacas**
2. Clique em **Historico de protecao**
3. Encontre o item bloqueado
4. Clique em **Acoes** → **Permitir no dispositivo**

**Ou adicione excecao:**

1. **Seguranca do Windows** → **Protecao contra virus e ameacas**
2. **Configuracoes de protecao** → **Gerenciar configuracoes**
3. Role ate **Exclusoes** → **Adicionar ou remover exclusoes**
4. Adicione a pasta ou arquivo do instalador

### Por que o Windows bloqueia?

O instalador .exe e criado com PyInstaller e nao possui assinatura digital de codigo. Isso e comum em projetos open-source. O codigo e 100% seguro e pode ser auditado no repositorio GitHub.

**Alternativas sem bloqueio:**
- Use a **Opcao 1** (pyRevit CLI) - recomendado
- Use a **Opcao 2** (Script PowerShell) - mais simples

---

## Ferramentas Incluidas

### Ferramentas.panel

| Ferramenta | Descricao |
|------------|-----------|
| **CoordenadasXYZ** | Exporta coordenadas de elementos para CSV |
| **Color-FiLL Forge** | Aplica cores por parametro em vistas |
| **Find and Replace** | Busca e substitui texto em folhas |
| **Isolate BY Parameters** | Isola elementos por valor de parametro |
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
| **Overhead** | Cria overhead em instalacoes |

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

### Se instalou via PowerShell ou Instalador (Opcoes 2/3):

Execute o script ou instalador novamente - ele detectara a versao instalada e fara a atualizacao automaticamente.

---

## Verificacao de Integridade

Para verificar que o arquivo baixado e autentico:

### Hash SHA256 (versao atual):

```
# Verificar no PowerShell:
Get-FileHash .\PYAMBAR_Installer.exe -Algorithm SHA256
Get-FileHash .\Install-PYAMBAR.ps1 -Algorithm SHA256
```

Compare com os hashes publicados na [pagina de releases](https://github.com/thiagobarretosn-hue/PYAMBAR/releases).

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
│   ├── Install-PYAMBAR.ps1
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

---

## Suporte

- **Issues**: [github.com/thiagobarretosn-hue/PYAMBAR/issues](https://github.com/thiagobarretosn-hue/PYAMBAR/issues)
- **Discussoes**: [github.com/thiagobarretosn-hue/PYAMBAR/discussions](https://github.com/thiagobarretosn-hue/PYAMBAR/discussions)
