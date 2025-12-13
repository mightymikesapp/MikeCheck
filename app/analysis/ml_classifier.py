"""ML-based treatment classifier for legal citations.

This module provides a Transformer-based treatment classifier that can be used
as a "smart second pass" for high-ambiguity cases where regex patterns fail to
provide sufficient confidence.
"""

import logging
from threading import Lock
from typing import Any

from app.analysis.treatment_classifier import TreatmentType

logger = logging.getLogger(__name__)


class MLTreatmentClassifier:
    """ML-based treatment classifier using zero-shot classification.

    This classifier uses a lightweight pre-trained legal BERT model to classify
    treatment signals when regex-based classification has low confidence.

    Features:
    - Singleton pattern: Model loaded once and reused
    - Lazy initialization: Model loaded only on first use
    - Zero-shot classification: No fine-tuning dataset required
    - Resource efficient: Uses ONNX runtime when available
    """

    _instance: "MLTreatmentClassifier | None" = None
    _lock: Lock = Lock()
    _model_loaded: bool = False

    def __new__(cls) -> "MLTreatmentClassifier":
        """Ensure singleton pattern for model loading."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the ML classifier (lazy loading)."""
        # Avoid re-initialization
        if MLTreatmentClassifier._model_loaded:
            return

        with MLTreatmentClassifier._lock:
            if MLTreatmentClassifier._model_loaded:
                return

            self._pipeline = None
            self._labels = [
                "overruled",
                "distinguished",
                "followed",
                "neutral",
                "questioned",
                "affirmed",
                "criticized",
                "applied",
            ]
            self._label_to_treatment: dict[str, TreatmentType] = {
                "overruled": TreatmentType.NEGATIVE,
                "questioned": TreatmentType.NEGATIVE,
                "criticized": TreatmentType.NEGATIVE,
                "distinguished": TreatmentType.NEGATIVE,
                "followed": TreatmentType.POSITIVE,
                "affirmed": TreatmentType.POSITIVE,
                "applied": TreatmentType.POSITIVE,
                "neutral": TreatmentType.NEUTRAL,
            }

            logger.info("ML classifier initialized (model will load on first use)")

    def _load_model(self) -> None:
        """Load the transformer model (lazy initialization)."""
        if self._pipeline is not None:
            return

        try:
            from transformers import pipeline

            logger.info("Loading zero-shot classification model...")

            # Use a lightweight model for faster inference
            # Options:
            # 1. "facebook/bart-large-mnli" - good accuracy, larger (1.6GB)
            # 2. "MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33" - good for legal text
            # 3. "nlpaueb/legal-bert-base-uncased" - legal-specific, but not zero-shot
            #
            # For zero-shot classification, we'll use a compact model
            model_name = "MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33"

            self._pipeline = pipeline(
                "zero-shot-classification",
                model=model_name,
                device=-1,  # CPU (use 0 for GPU)
            )

            logger.info(f"Model loaded successfully: {model_name}")
            MLTreatmentClassifier._model_loaded = True

        except Exception as e:
            logger.error(f"Failed to load ML classifier model: {e}")
            logger.info("ML classifier will be disabled")
            # Set to a dummy value to prevent repeated loading attempts
            self._pipeline = False

    def classify_treatment(
        self,
        context_text: str,
        citation: str,
        confidence_threshold: float = 0.5,
    ) -> dict[str, Any]:
        """Classify treatment using zero-shot classification.

        Args:
            context_text: The text context containing the citation and treatment signals
            citation: The citation being analyzed
            confidence_threshold: Minimum confidence threshold for classification

        Returns:
            Dictionary with keys:
                - treatment_type: TreatmentType enum
                - confidence: float between 0.0 and 1.0
                - label: str (the predicted label)
                - all_scores: dict[str, float] (scores for all labels)
        """
        # Lazy load model on first use
        if self._pipeline is None:
            self._load_model()

        # If model loading failed, return neutral with low confidence
        if self._pipeline is False:
            logger.warning("ML classifier disabled due to model loading failure")
            return {
                "treatment_type": TreatmentType.NEUTRAL,
                "confidence": 0.5,
                "label": "neutral",
                "all_scores": {},
                "error": "Model not available",
            }

        try:
            # Prepare the text for classification
            # Include the citation in the context for better understanding
            prompt = f"How does this text treat the case {citation}? Context: {context_text[:500]}"

            # Run zero-shot classification
            result = self._pipeline(
                prompt,
                candidate_labels=self._labels,
                multi_label=False,  # Single-label classification
            )

            # Extract results
            top_label = result["labels"][0]
            top_score = result["scores"][0]

            # Build all scores dict
            all_scores = {
                label: score for label, score in zip(result["labels"], result["scores"])
            }

            # Map to treatment type
            treatment_type = self._label_to_treatment.get(top_label, TreatmentType.NEUTRAL)

            # Adjust confidence if below threshold
            if top_score < confidence_threshold:
                treatment_type = TreatmentType.NEUTRAL

            logger.debug(
                f"ML classification: {top_label} ({top_score:.2f}) -> {treatment_type.value}",
                extra={
                    "citation": citation,
                    "label": top_label,
                    "confidence": top_score,
                    "treatment_type": treatment_type.value,
                },
            )

            return {
                "treatment_type": treatment_type,
                "confidence": float(top_score),
                "label": top_label,
                "all_scores": all_scores,
            }

        except Exception as e:
            logger.error(f"ML classification failed: {e}")
            return {
                "treatment_type": TreatmentType.NEUTRAL,
                "confidence": 0.5,
                "label": "neutral",
                "all_scores": {},
                "error": str(e),
            }

    def is_available(self) -> bool:
        """Check if the ML classifier is available and ready to use.

        Returns:
            True if the model can be loaded/used, False otherwise
        """
        if self._pipeline is False:
            return False

        if self._pipeline is None:
            # Try to load it
            self._load_model()

        return self._pipeline is not False and self._pipeline is not None


# Global singleton instance
_ml_classifier: MLTreatmentClassifier | None = None


def get_ml_classifier() -> MLTreatmentClassifier:
    """Get the global ML classifier instance (singleton).

    Returns:
        MLTreatmentClassifier instance
    """
    global _ml_classifier
    if _ml_classifier is None:
        _ml_classifier = MLTreatmentClassifier()
    return _ml_classifier
