"""Индексатор кодовой базы для семантического поиска"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
import litellm
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class CodeIndexer:
    """Индексатор кодовой базы с использованием векторной БД"""

    def __init__(
        self,
        index_path: str = ".code_index",
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Инициализация индексатора

        Args:
            index_path: Путь для хранения индекса
            embedding_model: Название модели для эмбеддингов (например, "text-embedding-3-small", "text-embedding-ada-002")
            chunk_size: Размер чанка в символах
            chunk_overlap: Перекрытие между чанками
            api_key: API ключ (можно также через переменную окружения)
            base_url: Базовый URL API (для кастомных провайдеров)
        """
        self.index_path = index_path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_model_name = embedding_model

        # Настройка litellm для embeddings
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        if base_url:
            litellm.api_base = base_url

        # Инициализация ChromaDB
        os.makedirs(index_path, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=index_path, settings=Settings(anonymized_telemetry=False)
        )

        try:
            self.collection = self.client.get_or_create_collection(
                name="code_index", metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Ошибка при создании коллекции: {e}")
            self.collection = self.client.create_collection(
                name="code_index", metadata={"hnsw:space": "cosine"}
            )

    async def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Получение эмбеддингов через litellm API

        Args:
            texts: Список текстов для векторизации

        Returns:
            Список эмбеддингов
        """
        try:
            response = await litellm.aembedding(
                model=self.embedding_model_name,
                input=texts,
            )

            # Извлечение эмбеддингов из ответа
            embeddings = [item["embedding"] for item in response.data]
            return embeddings
        except Exception as e:
            logger.error(f"Ошибка при получении эмбеддингов: {e}")
            raise

    async def index_project(
        self, project_path: str, exclude_dirs: Optional[List[str]] = None
    ) -> int:
        """
        Индексация всего проекта

        Args:
            project_path: Путь к проекту
            exclude_dirs: Список директорий для исключения

        Returns:
            Количество проиндексированных файлов
        """
        if exclude_dirs is None:
            exclude_dirs = [
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                "venv",
                ".env",
                "dist",
                "build",
            ]

        project_path = Path(project_path).resolve()
        indexed_count = 0

        logger.info(f"Начало индексации проекта: {project_path}")

        # Очистка старого индекса (опционально, можно сделать параметром)
        # self.collection.delete()

        for root, dirs, files in os.walk(project_path):
            # Фильтрация директорий
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                file_path = Path(root) / file

                # Пропуск бинарных файлов и больших файлов
                if self._should_skip_file(file_path):
                    continue

                try:
                    await self.index_file(str(file_path))
                    indexed_count += 1
                    if indexed_count % 10 == 0:
                        logger.info(f"Проиндексировано файлов: {indexed_count}")
                except Exception as e:
                    logger.warning(f"Ошибка при индексации {file_path}: {e}")

        logger.info(f"Индексация завершена. Всего файлов: {indexed_count}")
        return indexed_count

    def _should_skip_file(self, file_path: Path) -> bool:
        """Проверка, нужно ли пропустить файл"""
        # Пропуск больших файлов (>1MB)
        try:
            if file_path.stat().st_size > 1024 * 1024:
                return True
        except:
            return True

        # Пропуск бинарных расширений
        binary_extensions = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".ico",
        }
        if file_path.suffix.lower() in binary_extensions:
            return True

        return False

    async def index_file(self, file_path: str) -> None:
        """
        Индексация одного файла

        Args:
            file_path: Путь к файлу
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Не удалось прочитать файл {file_path}: {e}")
            return

        # Разбиение на чанки
        chunks = self._split_into_chunks(file_path, content)

        if not chunks:
            return

        # Генерация эмбеддингов через API
        texts = [chunk["text"] for chunk in chunks]
        embeddings = await self._get_embeddings(texts)

        # Сохранение в ChromaDB
        ids = [f"{file_path}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_path": file_path,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "chunk_index": i,
            }
            for i, chunk in enumerate(chunks)
        ]

        # Удаление старых чанков этого файла
        existing_ids = [
            id for id in self.collection.get()["ids"] if id.startswith(f"{file_path}:")
        ]
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        # Добавление новых чанков (embeddings уже список списков)
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def _split_into_chunks(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Разбиение файла на чанки

        Args:
            file_path: Путь к файлу
            content: Содержимое файла

        Returns:
            Список чанков с метаданными
        """
        chunks = []
        lines = content.split("\n")

        # Попытка разбить по функциям/классам для языков программирования
        if self._is_code_file(file_path):
            semantic_chunks = self._split_by_semantic_units(content, file_path)
            if semantic_chunks:
                return semantic_chunks

        # Простое разбиение по размеру
        current_chunk = []
        current_size = 0
        start_line = 0

        for i, line in enumerate(lines):
            line_size = len(line) + 1  # +1 для переноса строки

            if current_size + line_size > self.chunk_size and current_chunk:
                # Сохраняем текущий чанк
                chunks.append(
                    {
                        "text": "\n".join(current_chunk),
                        "start_line": start_line,
                        "end_line": i - 1,
                    }
                )

                # Начинаем новый чанк с перекрытием
                overlap_lines = min(len(current_chunk), self.chunk_overlap // 50)
                current_chunk = current_chunk[-overlap_lines:] + [line]
                current_size = sum(len(l) + 1 for l in current_chunk)
                start_line = i - overlap_lines
            else:
                current_chunk.append(line)
                current_size += line_size

        # Добавляем последний чанк
        if current_chunk:
            chunks.append(
                {
                    "text": "\n".join(current_chunk),
                    "start_line": start_line,
                    "end_line": len(lines) - 1,
                }
            )

        return chunks

    def _is_code_file(self, file_path: str) -> bool:
        """Проверка, является ли файл кодом"""
        code_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".cs",
            ".html",
            ".css",
            ".scss",
            ".sql",
            ".sh",
            ".yaml",
            ".yml",
            ".json",
        }
        return Path(file_path).suffix.lower() in code_extensions

    def _split_by_semantic_units(
        self, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Разбиение кода по семантическим единицам (функции, классы)"""
        chunks = []
        lines = content.split("\n")

        # Простая эвристика для Python
        if file_path.endswith(".py"):
            return self._split_python_code(content, lines)

        # Для других языков можно добавить специфичную логику
        return []

    def _split_python_code(
        self, content: str, lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Разбиение Python кода по функциям и классам"""
        chunks = []

        # Регулярные выражения для функций и классов
        function_pattern = re.compile(r"^(def|async def)\s+(\w+)\s*\(")
        class_pattern = re.compile(r"^class\s+(\w+)")

        current_unit = []
        current_start = 0
        indent_level = 0

        for i, line in enumerate(lines):
            stripped = line.lstrip()

            # Определение уровня отступа
            line_indent = len(line) - len(stripped)

            # Начало новой функции или класса
            if function_pattern.match(stripped) or class_pattern.match(stripped):
                # Сохраняем предыдущую единицу
                if current_unit and current_start < i:
                    chunks.append(
                        {
                            "text": "\n".join(lines[current_start:i]),
                            "start_line": current_start,
                            "end_line": i - 1,
                        }
                    )

                current_unit = [line]
                current_start = i
                indent_level = line_indent
            elif current_unit and line_indent > indent_level:
                # Продолжение текущей единицы
                current_unit.append(line)
            elif current_unit and stripped and line_indent <= indent_level:
                # Конец текущей единицы
                chunks.append(
                    {
                        "text": "\n".join(lines[current_start:i]),
                        "start_line": current_start,
                        "end_line": i - 1,
                    }
                )
                current_unit = []

        # Последняя единица
        if current_unit:
            chunks.append(
                {
                    "text": "\n".join(lines[current_start:]),
                    "start_line": current_start,
                    "end_line": len(lines) - 1,
                }
            )

        return chunks if chunks else []

    async def search(
        self,
        query: str,
        top_k: int = 5,
        file_path_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Семантический поиск по коду

        Args:
            query: Поисковый запрос
            top_k: Количество результатов
            file_path_filter: Фильтр по пути файла (опционально)

        Returns:
            Список результатов с метаданными
        """
        # Генерация эмбеддинга запроса через API
        query_embeddings = await self._get_embeddings([query])
        query_embedding = query_embeddings[0]

        # Поиск в ChromaDB
        where = None
        if file_path_filter:
            where = {"file_path": file_path_filter}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )

        # Форматирование результатов
        formatted_results = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                formatted_results.append(
                    {
                        "file_path": results["metadatas"][0][i]["file_path"],
                        "content": results["documents"][0][i],
                        "start_line": results["metadatas"][0][i]["start_line"],
                        "end_line": results["metadatas"][0][i]["end_line"],
                        "distance": (
                            results["distances"][0][i]
                            if "distances" in results
                            else None
                        ),
                    }
                )

        return formatted_results

    def clear_index(self) -> None:
        """Очистить индекс"""
        try:
            self.client.delete_collection(name="code_index")
            self.collection = self.client.create_collection(
                name="code_index", metadata={"hnsw:space": "cosine"}
            )
            logger.info("Индекс очищен")
        except Exception as e:
            logger.error(f"Ошибка при очистке индекса: {e}")
