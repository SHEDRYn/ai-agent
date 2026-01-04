"""Инструменты для операций с файлами"""

from pathlib import Path
from typing import Optional, Dict, Any
import logging

from ..base import BaseTool

logger = logging.getLogger(__name__)


class ReadFileTool(BaseTool):
    """Чтение файлов"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="read_file",
            description="Читает содержимое файла по указанному пути",
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_file": {
                        "type": "string",
                        "description": "Путь к файлу для чтения (относительно корня проекта или абсолютный)"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Номер строки для начала чтения (опционально)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Количество строк для чтения (опционально, если не указано - весь файл)"
                    }
                },
                "required": ["target_file"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(
        self,
        target_file: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Прочитать файл"""
        file_path = self._resolve_path(target_file)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {target_file}")
        
        if not file_path.is_file():
            raise ValueError(f"Путь не является файлом: {target_file}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if offset is not None or limit is not None:
                    lines = f.readlines()
                    start = offset - 1 if offset else 0
                    end = start + limit if limit else len(lines)
                    content = ''.join(lines[start:end])
                    return content
                else:
                    return f.read()
        except UnicodeDecodeError:
            # Попытка других кодировок
            for encoding in ['latin-1', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except:
                    continue
            raise ValueError(f"Не удалось декодировать файл {target_file}")
        except Exception as e:
            raise RuntimeError(f"Ошибка при чтении файла {target_file}: {str(e)}")
    
    def _resolve_path(self, file_path: str) -> Path:
        """Разрешение пути с проверкой безопасности"""
        path = Path(file_path)
        
        if path.is_absolute():
            # Проверка, что путь находится в workspace
            try:
                path.relative_to(self.workspace_root)
            except ValueError:
                raise ValueError(f"Доступ к файлам вне workspace запрещен: {file_path}")
        else:
            path = self.workspace_root / path
        
        return path.resolve()


class WriteFileTool(BaseTool):
    """Создание и перезапись файлов"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="write",
            description="Создает новый файл или перезаписывает существующий с указанным содержимым",
            parameters_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Путь к файлу для записи"
                    },
                    "contents": {
                        "type": "string",
                        "description": "Содержимое файла"
                    }
                },
                "required": ["file_path", "contents"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(self, file_path: str, contents: str) -> Dict[str, Any]:
        """Записать файл"""
        path = self._resolve_path(file_path)
        
        # Проверка безопасности
        try:
            path.relative_to(self.workspace_root)
        except ValueError:
            raise ValueError(f"Доступ к файлам вне workspace запрещен: {file_path}")
        
        # Создание директорий если нужно
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(contents)
            
            return {
                "status": "success",
                "file": str(path.relative_to(self.workspace_root)),
                "bytes_written": len(contents.encode('utf-8'))
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка при записи файла {file_path}: {str(e)}")
    
    def _resolve_path(self, file_path: str) -> Path:
        """Разрешение пути"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()


class SearchReplaceTool(BaseTool):
    """Редактирование файлов через поиск и замену"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="search_replace",
            description="Выполняет поиск и замену текста в файле",
            parameters_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Путь к файлу для редактирования"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Текст для замены"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Новый текст"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Заменить все вхождения (по умолчанию только первое)",
                        "default": False
                    }
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Dict[str, Any]:
        """Выполнить поиск и замену"""
        path = self._resolve_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверка наличия старой строки
            if old_string not in content:
                return {
                    "status": "not_found",
                    "message": f"Текст '{old_string[:50]}...' не найден в файле"
                }
            
            # Замена
            if replace_all:
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                count = 1
            
            # Запись обратно
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return {
                "status": "success",
                "file": str(path.relative_to(self.workspace_root)),
                "replacements": count
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка при редактировании файла {file_path}: {str(e)}")
    
    def _resolve_path(self, file_path: str) -> Path:
        """Разрешение пути"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()


class DeleteFileTool(BaseTool):
    """Удаление файлов"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="delete_file",
            description="Удаляет файл по указанному пути",
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_file": {
                        "type": "string",
                        "description": "Путь к файлу для удаления"
                    }
                },
                "required": ["target_file"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(self, target_file: str) -> Dict[str, Any]:
        """Удалить файл"""
        path = self._resolve_path(target_file)
        
        if not path.exists():
            return {
                "status": "not_found",
                "message": f"Файл не найден: {target_file}"
            }
        
        if not path.is_file():
            raise ValueError(f"Путь не является файлом: {target_file}")
        
        # Проверка безопасности (не удалять важные файлы)
        critical_files = {'.git', '.env', 'requirements.txt', 'package.json'}
        if path.name in critical_files:
            raise ValueError(f"Удаление критических файлов запрещено: {target_file}")
        
        try:
            path.unlink()
            return {
                "status": "success",
                "file": str(path.relative_to(self.workspace_root))
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка при удалении файла {target_file}: {str(e)}")
    
    def _resolve_path(self, file_path: str) -> Path:
        """Разрешение пути"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

