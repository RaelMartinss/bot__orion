# 🧠 ORION — Sistema de Memória Inteligente

## 🎯 Objetivo

Implementar um sistema de memória que permita ao ORION:

* Manter contexto de conversa
* Aprender com o usuário
* Adaptar respostas ao longo do tempo
* Evitar perda de contexto (amnésia)

---

## 🧩 Tipos de Memória

### ⚡ 1. Curto Prazo (Short-Term Memory)

* Guarda as últimas interações da conversa
* Usada para contexto imediato
* Limitada (ex: últimas 10–20 mensagens)

#### Exemplo:

```json
[
  { "role": "user", "content": "cria projeto node" },
  { "role": "assistant", "content": "executando..." },
]
```

---

### 💾 2. Longo Prazo (Long-Term Memory)

* Guarda informações importantes do usuário
* Persistida em arquivo
* Utilizada em sessões futuras

#### Exemplo:

```json
{
  "usuario": "Rael",
  "stack_preferida": ["node", "typescript", "express"],
  "padroes": ["cria projetos frequentemente"]
}
```

---

### 🧠 3. Memória Inteligente

* Filtra o que realmente importa
* Não armazena tudo
* Aprende padrões e preferências

---

## 🔄 Fluxo Completo

### 1. Usuário envia mensagem

```
"cria um projeto node com express"
```

---

### 2. Atualiza memória de curto prazo

```json
[
  { "role": "user", "content": "cria projeto node" }
]
```

---

### 3. Consulta memória de longo prazo

```json
{
  "stack_preferida": ["node", "typescript"]
}
```

---

### 4. Monta contexto da IA

```javascript
messages = [
  { role: "system", content: PROMPT_ORION },
  { role: "system", content: memoria_longo_prazo },
  ...memoria_curta,
  { role: "user", content: input }
];
```

---

### 5. IA responde

```
"Preparando ambiente. Projeto Node com Express inicializado."
```

---

### 6. Salva resposta no curto prazo

---

### 7. Filtro inteligente decide salvar ou não

#### Critérios:

✔ Salvar:

* Preferências
* Padrões repetidos
* Decisões importantes

❌ Ignorar:

* Perguntas simples
* Conversas aleatórias

---

### 8. Atualiza memória de longo prazo

```json
{
  "stack_preferida": ["node", "typescript", "express"]
}
```

---

## 🏗️ Estrutura de Arquivos

```
/memoria
  curto_prazo.json
  longo_prazo.json
```

---

## 🧠 Lógica de Filtro Inteligente

```javascript
function deveSalvar(mensagem) {
  const palavrasImportantes = ["sempre", "prefiro", "uso", "gosto"];

  return palavrasImportantes.some(p =>
    mensagem.toLowerCase().includes(p)
  );
}
```

---

## 🔥 Exemplo Prático

### Primeira interação:

Usuário:

```
cria projeto node com express
```

---

### Interação futura:

Usuário:

```
cria outro projeto
```

---

### ORION responde:

```
Configurando novo projeto Node com Express, como você costuma usar.
```

---

## 🚀 Melhorias Avançadas

### 🧠 Resumo automático

Ao invés de salvar tudo:

```
Usuário prefere Node + TypeScript + Express
```

---

### 🧠 Memória contextual

* Diferenciar trabalho vs pessoal
* Ajustar comportamento por horário
* Adaptar respostas ao contexto

---

## ⚠️ Boas Práticas

* Limitar memória de curto prazo (10–20 mensagens)
* Não salvar tudo indiscriminadamente
* Evitar arquivos muito grandes
* Validar dados antes de salvar

---

## 🎯 Benefícios

* ORION aprende com o tempo
* Respostas mais naturais e personalizadas
* Experiência estilo Jarvis
* Redução de repetição de contexto

---

## 🛰️ Status do Sistema

> Memória segmentada implementada.
> Contexto preservado.
> Amnésia eliminada.
