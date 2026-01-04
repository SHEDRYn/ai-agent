"""Инструменты для поиска кода"""

import os
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from ..base import BaseTool
from .indexer import CodeIndexer

logger = logging.getLogger(__name__)


class CodebaseSearchTool(BaseTool):
    """Семантический поиск по кодовой базе"""
    
    def __init__(self, indexer: CodeIndexer):
        super().__init__(
            name="codebase_search",
            description="Семантический поиск по кодовой базе. Находит релевантный код на основе смысла запроса.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на естественном языке"
                    },
                    "target_directories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список директорий для ограничения поиска (опционально)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
        self.indexer = indexer
    
    async def execute(
        self,
        query: str,
        target_directories: Optional[List[str]] = None,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Выполнить семантический поиск"""
        try:
            results = await self.indexer.search(query, top_k=max_results)
            
            # Фильтрация по директориям если указано
            if target_directories:
                filtered_results = []
                for result in results:
                    file_path = result["file_path"]
                    if any(file_path.startswith(str(Path(d).resolve())) for d in target_directories):
                        filtered_results.append(result)
                results = filtered_results
            
            return results
        except Exception as e:
            logger.error(f"Ошибка при семантическом поиске: {e}")
            return []


class GrepTool(BaseTool):
    """Поиск по точным совпадениям и регулярным выражениям"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="grep",
            description="Поиск по кодовой базе с использованием регулярных выражений или точных совпадений",
            parameters_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Регулярное выражение или текст для поиска"
                    },
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу или директории для поиска (по умолчанию вся кодовая база)"
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Учитывать регистр при поиске",
                        "default": False
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "Многострочный режим для регулярных выражений",
                        "default": False
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "Режим вывода: content (содержимое), files_with_matches (только файлы), count (количество)",
                        "default": "content"
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "Ограничение количества результатов",
                        "default": 50
                    }
                },
                "required": ["pattern"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        case_sensitive: bool = False,
        multiline: bool = False,
        output_mode: str = "content",
        head_limit: int = 50,
    ) -> Dict[str, Any]:
        """Выполнить поиск grep"""
        search_path = Path(path).resolve() if path else self.workspace_root
        
        if not search_path.exists():
            return {"error": f"Путь не найден: {search_path}"}
        
        # Компиляция регулярного выражения
        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE | re.DOTALL
        
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {"error": f"Невалидное регулярное выражение: {e}"}
        
        results = []
        file_count = 0
        match_count = 0
        
        # Рекурсивный обход файлов
        files_to_search = []
        if search_path.is_file():
            files_to_search = [search_path]
        else:
            # Исключаем некоторые директории
            exclude_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.code_index'}
            for root, dirs, files in os.walk(search_path):
                # Фильтрация директорий
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    file_path = Path(root) / file
                    # Пропуск бинарных файлов
                    if self._is_text_file(file_path):
                        files_to_search.append(file_path)
        
        # Поиск в файлах
        for file_path in files_to_search[:head_limit * 10]:  # Ограничение файлов для сканирования
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                matches = list(regex.finditer(content))
                if matches:
                    file_count += 1
                    match_count += len(matches)
                    
                    if output_mode == "files_with_matches":
                        results.append({
                            "file": str(file_path.relative_to(self.workspace_root)),
                            "match_count": len(matches)
                        })
                    elif output_mode == "content":
                        file_matches = []
                        for match in matches[:head_limit]:
                            # Получаем контекст вокруг совпадения
                            start = max(0, match.start() - 50)
                            end = min(len(content), match.end() + 50)
                            context = content[start:end]
                            
                            # Подсчет строк
                            line_start = content[:match.start()].count('\n') + 1
                            
                            file_matches.append({
                                "line": line_start,
                                "match": match.group(0),
                                "context": context
                            })
                        
                        if file_matches:
                            results.append({
                                "file": str(file_path.relative_to(self.workspace_root)),
                                "matches": file_matches
                            })
                    
                    if len(results) >= head_limit:
                        break
            except Exception as e:
                logger.debug(f"Ошибка при поиске в файле {file_path}: {e}")
                continue
        
        if output_mode == "count":
            return {
                "matches": match_count,
                "files": file_count
            }
        
        return {
            "results": results[:head_limit],
            "total_matches": match_count,
            "total_files": file_count
        }
    
    def _is_text_file(self, file_path: Path) -> bool:
        """Проверка, является ли файл текстовым"""
        text_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.html', '.css',
            '.scss', '.sql', '.sh', '.yaml', '.yml', '.json', '.md', '.txt',
            '.xml', '.toml', '.ini', '.conf', '.log'
        }
        if file_path.suffix.lower() in text_extensions:
            return True
        
        # Проверка первых байтов на текстовый контент
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(512)
                return not bool(chunk.translate(None, bytes(range(32, 127))))
        except:
            return False


class GlobFileSearchTool(BaseTool):
    """Поиск файлов по шаблонам"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="glob_file_search",
            description="Поиск файлов по шаблону (glob pattern)",
            parameters_schema={
                "type": "object",
                "properties": {
                    "glob_pattern": {
                        "type": "string",
                        "description": "Glob шаблон для поиска (например, '**/*.py', 'src/**/*.ts')"
                    },
                    "target_directory": {
                        "type": "string",
                        "description": "Директория для поиска (по умолчанию корень проекта)"
                    }
                },
                "required": ["glob_pattern"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(
        self,
        glob_pattern: str,
        target_directory: Optional[str] = None,
    ) -> List[str]:
        """Выполнить поиск файлов"""
        search_dir = Path(target_directory).resolve() if target_directory else self.workspace_root
        
        if not search_dir.exists():
            return []
        
        try:
            # Использование glob для рекурсивного поиска
            pattern = search_dir / glob_pattern
            matches = list(pattern.rglob(glob_pattern.split('/')[-1]) if '**' in glob_pattern else pattern.glob(glob_pattern))
            
            # Альтернативный метод через os.walk для лучшей поддержки **
            if '**' in glob_pattern or matches:
                # Нормализация пути
                if not glob_pattern.startswith('**/'):
                    # Добавляем **/ в начало если нужно
                    full_pattern = str(search_dir / glob_pattern)
                else:
                    full_pattern = str(search_dir / glob_pattern[3:])  # Убираем **/
                
                matches = []
                for root, dirs, files in os.walk(search_dir):
                    # Использование fnmatch для каждого уровня
                    relative_root = Path(root).relative_to(search_dir)
                    for file in files:
                        file_path = relative_root / file
                        if self._match_glob(str(file_path), glob_pattern):
                            matches.append(search_dir / file_path)
            
            # Убираем дубликаты и сортируем
            matches = sorted(set(matches))
            
            # Возвращаем относительные пути
            return [str(m.relative_to(self.workspace_root)) for m in matches]
        except Exception as e:
            logger.error(f"Ошибка при поиске файлов: {e}")
            return []
    
    def _match_glob(self, path: str, pattern: str) -> bool:
        """Простое сопоставление glob pattern (базовая реализация)"""
        import fnmatch
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, '**/' + pattern)

