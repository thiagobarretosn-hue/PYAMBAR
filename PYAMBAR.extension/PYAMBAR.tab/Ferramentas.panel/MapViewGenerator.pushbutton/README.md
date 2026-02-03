# Gerador de Mapa de Vista v1.0

## Descrição

Ferramenta pyRevit que cria automaticamente vistas "MAP" para auxiliar na localização dentro de projetos grandes. Combina funcionalidades de múltiplas ferramentas em um workflow automatizado.

## Autor

**Thiago Barreto Sobral Nunes**

## Funcionalidades

### Workflow Automatizado

1. **Duplicação de Vistas**: Cria cópias das vistas selecionadas (incluindo vistas dependentes automaticamente)
2. **Renomeação Inteligente**: Adiciona prefixo "MAP - " ao nome original
3. **Destaque de Região**: Cria FilledRegion na CropBox para destacar a área
4. **Ocultação de Grids**: Remove todas as grid bubbles para visualização limpa
5. **Visualização Total**: Desativa CropBox para mostrar o projeto inteiro

### Recursos v1.0

- ✅ Seleção múltipla de vistas
- ✅ Vistas dependentes copiadas automaticamente
- ✅ Escolha de tipo de FilledRegion configurável
- ✅ Processamento em lote (batch)
- ✅ Relatório detalhado no console
- ✅ Interface WPF intuitiva
- ✅ Validação completa de entrada
- ✅ Tratamento robusto de erros

## Como Usar

### Passo 1: Execute o Comando

Clique no botão "Gerador de Mapa de Vista" no painel de Ferramentas.

### Passo 2: Selecione Vistas

Na janela que abrir:
- Selecione uma ou mais vistas na lista (use Ctrl/Shift para múltipla seleção)
- Vistas dependentes serão copiadas automaticamente

### Passo 3: Escolha Tipo de FilledRegion

Selecione o tipo de FilledRegion que será usado para destacar a região da vista MAP.

### Passo 4: Gerar MAP

Clique em "Gerar MAP" e aguarde o processamento.

O script irá:
- Duplicar cada vista selecionada
- Criar vista MAP com prefixo "MAP - "
- Aplicar todos os ajustes automaticamente
- Mostrar relatório de sucesso/falha

## Aplicações Práticas

### 1. Localização em Projetos Grandes
Crie vistas MAP que mostram onde você está no contexto geral do projeto.

### 2. Navegação Facilitada
Use vistas MAP como referência visual ao lado de vistas detalhadas.

### 3. Documentação de Pranchas
Adicione vistas MAP em pranchas para contextualizar áreas específicas.

### 4. Apresentações
Utilize vistas MAP para mostrar localização durante apresentações.

## Detalhes Técnicos

### Vistas Suportadas

- FloorPlan (Plantas)
- CeilingPlan (Plantas de Forro)
- EngineeringPlan (Plantas de Engenharia)
- Section (Cortes)
- Elevation (Elevações)
- AreaPlan (Plantas de Área)

### Processo de Duplicação

Usa `ViewDuplicateOption.Duplicate` que:
- Copia a vista principal
- Inclui vistas dependentes automaticamente
- Mantém configurações de visualização

### FilledRegion na CropBox

A ferramenta detecta automaticamente:
- **Forma customizada**: Se CropBox foi modificada manualmente
- **Forma retangular**: Se CropBox está em formato padrão

### Grid Bubbles

Remove todas as grid bubbles (End0 e End1) de todos os grids visíveis na vista.

### CropBox

Desativa a limitação da CropBox:
- `CropBoxActive = False`: Remove limitação de visualização
- `CropBoxVisible = False`: Oculta linha da crop region

## Combinação de Ferramentas

Esta ferramenta integra funcionalidades de:

### 1. RegiaoNaCropBox
- Criação de FilledRegion na CropBox
- Detecção inteligente de forma (customizada vs. retangular)
- Seleção de tipo de preenchimento

### 2. ToggleGridBubbles
- Ocultação de grid bubbles
- Processamento de múltiplas vistas

### 3. Lógica Própria
- Duplicação automática de vistas
- Renomeação com prefixo MAP
- Desativação de CropBox
- Interface WPF customizada

## Tratamento de Erros

A ferramenta possui tratamento robusto:
- Validação de vistas duplicáveis
- Verificação de FilledRegion types disponíveis
- Nomes únicos (adiciona contador se necessário)
- Relatório detalhado de sucessos e falhas
- Rollback automático em caso de erro crítico

## Logs e Relatórios

Todos os detalhes são registrados no console pyRevit:
- Vistas processadas
- Etapas executadas por vista
- Sucessos e falhas
- IDs de elementos criados
- Erros detalhados com traceback

## Limitações Conhecidas

1. **Vistas Template**: Não podem ser duplicadas (são automaticamente excluídas)
2. **Vistas já MAP**: Vistas com prefixo "MAP - " são ignoradas
3. **FilledRegion**: Requer tipos de FilledRegion carregados no projeto
4. **CropBox**: Vistas sem CropBox válida não terão FilledRegion

## Versões

### v1.0 (2026-01-12)
- 🎉 Versão inicial
- ✨ Workflow completo integrado
- 🎨 Interface WPF moderna
- 📊 Relatórios detalhados
- 🔧 Tratamento robusto de erros

## Suporte

Para reportar bugs ou solicitar melhorias, contacte o autor.

---

**Desenvolvido com ❤️ para PYAMBAR(lab) Extension**
