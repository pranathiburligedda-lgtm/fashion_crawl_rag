"""
TrendDesk Database Module — MongoDB Atlas connection + article CRUD operations.
Uses Motor (async MongoDB driver) for non-blocking operations with FastAPI.
"""
import motor.motor_asyncio
from datetime import datetime, timezone
from typing import Optional
from config import MONGODB_URI, MONGODB_DB_NAME


# ── Lazy connection (created on first import) ──
client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
db = None


def get_db():
    """Return the database handle, creating the connection if needed."""
    global client, db
    if not MONGODB_URI:
        return None
    if client is None:
        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
            db = client[MONGODB_DB_NAME]
            print(f"✅ Connected to MongoDB Atlas: {MONGODB_DB_NAME}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return None
    return db


# ══════════════════════════════════════════
#  Article CRUD
# ══════════════════════════════════════════

async def save_article(article: dict) -> str:
    """
    Insert or update a crawled article.
    """
    database = await get_db()
    if not database:
        return "skipped"
    
    collection = database["articles"]
    article["updated_at"] = datetime.now(timezone.utc)
    if "crawled_at" not in article:
        article["crawled_at"] = datetime.now(timezone.utc)

    result = await collection.update_one(
        {"url": article["url"]},
        {"$set": article},
        upsert=True,
    )
    return str(result.upserted_id or "updated")


async def get_articles(
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
):
    """Fetch articles from the database, optionally filtered."""
    database = await get_db()
    if not database:
        return []
    
    collection = database["articles"]
    query = {}
    if source:
        query["source_name"] = source
    if category:
        query["category"] = category

    cursor = collection.find(query).sort("crawled_at", -1).limit(limit)
    articles = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        articles.append(doc)
    return articles


async def get_article_count() -> int:
    """Total number of crawled articles in the database."""
    database = await get_db()
    if not database:
        return 0
    return await database["articles"].count_documents({})


async def get_recent_articles(days: int = 7, limit: int = 20):
    """Return articles from the past N days."""
    database = await get_db()
    if not database:
        return []
        
    collection = database["articles"]
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = (
        collection.find({"crawled_at": {"$gte": cutoff}})
        .sort("crawled_at", -1)
        .limit(limit)
    )
    articles = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        articles.append(doc)
    return articles


async def get_db():
    """Return the database handle, creating the connection if needed."""
    global client, db
    if not MONGODB_URI:
        return None
    if client is None:
        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
            db = client[MONGODB_DB_NAME]
            
            # Setup Indexes (Knowledge Bank)
            await db["articles"].create_index("url", unique=True)
            await db["articles"].create_index([("title", "text"), ("content", "text")])
            
            print(f"✅ Connected to MongoDB Atlas & Initialized Knowledge Bank: {MONGODB_DB_NAME}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return None
    return db


async def search_knowledge_bank(query: str, limit: int = 5):
    """Search for relevant articles in the fashion knowledge bank."""
    database = await get_db()
    if not database:
        return []
        
    collection = database["articles"]
    # Using MongoDB Text Search
    cursor = collection.find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"}}
    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
    
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


async def get_sources_summary():
    """Return article counts grouped by source_name."""
    database = await get_db()
    if not database:
        return []
        
    pipeline = [
        {"$group": {"_id": "$source_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = []
    async for doc in database["articles"].aggregate(pipeline):
        results.append({"source": doc["_id"], "count": doc["count"]})
    return results
