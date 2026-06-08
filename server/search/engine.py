"""
搜索引擎 —— SearXNG 自部署 + 外部 API 备用
"""
from typing import List, Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from config import settings


class SearchEngine:
    """多源搜索引擎封装"""

    def __init__(self):
        self.searxng_url = settings.searxng_base_url.rstrip("/")
        self.bing_key = settings.bing_search_api_key
        self.timeout = httpx.Timeout(15.0)

    async def search(
        self, query: str, num_results: int = 5, source: str = "auto"
    ) -> List[dict]:
        """
        执行搜索

        Args:
            query: 搜索关键词
            num_results: 返回结果数
            source: "searxng" | "bing" | "auto"

        Returns:
            [{"title": str, "url": str, "snippet": str}, ...]
        """
        if source == "auto":
            # 优先 SearXNG，仅当 SearXNG 服务本身不可达时才回退
            results = await self._search_searxng(query, num_results)
            if results is not None:
                return results
            # SearXNG 挂了，尝试降级
            logger.warning("SearXNG unavailable, trying fallback...")
            # Bing API（如果有 key）
            if self.bing_key:
                results = await self._search_bing(query, num_results)
                if results:
                    return results
            # DDG Lite 最后尝试
            results = await self._search_ddg_lite(query, num_results)
            return results
        elif source == "searxng":
            return await self._search_searxng(query, num_results)
        elif source == "bing":
            return await self._search_bing(query, num_results)
        else:
            return []

    async def _search_searxng(self, query: str, num: int) -> List[dict] | None:
        """SearXNG 搜索，返回 None 表示服务不可达，[] 表示无结果"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.searxng_url}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "categories": "general",
                        "language": "zh-CN",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = []
                for r in data.get("results", [])[:num]:
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "") or r.get("snippet", ""),
                    })
                logger.info(f"SearXNG returned {len(results)} results")
                return results
        except Exception as e:
            logger.warning(f"SearXNG search failed: {e}")
            return None

    async def _search_bing(self, query: str, num: int) -> List[dict]:
        """Bing Search API 备用"""
        if not self.bing_key:
            logger.warning("No Bing API key configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    params={"q": query, "count": num, "mkt": "zh-CN"},
                    headers={"Ocp-Apim-Subscription-Key": self.bing_key},
                )
                resp.raise_for_status()
                data = resp.json()
                results = []
                for r in data.get("webPages", {}).get("value", [])[:num]:
                    results.append({
                        "title": r.get("name", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", ""),
                    })
                logger.info(f"Bing returned {len(results)} results")
                return results
        except Exception as e:
            logger.error(f"Bing search failed: {e}")
            return []

    async def _search_ddg_lite(self, query: str, num: int) -> List[dict]:
        """DuckDuckGo Lite 搜索（无需 API Key，全球可用）"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                results = []
                for row in soup.select("table > tr")[:num + 1]:
                    link = row.select_one("a.result-link")
                    snippet = row.select_one("td.result-snippet")
                    if link and link.get("href"):
                        results.append({
                            "title": link.get_text(strip=True),
                            "url": link["href"],
                            "snippet": snippet.get_text(strip=True) if snippet else "",
                        })
                logger.info(f"DDG lite returned {len(results)} results")
                return results[:num]
        except Exception as e:
            logger.warning(f"DDG lite search failed: {e}")
            return []

    async def fetch_page(self, url: str) -> Optional[str]:
        """抓取网页正文文本"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    },
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # 提取正文
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()

                body = soup.find("body")
                if body:
                    text = body.get_text(separator="\n", strip=True)
                    # 清理多余空行
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    return "\n".join(lines[:200])  # 限制长度
                return ""
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None


# 全局单例
search_engine = SearchEngine()
