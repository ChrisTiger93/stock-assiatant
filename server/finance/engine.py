"""
金融数据引擎 —— 美股行情、财务、新闻
基于 finnhub-python SDK，免费额度 60次/分钟
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from loguru import logger

from config import settings

# Finnhub SDK 是同步的，用线程池避免阻塞 event loop
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


class FinanceEngine:
    """Finnhub 美股数据封装"""

    def __init__(self):
        import finnhub
        import time

        self._client = finnhub.Client(api_key=settings.finnhub_api_key)
        self._metric_cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = 30  # 秒

    async def _get_metric_cached(self, symbol: str) -> dict:
        """获取 metric，30 秒内同一 symbol 复用缓存"""
        import time as _time
        now = _time.monotonic()
        sym = symbol.upper()
        if sym in self._metric_cache:
            ts, data = self._metric_cache[sym]
            if now - ts < self._cache_ttl:
                return data
        data = await self._run(self._client.company_basic_financials, sym, "all")
        self._metric_cache[sym] = (now, data)
        return data

    async def _run(self, fn, *args, **kwargs):
        """在线程池中执行同步 SDK 调用"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_EXECUTOR, lambda: fn(*args, **kwargs))

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def get_stock_price(self, symbol: str) -> dict:
        """实时行情 + 估值快照 + 公司概况"""
        sym = symbol.upper()
        try:
            quote, profile, metric = await asyncio.gather(
                self._run(self._client.quote, sym),
                self._run(self._client.company_profile2, symbol=sym),
                self._get_metric_cached(sym),
            )

            m = metric.get("metric", {}) if isinstance(metric, dict) else {}

            result = {
                "symbol": sym,
                "name": profile.get("name", ""),
                "exchange": profile.get("exchange", ""),
                # 行情
                "price": quote.get("c"),
                "previous_close": quote.get("pc"),
                "open": quote.get("o"),
                "day_high": quote.get("h"),
                "day_low": quote.get("l"),
                "change_pct": self._safe_round(quote.get("dp")),
                # 估值
                "market_cap": profile.get("marketCapitalization"),
                "pe_ratio": self._safe_round(
                    m.get("peBasicExclExtraTTM") or m.get("peInclExtraTTM")
                ),
                "pb_ratio": self._safe_round(m.get("pbAnnual") or m.get("pb")),
                "beta": self._safe_round(m.get("beta"), 2),
                "52w_high": m.get("52WeekHigh"),
                "52w_low": m.get("52WeekLow"),
                "dividend_yield": self._safe_round(m.get("dividendYieldIndicatedAnnual"), 4),
                # 行业
                "sector": profile.get("finnhubIndustry", ""),
                "industry": profile.get("finnhubIndustry", ""),
                "currency": "USD",
            }
            logger.info(f"Finance: price for {sym} → ${result['price']}")
            return result

        except Exception as e:
            logger.error(f"Finance: get_stock_price({sym}) failed: {e}")
            return {"symbol": sym, "error": str(e)}

    async def get_stock_financials(self, symbol: str) -> dict:
        """核心财务指标"""
        sym = symbol.upper()
        try:
            resp = await self._get_metric_cached(sym)
            m = resp.get("metric", {}) if isinstance(resp, dict) else {}

            result = {
                "symbol": sym,
                # 估值
                "pe_ttm": self._safe_round(m.get("peBasicExclExtraTTM")),
                "forward_pe": self._safe_round(m.get("forwardPE")),
                "eps_ttm": self._safe_round(m.get("epsInclExtraTTM") or m.get("epsExclExtraTTM")),
                # 增长
                "eps_growth_3y": self._safe_round(m.get("epsGrowth3Y")),
                "eps_growth_5y": self._safe_round(m.get("epsGrowth5Y")),
                "eps_growth_quarterly_yoy": self._safe_round(m.get("epsGrowthQuarterlyYoy")),
                "eps_growth_ttm_yoy": self._safe_round(m.get("epsGrowthTTMYoy")),
                "revenue_growth_3y": self._safe_round(m.get("revenueGrowth3Y")),
                "revenue_growth_5y": self._safe_round(m.get("revenueGrowth5Y")),
                "revenue_growth_quarterly_yoy": self._safe_round(m.get("revenueGrowthQuarterlyYoy")),
                "revenue_growth_ttm_yoy": self._safe_round(m.get("revenueGrowthTTMYoy")),
                # 利润率
                "gross_margin": self._safe_round(m.get("grossMarginTTM")),
                "operating_margin": self._safe_round(m.get("operatingMarginTTM")),
                "profit_margin": self._safe_round(m.get("netProfitMarginTTM")),
                # 回报率
                "roe": self._safe_round(m.get("roeTTM")),
                "roa": self._safe_round(m.get("roaTTM")),
                # 财务健康
                "current_ratio": self._safe_round(m.get("currentRatioAnnual")),
                "debt_to_equity": self._safe_round(m.get("totalDebt/totalEquityAnnual")),
                "interest_coverage": self._safe_round(m.get("netInterestCoverageTTM")),
                # 每股
                "book_value_per_share": self._safe_round(m.get("bookValuePerShareAnnual")),
                "cash_per_share": self._safe_round(m.get("cashPerSharePerShareAnnual")),
                "revenue_per_share": self._safe_round(m.get("revenuePerShareTTM")),
            }
            logger.info(f"Finance: financials for {sym} OK")
            return result

        except Exception as e:
            logger.error(f"Finance: get_stock_financials({sym}) failed: {e}")
            return {"symbol": sym, "error": str(e)}

    async def get_stock_news(self, symbol: str, count: int = 8) -> dict:
        """个股近期新闻 + 分析师评级 + 目标价"""
        sym = symbol.upper()
        today = datetime.now(timezone.utc)
        week_ago = today - timedelta(days=7)
        _from = week_ago.strftime("%Y-%m-%d")
        _to = today.strftime("%Y-%m-%d")

        # 并行请求，单个失败不影响其他
        news_data, recs, price_target = await asyncio.gather(
            self._safe_run(self._client.company_news, sym, _from=_from, to=_to),
            self._safe_run(self._client.recommendation_trends, sym),
            self._safe_run(self._client.price_target, sym),
        )

        # 新闻
        news_list = []
        for item in (news_data or [])[:count]:
            if not isinstance(item, dict):
                continue
            news_list.append({
                "title": item.get("headline", ""),
                "link": item.get("url", ""),
                "publisher": item.get("source", ""),
                "published": datetime.fromtimestamp(
                    item.get("datetime", 0), tz=timezone.utc
                ).isoformat() if item.get("datetime") else "",
                "summary": item.get("summary", ""),
            })

        # 分析师评级
        analyst = {}
        if recs and isinstance(recs, list) and len(recs) > 0:
            latest = recs[0]
            total = (
                (latest.get("strongBuy", 0) or 0)
                + (latest.get("buy", 0) or 0)
                + (latest.get("hold", 0) or 0)
                + (latest.get("sell", 0) or 0)
                + (latest.get("strongSell", 0) or 0)
            )
            analyst["period"] = latest.get("period", "")
            analyst["strongBuy"] = latest.get("strongBuy")
            analyst["buy"] = latest.get("buy")
            analyst["hold"] = latest.get("hold")
            analyst["sell"] = latest.get("sell")
            analyst["strongSell"] = latest.get("strongSell")
            analyst["total"] = total

        # 目标价（免费版可能 403）
        if isinstance(price_target, dict):
            analyst["target_mean"] = price_target.get("targetMean")
            analyst["target_high"] = price_target.get("targetHigh")
            analyst["target_low"] = price_target.get("targetLow")
            analyst["number_of_analysts"] = price_target.get("numberAnalysts")

        result = {
            "symbol": sym,
            "news": news_list,
            "analyst_rating": analyst,
        }
        logger.info(f"Finance: {len(news_list)} news for {sym}")
        return result

    async def _safe_run(self, fn, *args, **kwargs):
        """执行 SDK 调用，捕获异常返回 None"""
        try:
            return await self._run(fn, *args, **kwargs)
        except Exception as e:
            logger.warning(f"Finance: {fn.__name__}({args}) failed (non-fatal): {e}")
            return None

    @staticmethod
    def _safe_round(value, decimals=2):
        if value is None:
            return None
        try:
            return round(float(value), decimals)
        except (TypeError, ValueError):
            return value


finance_engine = FinanceEngine()
