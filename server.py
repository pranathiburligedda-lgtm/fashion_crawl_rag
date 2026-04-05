"""
TrendDesk FastAPI Server — Step 1
The central API that connects the frontend UI to the AI backend.

Endpoints:
  POST /api/search          — User asks a fashion question → AI answer + sources
  GET  /api/articles        — Browse crawled articles from MongoDB
  GET  /api/stats           — Dashboard stats (article count, source breakdown)
  POST /api/crawl           — Manually trigger a crawl of all 8 fashion sites
  POST /api/crawl/{source}  — Crawl a single source
  GET  /api/health          — Health check

The server also serves the frontend static files and runs a background
scheduler that triggers a full crawl every 24 hours.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from config import FRONTEND_URL, OPENAI_API_KEY, PINECONE_API_KEY, MONGODB_URI


# ══════════════════════════════════════════
#  Background Scheduler (crawl every 24h)
# ══════════════════════════════════════════

scheduler = None


def _start_scheduler():
    """Start the APScheduler background job for daily crawling."""
    global scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        async def scheduled_crawl():
            print("⏰ Scheduled crawl starting...")
            from crawler import crawl_all_sources
            await crawl_all_sources()

        scheduler.add_job(
            scheduled_crawl,
            trigger=IntervalTrigger(hours=24),
            id="daily_crawl",
            name="Daily Fashion Crawl",
            replace_existing=True,
        )
        scheduler.start()
        print("✅ Scheduler started — crawl runs every 24 hours")
    except Exception as e:
        print(f"⚠️  Scheduler init failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    print("🚀 TrendDesk API starting up...")
    _start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown()
    print("👋 TrendDesk API shutting down")


# ══════════════════════════════════════════
#  FastAPI App
# ══════════════════════════════════════════

app = FastAPI(
    title="TrendDesk API",
    description="AI-Powered Indian Fashion Trend Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the frontend to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════
#  Request / Response Models
# ══════════════════════════════════════════

class SearchRequest(BaseModel):
    question: str
    category: Optional[str] = None


class SearchResponse(BaseModel):
    answer: str
    sources: list
    question: str


# ══════════════════════════════════════════
#  API Endpoints
# ══════════════════════════════════════════

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    services = {
        "api": "ok",
        "openai": "configured" if OPENAI_API_KEY else "missing key",
        "pinecone": "configured" if PINECONE_API_KEY else "missing key",
        "mongodb": "configured" if MONGODB_URI else "missing URI",
    }
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Main search endpoint.
    User sends a fashion question → RAG pipeline → cited answer + source URLs.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Add OPENAI_API_KEY to .env",
        )

    try:
        from rag_pipeline import answer_question
        result = answer_question(request.question, category=request.category)
        return result
    except Exception as e:
        print(f"❌ Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/articles")
async def list_articles(
    source: Optional[str] = Query(None, description="Filter by source name"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200),
):
    """Browse all crawled articles."""
    from database import get_articles
    articles = await get_articles(source=source, category=category, limit=limit)
    return {"articles": articles, "count": len(articles)}


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics."""
    from database import get_article_count, get_sources_summary, get_recent_articles

    total = await get_article_count()
    sources = await get_sources_summary()
    recent = await get_recent_articles(days=7, limit=5)

    return {
        "total_articles": total,
        "sources": sources,
        "recent_articles": [
            {
                "title": a.get("title", ""),
                "source_name": a.get("source_name", ""),
                "url": a.get("url", ""),
                "crawled_at": a.get("crawled_at", ""),
            }
            for a in recent
        ],
    }


@app.post("/api/crawl")
async def trigger_crawl():
    """Manually trigger a full crawl of all 8 fashion sources."""
    from crawler import crawl_all_sources
    result = await crawl_all_sources()
    return result


@app.post("/api/crawl/{source_name}")
async def trigger_single_crawl(source_name: str):
    """Crawl a single source by name."""
    from crawler import crawl_single_source
    result = await crawl_single_source(source_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ══════════════════════════════════════════
#  Serve Frontend Static Files
# ══════════════════════════════════════════

# Serve index.html at root
@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")


# Serve other static assets (CSS, JS, images)
app.mount("/", StaticFiles(directory="."), name="static")


# ══════════════════════════════════════════
#  Run with: python server.py
# ══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🎯 TrendDesk API Server")
    print("   Frontend: http://localhost:8000")
    print("   API Docs: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
