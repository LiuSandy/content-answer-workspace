# Private Knowledge RAG Evaluation

`private-knowledge-rag.jsonl` contains synthetic document identifiers and questions only; it must not contain copyrighted source text, credentials, or private user content.

Run the deterministic CI baseline:

```bash
uv run python -m app.evaluation.run_retrieval_eval --dataset docs/evaluations/private-knowledge-rag.jsonl --backend deterministic
```

The deterministic backend validates dataset wiring and metric aggregation. It is not a substitute for the opt-in PostgreSQL evaluation against indexed test fixtures.
