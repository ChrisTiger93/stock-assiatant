package com.tigerbase.aiassistant

import android.app.Application
import com.tigerbase.aiassistant.data.PreferencesManager
import com.tigerbase.aiassistant.network.ApiService
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

class AiAssistantApp : Application() {

    lateinit var prefs: PreferencesManager
        private set

    val api: ApiService by lazy {
        val (url, _) = runBlocking {
            prefs.serverUrl.first() to prefs.apiKey.first()
        }
        buildApi(url)
    }

    override fun onCreate() {
        super.onCreate()
        prefs = PreferencesManager(this)
    }

    fun buildApi(serverUrl: String): ApiService {
        val okHttp = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                    .addHeader("X-API-Key", runBlocking { prefs.apiKey.first() })
                    .build()
                chain.proceed(request)
            }
            .build()

        return Retrofit.Builder()
            .baseUrl(serverUrl.trimEnd('/') + "/")
            .client(okHttp)
            .addConverterFactory(MoshiConverterFactory.create(
                Moshi.Builder()
                    .addLast(KotlinJsonAdapterFactory())
                    .build()
            ))
            .build()
            .create(ApiService::class.java)
    }
}
