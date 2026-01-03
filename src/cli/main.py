"""Точка входа CLI"""

import click
import asyncio
from .commands import cmd_chat, cmd_execute, cmd_index


@click.group()
def cli():
    """ИИ-агент с поддержкой инструментов и MCP-серверов"""
    pass


@cli.command()
@click.option('--config', '-c', help='Путь к файлу конфигурации')
@click.option('--verbose', '-v', is_flag=True, help='Подробный вывод')
def chat(config, verbose):
    """Интерактивный чат с агентом"""
    asyncio.run(cmd_chat(config, verbose))


@cli.command()
@click.argument('query')
@click.option('--config', '-c', help='Путь к файлу конфигурации')
@click.option('--verbose', '-v', is_flag=True, help='Подробный вывод')
def execute(query, config, verbose):
    """Выполнить один запрос"""
    asyncio.run(cmd_execute(query, config, verbose))


@cli.command()
@click.argument('project_path', default='.')
@click.option('--config', '-c', help='Путь к файлу конфигурации')
@click.option('--verbose', '-v', is_flag=True, help='Подробный вывод')
def index(project_path, config, verbose):
    """Проиндексировать проект для семантического поиска"""
    asyncio.run(cmd_index(project_path, config, verbose))


def main():
    """Главная функция"""
    cli()


if __name__ == '__main__':
    main()

