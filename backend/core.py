# -*- coding: utf-8 -*-
"""النواة المشتركة: OCR + PDF + قاعدة البيانات + البحث الدلالي + الإجابة"""
import os, re, sqlite3, hashlib
from pathlib import Path
from datetime import datetime

import numpy as np
from PIL import Image
import img2pdf
import pytesseract

APP_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR  = APP_DIR / "data"
PDF_DIR   = DATA_DIR / "pdfs"
DB_PATH   = DATA_DIR / "archive.db"
PDF_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.executescript("""
CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, pdf_path TEXT, pages INTEGER,
    created_at TEXT, sha1 TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS chunks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER, page INTEGER, chunk_index INTEGER,
    text TEXT, embedding BLOB);
""")

_embedder = None
def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _embedder

def embed_texts(texts):
    m = get_embedder()
    return m.encode(texts, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

def chunk_text(text, max_chars=900, overlap=150):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) <= max_chars:
            buf = (buf + "\n" + p).strip()
        else:
            if buf: chunks.append(buf)
            buf = p
    if buf: chunks.append(buf)
    final = []
    for c in chunks:
        while len(c) > max_chars + overlap:
            cut = c.rfind(" ", 0, max_chars)
            final.append(c[:cut]); c = c[cut - overlap:]
        final.append(c)
    return final

def ocr_image(img, langs="ara+eng"):
    return pytesseract.image_to_string(img, lang=langs)

def ingest_document(title, images: list):
    """images: قائمة من PIL.Image — تُرجع dict معلومات أو None لو مكرر"""
    sha = hashlib.sha1(b"".join(img.tobytes() for img in images)).hexdigest()
    if conn.execute("SELECT id FROM documents WHERE sha1=?", (sha,)).fetchone():
        return None
    safe = re.sub(r'[^\w\u0600-\u06FF.-]+', '_', title)[:60]
    pdf_path = PDF_DIR / f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([im.convert("RGB") for im in images]))

    cur = conn.execute(
        "INSERT INTO documents(title,pdf_path,pages,created_at,sha1) VALUES(?,?,?,?,?)",
        (title, str(pdf_path), len(images), datetime.now().isoformat(), sha))
    doc_id = cur.lastrowid

    for i, img in enumerate(images, start=1):
        chunks = chunk_text(ocr_image(img))
        if not chunks:
            continue
        embs = embed_texts(chunks)
        conn.executemany(
            "INSERT INTO chunks(doc_id,page,chunk_index,text,embedding) VALUES(?,?,?,?,?)",
            [(doc_id, i, j, c, e.tobytes()) for j, (c, e) in enumerate(zip(chunks, embs))])
    conn.commit()
    return {"doc_id": doc_id, "pdf": str(pdf_path), "pages": len(images)}

def search_chunks(query, top_k=4):
    q = embed_texts([query])[0]
    rows = conn.execute(
        "SELECT c.id, d.title, c.page, c.text, c.embedding "
        "FROM chunks c JOIN documents d ON d.id=c.doc_id").fetchall()
    if not rows:
        return []
    mat = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
    scores = mat @ q
    best = np.argsort(-scores)[:top_k]
    return [{"chunk_id": int(rows[i][0]), "title": rows[i][1],
             "page": int(rows[i][2]), "text": rows[i][3],
             "score": float(scores[i])} for i in best]

def ask_llm(prompt, base_url, api_key, model):
    import requests
    r = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        json={"model": model,
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.1},
        timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def answer_question(question, llm_cfg, top_k=4):
    results = search_chunks(question, top_k)
    if not results:
        return {"answer": "لا توجد بيانات في الأرشيف بعد.", "sources": []}
    ctx = "\n\n".join(
        f"[المصدر {i+1}: {r['title']} — صفحة {r['page']}]\n{r['text']}"
        for i, r in enumerate(results))
    prompt = f"""أنت مساعد أرشيف دقيق. أجب على السؤال أدناه **فقط** انطلاقاً من النصوص المرفقة.
- إن لم توجد الإجابة في النصوص فقل بوضوح: «لا توجد معلومة عن ذلك في الأرشيف».
- أرفق استشهاداً بعد كل معلومة بصيغة: [المصدر: العنوان — صفحة X].
- لا تخترع أي معلومة خارج النصوص.

=== النصوص ===
{ctx}

=== السؤال ===
{question}"""
    answer = ask_llm(prompt, **llm_cfg)
    return {"answer": answer, "sources": results}
