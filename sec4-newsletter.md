Work on a plan to implement this segment to the existing local-rag app. Document everything and keep it current. Always provide clear instructions.
 4. Newsletter / paper digestor

 Inbox → SIE classifies + summarizes + extracts key entities + pushes a daily digest. Uses the structured-output model (gliner2/qwen3-4b) to tag by topic, importance, action-required.

How the Local Pipeline Works:
1. Ingestion & Classification: Incoming newsletters, emails, or PDF research papers are automatically monitored and passed into the pipeline, where a small classification model categorizes them by topic and urgency.
2. Structured Entity Extraction: An extraction model (such as gliner_multi-v2.1) identifies key entities, organizations, authors, and actionable items, tagging them zero-shot for downstream indexing.
3. Summarization & Synthesis: A local LLM (such as a 4-bit quantized Qwen3-4B) synthesizes the extracted sections into highly concise, bulleted summaries tailored directly to your interest profile.

Why it works on M5/16GB:
Small classifier + small summarizer is a perfect fit. The agent loop on a 4-bit Qwen3-4B is highly workable for short summarization tasks. Because documents are processed asynchronously in small batches, memory usage remains extremely low (~3GB total for the entire pipeline), preventing system slowdowns during background execution.

What you get:
A triage layer for information overload. The 27B model would be better for complex multi-document reasoning, but the 4B is fully sufficient for short-form extraction, automated tagging, and clean daily digests without any external API latency or privacy leaks.

