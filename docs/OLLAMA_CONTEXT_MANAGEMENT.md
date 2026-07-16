# Ollama context management

ResearchHub limits local `qwen2.5:7b` requests to a 4096-token context on the 16 GB development laptop. A larger context increases KV-cache memory, slows CPU inference, and can push Windows and Docker Desktop into page-file thrashing. Qwen is used only for generation; the existing MiniLM embedding model remains the correct, substantially lighter model for pgvector retrieval.

## Request flow

The API retrieves up to 20 candidates, combines their existing semantic score with lightweight lexical relevance, removes exact and near duplicates, penalizes overlapping adjacent chunks, and reranks them. Oversized evidence is compressed by selecting query-relevant complete sentences, with extra weight for findings, conclusions, methods, and numeric evidence. No additional LLM call is made.

The context manager counts the system prompt, question, limited history, source metadata, a 600-token answer reserve, and a 300-token safety margin. It then fits at most six chunks into the remaining evidence budget. Citation labels are short (`[S1]`) inside the prompt and map back to the selected document/chunk metadata in the existing API citations.

The tokenizer is a conservative UTF-8/lexical approximation. It avoids loading a second Qwen tokenizer or model and is paired with the explicit safety margin. Full UI history stays in the database; model-visible history defaults to none and is capped at two turns/500 tokens if supplied.

## Resource profiles

- `NORMAL`: `num_ctx=4096`, `num_predict=500`, normally five chunks and at most 2600 evidence tokens.
- `LOW_MEMORY`: below 4 GB available RAM, `num_ctx=2048`, `num_predict=300`, at most three chunks.
- `CRITICAL`: below 2 GB available RAM, no Ollama generation; the API returns a safe temporary 503 response.

Only one generation acquires the shared Ollama semaphore. Other requests wait up to 120 seconds, then receive 429. HTTP connections are reused. OOM responses receive at most one degraded retry at 2048/300; ordinary expensive generations are not repeatedly retried.

## Configuration

All settings use the project `RESEARCHHUB_` prefix. The complete list and defaults are in `.env.example`. Recommended laptop values are:

```dotenv
RESEARCHHUB_OLLAMA_MODEL=qwen2.5:7b
RESEARCHHUB_OLLAMA_NUM_CTX=4096
RESEARCHHUB_OLLAMA_MAX_NUM_CTX=4096
RESEARCHHUB_OLLAMA_NUM_PREDICT=500
RESEARCHHUB_OLLAMA_MAX_NUM_PREDICT=600
RESEARCHHUB_OLLAMA_NUM_THREAD=6
RESEARCHHUB_OLLAMA_MAX_CONCURRENT_REQUESTS=1
RESEARCHHUB_RAG_RETRIEVAL_CANDIDATES=20
RESEARCHHUB_RAG_RERANK_TOP_K=5
RESEARCHHUB_RAG_MAX_CONTEXT_CHUNKS=6
RESEARCHHUB_RAG_MAX_CONTEXT_TOKENS=2600
```

On a larger production server, raise limits only after measuring available RAM and inference latency. Keep the context maximum explicit, use a dedicated Ollama host, retain a concurrency queue, and scale API/embedding work independently from generation.

## Windows monitoring

```powershell
Get-CimInstance Win32_OperatingSystem |
    Select-Object `
        @{Name="TotalRAM_GB";Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}},
        @{Name="FreeRAM_GB";Expression={[math]::Round($_.FreePhysicalMemory / 1MB, 2)}}

Get-Process |
    Sort-Object WorkingSet64 -Descending |
    Select-Object -First 15 Name,
        @{Name="RAM_MB";Expression={[math]::Round($_.WorkingSet64 / 1MB, 0)}}

ollama ps
```

Run the read-only synthetic benchmark:

```powershell
py -3.13 scripts\benchmark_context_budget.py
py -3.13 scripts\benchmark_context_budget.py --call-ollama
```

The first command never contacts Ollama or changes production data. The optional second command measures actual local inference.
