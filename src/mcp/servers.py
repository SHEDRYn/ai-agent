"""Управление MCP серверами"""

import yaml
import json
from typing import Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def load_mcp_config(config_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Загрузка конфигурации MCP серверов
    
    Args:
        config_path: Путь к файлу конфигурации (YAML или JSON)
    
    Returns:
        Словарь с конфигурацией серверов
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Файл конфигурации не найден: {config_path}")
        return {}
    
    try:
        if config_file.suffix in ['.yaml', '.yml']:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        elif config_file.suffix == '.json':
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {config_file.suffix}")
        
        # Извлечение mcpServers
        mcp_servers = data.get("mcpServers", {})
        return mcp_servers
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации MCP: {e}")
        return {}

