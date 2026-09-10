# -*- coding: utf-8 -*-
"""خادم FastAPI — يعمل على الكمبيوتر/السيرفر ويخدم تطبيق الأندرويد"""
import io, os
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import uvicorn

from core import ingest_document, search_chunks, answer_question

app = FastAPI(title="أرشيف الذكي API")

# اسمح لأي جهاز على الشبكة المحلية بالاتصال
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

LLM_CFG = {
    "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
    "api_key":  os.getenv("LLM_API_KEY", ""),
    "model":    os.getenv("LLM_MODEL", "llama3.1:8b"),
}

@app.post("/upload")
async def upload(title: str = Form(...), files: List[UploadFile] = File(...)):
    images = []
    for f in files:
        try:
            images.append(Image.open(io.BytesIO(await f.read())))
        except Exception:
            raise HTTPException(400, f"ملف غير مدعوم: {f.filename}")
    result = ingest_document(title, images)
    if result is None:
        return {"status": "duplicate", "message": "المستند موجود مسبقاً"}
    return {"status": "ok", **result}

@app.get("/search")
def search(q: str, top_k: int = 8):
    return {"results": search_chunks(q, top_k)}

@app.get("/ask")
def ask(q: str):
    try:
        return answer_question(q, LLM_CFG)
    except Exception as e:
        raise HTTPException(502, f"تعذر الاتصال بنموذج اللغة: {e}")

@app.get("/stats")
def stats():
    import core
    return {
        "documents": core.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks":    core.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
    }

if __name__ == "__main__":
    # host="0.0.0.0" حتى يصل إليه الهاتف عبر Wi-Fi
    uvicorn.run(app, host="0.0.0.0", port=8000)
