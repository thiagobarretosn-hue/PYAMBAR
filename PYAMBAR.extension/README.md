# PYAMBAR - Extensao pyRevit

Ferramentas de automacao BIM e MEP para Revit 2026.

## Requisitos

- Revit 2026
- pyRevit 5.0+ instalado
- Google Drive for Desktop (para sincronizacao automatica)

## Instalacao

### Passo 1: Verificar Google Drive
Certifique-se de que o Google Drive for Desktop esta instalado e o Shared Drive esta mapeado como `H:\`.

### Passo 2: Configurar pyRevit
1. Abrir Revit
2. Clicar em **pyRevit** > **Settings**
3. Ir na aba **Custom Extensions**
4. Clicar em **Add Folder**
5. Navegar ate:
   ```
   H:\Drives compartilhados\Ambar US\AMBAR US NEW\00 - PROCEDURES\01 - BIM\03 - AUTOMATION SOLUTIONS\PYREVIT\2.0\
   ```
6. Clicar **Save Settings and Reload**

### Passo 3: Verificar
Uma nova aba **PYAMBAR** deve aparecer no Revit.

---

## Ferramentas Disponiveis

### Ferramentas.panel
| Ferramenta | Descricao |
|------------|-----------|
| **CoordenadasnXYZ** | Gera coordenadas X, Y, Z de elementos e exporta para CSV/Schedule |
| **Isalate BY Parameters** | Isola elementos por valor de parametro |
| **Color-FiLL_Forge** | Preenche cores em plantas |
| **Find and Replace** | Busca e substitui texto em folhas |
| **Renomear Vistas** | Renomeia vistas em lote |
| **OcultarPorParametro** | Oculta elementos por parametro |
| **SomarComprimentos** | Soma comprimentos de elementos |
| **ToggleGridBubbles** | Liga/desliga bolhas de grid |
| **RegiaoNaCropBox** | Cria regiao na crop box |
| **AtualizarDataEmissao** | Atualiza data de emissao |
| **MapViewGenerator** | Gera mapa de vistas |

### SnapMEP.panel
| Ferramenta | Descricao |
|------------|-----------|
| **Move Connect** | Move e conecta elementos MEP |
| **Disconnect** | Desconecta elementos MEP |
| **Connect No Rotate** | Conecta sem rotacionar |
| **SlabPasses** | Cria passagens em lajes |
| **Rotacionar** | Rotaciona elementos MEP |

### Parameters.panel
| Ferramenta | Descricao |
|------------|-----------|
| **Copy Parameters** | Copia parametros entre elementos |
| **ParameterPalette** | Paleta de parametros frequentes |
| **Config Parameters** | Configuracao de parametros |

---

## Suporte

Em caso de problemas, contate:
- **Autor:** Thiago Barreto Sobral Nunes
- **Email:** thiagobarretosn@gmail.com

---

## Atualizacoes

As atualizacoes sao automaticas via Google Drive. Ao abrir o Revit, a versao mais recente sera carregada automaticamente.

**Versao atual:** 2.0
