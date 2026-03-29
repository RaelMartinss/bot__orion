"""
ml/intent_model.py
Classificador local de intenção para reduzir chamadas à IA externa.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TRAIN_PATH = BASE_DIR / "treino.json"
DEFAULT_MODEL_PATH = BASE_DIR / "modelo.pkl"
DEFAULT_CONFIDENCE_THRESHOLD = 0.18


class IntentModel:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            ngram_range=(1, 2),
        )
        self.model = MultinomialNB()

    def treinar(self, caminho: str | Path = DEFAULT_TRAIN_PATH):
        caminho = Path(caminho)
        with caminho.open("r", encoding="utf-8") as f:
            dados = json.load(f)

        textos = [d["texto"] for d in dados]
        labels = [d["intencao"] for d in dados]

        if not textos or not labels:
            raise ValueError("Dataset de treino vazio.")

        x_train = self.vectorizer.fit_transform(textos)
        self.model.fit(x_train, labels)
        joblib.dump((self.vectorizer, self.model), DEFAULT_MODEL_PATH)
        logger.info("🧠 Classificador de intenção treinado com %s exemplos.", len(dados))

    def carregar(self):
        self.vectorizer, self.model = joblib.load(DEFAULT_MODEL_PATH)

    def prever(self, texto: str) -> str:
        x = self.vectorizer.transform([texto])
        return str(self.model.predict(x)[0])

    def prever_com_confianca(self, texto: str) -> tuple[str, float]:
        x = self.vectorizer.transform([texto])
        intent = str(self.model.predict(x)[0])
        if hasattr(self.model, "predict_proba"):
            probabilidades = self.model.predict_proba(x)[0]
            confianca = float(max(probabilidades))
        else:
            confianca = 0.0
        return intent, confianca


_intent_model: IntentModel | None = None


def get_intent_model() -> IntentModel:
    global _intent_model
    if _intent_model is not None:
        return _intent_model

    model = IntentModel()
    try:
        if _precisa_retreinar():
            model.treinar()
        model.carregar()
    except Exception:
        logger.warning("Falha ao carregar modelo local; treinando do zero.", exc_info=True)
        model.treinar()
        model.carregar()

    _intent_model = model
    return _intent_model


def interpretar_comando(
    texto: str,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict | None:
    texto_limpo = (texto or "").strip()
    if len(texto_limpo) < 3:
        return None

    model = get_intent_model()
    intent, confidence = model.prever_com_confianca(texto_limpo)

    if confidence < confidence_threshold:
        logger.info(
            "🧠 ML local sem confiança suficiente: intent=%s confidence=%.2f texto=%r",
            intent,
            confidence,
            texto_limpo,
        )
        return None

    logger.info(
        "🧠 ML local classificou: intent=%s confidence=%.2f texto=%r",
        intent,
        confidence,
        texto_limpo,
    )
    return {
        "action": intent,
        "query": None,
        "delay": None,
        "confidence": confidence,
        "source": "ml",
    }


def adicionar_exemplo(texto: str, intencao: str, caminho: str | Path = DEFAULT_TRAIN_PATH):
    caminho = Path(caminho)
    with caminho.open("r", encoding="utf-8") as f:
        dados = json.load(f)

    dados.append({"texto": texto, "intencao": intencao})

    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    global _intent_model
    _intent_model = None
    get_intent_model()


def _precisa_retreinar() -> bool:
    if not DEFAULT_MODEL_PATH.exists():
        return True
    if not DEFAULT_TRAIN_PATH.exists():
        raise FileNotFoundError(f"Dataset não encontrado: {DEFAULT_TRAIN_PATH}")
    return DEFAULT_TRAIN_PATH.stat().st_mtime > DEFAULT_MODEL_PATH.stat().st_mtime
