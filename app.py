from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
import traceback
import PyPDF2
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import math
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from duckduckgo_search import DDGS

app = Flask(__name__, static_folder=".")
CORS(app)

# Configure Gemini
api_key = "AIzaSyBWn69P1lh_khlxiXBIJtpbtmxS2h8zgT4"
client = genai.Client(api_key=api_key)

# Store chat sessions per user (simple in-memory store)
chat_sessions = {}
# Store documents (embeddings and text chunks) per user
document_store = {}

def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += (chunk_size - overlap)
    return chunks

def extract_urls(text):
    return re.findall(r'(https?://\S+)', text)

async def run_crawl4ai(urls):
    content = ""
    async with AsyncWebCrawler() as crawler:
        for url in urls:
            try:
                result = await crawler.arun(url=url)
                if result and result.markdown:
                    # Limit each page context to 3000 chars to fit in prompt easily
                    content += f"--- Real-time Web Content from {url} ---\n{result.markdown[:3000]}\n\n"
            except Exception as e:
                print(f"DEBUG: crawl4ai error on {url}: {e}")
    return content

def perform_web_search_and_crawl(query):
    try:
        results = DDGS().text(query, max_results=2)
        urls = [r['href'] for r in results]
        if urls:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(run_crawl4ai(urls)), urls
    except Exception as e:
        print(f"DEBUG: DDGS error: {e}")
    return "", []

def crawl_provided_urls(urls):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(run_crawl4ai(urls))

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)

@app.route("/api/upload", methods=["POST"])
def upload_file():
    session_id = request.form.get("session_id", "default")
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400

    try:
        import io
        import time
        file_content = file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"

        if not text.strip():
            return jsonify({"error": "No text found in PDF (e.g., scanned image or empty). Please upload a text-searchable PDF."}), 400

        # Chunk text
        chunks = chunk_text(text)
        
        # Limit the number of chunks to avoid hitting free API key rate limits immediately
        if len(chunks) > 40:
            chunks = chunks[:40]
        
        # Embed chunks using Google GenAI
        embeddings = []
        for i, chunk in enumerate(chunks):
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=chunk
            )
            embeddings.append(response.embeddings[0].values)
            time.sleep(0.3) # respect API rate limits
            
        embeddings_np = np.array(embeddings)
        
        document_store[session_id] = {
            "chunks": chunks,
            "embeddings": embeddings_np
        }

        return jsonify({"status": "File processed successfully", "chunks_count": len(chunks)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Server encountered an error: {str(e)}"}), 500

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
        
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    persona = data.get("persona", "Assistant")
    language = data.get("language", "English")

    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    try:
        # Check if we have documents for this session
        context = ""
        if session_id in document_store:
            # Embed user query
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=user_message
            )
            query_embedding = np.array([response.embeddings[0].values])
            
            # Compute similarity
            doc_embeddings = document_store[session_id]["embeddings"]
            similarities = cosine_similarity(query_embedding, doc_embeddings)[0]
            
            # Get top 3 chunks
            top_k = 3
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            chunks = document_store[session_id]["chunks"]
            retrieved_chunks = [chunks[i] for i in top_indices if similarities[i] > 0.2] # simple threshold
            
            if retrieved_chunks:
                context = "Use the following extracted information from the uploaded document to help answer the user's question:\n\n"
                for i, chunk in enumerate(retrieved_chunks):
                    context += f"--- Document excerpt {i+1} ---\n{chunk}\n\n"

        # Integrate Crawl4AI Web context
        urls_in_query = extract_urls(user_message)
        web_context = ""
        crawled_urls = []
        if urls_in_query:
            web_context = crawl_provided_urls(urls_in_query)
            crawled_urls = urls_in_query
        elif len(user_message) > 8:
            # Auto search for queries
            web_context, crawled_urls = perform_web_search_and_crawl(user_message)

        if web_context:
            context += "Use the following real-time web search results to supplement your knowledge:\n\n" + web_context

        # Get or create a chat session for persistent context
        if session_id not in chat_sessions:
            chat_sessions[session_id] = client.chats.create(model="gemini-2.5-flash")

        chat_session = chat_sessions[session_id]
        
        system_instruction = f"You are a helpful {persona}. Set your internal tone and language strictly to {language}.\n"

        # Prepend context to the user message if available
        if context:
            full_message = f"{system_instruction}{context}User's Input:\n{user_message}"
        else:
            full_message = f"{system_instruction}User's Input:\n{user_message}"
            
        response = chat_session.send_message(full_message)

        return jsonify({
            "reply": response.text,
            "session_id": session_id,
            "sources": crawled_urls
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/clear", methods=["POST"])
def clear_session():
    data = request.get_json()
    if not data:
         data = {}
    session_id = data.get("session_id", "default")
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    if session_id in document_store:
        del document_store[session_id]
    return jsonify({"status": "cleared"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
