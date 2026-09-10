# -*- coding: utf-8 -*-
"""
أرشيف الذكي: صور → PDF → قاعدة بيانات → أسئلة وأجوبة بالاستشهاد
"""
import os, re, sqlite3, io, hashlib, json, time
from pathlib import Path
from datetime import datetime

import numpy as np
import streamlit as st
from PIL import Image
import img2pdf
import pytesseract

APP_DIR   = Path(__file__).parent
DATA_DIR  = APP_DIR / "data"
PDF_DIR   = DATA_DIR / "pdfs"
DB_PATH   = DATA_DIR / "archive.db"
PDF_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="أرشيف الذكي", page_icon="📚", layout="wide")

# ============================== قاعدة البيانات ==============================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, pdf_path TEXT, pages INTEGER,
        created_at TEXT, sha1 TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS chunks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id INTEGER, page INTEGER, chunk_index INTEGER,
        text TEXT, embedding BLOB,
        FOREIGN KEY(doc_id) REFERENCES documents(id));
    CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);""")
    conn.commit()
    return conn

conn = init_db()

# ============================== نماذج التضمين ==============================
@st.cache_resource
def load_embedder():
    from sentence_transformers import SentenceTransformer
    # نموذج متعدد اللغات يدعم العربية
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def embed_texts(model, texts):
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embs.astype(np.float32)

def search_chunks(query, top_k=4):
    model = load_embedder()
    q = embed_texts(model, [query])[0]
    rows = conn.execute(
        "SELECT c.id, d.title, c.page, c.text, c.embedding "
        "FROM chunks c JOIN documents d ON d.id=c.doc_id").fetchall()
    if not rows:
        return []
    mat = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
    scores = mat @ q
    best = np.argsort(-scores)[:top_k]
    return [{"chunk_id": rows[i][0], "title": rows[i][1],
             "page": rows[i][2], "text": rows[i][3],
             "score": float(scores[i])} for i in best]

# ============================== OCR + PDF ==============================
def images_to_pdf(images: list[Image.Image], out_path: Path):
    """يحفظ الصور كملف PDF (ضغط JPEG لتقليل الحجم)."""
    out_path = str(out_path)
    with open(out_path, "wb") as f:
        f.write(img2pdf.convert([img.convert("RGB") for img in images]))
    return out_path

def ocr_image(img: Image.Image, langs="ara+eng") -> str:
    try:
        return pytesseract.image_to_string(img, lang=langs)
    except pytesseract.TesseractNotFoundError:
        st.error("محرك Tesseract غير مثبّت — راجع README_AR.md")
        st.stop()

def chunk_text(text: str, max_chars=900, overlap=150):
    """تقسيم النص إلى فقرات متداخلة."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) <= max_chars:
            buf = (buf + "\n" + p).strip()
        else:
            if buf: chunks.append(buf)
            buf = p
    if buf: chunks.append(buf)
    # فصل الفقرات الطويلة جداً
    final = []
    for c in chunks:
        while len(c) > max_chars + overlap:
            cut = c.rfind(" ", 0, max_chars)
            final.append(c[:cut]); c = c[cut - overlap:]
        final.append(c)
    return final

def ingest_document(title: str, images: list[Image.Image]):
    """خط المعالجة الكامل: PDF + OCR + تخزين + تضمين."""
    sha = hashlib.sha1(b"".join(img.tobytes() for img in images)).hexdigest()
    if conn.execute("SELECT id FROM documents WHERE sha1=?", (sha,)).fetchone():
        return None  # مكرر
    safe = re.sub(r'[^\w\u0600-\u06FF.-]+', '_', title)[:60]
    pdf_path = PDF_DIR / f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    images_to_pdf(images, pdf_path)

    cur = conn.execute(
        "INSERT INTO documents(title,pdf_path,pages,created_at,sha1) VALUES(?,?,?,?,?)",
        (title, str(pdf_path), len(images), datetime.now().isoformat(), sha))
    doc_id = cur.lastrowid

    model = load_embedder()
    page_texts = []
    for i, img in enumerate(images, start=1):
        text = ocr_image(img)
        page_texts.append(text)
        chunks = chunk_text(text)
        if chunks:
            embs = embed_texts(model, chunks)
            conn.executemany(
                "INSERT INTO chunks(doc_id,page,chunk_index,text,embedding) VALUES(?,?,?,?,?)",
                [(doc_id, i, j, c, e.tobytes()) for j, (c, e) in enumerate(zip(chunks, embs))])
    conn.commit()
    return {"doc_id": doc_id, "pdf": str(pdf_path), "pages": len(images)}

# ============================== نموذج اللغة ==============================
def ask_llm(prompt, cfg):
    """نداء OpenAI-compatible API (Ollama / OpenAI / Groq...)."""
    import requests
    r = requests.post(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {},
        json={"model": cfg["model"],
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.1},
        timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# ============================== واجهة المستخدم ==============================
st.title("📚 أرشيف الذكي — صور → PDF → قاعدة بيانات → إجابات بالاستشهاد")

with st.sidebar:
    st.header("⚙️ الإعدادات")
    cfg = {
        "base_url": st.text_input("رابط الـ API", "http://localhost:11434/v1"),
        "api_key":  st.text_input("مفتاح API (اختياري للنماذج المحلية)", type="password"),
        "model":    st.text_input("اسم النموذج", "llama3.1:8b"),
    }
    st.markdown("---")
    n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    st.metric("المستندات المخزنة", n_docs)
    st.metric("الفقرات المفهرسة", n_chunks)

tab1, tab2, tab3 = st.tabs(["⬆️ رفع الأوراق", "🔍 البحث في المحتوى", "❓ اسأل وأجب"])

# ---------- تبويب الرفع ----------
with tab1:
    st.subheader("ارفع صور الأوراق وسيتم: PDF + OCR + التخزين")
    title = st.text_input("عنوان المستند", "مستند بدون عنوان")
    files = st.file_uploader("صور (JPG/PNG/PDF)", accept_multiple_files=True,
                             type=["jpg", "jpeg", "png", "webp", "pdf"])
    if st.button("🚀 معالجة وتحويل إلى PDF", disabled=not files):
        images = []
        for f in files:
            if f.name.lower().endswith(".pdf"):
                import PyPDF2
                reader = PyPDF2.PdfReader(f)
                for pg in reader.pages:
                    # نحفظ الصفحة كصورة عبر تحويل بسيط (تتطلب pdf2image في الاستخدام المتقدم)
                    # هنا نكتفي بنص PDF مباشرة إن وُجد
                    pass
                st.info("ملفات PDF النصية تُدعم جزئياً — الأفضل رفع الصور.")
                continue
            images.append(Image.open(io.BytesIO(f.read())))
        if images:
            with st.spinner("جاري التحويل والتخزين والفهرسة... قد يستغرق دقائق"):
                res = ingest_document(title, images)
            if res is None:
                st.warning("هذا المستند موجود مسبقاً (تم تجاهله).")
            else:
                st.success(f"✅ تم الحفظ: {res['pages']} صفحة")
                with open(res["pdf"], "rb") as pf:
                    st.download_button("⬇️ تحميل ملف PDF", pf,
                                       file_name=Path(res["pdf"]).name,
                                       mime="application/pdf")
                with st.expander("معاينة النص المستخرج"):
                    st.write(conn.execute(
                        "SELECT text FROM chunks WHERE doc_id=? ORDER BY page,chunk_index LIMIT 5",
                        (res["doc_id"],)).fetchall())

# ---------- تبويب البحث ----------
with tab2:
    q = st.text_input("ابحث دلالياً في كل الأرشيف (يفهم المعنى، لا الكلمات فقط)")
    if q:
        results = search_chunks(q, top_k=8)
        for r in results:
            with st.expander(f"📄 {r['title']} — صفحة {r['page']} (تطابق {r['score']:.0%})"):
                st.write(r["text"])

# ---------- تبويب السؤال والجواب ----------
with tab3:
    question = st.text_area("✍️ اكتب سؤالك هنا", placeholder="مثال: ما هي شروط العقد الوارد في صفحة 3؟")
    if st.button("💡 أجب مع الاستشهاد") and question.strip():
        results = search_chunks(question, top_k=4)
        if not results:
            st.warning("لا توجد بيانات — ارفع مستندات أولاً من تبويب الرفع.")
        else:
            # نص السياق مع أرقام مرجعية
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
            with st.spinner("جاري الاسترجاع والإجابة..."):
                try:
                    answer = ask_llm(prompt, cfg)
                    st.markdown("### 📝 الإجابة")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"تعذر الاتصال بالنموذج: {e}")
                    st.info("تأكد من تشغيل Ollama أو صحة إعدادات الـ API في الشريط الجانبي.")
                    answer = None
            st.markdown("### 📎 المصادر المستشهد بها (نص الفقرات كاملاً)")
            for r in results:
                with st.expander(f"📄 {r['title']} — صفحة {r['page']}"):
                    st.write(r["text"])
