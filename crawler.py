"""
TrendDesk Crawler — Step 2
Crawls 8 Indian fashion websites using crawl4ai and stores articles in MongoDB Atlas.
Can be run standalone or triggered from the FastAPI scheduler.

Each crawled page is:
1.  Rendered with crawl4ai (handles JS-heavy sites)
2.  Cleaned into markdown text
3.  Split into individual article chunks
4.  Stored in MongoDB with title, content, URL, date, source_name, and category tags
5.  Embedded via OpenAI and upserted into Pinecone for RAG search
"""
import asyncio
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from config import (
    FASHION_SOURCES,
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)

# ── Optional imports (graceful if keys are missing) ──
openai_client = None
pinecone_index = None


def _init_openai():
    global openai_client
    if openai_client is None and OPENAI_API_KEY:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return openai_client


def _init_pinecone():
    global pinecone_index
    if pinecone_index is None and PINECONE_API_KEY:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        # Create index if it doesn't exist
        existing = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing:
            from pinecone import ServerlessSpec
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            print(f"✅ Created Pinecone index '{PINECONE_INDEX_NAME}'")
        pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return pinecone_index


# ══════════════════════════════════════════
#  Text Processing Helpers
# ══════════════════════════════════════════

def _extract_articles_from_markdown(markdown: str, source_name: str, source_url: str, category: str):
    """
    Split a page's markdown into individual article chunks.
    Each chunk becomes one document in the database.
    """
    # Split on markdown headings (##, ###) — each heading = new article
    sections = re.split(r'\n(?=#{1,3}\s)', markdown)

    articles = []
    for section in sections:
        section = section.strip()
        if len(section) < 80:
            continue  # skip tiny fragments

        # Extract title from first heading or first line
        title_match = re.match(r'^#{1,3}\s+(.*)', section)
        title = title_match.group(1).strip() if title_match else section[:100].strip()

        # Clean the content
        content = section
        # Remove image markdown
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        # Remove excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()

        if len(content) < 50:
            continue

        # Generate a stable ID from URL + title
        doc_id = hashlib.md5(f"{source_url}:{title}".encode()).hexdigest()

        articles.append({
            "doc_id": doc_id,
            "title": title[:300],
            "content": content[:5000],  # cap at 5000 chars
            "url": source_url,
            "source_name": source_name,
            "category": category,
            "crawled_at": datetime.now(timezone.utc),
        })

    return articles


def _get_embedding(text: str) -> Optional[list]:
    """Generate an embedding vector for a text chunk using OpenAI."""
    client = _init_openai()
    if not client:
        return None
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # model token limit safety
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"  ⚠️  Embedding error: {e}")
        return None


async def _upsert_to_pinecone(articles: list):
    """Embed articles and upsert vectors into Pinecone."""
    index = _init_pinecone()
    if not index:
        print("  ⏭️  Skipping Pinecone (no API key configured)")
        return

    vectors = []
    for article in articles:
        text_for_embedding = f"{article['title']}\n\n{article['content']}"
        embedding = _get_embedding(text_for_embedding)
        if embedding is None:
            continue

        vectors.append({
            "id": article["doc_id"],
            "values": embedding,
            "metadata": {
                "title": article["title"][:200],
                "url": article["url"],
                "source_name": article["source_name"],
                "category": article["category"],
                "content": article["content"][:2000],  # Pinecone metadata size limit
                "crawled_at": article["crawled_at"].isoformat(),
            },
        })

    if vectors:
        # Upsert in batches of 50
        for i in range(0, len(vectors), 50):
            batch = vectors[i : i + 50]
            index.upsert(vectors=batch)
        print(f"  📌 Upserted {len(vectors)} vectors to Pinecone")


# ══════════════════════════════════════════
#  Main Crawl Function
# ══════════════════════════════════════════

async def crawl_all_sources():
    """
    Crawl all 8 Indian fashion websites, extract articles,
    save to MongoDB, and index in Pinecone.
    Returns a summary dict.
    """
    # Lazy import to avoid circular dependency when used from server.py
    from database import save_article

    print("=" * 60)
    print(f"🕷️  TrendDesk Daily Crawl — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    total_articles = 0
    source_results = []

    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
    )

    crawl_config = CrawlerRunConfig(
        word_count_threshold=30,
        excluded_tags=["nav", "footer", "header", "aside"],
        exclude_external_links=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for source in FASHION_SOURCES:
            name = source["name"]
            url = source["url"]
            category = source["category"]

            print(f"\n🌐 Crawling: {name} ({url})")
            try:
                result = await crawler.arun(
                    url=url,
                    config=crawl_config,
                )

                if not result.success:
                    print(f"  ❌ Failed: {result.error_message}")
                    source_results.append({"source": name, "status": "failed", "articles": 0})
                    continue

                markdown_content = result.markdown or ""
                print(f"  📄 Got {len(markdown_content)} chars of content")

                # Extract individual articles
                articles = _extract_articles_from_markdown(
                    markdown_content, name, url, category
                )
                print(f"  📰 Extracted {len(articles)} article chunks")

                # Save each article to MongoDB
                for article in articles:
                    await save_article(article)

                # Index in Pinecone (vector embeddings)
                await _upsert_to_pinecone(articles)

                total_articles += len(articles)
                source_results.append({
                    "source": name,
                    "status": "success",
                    "articles": len(articles),
                })

            except Exception as e:
                print(f"  ❌ Error crawling {name}: {e}")
                source_results.append({"source": name, "status": "error", "articles": 0, "error": str(e)})

    print(f"\n{'=' * 60}")
    print(f"✅ Crawl complete — {total_articles} total articles saved")
    print("=" * 60)

    return {
        "total_articles": total_articles,
        "sources": source_results,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


async def crawl_single_source(source_name: str):
    """Crawl a single source by name. Useful for testing."""
    source = next((s for s in FASHION_SOURCES if s["name"] == source_name), None)
    if not source:
        return {"error": f"Source '{source_name}' not found"}

    from database import save_article

    browser_config = BrowserConfig(headless=True, verbose=False)
    crawl_config = CrawlerRunConfig(
        word_count_threshold=30,
        excluded_tags=["nav", "footer", "header", "aside"],
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=source["url"], config=crawl_config)
        if not result.success:
            return {"error": result.error_message}

        articles = _extract_articles_from_markdown(
            result.markdown or "", source["name"], source["url"], source["category"]
        )
        for article in articles:
            await save_article(article)

        await _upsert_to_pinecone(articles)
        return {"source": source["name"], "articles_saved": len(articles)}


# ── Run standalone ──
if __name__ == "__main__":
    asyncio.run(crawl_all_sources())
