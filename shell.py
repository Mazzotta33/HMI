"""Командный интерфейс. Запуск: python shell.py [каталог]."""
import argparse
from pathlib import Path
from fileops import (
    FileError, copy_files, list_directory, resolve_directory, select_file_names,
)


HELP = '''Команды:
  dir [маска]                 Содержимое текущего каталога
  cd [путь]                   Перейти в каталог / показать текущий путь
  copy <имя|маска> <каталог>   Копировать файлы в существующий каталог
  help [команда]              Справка
  exit                        Выход

Маски: * — любое число символов, ? — ровно один символ.
Имена и пути с пробелами заключайте в двойные кавычки.
Пути Windows сохраняют обратные слеши. Регистр команд и масок не важен.
Копируются только файлы текущего каталога, без вложенных папок и ссылок.
Исходные файлы сохраняются. Существующие файлы не перезаписываются.

Примеры:
  dir *.txt
  cd "D:\\Учебные работы"
  copy "мой файл.txt" "D:\\Архив"
  copy *.txt ..\\Результат
  copy отчёт_?.docx "D:\\Архив"'''


COMMAND_ARGUMENT_COUNTS = {
    'dir': (0, 1),
    'cd': (0, 1),
    'copy': (2, 2),
    'help': (0, 1),
    'exit': (0, 0),
}


def tokenize(line: str) -> list[str]:
    """Кавычки группируют пробелы, обратные слеши остаются буквальными."""
    arguments = []
    current_argument = []
    inside_quotes = False
    argument_started = False
    for character in line:
        if character == '"':
            inside_quotes = not inside_quotes
            argument_started = True
        elif character.isspace() and not inside_quotes:
            if argument_started:
                arguments.append(''.join(current_argument))
                current_argument = []
                argument_started = False
        else:
            current_argument.append(character)
            argument_started = True
    if inside_quotes:
        raise FileError('Не закрыта двойная кавычка.')
    if argument_started:
        arguments.append(''.join(current_argument))
    return arguments


class Shell:
    """Хранит текущий каталог и выполняет команды лабораторного языка."""

    def __init__(self, initial_directory: str = '.'):
        self.current_directory = resolve_directory(Path.cwd(), initial_directory)

    def execute(self, line: str) -> bool:
        """Выполняет строку; False означает команду завершения работы."""
        arguments = tokenize(line)
        if not arguments:
            return True
        command, *parameters = arguments
        command = command.lower()
        if command not in COMMAND_ARGUMENT_COUNTS:
            raise FileError(f'Неизвестная команда: {command}. Введите help.')
        minimum_count, maximum_count = COMMAND_ARGUMENT_COUNTS[command]
        if not minimum_count <= len(parameters) <= maximum_count:
            raise FileError(f'Неверное число параметров: {command}. Введите help {command}.')
        if command == 'exit':
            return False
        handlers = {
            'help': self.show_help,
            'cd': self.change_directory,
            'dir': self.show_directory,
            'copy': self.copy_to_directory,
        }
        handlers[command](*parameters)
        return True

    def show_help(self, command: str | None = None) -> None:
        if command and command.lower() not in COMMAND_ARGUMENT_COUNTS:
            raise FileError(f'Неизвестная команда: {command}')
        print(HELP)

    def change_directory(self, path: str | None = None) -> None:
        if path is not None:
            self.current_directory = resolve_directory(self.current_directory, path)
        print(self.current_directory)

    def show_directory(self, mask: str = '*') -> None:
        entries = list_directory(self.current_directory, mask)
        for entry in entries:
            size_text = '<КАТАЛОГ>' if entry.is_dir else f'{entry.size:,} Б'
            print(f'{entry.formatted_modified_time}  {size_text:>15}  {entry.name}')
        directory_count = sum(entry.is_dir for entry in entries)
        file_count = len(entries) - directory_count
        print(f'Каталогов: {directory_count}; файлов: {file_count}')

    def copy_to_directory(self, mask: str, destination_directory: str) -> None:
        file_names = select_file_names(self.current_directory, mask)
        copied_paths = copy_files(self.current_directory, file_names, destination_directory)
        for copied_path in copied_paths:
            print(f'{copied_path.name} → {copied_path.parent}')
        print(f'Скопировано файлов: {len(copied_paths)}')


def main():
    parser = argparse.ArgumentParser(description='HMI — копирование файлов, командный язык')
    parser.add_argument('directory', nargs='?', default='.')
    args = parser.parse_args()
    try:
        shell = Shell(args.directory)
    except FileError as exc:
        parser.exit(1, f'{exc}\n')
    print('HMI — копирование в указанный каталог. Справка: help')
    while True:
        try:
            if not shell.execute(input(f'{shell.current_directory}> ')):
                break
        except (EOFError, KeyboardInterrupt):
            print('\nВыход.')
            break
        except FileError as exc:
            print(f'Ошибка: {exc}')


if __name__ == '__main__':
    main()
