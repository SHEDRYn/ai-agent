"""Внешние инструменты (поиск в интернете)"""

import os
import asyncio
from typing import Dict, Any
import logging

from ..base import BaseTool

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Поиск в интернете"""
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Выполняет поиск в интернете и возвращает релевантные результаты",
            parameters_schema={
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 5)",
                        "default": 5
                    }
                },
                "required": ["search_term"]
            }
        )
        self.provider = self._init_provider()
    
    def _init_provider(self):
        """Инициализация провайдера поиска"""
        # Попытка использовать DuckDuckGo (бесплатный, не требует API ключа)
        try:
            from duckduckgo_search import DDGS
            return "duckduckgo"
        except ImportError:
            pass
        
        # Попытка использовать Tavily (требует API ключ)
        try:
            from tavily import TavilyClient
            api_key = os.getenv("TAVILY_API_KEY")
            if api_key:
                return TavilyClient(api_key=api_key)
        except ImportError:
            pass
        
        logger.warning("Не найден ни один провайдер поиска. Установите duckduckgo-search или tavily-python")
        return None
    
    async def execute(
        self,
        search_term: str,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Выполнить поиск"""
        if self.provider is None:
            return {
                "error": "Провайдер поиска не настроен. Установите duckduckgo-search или tavily-python",
                "results": []
            }
        
        try:
            if self.provider == "duckduckgo":
                return await self._search_duckduckgo(search_term, max_results)
            else:
                # Tavily
                return await self._search_tavily(search_term, max_results)
        except Exception as e:
            logger.error(f"Ошибка при поиске: {e}", exc_info=True)
            return {
                "error": str(e),
                "results": []
            }
    
    async def _search_duckduckgo(self, search_term: str, max_results: int) -> Dict[str, Any]:
        """Поиск через DuckDuckGo"""
        try:
            from duckduckgo_search import DDGS
            
            # Запуск в executor, так как DDGS синхронный
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(search_term, max_results=max_results))
            )
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                })
            
            return {
                "provider": "duckduckgo",
                "results": formatted_results,
                "count": len(formatted_results)
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка DuckDuckGo поиска: {str(e)}")
    
    async def _search_tavily(self, search_term: str, max_results: int) -> Dict[str, Any]:
        """Поиск через Tavily"""
        try:
            results = self.provider.search(
                query=search_term,
                max_results=max_results,
            )
            
            formatted_results = []
            for result in results.get("results", []):
                formatted_results.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("content", ""),
                })
            
            return {
                "provider": "tavily",
                "results": formatted_results,
                "count": len(formatted_results)
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка Tavily поиска: {str(e)}")

