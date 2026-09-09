"""Static-analysis tables: how lab code and dependencies map to components.

Detected components are always re-derived from the corpus source on every
run, so they never go stale. Curated data (corpora/<name>/<vN>/data/flows.yaml) can add
components static analysis cannot see (components_extra) or remove false
positives (components_suppress).
"""

import re

# Fixed component vocabulary: slug -> (display label, tooltip).
COMPONENTS: dict[str, tuple[str, str]] = {
    "llm": ("LLM", "Chat or completion calls to a large language model"),
    "prompting": ("Prompting", "Prompt technique: zero-shot, few-shot, system prompts, CoT"),
    "embeddings": ("Embeddings", "Text converted to vectors for similarity"),
    "vector-db": ("Vector DB", "ChromaDB vector storage and similarity search"),
    "rag": ("RAG", "Retrieval-augmented generation: retrieve, then answer"),
    "retrieval": ("Retrieval", "Search strategy work: BM25, hybrid, re-ranking"),
    "tool-calling": ("Tool calling", "LLM requests execution of declared tools or functions"),
    "agents": ("Agent", "LLM loop that plans and acts with tools"),
    "multi-agent": ("Multi-agent", "Multiple agents cooperating or delegating"),
    "mcp": ("MCP", "Model Context Protocol servers and clients"),
    "a2a": ("A2A", "Agent2Agent protocol between independent agents"),
    "memory": ("Memory", "Conversation state across turns: checkpoints, summarization"),
    "structured-output": ("Structured output", "JSON mode or schema-validated responses"),
    "guardrails": ("Guardrails", "Input/output validation and fail-closed handling"),
    "security": ("Security", "Prompt injection, allowlists, adversarial robustness"),
    "observability": ("Observability", "Tracing and spans via OpenTelemetry"),
    "evaluation": ("Evaluation", "Retrieval metrics and LLM-as-judge scoring"),
    "fine-tuning": ("Fine-tuning", "Training model weights (LoRA)"),
    "cost": ("Token & cost", "Token counting, trimming, caching, batching"),
    "streaming": ("Streaming", "Token-by-token streamed responses"),
    "hitl": ("Human-in-the-loop", "Approval gates before a tool runs"),
    "ui": ("UI", "Streamlit user interface"),
    "http-service": ("HTTP service", "FastAPI web service wrapper"),
    "gateway": ("Gateway", "Multi-provider routing and failover"),
}

# Normalized lab pyproject dependency name -> components it implies.
DEP_COMPONENTS: dict[str, list[str]] = {
    "openai": ["llm"],
    "anthropic": ["llm"],
    "ollama": ["llm"],
    "langchain": ["llm"],
    "langchain-openai": ["llm"],
    "langchain-anthropic": ["llm"],
    "langchain-ollama": ["llm"],
    "chromadb": ["vector-db", "embeddings"],
    "rank-bm25": ["retrieval"],
    "mcp": ["mcp"],
    "langchain-mcp-adapters": ["mcp"],
    "a2a-sdk": ["a2a", "multi-agent"],
    "traceloop-sdk": ["observability"],
    "pydantic": ["structured-output"],
    "tiktoken": ["cost"],
    "torch": ["fine-tuning"],
    "transformers": ["fine-tuning"],
    "peft": ["fine-tuning"],
    "streamlit": ["ui"],
    "fastapi": ["http-service"],
}

# Regexes run over the concatenated *.py sources of a lab.
CODE_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"create_agent|AgentExecutor"), ["agents"]),
    (re.compile(r"@tool\b|\btools\s*=|tool_calls|tool_call\b|\btool_use\b"), ["tool-calling"]),
    (re.compile(r"FastMCP|MultiServerMCPClient|mcp[-_.]server"), ["mcp"]),
    (re.compile(r"InMemorySaver|MemorySaver|checkpointer|SummarizationMiddleware"), ["memory"]),
    (re.compile(r"HumanInTheLoopMiddleware|langgraph\.types import Command"), ["hitl"]),
    (re.compile(r"ALLOWED_|allowlist|injection", re.IGNORECASE), ["security"]),
    (re.compile(r"[Gg]uard"), ["guardrails"]),
    (re.compile(r"model_validate|response_format|json_object|\"format\"\s*:\s*\"json\""), ["structured-output"]),
    (re.compile(
        r"embeddings\.create|/api/embeddings|embed_query|embed_documents"
        r"|OllamaEmbeddings|OpenAIEmbeddings|nomic-embed-text|text-embedding-3"
    ), ["embeddings"]),
    (re.compile(r"judge|precision|recall", re.IGNORECASE), ["evaluation"]),
    (re.compile(r"stream=True|messages\.stream|\"stream\"\s*:\s*True"), ["streaming"]),
    (re.compile(r"FALLBACK_PROVIDER|failover", re.IGNORECASE), ["gateway"]),
]

# Providers detected via literal strings in lab code.
PROVIDERS = ["ollama", "openai", "anthropic"]

# Floor components for concept-only chapters (no lab code to fingerprint),
# keyed on keywords in title + description. Curation is the real source here.
DOC_KEYWORDS: dict[str, list[str]] = {
    "agent": ["agents"],
    "responsib": ["guardrails"],
    "llm": ["llm"],
    "language model": ["llm"],
}
