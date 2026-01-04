"""Инструменты для работы с директориями"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..base import BaseTool

logger = logging.getLogger(__name__)


class ListDirTool(BaseTool):
    """Просмотр содержимого директорий"""

    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="list_dir",
            description="Просматривает содержимое директории",
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_directory": {
                        "type": "string",
                        "description": "Путь к директории (по умолчанию корень проекта)",
                    },
                    "ignore_globs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список glob паттернов для игнорирования файлов/директорий",
                    },
                },
                "required": [],
            },
        )
        self.workspace_root = Path(workspace_root).resolve()

    async def execute(
        self,
        target_directory: Optional[str] = None,
        ignore_globs: Optional[List[str]] = None,
    ) -> Dict:
        """Просмотреть содержимое директории"""
        if target_directory:
            dir_path = self._resolve_path(target_directory)
        else:
            dir_path = self.workspace_root

        if not dir_path.exists():
            raise FileNotFoundError(f"Директория не найдена: {target_directory or '.'}")

        if not dir_path.is_dir():
            raise ValueError(f"Путь не является директорией: {target_directory}")

        # Значения по умолчанию для игнорирования
        if ignore_globs is None:
            ignore_globs = [
                "**/__pycache__/**",
                "**/.git/**",
                "**/node_modules/**",
                "**/.venv/**",
                "**/venv/**",
                "**/.code_index/**",
            ]

        files = []
        directories = []

        try:
            entries = list(dir_path.iterdir())

            for entry in entries:
                # Проверка на игнорирование
                if self._should_ignore(entry, ignore_globs):
                    continue

                # Пропускаем записи, которые находятся вне workspace_root
                if not self._is_in_workspace(entry):
                    continue

                try:
                    relative_path = entry.relative_to(self.workspace_root)
                except ValueError:
                    # Если не удалось получить относительный путь, пропускаем
                    continue

                entry_info = {
                    "name": entry.name,
                    "path": str(relative_path),
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                }

                if entry.is_file():
                    try:
                        entry_info["size"] = entry.stat().st_size
                    except:
                        entry_info["size"] = None
                    files.append(entry_info)
                else:
                    directories.append(entry_info)

            return {
                "directory": str(dir_path.relative_to(self.workspace_root)),
                "files": sorted(files, key=lambda x: x["name"]),
                "directories": sorted(directories, key=lambda x: x["name"]),
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка при просмотре директории: {str(e)}")

    def _resolve_path(self, directory_path: str) -> Path:
        """Разрешение пути"""
        path = Path(directory_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        return path.resolve()

    def _is_in_workspace(self, path: Path) -> bool:
        """Проверка, находится ли путь внутри workspace_root"""
        try:
            resolved_path = path.resolve()
            resolved_workspace = self.workspace_root.resolve()
            # Используем relative_to для проверки - если путь находится внутри, ошибки не будет
            resolved_path.relative_to(resolved_workspace)
            return True
        except (ValueError, OSError):
            return False

    def _should_ignore(self, path: Path, ignore_globs: List[str]) -> bool:
        """Проверка, нужно ли игнорировать путь"""
        import fnmatch

        # Если путь находится вне workspace_root, игнорируем его
        if not self._is_in_workspace(path):
            return True

        try:
            relative_path = path.relative_to(self.workspace_root)
            path_str = str(relative_path)
        except ValueError:
            # Если не удалось получить относительный путь, игнорируем
            return True

        for pattern in ignore_globs:
            # Упрощенная проверка glob
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                path.name, pattern
            ):
                return True
            # Проверка родительских директорий
            for parent in path.parents:
                # Проверяем только родительские директории внутри workspace_root
                if not self._is_in_workspace(parent):
                    break
                try:
                    parent_relative = parent.relative_to(self.workspace_root)
                    if fnmatch.fnmatch(str(parent_relative), pattern):
                        return True
                except ValueError:
                    break

        return False
