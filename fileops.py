"""Общие операции для командного языка и интерфейса с меню."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
import os
import re
import shutil


class FileError(Exception):
    """Ошибка, которую можно показать пользователю."""


@dataclass(frozen=True)
class DirectoryEntry:
    """Сведения об одном объекте каталога без привязки к интерфейсу."""
    name: str
    is_dir: bool
    size: int
    modified: float

    @property
    def formatted_modified_time(self) -> str:
        return datetime.fromtimestamp(self.modified).strftime('%d.%m.%Y %H:%M')


def resolve_directory(base_directory: Path, path_text: str = '.') -> Path:
    """Разрешает путь относительно base_directory и проверяет чтение каталога."""
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path(base_directory) / path
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


def matches_mask(file_name: str, mask: str) -> bool:
    """Только * и ? — специальные символы; сравнение без учёта регистра."""
    pattern_parts = []
    for character in mask:
        if character == '*':
            pattern_parts.append('.*')
        elif character == '?':
            pattern_parts.append('.')
        else:
            pattern_parts.append(re.escape(character))
    return re.fullmatch(''.join(pattern_parts), file_name, re.IGNORECASE) is not None


def list_directory(directory_path: Path, mask: str = '*') -> list[DirectoryEntry]:
    try:
        entries = []
        for child_path in Path(directory_path).iterdir():
            if matches_mask(child_path.name, mask):
                file_info = child_path.stat()
                entries.append(DirectoryEntry(
                    child_path.name, child_path.is_dir(),
                    file_info.st_size, file_info.st_mtime,
                ))
        return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.casefold()))
    except OSError as exc:
        raise FileError(f'Не удалось прочитать каталог: {exc}') from exc


def select_file_names(directory_path: Path, mask: str) -> list[str]:
    """Отбирает имена файлов текущего каталога по имени или маске."""
    if not mask or any(character in mask for character in '/\\:'):
        raise FileError('Укажите имя или маску без пути. Для перехода используйте cd.')
    file_names = [entry.name for entry in list_directory(directory_path, mask) if not entry.is_dir]
    if not file_names:
        raise FileError(f'Нет файлов, соответствующих имени или маске: {mask}')
    return file_names


def build_copy_plan(
    source_directory: Path,
    file_names: Iterable[str],
    destination_directory: Path | str,
) -> list[tuple[Path, Path]]:
    """Проверяет весь набор до копирования. Существующие объекты не заменяются."""
    source_directory = resolve_directory(source_directory)
    destination_directory = resolve_directory(source_directory, str(destination_directory))
    if source_directory == destination_directory:
        raise FileError('Каталог назначения совпадает с исходным каталогом.')
    # Повторно выделенный файл копируется один раз, исходный порядок сохраняется.
    unique_file_names = list(dict.fromkeys(file_names))
    if not unique_file_names:
        raise FileError('Не выбраны файлы для копирования.')
    try:
        occupied_names = {path.name.casefold() for path in destination_directory.iterdir()}
    except OSError as exc:
        raise FileError(f'Не удалось прочитать каталог назначения: {exc}') from exc
    plan = []
    for file_name in unique_file_names:
        if (file_name in ('.', '..') or Path(file_name).name != file_name
                or any(character in file_name for character in '/\\:')):
            raise FileError(f'Недопустимое имя файла: {file_name}')
        source_path = source_directory / file_name
        destination_path = destination_directory / file_name
        if source_path.is_symlink() or not source_path.is_file():
            raise FileError(f'Не является обычным файлом (либо является ссылкой): {file_name}')
        if file_name.casefold() in occupied_names:
            raise FileError(f'В каталоге назначения уже есть «{file_name}». Копирование отменено.')
        occupied_names.add(file_name.casefold())
        plan.append((source_path, destination_path))
    return plan


def copy_files(
    source_directory: Path,
    file_names: Iterable[str],
    destination_directory: Path | str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """Копирует с исключительным созданием: чужие файлы никогда не затираются.

    При ошибке удаляется только незавершённая копия текущего файла.
    Уже завершённые копии сохраняются; их количество включается в ошибку.
    on_progress вызывается после каждого завершённого файла с количеством
    готовых файлов, общим количеством и именем файла. Callback выполняется
    в том же потоке, что и copy_files; при успехе возвращаются пути копий.
    """
    completed_paths = []
    try:
        copy_plan = build_copy_plan(source_directory, file_names, destination_directory)
        for source_path, destination_path in copy_plan:
            destination_created = False
            try:
                with source_path.open('rb') as source_stream:
                    with destination_path.open('xb') as destination_stream:
                        destination_created = True
                        shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)
            except OSError:
                if destination_created:
                    destination_path.unlink(missing_ok=True)
                raise
            completed_paths.append(destination_path)
            if on_progress:
                on_progress(len(completed_paths), len(copy_plan), source_path.name)
    except OSError as exc:
        raise FileError(f'Ошибка копирования: {exc}. Завершено файлов: {len(completed_paths)}. '
                        'Завершённые копии сохранены; проверьте каталог назначения.') from exc
    return completed_paths
