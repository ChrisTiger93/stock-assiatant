package com.tigerbase.aiassistant.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.tigerbase.aiassistant.ui.chat.ChatScreen
import com.tigerbase.aiassistant.ui.conversations.ConversationListScreen
import com.tigerbase.aiassistant.ui.settings.SettingsScreen

object Routes {
    const val CONVERSATIONS = "conversations"
    const val CHAT = "chat/{conversationId}"
    const val SETTINGS = "settings"

    fun chat(conversationId: String) = "chat/$conversationId"
}

@Composable
fun NavGraph(navController: NavHostController) {
    NavHost(
        navController = navController,
        startDestination = Routes.CONVERSATIONS,
    ) {
        composable(Routes.CONVERSATIONS) {
            ConversationListScreen(
                onConversationClick = { id ->
                    navController.navigate(Routes.chat(id))
                },
                onSettingsClick = {
                    navController.navigate(Routes.SETTINGS)
                },
            )
        }

        composable(
            route = Routes.CHAT,
            arguments = listOf(navArgument("conversationId") { type = NavType.StringType }),
        ) { backStackEntry ->
            val conversationId = backStackEntry.arguments?.getString("conversationId") ?: return@composable
            ChatScreen(
                conversationId = conversationId,
                onBack = { navController.popBackStack() },
            )
        }

        composable(Routes.SETTINGS) {
            SettingsScreen(
                onConnected = { navController.popBackStack() },
            )
        }
    }
}
