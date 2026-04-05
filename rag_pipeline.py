"""
TrendDesk RAG Pipeline — the "AI brain".
1. Takes a user question
2. Embeds the question via OpenAI
3. Searches Pinecone for the most relevant fashion articles
4. Sends the matched articles + question to GPT-4o-mini
5. Returns a cited answer with source URLs
"""
from typing import Optional
from config import (
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL,
    CHAT_MODEL,
)

# ── Lazy singletons ──
_openai_client = None
_pinecone_index = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _get_pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


# ══════════════════════════════════════════
#  Core RAG functions
# ══════════════════════════════════════════

def embed_query(text: str) -> list:
    """Generate embedding vector for the user's question."""
    client = _get_openai()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000],
    )
    return response.data[0].embedding


def search_pinecone(query_vector: list, top_k: int = 5, category: Optional[str] = None) -> list:
    """
    Search Pinecone for the most relevant article chunks.
    Returns a list of dicts with title, content, url, source_name, score.
    """
    index = _get_pinecone()

    filter_dict = {}
    if category:
        filter_dict["category"] = category

    results = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict if filter_dict else None,
    )

    matches = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        matches.append({
            "title": meta.get("title", "Untitled"),
            "content": meta.get("content", ""),
            "url": meta.get("url", ""),
            "source_name": meta.get("source_name", "Unknown"),
            "category": meta.get("category", ""),
            "score": round(match.get("score", 0), 4),
        })
    return matches


def generate_answer(question: str, context_articles: list) -> str:
    """
    Send the user question + retrieved article context to GPT-4o-mini
    and generate a fashion trend answer with citations.
    """
    client = _get_openai()

    # Build context block from retrieved articles
    context_parts = []
    for i, article in enumerate(context_articles, 1):
        context_parts.append(
            f"[Source {i}] {article['source_name']} — {article['title']}\n"
            f"URL: {article['url']}\n"
            f"Content: {article['content'][:1500]}\n"
        )

    context_block = "\n---\n".join(context_parts)

    system_prompt = """You are TrendDesk AI — an expert Indian fashion trend analyst.

Your job is to answer user questions about Indian fashion trends using ONLY the provided source articles.

RULES:
1. Base your answer ONLY on the provided source articles
2. Cite sources using [Source N] notation at the end of relevant sentences
3. If the sources don't contain relevant information, say so honestly
4. Focus on Indian fashion context — kurtis, sarees, lehengas, ethnic wear, etc.
5. Provide specific, actionable trend insights
6. Use bullet points for clarity when listing trends
7. Mention specific colors, fabrics, patterns, and styles when available
8. Keep your answer concise but comprehensive (200-400 words)
"""

    user_message = f"""Question: {question}

Here are the most relevant articles from our fashion knowledge base:

{context_block}

Based on these sources, provide a comprehensive answer about Indian fashion trends."""

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.4,
        max_tokens=800,
    )

    return response.choices[0].message.content


# ══════════════════════════════════════════
#  High-level API
# ══════════════════════════════════════════

def answer_question(question: str, category: Optional[str] = None) -> dict:
    """
    Full RAG pipeline:
    question → embed → search Pinecone → GPT-4o-mini → cited answer.

    Returns:
    {
        "answer": "...",
        "sources": [ {title, url, source_name, score}, ... ],
        "question": "..."
    }
    """
    # 1. Embed the question
    query_vector = embed_query(question)

    # 2. Search Pinecone for relevant articles
    matches = search_pinecone(query_vector, top_k=5, category=category)

    if not matches:
        return {
            "answer": "I couldn't find any relevant fashion articles in our database yet. "
                      "Please run the crawler first to populate the knowledge base, "
                      "or try a different question.",
            "sources": [],
            "question": question,
        }

    # 3. Generate answer with citations
    answer = generate_answer(question, matches)

    # 4. Build source list (deduplicated by URL)
    seen_urls = set()
    sources = []
    for m in matches:
        if m["url"] not in seen_urls:
            seen_urls.add(m["url"])
            sources.append({
                "title": m["title"],
                "url": m["url"],
                "source_name": m["source_name"],
                "score": m["score"],
            })

    return {
        "answer": answer,
        "sources": sources,
        "question": question,
    }
