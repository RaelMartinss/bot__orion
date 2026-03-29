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
DEFAULT_CONFIDENCE_THRESHOLD = 0.45
DEFAULT_MARGIN_THRESHOLD = 0.15   # diferença mínima entre 1º e 2º colocado


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

    def prever_com_confianca(self, texto: str) -> tuple[str, float, float]:
        """Retorna (intent, top_confidence, margin_sobre_segundo)."""
        x = self.vectorizer.transform([texto])
        intent = str(self.model.predict(x)[0])
        if hasattr(self.model, "predict_proba"):
            probs = sorted(self.model.predict_proba(x)[0], reverse=True)
            top = float(probs[0])
            second = float(probs[1]) if len(probs) > 1 else 0.0
            margin = top - second
        else:
            top = 0.0
            margin = 0.0
        return intent, top, margin


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
    margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
) -> dict | None:
    texto_limpo = (texto or "").strip()
    if len(texto_limpo) < 3:
        return None

    model = get_intent_model()
    intent, confidence, margin = model.prever_com_confianca(texto_limpo)

    if confidence < confidence_threshold or margin < margin_threshold:
        logger.info(
            "🧠 ML rejeitado: intent=%s confidence=%.2f margin=%.2f texto=%r",
            intent, confidence, margin, texto_limpo,
        )
        return None

    query = _extrair_query(texto_limpo, intent)
    logger.info(
        "🧠 ML classificou: intent=%s query=%r confidence=%.2f margin=%.2f texto=%r",
        intent, query, confidence, margin, texto_limpo,
    )
    return {
        "action": intent,
        "query": query,
        "delay": None,
        "confidence": confidence,
        "source": "ml",
    }


_QUERY_TRIGGERS: dict[str, list[str]] = {
    "spotify": [
        'toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
        'reproduz', 'reproduzir', 'bota', 'botar', 'põe',
        'escuta', 'escutar', 'spotify', 'música', 'musica',
        'song', 'faixa', 'a música', 'a musica', 'no spotify',
        'me', 'pra mim', 'para mim',
    ],
    "youtube": [
        'youtube', 'no youtube', 'assistir', 'assiste', 'ver',
        'video', 'vídeo', 'clipe', 'busca', 'buscar',
        'toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
        'escuta', 'escutar', 'reproduz', 'reproduzir',
    ],
    "netflix": [
        'netflix', 'filme', 'série', 'serie', 'episódio', 'episodio',
        'na netflix', 'assistir', 'assiste',
    ],
    "jogo": [
        'abre', 'abrir', 'joga', 'jogar', 'iniciar', 'inicia',
        'lança', 'lançar', 'lanca', 'lancar', 'o jogo', 'jogo',
    ],
}


def _extrair_query(texto: str, action: str) -> str | None:
    """Extrai a query do texto para ações que a requerem (spotify, youtube, etc.)."""
    triggers = _QUERY_TRIGGERS.get(action)
    if not triggers:
        return None
    from utils.intent_parser import _query
    return _query(texto, triggers)


def adicionar_exemplo(texto: str, intencao: str, caminho: str | Path = DEFAULT_TRAIN_PATH):
    texto = (texto or "").strip()
    if len(texto) < 3:
        return

    caminho = Path(caminho)
    with caminho.open("r", encoding="utf-8") as f:
        dados = json.load(f)

    if any(d["texto"] == texto and d["intencao"] == intencao for d in dados):
        logger.debug("🧠 Exemplo já existe no treino: %r → %r", texto, intencao)
        return

    dados.append({"texto": texto, "intencao": intencao})

    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    logger.info("🧠 Novo exemplo de treino: %r → %r (total: %d)", texto, intencao, len(dados))

    global _intent_model
    _intent_model = None
    get_intent_model()


def _precisa_retreinar() -> bool:
    if not DEFAULT_MODEL_PATH.exists():
        return True
    if not DEFAULT_TRAIN_PATH.exists():
        raise FileNotFoundError(f"Dataset não encontrado: {DEFAULT_TRAIN_PATH}")
    return DEFAULT_TRAIN_PATH.stat().st_mtime > DEFAULT_MODEL_PATH.stat().st_mtime
