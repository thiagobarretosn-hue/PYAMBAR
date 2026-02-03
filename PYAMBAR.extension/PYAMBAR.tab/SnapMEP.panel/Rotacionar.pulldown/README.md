# Rotacionar MEP - Pulldown

## 🎯 Objetivo
Rotacionar elementos MEP mantendo **conexões intactas**.

## 📦 Ferramentas

### ✅ Rotacionar Com Conexões
- Detecta TODOS elementos conectados recursivamente
- Rotaciona grupo completo mantendo conexões
- Ângulo customizável

### ⚡ Rotação 90°
- Versão rápida com ângulo fixo
- Mesma lógica de preservação de conexões

## 🔧 Como Funciona

### Problema Original
Revit desconecta elementos ao rotacionar porque tenta manter integridade geométrica individual.

### Solução Implementada
1. Coleta elementos conectados via `ConnectorManager`
2. Percorre recursivamente todos `connector.AllRefs`
3. Rotaciona grupo usando `ElementTransformUtils.RotateElements()` (plural)

## 📝 Snippet Criado
`Snippets/mep_connected_elements.py`
- `get_connected_elements()` - Coleta recursiva
- `get_connector_at_point()` - Busca connector por ponto

## 🚀 Uso
1. Clique no botão
2. Selecione elemento MEP
3. Clique no ponto de rotação
4. Informe ângulo (se aplicável)

## 🔗 API Key
- `ElementTransformUtils.RotateElements()` - Rotação múltipla
- `ConnectorManager.Connectors` - Iteração de conectores
- `Connector.AllRefs` - Referências conectadas
- `Connector.IsConnected` - Status de conexão
