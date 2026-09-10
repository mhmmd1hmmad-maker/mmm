# 📱 تشغيل «أرشيف الذكي» على أندرويد

هناك طريقتان — اختر ما يناسبك:

---

## الخيار أ — Termux (الأسرع، بدون برمجة، 15 دقيقة)

شغّل كل شيء **على الهاتف نفسه**:

```bash
# 1) ثبّت Termux من F-Droid (ليس Google Play)
pkg update && pkg install python tesseract tur-repo
pip install streamlit img2pdf pytesseract pillow             sentence-transformers numpy requests PyPDF2

# 2) نسخة عربية من بيانات OCR
pkg install tesseract-data-ara   # إن لم تنجح، حمّل ara.traineddata يدوياً
mkdir -p $PREFIX/share/tessdata && cp ara.traineddata $PREFIX/share/tessdata/

# 3) شغّل تطبيق الويب
cd pdf_archive_app
streamlit run app.py --server.address 0.0.0.0
```

ثم افتح المتصفح على: `http://localhost:8501` — يعمل كل شيء (رفع صور، PDF، أسئلة) داخل متصفح الهاتف.

> ⚠️ نموذج اللغة (llama3.1) لا يعمل على الهاتف — استخدم بدلاً منه:
> - إما API سحابي (Groq/OpenRouter — سريع ورخيص جداً) وأدخل رابطه في إعدادات التطبيق،
> - أو شغّل Ollama على الكمبيوتر وأدخل `http://IP-الكمبيوتر:11434/v1`.

---

## الخيار ب — تطبيق أندرويد حقيقي (Kotlin + خادم FastAPI)

المعمارية: **الهاتف يلتقط الصور ويرسلها → الخادم يحوّلها PDF + OCR + يخزّن → الهاتف يسأل ويستلم الإجابة بالاستشهادات.**

### 1) الخادم (على كمبيوتر أو VPS)

```bash
cd backend
pip install -r requirements.txt
# (ثبّت Tesseract كما في README الأساسي)
python api.py        # يعمل على 0.0.0.0:8000
```

أوجد IP جهازك: `ipconfig` (Windows) أو `ifconfig` (Linux/macOS) — مثلاً `192.168.1.5`.

### 2) تطبيق الأندرويد

1. افتح **Android Studio** ← مشروع جديد «Empty Views Activity» باسم `SmartArchive` وباكدج `com.smartarchive.app`
2. استبدل/أضف الملفات من مجلد `android/` المرفق:
   - `MainActivity.kt` + `SourcesAdapter.kt` ← `app/src/main/java/com/smartarchive/app/`
   - `activity_main.xml` + `item_source.xml` ← `app/src/main/res/layout/`
   - `AndroidManifest.xml` ← `app/src/main/`
   - `network_security_config.xml` ← `app/src/main/res/xml/`
   - `build.gradle.kts` ← `app/`
3. في `MainActivity.kt` غيّر `SERVER` إلى IP جهازك، وفي `network_security_config.xml` كذلك.
4. Build ← Run على هاتفك بنفس شبكة Wi-Fi.

### شاشات التطبيق
- **📷 تصوير / 🖼️ المعرض / ⬆️ حفظ PDF**: التقاط أو اختيار الأوراق ورفعها (الخادم يحوّلها PDF ويفهرسها)
- **✍️ سؤال + 💡 أجب**: الإجابة مع استشهادات `[المصدر: العنوان — صفحة X]`، ثم قائمة الفقرات المصدر قابلة للتوسيع

---

## مقارنة سريعة

| | Termux | تطبيق Kotlin |
|---|---|---|
| وقت الإعداد | 15 دقيقة | ساعة+ |
| يعمل دون إنترنت | ✅ (ما عدا نموذج اللغة) | ❌ يحتاج خادماً |
| واجهة أصلية أندرويد | ❌ متصفح | ✅ |
| توسعة مستقبلية (دفع/سحابة) | صعب | سهل |
