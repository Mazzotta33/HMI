"""Командный интерфейс. Запуск: python shell.py [каталог]."""
import argparse
from pathlib import Path
from fileops import FileError, directory, list_directory, select_files, copy_files


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


def tokenize(line):
    """Кавычки группируют пробелы, обратные слеши остаются буквальными."""
    words, buffer, quoted, started = [], [], False, False
    for char in line:
        if char == '"':
            quoted = not quoted
            started = True
        elif char.isspace() and not quoted:
            if started:
                words.append(''.join(buffer))
                buffer, started = [], False
        else:
            buffer.append(char)
            started = True
    if quoted:
        raise FileError('Не закрыта двойная кавычка.')
    if started:
        words.append(''.join(buffer))
    return words


class Shell:
    def __init__(self, path='.'):
        self.cwd = directory(Path.cwd(), path)

    def execute(self, line):
        words = tokenize(line)
        if not words:
            return True
        command, *args = words
        command = command.lower()
        limits = {'dir': (0, 1), 'cd': (0, 1), 'copy': (2, 2), 'help': (0, 1), 'exit': (0, 0)}
        if command not in limits:
            raise FileError(f'Неизвестная команда: {command}. Введите help.')
        low, high = limits[command]
        if not low <= len(args) <= high:
            raise FileError(f'Неверное число параметров: {command}. Введите help {command}.')
        if command == 'exit':
            return False
        if command == 'help':
            if args and args[0].lower() not in limits:
                raise FileError(f'Неизвестная команда: {args[0]}')
            print(HELP)
        elif command == 'cd':
            if args:
                self.cwd = directory(self.cwd, args[0])
            print(self.cwd)
        elif command == 'dir':
            entries = list_directory(self.cwd, args[0] if args else '*')
            for entry in entries:
                size = '<КАТАЛОГ>' if entry.is_dir else f'{entry.size:,} Б'
                print(f'{entry.date}  {size:>15}  {entry.name}')
            print(f'Каталогов: {sum(e.is_dir for e in entries)}; файлов: {sum(not e.is_dir for e in entries)}')
        elif command == 'copy':
            names = select_files(self.cwd, args[0])
            paths = copy_files(self.cwd, names, args[1])
            for path in paths:
                print(f'{path.name} → {path.parent}')
            print(f'Скопировано файлов: {len(paths)}')
        return True


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
            if not shell.execute(input(f'{shell.cwd}> ')):
                break
        except (EOFError, KeyboardInterrupt):
            print('\nВыход.')
            break
        except FileError as exc:
            print(f'Ошибка: {exc}')


if __name__ == '__main__':
    main()
