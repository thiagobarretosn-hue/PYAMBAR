# Ocultar Elementos por Parâmetro

## Descrição
Ferramenta para ocultar elementos em vistas do Revit com base em valores de parâmetros específicos.

## Funcionalidades

### 1. Seleção de Parâmetro
- Lista todos os parâmetros disponíveis nos elementos do projeto
- Mostra a quantidade de parâmetros disponíveis
- Atualiza automaticamente os valores disponíveis ao selecionar um parâmetro

### 2. Seleção de Valor
- Exibe todos os valores únicos do parâmetro selecionado
- Mostra quantos valores únicos foram encontrados
- Conta automaticamente quantos elementos possuem aquele valor

### 3. Opções de Vista
A ferramenta oferece três opções para aplicar a ocultação:

- **Vista Atual**: Oculta elementos apenas na vista ativa
- **Selecionar Vista(s) Específica(s)**: Permite escolher múltiplas vistas
- **Todas as Vistas**: Aplica a ocultação em todas as vistas do projeto

### 4. Informações em Tempo Real
- Contador de elementos encontrados com os critérios selecionados
- Informações sobre parâmetro e valor selecionados
- Indicação de quantas vistas serão afetadas
- Validação antes de permitir executar a ação

## Como Usar

1. **Abra o Revit** e carregue seu projeto
2. **Clique no botão** "Ocultar por Parâmetro" no painel Ferramentas
3. **Selecione um parâmetro** da lista suspensa (ex: "Family", "Type", "Comments", etc.)
4. **Escolha o valor** que deseja filtrar (ex: se escolheu "Family", verá todas as famílias)
5. **Escolha onde ocultar**:
   - Vista atual
   - Vistas específicas (selecione na lista)
   - Todas as vistas
6. **Clique em "Ocultar Elementos"**

## Exemplos de Uso

### Exemplo 1: Ocultar todas as tubulações de um tipo específico
1. Parâmetro: "Type"
2. Valor: "Pipe - 50mm"
3. Vista: Todas as vistas
4. Resultado: Todas as tubulações de 50mm serão ocultadas em todas as vistas

### Exemplo 2: Ocultar elementos com comentário específico
1. Parâmetro: "Comments"
2. Valor: "DEMOLIR"
3. Vista: Vista atual
4. Resultado: Todos os elementos marcados com "DEMOLIR" serão ocultados na vista atual

### Exemplo 3: Ocultar família específica em plantas selecionadas
1. Parâmetro: "Family"
2. Valor: "Porta - Simples"
3. Vista: Selecionar vistas específicas (escolher 3 plantas)
4. Resultado: Todas as portas simples serão ocultadas apenas nas 3 plantas selecionadas

## Recursos Técnicos

### Interface WPF
- Interface moderna e responsiva
- Design dark theme compatível com Revit
- Atualizações em tempo real
- Validação de entrada do usuário

### Performance
- Coleta otimizada de elementos
- Filtragem eficiente por parâmetros
- Processamento em batch para múltiplas vistas
- Relatório detalhado de operações

### Segurança
- Transação única para garantir integridade
- Rollback automático em caso de erro
- Validação de categoria antes de ocultar
- Verificação de permissões de vista

## Saída de Dados

A ferramenta gera um relatório completo no output do pyRevit:
- Parâmetro e valor utilizados
- Quantidade de elementos encontrados
- Lista de vistas processadas
- Quantidade de elementos ocultados por vista
- Resumo final com totais

## Requisitos

- Revit 2020 ou superior
- pyRevit instalado e configurado
- Projeto do Revit aberto

## Limitações

- Não oculta elementos em vistas que são templates
- Só oculta elementos cuja categoria pode ser ocultada na vista
- Requer que os elementos tenham o parâmetro selecionado

## Autor
**PYAMBAR Lab**

## Versão
1.0.0

## Licença
Este script faz parte da extensão PYAMBAR Lab.
