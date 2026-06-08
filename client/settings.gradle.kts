pluginManagement {
    repositories {
        maven("https://maven.aliyun.com/repository/public")
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/google") // 对于Android项目很重要
        maven("https://maven.aliyun.com/repository/gradle-plugin")
        // 保留gradlePluginPortal()和google()，但将其放在国内源之后可能会减慢速度
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven("https://maven.aliyun.com/repository/public")
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/google") // 对于Android项目很重要
        google()
        mavenCentral()
    }
}

rootProject.name = "AiAssistant"
include(":app")
