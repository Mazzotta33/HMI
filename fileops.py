"""Общие операции для командного языка и интерфейса с меню."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import shutil


class FileError(Exception):
    """Ошибка, которую можно показать пользователю."""


@dataclass(frozen=True)
class Entry:
    name: str
    is_dir: bool
    size: int
    modified: float

    @property
    def date(self):
        return datetime.fromtimestamp(self.modified).strftime('%d.%m.%Y %H:%M')


def directory(base, value='.'):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(base) / path
    try:
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise FileError(f'Это файл, а не каталог: {path}')
        # Проверяем возможность чтения, а не только существование.
        with os.scandir(path):
            pass
        return path
    except OSError as exc:
        raise FileError(f'Каталог недоступен: {path}. {exc.strerror}') from exc


def matches(name, mask):
    """Только * и ? — специальные символы; сравнение без учёта регистра."""
    import re
    expression = ''.join('.*' if c == '*' else '.' if c == '?' else re.escape(c)
                         for c in mask)
    return re.fullmatch(expression, name, re.IGNORECASE) is not None


def list_directory(path, mask='*'):
    try:
        result = []
        for child in Path(path).iterdir():
            if matches(child.name, mask):
                info = child.stat()
                result.append(Entry(child.name, child.is_dir(), info.st_size, info.st_mtime))
        return sorted(result, key=lambda e: (not e.is_dir, e.name.casefold()))
    except OSError as exc:
        raise FileError(f'Не удалось прочитать каталог: {exc}') from exc


def select_files(path, mask):
    if not mask or any(c in mask for c in '/\\:'):
        raise FileError('Укажите имя или маску без пути. Для перехода используйте cd.')
    files = [e.name for e in list_directory(path, mask) if not e.is_dir]
    if not files:
        raise FileError(f'Нет файлов, соответствующих имени или маске: {mask}')
    return files


def plan_copy(source, names, target):
    """Проверяет весь набор до копирования. Существующие объекты не заменяются."""
    source = directory(source)
    target = directory(source, str(target))
    if source == target:
        raise FileError('Каталог назначения совпадает с исходным каталогом.')
    names = list(dict.fromkeys(names))
    if not names:
        raise FileError('Не выбраны файлы для копирования.')
    try:
        existing = {p.name.casefold() for p in target.iterdir()}
    except OSError as exc:
        raise FileError(f'Не удалось прочитать каталог назначения: {exc}') from exc
    plan = []
    for name in names:
        if name in ('.', '..') or Path(name).name != name or any(c in name for c in '/\\:'):
            raise FileError(f'Недопустимое имя файла: {name}')
        src, dst = source / name, target / name
        if src.is_symlink() or not src.is_file():
            raise FileError(f'Не является обычным файлом (либо является ссылкой): {name}')
        if name.casefold() in existing:
            raise FileError(f'В каталоге назначения уже есть «{name}». Копирование отменено.')
        existing.add(name.casefold())
        plan.append((src, dst))
    return plan


def copy_files(source, names, target, progress=None):
    """Копирует с исключительным созданием: чужие файлы никогда не затираются.

    При ошибке удаляется только незавершённая копия текущего файла.
    Уже завершённые копии сохраняются; их количество включается в ошибку.
    """
    completed = []
    try:
        plan = plan_copy(source, names, target)
        for src, dst in plan:
            created = False
            try:
                with src.open('rb') as reader:
                    with dst.open('xb') as writer:
                        created = True
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
            except OSError:
                if created:
                    dst.unlink(missing_ok=True)
                raise
            completed.append(dst)
            if progress:
                progress(len(completed), len(plan), src.name)
    except OSError as exc:
        raise FileError(f'Ошибка копирования: {exc}. Завершено файлов: {len(completed)}. '
                        'Завершённые копии сохранены; проверьте каталог назначения.') from exc
    return completed
