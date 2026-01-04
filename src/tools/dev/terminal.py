"""Инструменты для выполнения команд в терминале"""

import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
import logging

from ..base import BaseTool

logger = logging.getLogger(__name__)


class RunTerminalCmdTool(BaseTool):
    """Выполнение команд в терминале"""

    def __init__(self, workspace_root: str = ".", max_timeout: int = 300):
        super().__init__(
            name="run_terminal_cmd",
            description="Выполняет системную команду в терминале и возвращает результат",
            parameters_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Команда для выполнения",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Рабочая директория (по умолчанию корень проекта)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Таймаут выполнения в секундах (по умолчанию 60)",
                        "default": 60,
                    },
                },
                "required": ["command"],
            },
        )
        self.workspace_root = Path(workspace_root).resolve()
        self.max_timeout = max_timeout

    async def execute(
        self,
        command: str,
        working_dir: Optional[str] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Выполнить команду"""
        # Безопасность: ограничение таймаута
        timeout = min(timeout, self.max_timeout)

        # Определение рабочей директории
        if working_dir:
            work_dir = Path(working_dir).resolve()
            if not work_dir.exists():
                raise ValueError(f"Рабочая директория не найдена: {working_dir}")
        else:
            work_dir = self.workspace_root

        # Проверка безопасности команды (базовая)
        dangerous_commands = ["rm -rf", "format", "del /f", "shutdown", "reboot"]
        command_lower = command.lower()
        for dangerous in dangerous_commands:
            if dangerous in command_lower:
                raise ValueError(f"Выполнение опасных команд запрещено: {dangerous}")

        try:
            # Выполнение команды
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                limit=1024 * 1024,  # Лимит вывода 1MB
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Таймаут выполнения ({timeout}s)",
                    "timeout": True,
                }

            return {
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "timeout": False,
            }
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды: {e}", exc_info=True)
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Ошибка выполнения: {str(e)}",
                "timeout": False,
            }
