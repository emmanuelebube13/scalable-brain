from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np
from typing import Dict, List
import math
from collections import defaultdict

# ==================== ONE-TIME LOAD AT SYSTEM STARTUP (CPU ONLY) ====================
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")

LABEL2ID = model.config.label2id
NEG_IDX = LABEL2ID["negative"]
NEU_IDX = LABEL2ID["neutral"]
POS_IDX = LABEL2ID["positive"]

MAX_ENTROPY = math.log2(3)

class ScalableBrainFinBERT:
    """Institutional-grade FinBERT – MVP-ready, CPU-optimized, bug-free"""

    BATCH_SIZE = 8  # CPU cache-friendly (was 32 → hostile)

    @staticmethod
    def _shannon_entropy(probs: np.ndarray) -> float:
        probs = np.clip(probs, 1e-12, 1.0)
        entropy = -np.sum(probs * np.log2(probs))
        return entropy / MAX_ENTROPY

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 450, overlap: int = 50) -> List[str]:
        tokens = tokenizer.encode(text, add_special_tokens=False)
        if len(tokens) <= chunk_size:
            return [text]
        chunks = []
        for i in range(0, len(tokens), chunk_size - overlap):
            chunk_tokens = tokens[i:i + chunk_size]
            chunks.append(tokenizer.decode(chunk_tokens, skip_special_tokens=True))
        return chunks

    @staticmethod
    def _fallback() -> Dict:
        return {
            'sentiment_score': 0.0,
            'positive_prob': 0.0,
            'negative_prob': 0.0,
            'neutral_prob': 1.0,
            'dispersion': 0.0,
            'dominant': 'neutral',
            'raw_label': 'neutral'
        }

    @staticmethod
    def get_features(text: str, auto_chunk: bool = True) -> Dict:
        if not text or len(text.strip()) == 0:
            return ScalableBrainFinBERT._fallback()
        tokens = tokenizer.encode(text, add_special_tokens=False)
        if len(tokens) < 3:
            return ScalableBrainFinBERT._fallback()
        if auto_chunk and len(tokens) > 512:
            chunks = ScalableBrainFinBERT._chunk_text(text)
            chunk_features = [ScalableBrainFinBERT._process_single_chunk(c) for c in chunks]
            return ScalableBrainFinBERT._aggregate_chunks(chunk_features)
        return ScalableBrainFinBERT._process_single_chunk(text)

    @staticmethod
    def _process_single_chunk(text: str) -> Dict:
        inputs = tokenizer(text, padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0].numpy()
        neg_p = float(probs[NEG_IDX])
        neu_p = float(probs[NEU_IDX])
        pos_p = float(probs[POS_IDX])
        sentiment_score = pos_p - neg_p
        dispersion = ScalableBrainFinBERT._shannon_entropy(probs)
        dominant_idx = int(np.argmax(probs))
        dominant = model.config.id2label[dominant_idx]
        return {
            'sentiment_score': round(sentiment_score, 4),
            'positive_prob': round(pos_p, 4),
            'negative_prob': round(neg_p, 4),
            'neutral_prob': round(neu_p, 4),
            'dispersion': round(dispersion, 4),
            'dominant': dominant,
            'raw_label': dominant
        }

    @staticmethod
    def _aggregate_chunks(chunk_features: List[Dict]) -> Dict:
        if not chunk_features:
            return ScalableBrainFinBERT._fallback()
        avg_sent = np.mean([f['sentiment_score'] for f in chunk_features])
        avg_pos = np.mean([f['positive_prob'] for f in chunk_features])
        avg_neg = np.mean([f['negative_prob'] for f in chunk_features])
        avg_neu = np.mean([f['neutral_prob'] for f in chunk_features])
        mean_probs = np.zeros(3)
        mean_probs[NEG_IDX] = avg_neg
        mean_probs[NEU_IDX] = avg_neu
        mean_probs[POS_IDX] = avg_pos
        dominant_idx = int(np.argmax(mean_probs))
        dominant = model.config.id2label[dominant_idx]
        max_disp = max(f['dispersion'] for f in chunk_features)
        return {
            'sentiment_score': round(float(avg_sent), 4),
            'positive_prob': round(float(avg_pos), 4),
            'negative_prob': round(float(avg_neg), 4),
            'neutral_prob': round(float(avg_neu), 4),
            'dispersion': round(float(max_disp), 4),
            'dominant': dominant,
            'raw_label': dominant
        }

    @staticmethod
    def batch_features(text_list: List[str]) -> List[Dict]:
        """MVP-FIXED: no desync, no overwrite, CPU-safe"""
        if not text_list:
            return []
        
        # PHASE 1: Collect chunks + map (single tokenization)
        chunk_list = []
        chunk_orig_map = []          # which original text each chunk belongs to
        results = [None] * len(text_list)
        
        for i, text in enumerate(text_list):
            if not text or len(text.strip()) == 0:
                results[i] = ScalableBrainFinBERT._fallback()
                continue
            tokens = tokenizer.encode(text, add_special_tokens=False)
            if len(tokens) < 3:
                results[i] = ScalableBrainFinBERT._fallback()
                continue
            chunks = ScalableBrainFinBERT._chunk_text(text) if len(tokens) > 512 else [text]
            chunk_list.extend(chunks)
            chunk_orig_map.extend([i] * len(chunks))
        
        if not chunk_list:
            return results
        
        # PHASE 2: Mini-batch inference (CPU-safe)
        all_chunk_probs = []
        for start in range(0, len(chunk_list), ScalableBrainFinBERT.BATCH_SIZE):
            batch_texts = chunk_list[start : start + ScalableBrainFinBERT.BATCH_SIZE]
            inputs = tokenizer(batch_texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)
                probs_batch = torch.nn.functional.softmax(outputs.logits, dim=-1).numpy()
            all_chunk_probs.extend(probs_batch.tolist())  # list for easy grouping
        
        # PHASE 3: Post-aggregation (fixes overwrite + desync)
        grouped_probs = defaultdict(list)
        for chunk_idx, orig_i in enumerate(chunk_orig_map):
            grouped_probs[orig_i].append(np.array(all_chunk_probs[chunk_idx]))
        
        for orig_i, probs_list in grouped_probs.items():
            # Build temporary feature list for aggregation
            temp_features = []
            for p in probs_list:
                neg_p = float(p[NEG_IDX])
                neu_p = float(p[NEU_IDX])
                pos_p = float(p[POS_IDX])
                temp_features.append({
                    'sentiment_score': pos_p - neg_p,
                    'positive_prob': pos_p,
                    'negative_prob': neg_p,
                    'neutral_prob': neu_p,
                    'dispersion': ScalableBrainFinBERT._shannon_entropy(p)
                })
            results[orig_i] = ScalableBrainFinBERT._aggregate_chunks(temp_features)
        
        # Fill any remaining None (should never happen)
        for i in range(len(results)):
            if results[i] is None:
                results[i] = ScalableBrainFinBERT._fallback()
        
        return results
    

