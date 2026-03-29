# 👁️ Orion Vision (Nível 3) — Guia de Implementação

> Objetivo: dar ao Orion “olhos” para entender o que está na tela e sugerir/agir com base nisso — com segurança e eficiência.

---

## ⚠️ Antes de tudo (importante)

* **Privacidade**: você estará capturando a tela. Defina regras claras (quando ligar/desligar).
* **Performance**: OCR + visão pode pesar CPU/GPU.
* **Controle**: o Orion **não deve agir automaticamente sem confirmação** em ações sensíveis.

---

## 🧠 Arquitetura (simples e escalável)

```text
[Screen Capture]
        ↓
[Preprocessamento]
        ↓
[OCR + Heurísticas]
        ↓
[Detector de Contexto]
        ↓
[Orion (decisão + sugestão)]
```

---

## 🧩 Stack recomendada (Windows)

* Captura de tela: `PIL.ImageGrab` ou `mss` (mais rápido)
* OCR: `pytesseract`
* Automação (opcional): `pyautogui`
* (Opcional avançado) Visão: `opencv-python`

---

## 📦 Instalação

```bash
pip install pillow pytesseract opencv-python mss
```

### Instalar Tesseract (Windows)

1. Baixe: https://github.com/tesseract-ocr/tesseract
2. Instale (ex: `C:\Program Files\Tesseract-OCR`)
3. Configure no Python:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

---

## 🧪 Etapa 1 — Capturar tela

```python
from PIL import ImageGrab

def capturar_tela():
    return ImageGrab.grab()
```

> Dica: para performance, prefira capturar **regiões** (ex: só a área do VS Code).

---

## 🔎 Etapa 2 — Extrair texto (OCR)

```python
import pytesseract

def extrair_texto(img):
    return pytesseract.image_to_string(img)
```

---

## ⚙️ Etapa 3 — Pré-processamento (melhora MUITO o OCR)

```python
import cv2
import numpy as np

def preprocessar(img):
    img = np.array(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return thresh
```

---

## 🧠 Etapa 4 — Detectar contexto

Comece simples com regras:

```python
def detectar_contexto(texto):
    t = texto.lower()

    if "error" in t or "exception" in t:
        return "erro_codigo"

    if "npm" in t or "node" in t:
        return "node_project"

    if "youtube" in t:
        return "youtube"

    return "desconhecido"
```

---

## 🤖 Etapa 5 — Integrar com Orion

```python
def analisar_tela():
    img = capturar_tela()
    img_proc = preprocessar(img)
    texto = extrair_texto(img_proc)

    contexto = detectar_contexto(texto)

    if contexto == "erro_codigo":
        return "⚠️ Vi um erro no código. Quer que eu te ajude?"
    
    if contexto == "node_project":
        return "👨‍💻 Projeto Node detectado. Quer rodar com npm start?"

    return None
```

---

## 🔁 Etapa 6 — Loop inteligente (NÃO exagerar!)

```python
import time

def loop_vision():
    while True:
        resposta = analisar_tela()
        if resposta:
            print(resposta)  # ou enviar pro Telegram
        
        time.sleep(10)  # ajuste: 5–15s
```

---

## ⚡ Otimizações essenciais

* ❌ Não capture a tela toda sempre
* ✅ Use regiões específicas (ex: janela ativa)
* ❌ Não rode a cada segundo
* ✅ Intervalo de 5–15s
* ✅ Cache de contexto (evitar repetir mesma sugestão)

---

## 🔐 Controle de ativação (OBRIGATÓRIO)

Crie comandos:

* “Orion, ativa visão”
* “Orion, desativa visão”

```python
VISION_ATIVO = False
```

---

