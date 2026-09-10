package com.smartarchive.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import com.smartarchive.app.databinding.ActivityMainBinding
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {
    private lateinit var b: ActivityMainBinding
    private val client = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS).build()

    // ⚠️ غيّر هذا إلى IP جهازك الذي يشغّل الخادم (تجده بـ ipconfig / ifconfig)
    private val SERVER = "http://192.168.1.5:8000"

    private val pickedImages = mutableListOf<Uri>()

    private val pickImages = registerForActivityResult(
        ActivityResultContracts.GetMultipleContents()) { uris ->
        pickedImages.clear(); pickedImages.addAll(uris)
        b.tvStatus.text = "تم اختيار ${uris.size} صورة"
    }

    private val takePhoto = registerForActivityResult(
        ActivityResultContracts.TakePicturePreview()) { bmp ->
        bmp?.let {
            val f = File(cacheDir, "capture_${System.currentTimeMillis()}.jpg")
            FileOutputStream(f).use { s -> it.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, s) }
            pickedImages.clear(); pickedImages.add(Uri.fromFile(f))
            b.tvStatus.text = "تم التقاط صورة"
        }
    }

    private val reqPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) takePhoto.launch(null)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)

        b.btnGallery.setOnClickListener { pickImages.launch("image/*") }
        b.btnCamera.setOnClickListener {
            val perm = Manifest.permission.CAMERA
            if (ContextCompat.checkSelfPermission(this, perm) ==
                PackageManager.PERMISSION_GRANTED)
                takePhoto.launch(null)
            else reqPermission.launch(perm)
        }

        b.btnUpload.setOnClickListener { upload() }
        b.btnAsk.setOnClickListener { ask() }
    }

    /** 1) رفع الصور → يحوّلها الخادم إلى PDF ويخزّنها ويفهرسها */
    private fun upload() {
        if (pickedImages.isEmpty()) { toast("اختر صوراً أولاً"); return }
        val title = b.etTitle.text.toString().ifBlank { "مستند بدون عنوان" }
        b.tvStatus.text = "⏳ جاري الرفع والمعالجة..."
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                    .addFormDataPart("title", title)
                pickedImages.forEachIndexed { i, uri ->
                    val tmp = File(cacheDir, "up_$i.jpg")
                    contentResolver.openInputStream(uri)?.use { input ->
                        FileOutputStream(tmp).use { input.copyTo(it) }
                    }
                    body.addFormDataPart("files", tmp.name,
                        tmp.asRequestBody("image/jpeg".toMediaType()))
                }
                val req = Request.Builder().url("$SERVER/upload")
                    .post(body.build()).build()
                val resp = JSONObject(client.newCall(req).execute().body!!.string())
                withContext(Dispatchers.Main) {
                    val pages = resp.optInt("pages")
                    b.tvStatus.text = if (resp.optString("status") == "duplicate")
                        "⚠️ المستند موجود مسبقاً" else "✅ تم الحفظ ($pages صفحات) كـ PDF"
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) { b.tvStatus.text = "❌ خطأ: ${e.message}" }
            }
        }
    }

    /** 2) السؤال → إجابة + فقرات الاستشهاد */
    private fun ask() {
        val q = b.etQuestion.text.toString().trim()
        if (q.isEmpty()) { toast("اكتب سؤالاً"); return }
        b.tvAnswer.text = "⏳ جاري البحث والإجابة..."
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val req = Request.Builder()
                    .url("$SERVER/ask?q=${Uri.encode(q)}").get().build()
                val json = JSONObject(client.newCall(req).execute().body!!.string())
                val answer = json.getString("answer")
                val sources = json.getJSONArray("sources")
                withContext(Dispatchers.Main) {
                    b.tvAnswer.text = answer
                    val items = (0 until sources.length()).map { i ->
                        val s = sources.getJSONObject(i)
                        SourceItem(s.getString("title"), s.getInt("page"),
                                   s.getString("text"))
                    }
                    b.rvSources.layoutManager = LinearLayoutManager(this@MainActivity)
                    b.rvSources.adapter = SourcesAdapter(items)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) { b.tvAnswer.text = "❌ خطأ: ${e.message}" }
            }
        }
    }

    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()
}

data class SourceItem(val title: String, val page: Int, val text: String)
