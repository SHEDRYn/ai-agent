"""Базовые классы для инструментов"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
import json
import inspect
from functools import wraps


class BaseTool(ABC):
    """Абстрактный базовый класс для инструментов"""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
    ):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Выполнить инструмент"""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Получить схему инструмента в формате OpenAI tools"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """Валидация аргументов (базовая реализация, можно расширить)"""
        required = self.parameters_schema.get("required", [])
        properties = self.parameters_schema.get("properties", {})
        
        # Проверка обязательных параметров
        for param in required:
            if param not in arguments:
                return False
        
        # Проверка типов (базовая)
        for param, value in arguments.items():
            if param not in properties:
                continue
            param_schema = properties[param]
            expected_type = param_schema.get("type")
            if expected_type and not self._check_type(value, expected_type):
                return False
        
        return True
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Проверка типа значения"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        python_type = type_map.get(expected_type)
        if python_type:
            return isinstance(value, python_type)
        return True


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters_schema: Optional[Dict[str, Any]] = None,
):
    """
    Декоратор для регистрации функции как инструмента
    
    Args:
        name: Имя инструмента (по умолчанию имя функции)
        description: Описание инструмента (можно получить из docstring)
        parameters_schema: JSON Schema для параметров (можно автоматически из аннотаций)
    """
    def decorator(func: Callable):
        # Автоматическое определение параметров из аннотаций
        if parameters_schema is None:
            schema = _infer_schema_from_function(func)
        else:
            schema = parameters_schema
        
        # Определение имени
        tool_name = name or func.__name__
        
        # Определение описания
        tool_description = description or func.__doc__ or ""
        
        # Создание класса-обертки
        class ToolWrapper(BaseTool):
            def __init__(self):
                super().__init__(tool_name, tool_description, schema)
                self.func = func
            
            async def execute(self, **kwargs):
                if inspect.iscoroutinefunction(func):
                    return await self.func(**kwargs)
                else:
                    return self.func(**kwargs)
        
        wrapper = ToolWrapper()
        wrapper._original_func = func  # Сохраняем ссылку на оригинальную функцию
        return wrapper
    
    return decorator


def _infer_schema_from_function(func: Callable) -> Dict[str, Any]:
    """Автоматическое создание JSON Schema из аннотаций функции"""
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        
        param_info = {"type": "string"}  # По умолчанию
        
        if param.annotation != inspect.Parameter.empty:
            param_type = param.annotation
            if param_type in type_map:
                param_info["type"] = type_map[param_type]
            elif hasattr(param_type, "__origin__"):
                # Обработка Optional, Union и т.д.
                if param_type.__origin__ is type(None) or (
                    hasattr(param_type, "__args__") and type(None) in param_type.__args__
                ):
                    # Optional - не обязательный параметр
                    pass
                else:
                    origin = param_type.__origin__
                    if origin in type_map:
                        param_info["type"] = type_map[origin]
        
        properties[param_name] = param_info
        
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }

