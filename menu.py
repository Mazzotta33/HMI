"""Интерфейс с меню на стандартных виджетах Tkinter/ttk."""
import argparse
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from fileops import FileError, directory, list_directory, matches, plan_copy, copy_files
from shell import HELP


class App(tk.Tk):
    def __init__(self, path='.'):
        super().__init__()
        self.title('HMI — Копирование в указанный каталог')
        self.geometry('980x640')
        self.minsize(720, 460)
        self.cwd = directory(Path.cwd(), path)
        self.busy = False
        self.events = queue.Queue()
        self.path_var = tk.StringVar()
        self.filter_var = tk.StringVar(value='*')
        self.status = tk.StringVar()
        self.sort_key, self.reverse = 'name', False
        self.build_menu()
        toolbar = ttk.Frame(self, padding=10)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='↑ На уровень выше', command=self.up).pack(side='left')
        ttk.Label(toolbar, text='  Каталог: ').pack(side='left')
        address = ttk.Entry(toolbar, textvariable=self.path_var)
        address.pack(side='left', fill='x', expand=True, padx=6)
        address.bind('<Return>', lambda e: self.navigate(self.path_var.get()))
        ttk.Button(toolbar, text='Открыть…', command=self.choose_directory).pack(side='left')
        actions = ttk.Frame(self, padding=(10, 0, 10, 10))
        actions.pack(fill='x')
        self.copy_button = ttk.Button(actions, text='Копировать в…', command=self.copy_dialog)
        self.copy_button.pack(side='left')
        ttk.Button(actions, text='Выделить по маске…', command=self.select_mask).pack(side='left', padx=8)
        ttk.Label(actions, text='Показать:').pack(side='left', padx=(16, 4))
        mask_entry = ttk.Entry(actions, textvariable=self.filter_var, width=18)
        mask_entry.pack(side='left')
        mask_entry.bind('<Return>', lambda e: self.refresh())
        ttk.Button(actions, text='Применить', command=self.refresh).pack(side='left', padx=6)
        frame = ttk.Frame(self, padding=(10, 0))
        frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frame, columns=('name', 'size', 'date'), show='headings', selectmode='extended')
        for key, title, width in [('name', 'Имя', 450), ('size', 'Размер, байт', 130), ('date', 'Изменён', 170)]:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort(k))
            self.tree.column(key, width=width, anchor='e' if key == 'size' else 'w')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.selection_changed())
        self.tree.bind('<Double-1>', self.activate)
        self.tree.bind('<Return>', self.activate)
        self.tree.bind('<BackSpace>', lambda e: self.up())
        self.tree.bind('<Button-3>', self.context_menu)
        self.tree.bind('<Control-a>', lambda e: self.select_all())
        self.bind('<F5>', lambda e: self.refresh())
        self.bind('<F1>', lambda e: self.show_help())
        self.bind('<Control-Shift-C>', lambda e: self.copy_dialog())
        ttk.Label(self, textvariable=self.status, padding=10, anchor='w').pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def build_menu(self):
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label='Открыть каталог…', command=self.choose_directory)
        file_menu.add_command(label='На уровень выше', command=self.up)
        file_menu.add_separator()
        file_menu.add_command(label='Выход', command=self.close)
        bar.add_cascade(label='Файл', menu=file_menu)
        self.edit = tk.Menu(bar, tearoff=False)
        self.edit.add_command(label='Копировать в…', command=self.copy_dialog)
        self.edit.add_separator()
        self.edit.add_command(label='Выделить все файлы', command=self.select_all)
        self.edit.add_command(label='Выделить по маске…', command=self.select_mask)
        self.edit.add_command(label='Снять выделение', command=lambda: self.tree.selection_remove(self.tree.selection()))
        bar.add_cascade(label='Правка', menu=self.edit)
        view = tk.Menu(bar, tearoff=False)
        view.add_command(label='Обновить', accelerator='F5', command=self.refresh)
        sorting = tk.Menu(view, tearoff=False)
        self.sort_var = tk.StringVar(value='name')
        for key, label in [('name', 'По имени'), ('size', 'По размеру'), ('date', 'По времени изменения')]:
            sorting.add_radiobutton(label=label, variable=self.sort_var, value=key,
                                    command=lambda k=key: self.sort(k))
        view.add_cascade(label='Сортировка', menu=sorting)
        bar.add_cascade(label='Вид', menu=view)
        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label='Как пользоваться', accelerator='F1', command=self.show_help)
        help_menu.add_command(label='О программе', command=lambda: messagebox.showinfo(
            'О программе', 'HMI\nЛабораторная работа № 2\nКомандный язык и меню\nВариант: копирование в указанный каталог.'))
        bar.add_cascade(label='Справка', menu=help_menu)
        self.configure(menu=bar)
        self.popup = tk.Menu(self, tearoff=False)
        self.popup.add_command(label='Копировать в…', command=self.copy_dialog)
        self.popup.add_command(label='Выделить все файлы', command=self.select_all)
        self.popup.add_command(label='Обновить', command=self.refresh)

    def navigate(self, value):
        if self.busy:
            return
        try:
            new = directory(self.cwd, value)
            list_directory(new)
            self.cwd = new
            self.refresh()
        except FileError as exc:
            self.path_var.set(str(self.cwd))
            messagebox.showerror('Переход невозможен', str(exc))

    def choose_directory(self):
        if not self.busy:
            path = filedialog.askdirectory(initialdir=self.cwd, title='Открыть каталог', mustexist=True)
            if path:
                self.navigate(path)

    def up(self):
        self.navigate(str(self.cwd.parent))

    def refresh(self):
        if self.busy:
            return
        try:
            entries = list_directory(self.cwd, self.filter_var.get() or '*')
        except FileError as exc:
            messagebox.showerror('Ошибка чтения', str(exc))
            return
        self.entries = {e.name: e for e in entries}
        key = {'name': lambda e: e.name.casefold(), 'size': lambda e: e.size,
               'date': lambda e: e.modified}[self.sort_key]
        entries.sort(key=key, reverse=self.reverse)
        entries.sort(key=lambda e: not e.is_dir)
        self.tree.delete(*self.tree.get_children())
        if self.cwd.parent != self.cwd:
            self.tree.insert('', 'end', iid='..', values=('..', '<КАТАЛОГ>', ''))
        for entry in entries:
            self.tree.insert('', 'end', iid=entry.name,
                             values=(entry.name, '<КАТАЛОГ>' if entry.is_dir else f'{entry.size:,}', entry.date))
        self.path_var.set(str(self.cwd))
        self.selection_changed()

    def sort(self, key):
        self.reverse = not self.reverse if self.sort_key == key else False
        self.sort_key = key
        self.sort_var.set(key)
        self.refresh()

    def selected_files(self):
        return [n for n in self.tree.selection() if n in self.entries and not self.entries[n].is_dir]

    def selection_changed(self):
        count = len(self.selected_files())
        state = 'normal' if count and not self.busy else 'disabled'
        self.copy_button.configure(state=state)
        self.edit.entryconfigure(0, state=state)
        self.popup.entryconfigure(0, state=state)
        if not self.busy:
            self.status.set(f'Объектов: {len(self.entries)}   |   Выбрано файлов: {count}')

    def select_all(self):
        if not self.busy:
            self.tree.selection_set([n for n, e in self.entries.items() if not e.is_dir])
        return 'break'

    def select_mask(self):
        if self.busy:
            return
        mask = simpledialog.askstring('Выделение по маске', 'Маска (* — любые символы, ? — один):', initialvalue='*.txt', parent=self)
        if mask:
            names = [n for n, e in self.entries.items() if not e.is_dir and matches(n, mask)]
            self.tree.selection_set(names)
            if not names:
                messagebox.showinfo('Выделение', 'Среди отображаемых файлов совпадений нет.')

    def activate(self, event=None):
        if self.busy:
            return
        name = self.tree.focus()
        if name == '..':
            self.up()
        elif name in self.entries and self.entries[name].is_dir:
            self.navigate(name)
        elif name:
            self.copy_dialog()

    def context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        self.selection_changed()
        self.popup.tk_popup(event.x_root, event.y_root)

    def copy_dialog(self):
        if self.busy:
            return
        names = self.selected_files()
        if not names:
            return
        target = filedialog.askdirectory(title='Копировать в указанный каталог', initialdir=self.cwd, mustexist=True)
        if not target:
            return
        try:
            plan_copy(self.cwd, names, target)
        except (FileError, OSError) as exc:
            messagebox.showerror('Копирование невозможно', str(exc))
            return
        preview = '\n'.join(names[:12])
        if len(names) > 12:
            preview += f'\n… и ещё {len(names) - 12}'
        if not messagebox.askokcancel('Копирование файлов',
                f'Файлов: {len(names)}\n\n{preview}\n\nИз: {self.cwd}\nВ: {target}\n\nСуществующие файлы не заменяются.'):
            return
        self.busy = True
        self.selection_changed()
        self.status.set('Копирование…')
        source = self.cwd

        def worker():
            try:
                result = copy_files(source, names, target,
                                    lambda done, total, name: self.events.put(('progress', f'{done}/{total}: {name}')))
                self.events.put(('done', f'Скопировано файлов: {len(result)}. Каталог: {target}'))
            except (FileError, OSError) as exc:
                self.events.put(('error', str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(80, self.poll_copy)

    def poll_copy(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                self.status.set(text)
                if kind in ('done', 'error'):
                    self.busy = False
                    self.selection_changed()
                    self.status.set(text)
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
            'Во время копирования дождитесь результата, затем можно закрыть окно.\n\n' + HELP)

    def close(self):
        if self.busy:
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
