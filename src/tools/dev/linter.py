"""Инструменты для проверки кода линтерами"""

import subprocess
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from ..base import BaseTool

logger = logging.getLogger(__name__)


class ReadLintsTool(BaseTool):
    """Проверка ошибок линтера"""
    
    def __init__(self, workspace_root: str = "."):
        super().__init__(
            name="read_lints",
            description="Проверяет код с помощью линтеров (flake8, pylint, mypy и т.д.) и возвращает найденные ошибки",
            parameters_schema={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Пути к файлам или директориям для проверки (если не указано - весь проект)"
                    },
                    "linter": {
                        "type": "string",
                        "enum": ["auto", "flake8", "pylint", "mypy", "ruff"],
                        "description": "Используемый линтер (auto - автоматический выбор)",
                        "default": "auto"
                    }
                },
                "required": []
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
    
    async def execute(
        self,
        paths: Optional[List[str]] = None,
        linter: str = "auto",
    ) -> Dict[str, Any]:
        """Проверить код линтером"""
        if paths is None:
            paths = [str(self.workspace_root)]
        
        # Определение линтера
        if linter == "auto":
            linter = self._detect_linter()
        
        if linter == "flake8":
            return await self._run_flake8(paths)
        elif linter == "pylint":
            return await self._run_pylint(paths)
        elif linter == "mypy":
            return await self._run_mypy(paths)
        elif linter == "ruff":
            return await self._run_ruff(paths)
        else:
            return {
                "error": f"Неподдерживаемый линтер: {linter}",
                "linter": linter
            }
    
    def _detect_linter(self) -> str:
        """Автоматическое определение доступного линтера"""
        # Проверка наличия линтеров
        for linter in ["ruff", "flake8", "pylint", "mypy"]:
            try:
                result = subprocess.run(
                    [linter, "--version"],
                    capture_output=True,
                    timeout=2,
                    cwd=self.workspace_root
                )
                if result.returncode == 0 or result.returncode == 1:  # Некоторые линтеры возвращают 1 для --version
                    return linter
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        return "flake8"  # По умолчанию
    
    async def _run_flake8(self, paths: List[str]) -> Dict[str, Any]:
        """Запуск flake8"""
        try:
            cmd = ["flake8", "--format=json", *paths]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_root
            )
            
            errors = []
            if result.stdout:
                try:
                    # flake8 --format=json возвращает JSON построчно
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            errors.append(json.loads(line))
                except json.JSONDecodeError:
                    # Парсинг обычного вывода
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            parts = line.split(':', 3)
                            if len(parts) >= 4:
                                errors.append({
                                    "filename": parts[0],
                                    "line_number": int(parts[1]),
                                    "column_number": int(parts[2]),
                                    "text": parts[3].strip(),
                                    "code": parts[3].strip().split()[0] if parts[3].strip() else ""
                                })
            
            return {
                "linter": "flake8",
                "errors": errors,
                "error_count": len(errors)
            }
        except subprocess.TimeoutExpired:
            return {"linter": "flake8", "error": "Таймаут выполнения", "errors": []}
        except FileNotFoundError:
            return {"linter": "flake8", "error": "flake8 не установлен", "errors": []}
        except Exception as e:
            return {"linter": "flake8", "error": str(e), "errors": []}
    
    async def _run_pylint(self, paths: List[str]) -> Dict[str, Any]:
        """Запуск pylint"""
        try:
            cmd = ["pylint", "--output-format=json", *paths]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.workspace_root
            )
            
            errors = []
            if result.stdout:
                try:
                    errors = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            
            return {
                "linter": "pylint",
                "errors": errors,
                "error_count": len(errors)
            }
        except subprocess.TimeoutExpired:
            return {"linter": "pylint", "error": "Таймаут выполнения", "errors": []}
        except FileNotFoundError:
            return {"linter": "pylint", "error": "pylint не установлен", "errors": []}
        except Exception as e:
            return {"linter": "pylint", "error": str(e), "errors": []}
    
    async def _run_mypy(self, paths: List[str]) -> Dict[str, Any]:
        """Запуск mypy"""
        try:
            cmd = ["mypy", "--show-error-codes", "--no-error-summary", *paths]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.workspace_root
            )
            
            errors = []
            for line in result.stdout.split('\n'):
                if ':' in line and 'error:' in line:
                    parts = line.split(':', 3)
                    if len(parts) >= 4:
                        errors.append({
                            "filename": parts[0],
                            "line_number": int(parts[1]),
                            "text": parts[3].strip(),
                        })
            
            return {
                "linter": "mypy",
                "errors": errors,
                "error_count": len(errors)
            }
        except subprocess.TimeoutExpired:
            return {"linter": "mypy", "error": "Таймаут выполнения", "errors": []}
        except FileNotFoundError:
            return {"linter": "mypy", "error": "mypy не установлен", "errors": []}
        except Exception as e:
            return {"linter": "mypy", "error": str(e), "errors": []}
    
    async def _run_ruff(self, paths: List[str]) -> Dict[str, Any]:
        """Запуск ruff"""
        try:
            cmd = ["ruff", "check", "--output-format=json", *paths]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_root
            )
            
            errors = []
            if result.stdout:
                try:
                    errors = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            
            return {
                "linter": "ruff",
                "errors": errors,
                "error_count": len(errors)
            }
        except subprocess.TimeoutExpired:
            return {"linter": "ruff", "error": "Таймаут выполнения", "errors": []}
        except FileNotFoundError:
            return {"linter": "ruff", "error": "ruff не установлен", "errors": []}
        except Exception as e:
            return {"linter": "ruff", "error": str(e), "errors": []}

