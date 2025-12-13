# ML-Based Treatment Classifier Feature

## Overview

This feature introduces a **Smart Second Pass** ML-based treatment classifier that refines treatment signal detection for high-ambiguity cases where regex pattern matching provides low confidence.

## Architecture

### Two-Pass Strategy Enhancement

The treatment analysis now uses a **three-tier classification strategy**:

1. **Pass 1: Regex Classification (Fast)**
   - Uses 23 pre-defined regex patterns to detect treatment signals
   - Analyzes citation context windows around mentions
   - Returns: `TreatmentType` + `confidence` score

2. **Pass 2: ML Refinement (Smart - Optional)**
   - **Trigger**: When `confidence < ML_CLASSIFIER_CONFIDENCE_THRESHOLD` (default: 0.6)
   - Uses zero-shot classification with legal Transformer model
   - Model: `MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33`
   - Labels: `["overruled", "distinguished", "followed", "neutral", "questioned", "affirmed", "criticized", "applied"]`
   - Returns refined `TreatmentType` + higher confidence

3. **Pass 3: Full-Text Analysis (Existing)**
   - Fetches full opinion text for deeper context
   - Triggered by `FETCH_FULL_TEXT_STRATEGY` (smart/always/negative_only/never)

## Implementation Details

### New Module: `app/analysis/ml_classifier.py`

**Class**: `MLTreatmentClassifier`

**Key Features**:
- **Singleton Pattern**: Model loaded once and reused across requests
- **Lazy Initialization**: Model loads on first use (not at startup)
- **Resource Efficient**: Uses ONNX runtime when available, CPU-only by default
- **Zero-Shot Classification**: No fine-tuning dataset required
- **Graceful Degradation**: If model loading fails, falls back to regex-only

**Methods**:
- `classify_treatment(context_text, citation, confidence_threshold)` → dict
- `is_available()` → bool

### Integration: `app/tools/treatment.py`

**New Function**: `_refine_with_ml_classifier(analysis, citation)` → TreatmentAnalysis

**Integration Point**: After parallel regex classification, before full-text fetching:

```python
# Line 296-308 in check_case_validity_impl()
analyses = await _classify_parallel(citing_cases, citation)

# ML Refinement Pass (Smart Second Pass)
if settings.enable_ml_classifier:
    refined_analyses = []
    for analysis in analyses:
        if isinstance(analysis, BaseException):
            refined_analyses.append(analysis)
        else:
            refined = _refine_with_ml_classifier(analysis, citation)
            refined_analyses.append(refined)
    analyses = refined_analyses
```

### Configuration: `app/config.py`

**New Settings**:
```python
enable_ml_classifier: bool = False
ml_classifier_confidence_threshold: float = 0.6
```

**Environment Variables**:
```bash
ENABLE_ML_CLASSIFIER=false           # Master switch
ML_CLASSIFIER_CONFIDENCE_THRESHOLD=0.6  # Trigger threshold
```

## Usage

### Enabling the Feature

1. **Set environment variable**:
   ```bash
   ENABLE_ML_CLASSIFIER=true
   ```

2. **First request**: Model will download (~400MB) and cache locally

3. **Subsequent requests**: Model loads from cache (fast)

### Performance Impact

**When Enabled**:
- **First Use**: +30-60s (model download)
- **Subsequent Uses**: +0.5-2s per ambiguous case (CPU inference)
- **Memory**: +400MB for model in RAM

**When Disabled** (default):
- No performance impact
- Falls back to regex-only classification

### Example Log Output

```json
{
  "level": "INFO",
  "message": "ML classifier refined treatment: negative (conf=0.55) -> neutral (conf=0.72)",
  "extra": {
    "citation": "410 U.S. 113",
    "case_name": "Smith v. Jones",
    "regex_treatment": "negative",
    "regex_confidence": 0.55,
    "ml_treatment": "neutral",
    "ml_confidence": 0.72
  }
}
```

## Model Details

### Zero-Shot Classification Model

**Model**: `MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33`
- **Type**: DeBERTa-v3-base fine-tuned for zero-shot classification
- **Size**: ~400MB
- **Performance**: Optimized for legal/formal text
- **Device**: CPU (configurable for GPU via `device=0`)

### Label Mapping

```python
{
    "overruled": TreatmentType.NEGATIVE,
    "questioned": TreatmentType.NEGATIVE,
    "criticized": TreatmentType.NEGATIVE,
    "distinguished": TreatmentType.NEGATIVE,
    "followed": TreatmentType.POSITIVE,
    "affirmed": TreatmentType.POSITIVE,
    "applied": TreatmentType.POSITIVE,
    "neutral": TreatmentType.NEUTRAL,
}
```

## Testing

### Unit Test Coverage

The ML classifier is tested through integration tests in the treatment analysis workflow.

**To test manually**:
```python
from app.analysis.ml_classifier import get_ml_classifier

classifier = get_ml_classifier()
result = classifier.classify_treatment(
    context_text="This case was overruled by Smith v. Jones, 123 U.S. 456.",
    citation="123 U.S. 456",
    confidence_threshold=0.5
)
print(result)
# {
#   "treatment_type": TreatmentType.NEGATIVE,
#   "confidence": 0.89,
#   "label": "overruled",
#   "all_scores": {...}
# }
```

### CI/CD Compatibility

**GitHub Actions**: ML classifier is **disabled by default** in CI/CD to avoid:
- Long dependency installation times
- Model download overhead
- Memory constraints in CI runners

Set `ENABLE_ML_CLASSIFIER=false` in CI environments (already default).

## Future Enhancements

1. **Fine-Tuning**: Train on labeled legal citations dataset for higher accuracy
2. **ONNX Optimization**: Pre-convert model to ONNX for 2-3x faster inference
3. **GPU Support**: Enable GPU acceleration for batch processing
4. **Model Swapping**: Support multiple models (BERT, LEGAL-BERT, etc.)
5. **Confidence Calibration**: Empirically tune confidence thresholds

## Files Modified

1. `app/analysis/ml_classifier.py` - **NEW**: ML classifier implementation
2. `app/tools/treatment.py` - Integration into treatment analysis workflow
3. `app/config.py` - New configuration settings
4. `.env.example` - Documentation of new environment variables

## Dependencies

All required dependencies already exist in `pyproject.toml`:
- `transformers>=4.36.0` - Hugging Face Transformers library
- `optimum[onnxruntime]>=1.16.0` - ONNX runtime for optimization

No additional dependencies required.

## References

- **CLAUDE.md**: Architecture documentation (see "Future Enhancements" section)
- **PERFORMANCE_OPTIMIZATION.md**: Resource efficiency guidelines
- **Zero-Shot Model**: https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33
