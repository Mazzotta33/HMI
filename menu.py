"""Интерфейс с меню на стандартных виджетах Tkinter/ttk."""
import argparse
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from fileops import FileError, resolve_directory, list_directory, matches_mask, build_copy_plan, copy_files


class App(tk.Tk):
    """Окно файлового менеджера; операции с файлами выполняет fileops."""

    def __init__(self, initial_directory: str = '.'):
        super().__init__()
        self.title('HMI — Копирование в указанный каталог')
        self.geometry('980x640')
        self.minsize(720, 460)
        self.current_directory = resolve_directory(Path.cwd(), initial_directory)
        self.copy_in_progress = False
        self.copy_events = queue.Queue()
        self.directory_text = tk.StringVar()
        self.filter_mask = tk.StringVar(value='*')
        self.status_text = tk.StringVar()
        self.sort_column = 'name'
        self.sort_descending = False
        self.entries_by_name = {}
        self.build_menu()
        self.build_toolbar()
        self.build_action_panel()
        self.build_file_list()
        self.bind_keyboard_shortcuts()
        ttk.Label(self, textvariable=self.status_text, padding=10, anchor='w').pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, padding=10)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='↑ На уровень выше', command=self.up).pack(side='left')
        ttk.Label(toolbar, text='  Каталог: ').pack(side='left')
        address = ttk.Entry(toolbar, textvariable=self.directory_text)
        address.pack(side='left', fill='x', expand=True, padx=6)
        address.bind('<Return>', lambda e: self.navigate(self.directory_text.get()))
        ttk.Button(toolbar, text='Открыть…', command=self.choose_directory).pack(side='left')

    def build_action_panel(self) -> None:
        actions = ttk.Frame(self, padding=(10, 0, 10, 10))
        actions.pack(fill='x')
        self.copy_button = ttk.Button(actions, text='Копировать в…', command=self.copy_dialog)
        self.copy_button.pack(side='left')
        ttk.Button(actions, text='Выделить по маске…', command=self.select_mask).pack(side='left', padx=8)
        ttk.Label(actions, text='Показать:').pack(side='left', padx=(16, 4))
        mask_entry = ttk.Entry(actions, textvariable=self.filter_mask, width=18)
        mask_entry.pack(side='left')
        mask_entry.bind('<Return>', lambda e: self.refresh())
        ttk.Button(actions, text='Применить', command=self.refresh).pack(side='left', padx=6)

    def build_file_list(self) -> None:
        frame = ttk.Frame(self, padding=(10, 0))
        frame.pack(fill='both', expand=True)
        self.file_list = ttk.Treeview(frame, columns=('name', 'size', 'date'), show='headings', selectmode='extended')
        for key, title, width in [('name', 'Имя', 450), ('size', 'Размер, байт', 130), ('date', 'Изменён', 170)]:
            self.file_list.heading(key, text=title, command=lambda k=key: self.sort(k))
            self.file_list.column(key, width=width, anchor='e' if key == 'size' else 'w')
        self.file_list.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.file_list.yview)
        scroll.pack(side='right', fill='y')
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.bind('<<TreeviewSelect>>', lambda e: self.selection_changed())
        self.file_list.bind('<Double-1>', self.activate)
        self.file_list.bind('<Return>', self.activate)
        self.file_list.bind('<BackSpace>', lambda e: self.up())
        self.file_list.bind('<Button-3>', self.context_menu)
        self.file_list.bind('<Control-a>', lambda e: self.select_all())

    def bind_keyboard_shortcuts(self) -> None:
        self.bind('<F5>', lambda e: self.refresh())
        self.bind('<F1>', lambda e: self.show_help())
        self.bind('<Control-Shift-C>', lambda e: self.copy_dialog())

    def build_menu(self):
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label='Открыть каталог…', command=self.choose_directory)
        file_menu.add_command(label='На уровень выше', command=self.up)
        file_menu.add_separator()
        file_menu.add_command(label='Выход', command=self.close)
        bar.add_cascade(label='Файл', menu=file_menu)
        self.edit_menu = tk.Menu(bar, tearoff=False)
        self.edit_menu.add_command(label='Копировать в…', command=self.copy_dialog)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label='Выделить все файлы', command=self.select_all)
        self.edit_menu.add_command(label='Выделить по маске…', command=self.select_mask)
        self.edit_menu.add_command(label='Снять выделение', command=lambda: self.file_list.selection_remove(self.file_list.selection()))
        bar.add_cascade(label='Правка', menu=self.edit_menu)
        view = tk.Menu(bar, tearoff=False)
        view.add_command(label='Обновить', accelerator='F5', command=self.refresh)
        sorting = tk.Menu(view, tearoff=False)
        self.sort_column_choice = tk.StringVar(value='name')
        for key, label in [('name', 'По имени'), ('size', 'По размеру'), ('date', 'По времени изменения')]:
            sorting.add_radiobutton(label=label, variable=self.sort_column_choice, value=key,
                                    command=lambda k=key: self.sort(k))
        view.add_cascade(label='Сортировка', menu=sorting)
        bar.add_cascade(label='Вид', menu=view)
        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label='Как пользоваться', accelerator='F1', command=self.show_help)
        help_menu.add_command(label='О программе', command=lambda: messagebox.showinfo(
            'О программе', 'HMI\nЛабораторная работа № 2\nКомандный язык и меню\nВариант: копирование в указанный каталог.'))
        bar.add_cascade(label='Справка', menu=help_menu)
        self.configure(menu=bar)
        self.context_popup = tk.Menu(self, tearoff=False)
        self.context_popup.add_command(label='Копировать в…', command=self.copy_dialog)
        self.context_popup.add_command(label='Выделить все файлы', command=self.select_all)
        self.context_popup.add_command(label='Обновить', command=self.refresh)

    def navigate(self, value):
        if self.copy_in_progress:
            return
        try:
            new_directory = resolve_directory(self.current_directory, value)
            list_directory(new_directory)
            self.current_directory = new_directory
            self.refresh()
        except FileError as exc:
            self.directory_text.set(str(self.current_directory))
            messagebox.showerror('Переход невозможен', str(exc))

    def choose_directory(self):
        if not self.copy_in_progress:
            path = filedialog.askdirectory(initialdir=self.current_directory, title='Открыть каталог', mustexist=True)
            if path:
                self.navigate(path)

    def up(self):
        self.navigate(str(self.current_directory.parent))

    def refresh(self):
        if self.copy_in_progress:
            return
        try:
            entries = list_directory(self.current_directory, self.filter_mask.get() or '*')
        except FileError as exc:
            messagebox.showerror('Ошибка чтения', str(exc))
            return
        self.entries_by_name = {entry.name: entry for entry in entries}
        sort_keys = {
            'name': lambda entry: entry.name.casefold(),
            'size': lambda entry: entry.size,
            'date': lambda entry: entry.modified,
        }
        entries.sort(key=sort_keys[self.sort_column], reverse=self.sort_descending)
        entries.sort(key=lambda entry: not entry.is_dir)
        self.file_list.delete(*self.file_list.get_children())
        if self.current_directory.parent != self.current_directory:
            self.file_list.insert('', 'end', iid='..', values=('..', '<КАТАЛОГ>', ''))
        for entry in entries:
            self.file_list.insert('', 'end', iid=entry.name,
                             values=(entry.name, '<КАТАЛОГ>' if entry.is_dir else f'{entry.size:,}', entry.formatted_modified_time))
        self.directory_text.set(str(self.current_directory))
        self.selection_changed()

    def sort(self, key):
        if self.copy_in_progress:
            # Пункт-переключатель меню мог изменить StringVar до вызова обработчика.
            self.sort_column_choice.set(self.sort_column)
            return
        self.sort_descending = not self.sort_descending if self.sort_column == key else False
        self.sort_column = key
        self.sort_column_choice.set(key)
        self.refresh()

    def selected_files(self):
        return [name for name in self.file_list.selection()
                if name in self.entries_by_name and not self.entries_by_name[name].is_dir]

    def selection_changed(self):
        count = len(self.selected_files())
        state = 'normal' if count and not self.copy_in_progress else 'disabled'
        self.copy_button.configure(state=state)
        self.edit_menu.entryconfigure(0, state=state)
        self.context_popup.entryconfigure(0, state=state)
        if not self.copy_in_progress:
            self.status_text.set(f'Объектов: {len(self.entries_by_name)}   |   Выбрано файлов: {count}')

    def select_all(self):
        if not self.copy_in_progress:
            file_names = [name for name, entry in self.entries_by_name.items() if not entry.is_dir]
            self.file_list.selection_set(file_names)
        return 'break'

    def select_mask(self):
        if self.copy_in_progress:
            return
        mask = simpledialog.askstring('Выделение по маске', 'Маска (* — любые символы, ? — один):', initialvalue='*.txt', parent=self)
        if mask:
            file_names = [name for name, entry in self.entries_by_name.items()
                          if not entry.is_dir and matches_mask(name, mask)]
            self.file_list.selection_set(file_names)
            if not file_names:
                messagebox.showinfo('Выделение', 'Среди отображаемых файлов совпадений нет.')

    def activate(self, event=None):
        if self.copy_in_progress:
            return
        name = self.file_list.focus()
        if name == '..':
            self.up()
        elif name in self.entries_by_name and self.entries_by_name[name].is_dir:
            self.navigate(name)
        elif name:
            self.copy_dialog()

    def context_menu(self, event):
        item = self.file_list.identify_row(event.y)
        if item and item not in self.file_list.selection():
            self.file_list.selection_set(item)
        self.selection_changed()
        try:
            self.context_popup.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_popup.grab_release()

    def copy_dialog(self):
        if self.copy_in_progress:
            return
        file_names = self.selected_files()
        if not file_names:
            return
        destination_directory = filedialog.askdirectory(
            title='Копировать в указанный каталог',
            initialdir=self.current_directory, mustexist=True,
        )
        if not destination_directory:
            return
        try:
            build_copy_plan(self.current_directory, file_names, destination_directory)
        except (FileError, OSError) as exc:
            messagebox.showerror('Копирование невозможно', str(exc))
            return
        if not self.confirm_copy(file_names, destination_directory):
            return
        self.start_copy(file_names, destination_directory)

    def confirm_copy(self, file_names: list[str], destination_directory: str) -> bool:
        preview = '\n'.join(file_names[:12])
        if len(file_names) > 12:
            preview += f'\n… и ещё {len(file_names) - 12}'
        return messagebox.askokcancel(
            'Копирование файлов',
            f'Файлов: {len(file_names)}\n\n{preview}\n\n'
            f'Из: {self.current_directory}\nВ: {destination_directory}\n\n'
            'Существующие файлы не заменяются.',
        )

    def start_copy(self, file_names: list[str], destination_directory: str) -> None:
        self.copy_in_progress = True
        self.selection_changed()
        self.status_text.set('Копирование…')
        threading.Thread(
            target=self.run_copy_in_background,
            args=(self.current_directory, file_names, destination_directory),
            daemon=True,
        ).start()
        self.after(80, self.poll_copy)

    def run_copy_in_background(
        self, source_directory: Path, file_names: list[str], destination_directory: str,
    ) -> None:
        """Рабочий поток передаёт события через очередь, не обращаясь к Tkinter."""
        try:
            copied_paths = copy_files(
                source_directory, file_names, destination_directory,
                on_progress=self.report_copy_progress,
            )
            message = f'Скопировано файлов: {len(copied_paths)}. Каталог: {destination_directory}'
            self.copy_events.put(('done', message))
        except (FileError, OSError) as exc:
            self.copy_events.put(('error', str(exc)))

    def report_copy_progress(self, completed_count: int, total_count: int, file_name: str) -> None:
        self.copy_events.put(('progress', f'{completed_count}/{total_count}: {file_name}'))

    def poll_copy(self):
        try:
            while True:
                kind, text = self.copy_events.get_nowait()
                self.status_text.set(text)
                if kind in ('done', 'error'):
                    self.copy_in_progress = False
                    self.selection_changed()
                    self.status_text.set(text)
                    if kind == 'error':
                        messagebox.showerror('Ошибка копирования', text)
                    else:
                        messagebox.showinfo('Копирование завершено', text)
                    return
        except queue.Empty:
            pass
        self.after(80, self.poll_copy)

    def show_help(self):
        messagebox.showinfo('Как пользоваться',
            'Откройте каталог через меню «Файл» или адресную строку.\n'
            'Двойной щелчок по папке открывает её, Backspace — на уровень выше.\n'
            'Выделите файлы с Ctrl/Shift, все файлы или файлы по маске через «Правка».\n'
            'Выберите «Правка → Копировать в…» и каталог назначения.\n'
            'Двойной щелчок по файлу также открывает копирование.\n'
            'Фильтр ограничивает список и выделение. Сортировка — по заголовкам столбцов.\n'
            'Подкаталоги и символические ссылки не копируются.\n'
            'Во время копирования дождитесь результата, затем можно закрыть окно.')

    def close(self):
        if self.copy_in_progress:
            messagebox.showinfo('Копирование', 'Дождитесь завершения копирования файлов.')
        else:
            self.destroy()


def main():
    parser = argparse.ArgumentParser(description='HMI — интерфейс с меню')
    parser.add_argument('directory', nargs='?', default='.')
    args = parser.parse_args()
    try:
        App(args.directory).mainloop()
    except FileError as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
