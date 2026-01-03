"""Инструменты для управления списком задач"""

import json
import yaml
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import logging

from ..base import BaseTool

logger = logging.getLogger(__name__)


class TodoWriteTool(BaseTool):
    """Управление списком задач (TODO)"""
    
    def __init__(self, workspace_root: str = ".", todo_file: str = ".todo.json"):
        super().__init__(
            name="todo_write",
            description="Создает и управляет списком задач (TODO). Задачи могут быть pending, in_progress, completed, cancelled",
            parameters_schema={
                "type": "object",
                "properties": {
                    "merge": {
                        "type": "boolean",
                        "description": "Объединить с существующими задачами (true) или заменить (false)",
                        "default": True
                    },
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "cancelled"]
                                }
                            },
                            "required": ["id", "content", "status"]
                        },
                        "description": "Список задач"
                    }
                },
                "required": ["todos"]
            }
        )
        self.workspace_root = Path(workspace_root).resolve()
        self.todo_file = self.workspace_root / todo_file
    
    async def execute(
        self,
        todos: List[Dict[str, Any]],
        merge: bool = True,
    ) -> Dict[str, Any]:
        """Записать задачи"""
        # Загрузка существующих задач
        existing_todos = {}
        if merge and self.todo_file.exists():
            try:
                with open(self.todo_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_todos = {todo["id"]: todo for todo in data.get("todos", [])}
            except Exception as e:
                logger.warning(f"Ошибка при загрузке существующих задач: {e}")
        
        # Обновление задач
        if merge:
            for todo in todos:
                existing_todos[todo["id"]] = todo
            final_todos = list(existing_todos.values())
        else:
            final_todos = todos
        
        # Добавление временных меток
        for todo in final_todos:
            if "updated_at" not in todo:
                todo["updated_at"] = datetime.now().isoformat()
            elif todo["id"] in [t["id"] for t in todos]:
                todo["updated_at"] = datetime.now().isoformat()
        
        # Сохранение
        data = {
            "todos": final_todos,
            "updated_at": datetime.now().isoformat()
        }
        
        try:
            with open(self.todo_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return {
                "status": "success",
                "total_todos": len(final_todos),
                "file": str(self.todo_file.relative_to(self.workspace_root))
            }
        except Exception as e:
            raise RuntimeError(f"Ошибка при сохранении задач: {str(e)}")
    
    async def read_todos(self) -> List[Dict[str, Any]]:
        """Прочитать все задачи (вспомогательный метод)"""
        if not self.todo_file.exists():
            return []
        
        try:
            with open(self.todo_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("todos", [])
        except Exception as e:
            logger.error(f"Ошибка при чтении задач: {e}")
            return []

