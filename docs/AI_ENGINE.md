# Explainable Overlap Engine

## Model and storage

The primary local model is `sentence-transformers/all-MiniLM-L6-v2`. It generates normalized 384-dimensional text embeddings. PostgreSQL stores them in a native pgvector column and creates an HNSW cosine index. SQLite tests use JSON through a dialect-aware type. Complaint title and body are hashed; unchanged text reuses the persisted embedding.

No complaint text leaves the environment. Model loading is lazy. If the model or cache is unavailable, the engine reports `feature-hash-fallback` in health/settings and uses a deterministic 384-dimensional token/bigram vector. That score is named as fallback and is never claimed to be transformer output.

## Candidate and scoring pipeline

1. Resolve the canonical institution from its internal ID / AICTE Permanent ID. Normalized names, aliases and fuzzy similarity support import resolution; ambiguity is never silently merged.
2. Retrieve at most 75 recent active candidates for the same canonical institution. This rule both improves relevance and bounds request work.
3. Generate or reuse text embeddings and calculate cosine similarity.
4. Build an explainable hybrid score: 62% semantic similarity, 18% canonical identity, 8% category match, 7% cross-bureau ownership and 5% both-active evidence.
5. Classify `likely_duplicate`, `cross_bureau_related`, or `shared_institution_activity`. Low-similarity same-institution cases explicitly explain that identity alone does not imply duplication.
6. Fingerprint case IDs plus both text hashes. An unchanged rejected finding cannot repeatedly reappear; meaningful text change creates an auditable new evaluation.
7. Notify authorized officials. A human can confirm, reject or mark unrelated. Confirmation can link cases and open coordination; it never fabricates an authoritative decision.

Default synthetic demonstration thresholds are stored in `application_settings` (`0.42` shared activity, `0.55` related, `0.82` likely duplicate) and can be administered without code changes.

## Evaluation methodology

`python -m app.ml.evaluate --sweep` deterministically creates 120 labeled synthetic pairs across exact duplicates, paraphrases, related cases, same-institution unrelated cases, different-institution similar cases and different-institution unrelated cases. It calculates embeddings using the active backend and prints precision, recall, F1, false-positive/negative counts and rates, confusion matrix, plus a ten-threshold sweep. Metrics are computed on every run and are not hardcoded.

The verified MiniLM run is recorded in `docs/evaluation-results.json`. The selected synthetic threshold `0.55` produced precision `1.0000`, recall `0.8667`, F1 `0.9286`, no false positives and 8 false negatives (120 pairs). At `0.50`, recall rose to `1.0000` with 8 false positives. That tradeoff is why reviewable shared-institution activity uses a lower advisory threshold while likely-duplicate labeling remains stricter. Synthetic phrase performance is evidence of repeatability, not a claim of production accuracy. Before official use, AICTE domain reviewers should label a representative, privacy-approved historical sample, choose thresholds by risk tolerance and monitor bureau/category drift.

## Known limitations

- Synthetic language is more regular than real complaints and cannot establish production accuracy.
- Candidate selection prioritizes canonical institution matches; unresolved identity needs a human resolution queue before semantic comparison.
- MiniLM can miss procedural relationships or overvalue common administrative language.
- Scores support triage only. Confirming duplication, conflict or administrative action always belongs to an authorized official.

