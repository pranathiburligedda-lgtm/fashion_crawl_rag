"""
TrendDesk Configuration — loads environment variables and exposes them as typed settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Google Gemini ──
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "AIzaSyANjiiqsWIGP1fMyhd-lIBqQW944KmlsZg")

# ── Pexels API ──
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")

# ── OpenAI ──
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── MongoDB Atlas ──
MONGODB_URI: str = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME: str = "trenddesk"

# ── Pinecone ──
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "trenddesk-articles")

# ── Embedding model ──
EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIMENSION: int = 1536

# ── Chat model ──
CHAT_MODEL: str = "gpt-4o-mini"

# ── CORS ──
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")

# ── Fashion sources to crawl ──
FASHION_SOURCES = [
    {
        "name": "Vogue India",
        "url": "https://www.vogue.in/fashion/trends",
        "category": "premium"
    },
    {
        "name": "Filmfare Fashion",
        "url": "https://www.filmfare.com/fashion",
        "category": "celebrity"
    },
    {
        "name": "FDCI",
        "url": "https://www.fdci.org",
        "category": "designer"
    },
    {
        "name": "Lakme Fashion Week",
        "url": "https://lakmefashionweek.co.in",
        "category": "runway"
    },
    {
        "name": "Myntra Blog",
        "url": "https://www.myntra.com/blog",
        "category": "retail"
    },
    {
        "name": "Femina Style",
        "url": "https://www.femina.in/fashion",
        "category": "lifestyle"
    },
    {
        "name": "Elle India",
        "url": "https://www.elle.in/fashion/",
        "category": "premium"
    },
    {
        "name": "Grazia India",
        "url": "https://www.grazia.co.in/fashion",
        "category": "premium"
    },
]
