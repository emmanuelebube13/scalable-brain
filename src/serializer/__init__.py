"""MODEL-007 — model serializer & artifact registry.

Bundles the System-1 outputs (hmm_model.joblib + strategy_weights.json +
regime_strategy_map.json + generated model_metadata.json + checksums.sha256) into an
immutable timestamped version published via the pluggable StorageBackend, then flips an
atomic latest.json pointer — only after every object's SHA256 round-trip verifies.
Refuses to promote on a missing artifact, checksum mismatch, an empty regime map, or
any secret detected in a bundle file.
"""
