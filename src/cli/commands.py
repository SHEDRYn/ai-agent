"""CLI команды"""

import asyncio
import yaml
import json
from pathlib import Path
from typing import Optional
import logging

from ..agent.orchestrator import AgentOrchestrator
from ..llm.client import LLMClient
from ..tools.registry import ToolRegistry
from ..tools.code.indexer import CodeIndexer
from ..tools.code.search import CodebaseSearchTool, GrepTool, GlobFileSearchTool
from ..tools.file.operations import ReadFileTool, WriteFileTool, SearchReplaceTool, DeleteFileTool
from ..tools.file.directory import ListDirTool
from ..tools.dev.linter import ReadLintsTool
from ..tools.dev.terminal import RunTerminalCmdTool
from ..tools.dev.todo import TodoWriteTool
from ..tools.external.web import WebSearchTool
from ..mcp.client import MCPClient
from ..mcp.servers import load_mcp_config

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Настройка логирования"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def load_config(config_path: Optional[str] = None) -> dict:
    """Загрузка конфигурации"""
    if config_path is None:
        config_path = "config/default.yaml"
    
    config_file = Path(config_path)
    if not config_file.exists():
        logger.warning(f"Файл конфигурации не найден: {config_path}")
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


async def init_agent(config: dict, workspace_root: str = ".") -> AgentOrchestrator:
    """Инициализация агента"""
    # LLM клиент
    llm_config = config.get("llm", {})
    llm_client = LLMClient(
        model=llm_config.get("model", "gpt-4"),
        api_key=llm_config.get("api_key"),
        base_url=llm_config.get("base_url"),
        temperature=llm_config.get("temperature", 0.7),
        max_tokens=llm_config.get("max_tokens"),
    )
    
    # Регистр инструментов
    tool_registry = ToolRegistry()
    tools_config = config.get("tools", {})
    agent_config = config.get("agent", {})
    workspace = agent_config.get("workspace_root", workspace_root)
    
    # Индексатор кода
    code_search_config = tools_config.get("codebase_search", {})
    code_indexer = CodeIndexer(
        index_path=code_search_config.get("index_path", ".code_index"),
        embedding_model=code_search_config.get("embedding_model", "text-embedding-3-small"),
        api_key=llm_config.get("api_key"),
        base_url=llm_config.get("base_url"),
    )
    
    # Регистрация инструментов кода
    if tools_config.get("codebase_search", {}).get("enabled", True):
        tool_registry.register(CodebaseSearchTool(code_indexer))
    if tools_config.get("grep", {}).get("enabled", True):
        tool_registry.register(GrepTool(workspace))
    if tools_config.get("glob_file_search", {}).get("enabled", True):
        tool_registry.register(GlobFileSearchTool(workspace))
    
    # Регистрация инструментов файлов
    if tools_config.get("read_file", {}).get("enabled", True):
        tool_registry.register(ReadFileTool(workspace))
    if tools_config.get("write", {}).get("enabled", True):
        tool_registry.register(WriteFileTool(workspace))
    if tools_config.get("search_replace", {}).get("enabled", True):
        tool_registry.register(SearchReplaceTool(workspace))
    if tools_config.get("delete_file", {}).get("enabled", True):
        tool_registry.register(DeleteFileTool(workspace))
    if tools_config.get("list_dir", {}).get("enabled", True):
        tool_registry.register(ListDirTool(workspace))
    
    # Регистрация инструментов разработки
    if tools_config.get("read_lints", {}).get("enabled", True):
        tool_registry.register(ReadLintsTool(workspace))
    
    terminal_config = tools_config.get("run_terminal_cmd", {})
    if terminal_config.get("enabled", True):
        tool_registry.register(RunTerminalCmdTool(
            workspace,
            max_timeout=terminal_config.get("max_timeout", 300)
        ))
    
    todo_config = tools_config.get("todo_write", {})
    if todo_config.get("enabled", True):
        tool_registry.register(TodoWriteTool(
            workspace,
            todo_file=todo_config.get("todo_file", ".todo.json")
        ))
    
    # Регистрация внешних инструментов
    if tools_config.get("web_search", {}).get("enabled", True):
        tool_registry.register(WebSearchTool())
    
    # MCP клиент
    mcp_client = None
    mcp_servers_config = config.get("mcpServers", {})
    if mcp_servers_config:
        mcp_client = MCPClient()
        for name, server_config in mcp_servers_config.items():
            try:
                await mcp_client.connect_server(name, server_config)
            except Exception as e:
                logger.warning(f"Не удалось подключиться к MCP серверу {name}: {e}")
    
    # Создание оркестратора
    agent_config = config.get("agent", {})
    orchestrator = AgentOrchestrator(
        llm_client=llm_client,
        tool_registry=tool_registry,
        mcp_client=mcp_client,
        max_iterations=agent_config.get("max_iterations", 20),
    )
    
    return orchestrator


async def cmd_chat(config_path: Optional[str] = None, verbose: bool = False):
    """Интерактивный чат с агентом"""
    setup_logging(verbose)
    config = load_config(config_path)
    
    print("Инициализация агента...")
    agent = await init_agent(config)
    print("Агент готов! Введите 'quit' или 'exit' для выхода.\n")
    
    while True:
        try:
            user_input = input("Вы: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if not user_input:
                continue
            
            print("\nАгент думает...")
            response = await agent.process_user_request(user_input)
            print(f"\nАгент: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\nВыход...")
            break
        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            print(f"\nОшибка: {e}\n")
    
    # Очистка
    if agent.mcp_client:
        await agent.mcp_client.disconnect_all()


async def cmd_execute(query: str, config_path: Optional[str] = None, verbose: bool = False):
    """Одноразовое выполнение запроса"""
    setup_logging(verbose)
    config = load_config(config_path)
    
    agent = await init_agent(config)
    
    try:
        response = await agent.process_user_request(query)
        print(response)
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        print(f"Ошибка: {e}")
    finally:
        if agent.mcp_client:
            await agent.mcp_client.disconnect_all()


async def cmd_index(project_path: str = ".", config_path: Optional[str] = None, verbose: bool = False):
    """Индексация проекта"""
    setup_logging(verbose)
    config = load_config(config_path)
    
    llm_config = config.get("llm", {})
    code_search_config = config.get("tools", {}).get("codebase_search", {})
    indexer = CodeIndexer(
        index_path=code_search_config.get("index_path", ".code_index"),
        embedding_model=code_search_config.get("embedding_model", "text-embedding-3-small"),
        api_key=llm_config.get("api_key"),
        base_url=llm_config.get("base_url"),
    )
    
    print(f"Начало индексации проекта: {project_path}")
    count = await indexer.index_project(project_path)
    print(f"Индексация завершена. Проиндексировано файлов: {count}")

