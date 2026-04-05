"""
TrendDesk FastAPI Server
Flow: User question → Pinecone vector search → OpenAI GPT answer → cited response with source URLs.
Falls back to Gemini + Crawl4AI when OpenAI/Pinecone keys are not set.
"""
import os
import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

from config import (
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    FASHION_SOURCES,
    PEXELS_API_KEY,
)

# ── Gemini (fallback) — model cascade so quota on one model falls through ─────
import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

# Ordered list: try each model; skip to next on 429/quota error
GEMINI_MODEL_CASCADE = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]
print(f"✅ TrendDesk AI — Gemini fallback ready (cascade: {', '.join(GEMINI_MODEL_CASCADE)})")


async def _gemini_generate(prompt: str) -> str:
    """Try each Gemini model in cascade order; raise last error if all fail."""
    last_err = None
    for model_name in GEMINI_MODEL_CASCADE:
        try:
            model = genai.GenerativeModel(model_name)
            response = await model.generate_content_async(prompt)
            print(f"✅ Gemini response from: {model_name}")
            return response.text
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                print(f"⚠️  {model_name} quota hit — trying next model…")
                last_err = e
                continue
            # Non-quota error — re-raise immediately
            raise
    raise last_err or RuntimeError("All Gemini models failed")


# ── Determine which pipeline to use ───────────────────────────────────────────
USE_RAG = bool(OPENAI_API_KEY and PINECONE_API_KEY and PINECONE_INDEX_NAME)
if USE_RAG:
    print("✅ RAG Pipeline: Pinecone + OpenAI enabled")
else:
    print("⚠️  RAG Pipeline: OpenAI/Pinecone keys not set – using Gemini + Crawl4AI fallback")


# ══════════════════════════════════════════
#  App Lifecycle — Scheduler
# ══════════════════════════════════════════

from apscheduler.schedulers.asyncio import AsyncIOScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    from crawler import crawl_all_sources
    scheduler.add_job(crawl_all_sources, "interval", hours=24)
    scheduler.start()
    print("⏰ TrendDesk Scheduler Started — Daily Crawl Active")
    yield
    scheduler.shutdown()
    print("👋 TrendDesk Scheduler Stopped")


app = FastAPI(title="TrendDesk AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════
#  Data Models
# ══════════════════════════════════════════

class SearchRequest(BaseModel):
    question: str
    category: Optional[str] = None


class Source(BaseModel):
    title: str
    url: str
    source_name: str
    score: float = 1.0


class PexelsImage(BaseModel):
    url: str
    photographer: str
    photographer_url: str
    small: str


class SearchResponse(BaseModel):
    answer: str
    sources: List[Source]
    images: List[PexelsImage]
    question: str
    pipeline: str  # "rag" | "fallback"


# ══════════════════════════════════════════
#  Pexels Image Fetcher
# ══════════════════════════════════════════

async def get_pexels_images(query: str, count: int = 6) -> List[PexelsImage]:
    if not PEXELS_API_KEY:
        return []
    url = f"https://api.pexels.com/v1/search?query={query}&per_page={count}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"Authorization": PEXELS_API_KEY})
            if r.status_code == 200:
                return [
                    PexelsImage(
                        url=img["src"]["large2x"],
                        photographer=img["photographer"],
                        photographer_url=img["photographer_url"],
                        small=img["src"]["medium"],
                    )
                    for img in r.json().get("photos", [])
                ]
    except Exception as e:
        print(f"⚠️  Pexels error: {e}")
    return []


# ══════════════════════════════════════════
#  RAG Pipeline (Pinecone + OpenAI)
# ══════════════════════════════════════════

async def run_rag_pipeline(question: str, category: Optional[str] = None) -> dict:
    """
    Runs the full RAG pipeline asynchronously:
      question → OpenAI embed → Pinecone search → GPT-4o-mini answer
    Returns { answer, sources }
    """
    loop = asyncio.get_event_loop()
    from rag_pipeline import answer_question
    result = await loop.run_in_executor(None, answer_question, question, category)
    return result


# ══════════════════════════════════════════
#  Crawl4AI + Gemini Fallback
# ══════════════════════════════════════════

async def run_gemini_fallback(question: str) -> dict:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    sources_to_crawl = FASHION_SOURCES[:4]
    browser_config = BrowserConfig(headless=True, verbose=False, ignore_https_errors=True)
    crawl_config = CrawlerRunConfig(
        word_count_threshold=30,
        exclude_external_links=True,
        process_iframes=False,
        remove_overlay_elements=True,
    )

    crawled = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for s in sources_to_crawl:
            try:
                res = await crawler.arun(url=s["url"], config=crawl_config)
                if res.success:
                    crawled.append({
                        "title": f"{s['name']} — Trending Now",
                        "url": s["url"],
                        "source_name": s["name"],
                        "content": res.markdown[:3000],
                    })
                else:
                    print(f"⚠️  Crawl failed {s['name']}: {res.error_message}")
            except Exception as e:
                print(f"❌ Crawl error {s['name']}: {e}")

    if not crawled:
        return {
            "answer": "Could not retrieve fashion data from sources at the moment. Please try again shortly.",
            "sources": [],
        }

    context_text = "\n\n".join(
        f"[Source {i+1}] {s['source_name']} ({s['url']}):\n{s['content']}"
        for i, s in enumerate(crawled)
    )
    prompt = f"""You are TrendDesk AI — an expert Indian fashion trend analyst.

Question: {question}

Context from crawled fashion sites:
{context_text}

Instructions:
1. Base your answer ONLY on the provided context.
2. Format your response with clear paragraphs and bullet points for trends.
3. Use [Source N] notation inline to cite where you got each piece of information.
4. Focus on Indian fashion: ethnic wear, celebrity trends, seasonal styles.
5. Keep it professional and concise (200-400 words).
"""
    try:
        # Use the cascade — tries each model until one works
        answer = await _gemini_generate(prompt)
    except Exception as e:
        print(f"⚠️  All Gemini models failed or quota exceeded: {e}")
        answer = "Our AI text generation is currently hitting rate limits (API Quota Exceeded). However, we have successfully searched and summarized the latest trends from the web below. Click on any of the live source cards above to read the full fashion insights."

    sources = [
        {"title": s["title"], "url": s["url"], "source_name": s["source_name"], "score": 1.0}
        for s in crawled
    ]
    return {"answer": answer, "sources": sources}


# ══════════════════════════════════════════
#  API Endpoints
# ══════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "api": "TrendDesk AI",
        "pipeline": "rag" if USE_RAG else "fallback",
        "rag_ready": USE_RAG,
    }


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    try:
        # Run Pexels fetch in parallel with the RAG/fallback pipeline
        if USE_RAG:
            pipeline_label = "rag"
            rag_task = run_rag_pipeline(question, request.category)
        else:
            pipeline_label = "fallback"
            rag_task = run_gemini_fallback(question)

        pexels_task = get_pexels_images(question)
        rag_result, pexels_images = await asyncio.gather(rag_task, pexels_task)

        # Normalise sources list
        raw_sources = rag_result.get("sources", [])
        sources = []
        for s in raw_sources:
            sources.append(
                Source(
                    title=s.get("title", "Untitled"),
                    url=s.get("url", ""),
                    source_name=s.get("source_name", "Unknown"),
                    score=float(s.get("score", 1.0)),
                )
            )

        return SearchResponse(
            answer=rag_result.get("answer", ""),
            sources=sources,
            images=pexels_images,
            question=question,
            pipeline=pipeline_label,
        )

    except Exception as e:
        print(f"🔥 Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
#  Stats & Crawl Endpoints
# ══════════════════════════════════════════

@app.get("/api/stats")
async def get_stats():
    from database import get_article_count, get_sources_summary
    try:
        total = await get_article_count()
        sources = await get_sources_summary()
        return {"total_articles": total, "sources": sources, "status": "active"}
    except Exception as e:
        return {"error": str(e), "total_articles": 0, "sources": []}


@app.post("/api/crawl")
async def trigger_crawl():
    from crawler import crawl_all_sources
    asyncio.create_task(crawl_all_sources())
    return {"message": "Crawl triggered in background"}


# ══════════════════════════════════════════
#  Static File Serving
# ══════════════════════════════════════════

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

app.mount("/", StaticFiles(directory="."), name="static")


# ══════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
