Candidate use cases for SIE on M5/16GB 
Use Case #1:
Local RAG over your ~/Documents

 Index every PDF, markdown, txt, and docx in a folder. Query it from the terminal or any OpenAI-compatible client. Fully private, zero per-query cost.

 Why it works on M5/16GB: bge-m3 (~2.3GB) + a small reranker (~100MB) = leaves ~13GB free for OS, browser, IDE, and the vector DB itself (Qdrant runs fine in-memory for tens of thousands of chunks).

 What you get: A private, semantic search engine for everything you've ever saved. "Find that paper about vector quantization" instead of grep.

