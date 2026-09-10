// app/build.gradle.kts — أضف هذه الأسطر داخل android {}
plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }

android {
    namespace = "com.smartarchive.app"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.smartarchive.app"
        minSdk = 24; targetSdk = 34; versionCode = 1; versionName = "1.0"
    }
    buildFeatures { viewBinding = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("com.google.android.material:material:1.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
