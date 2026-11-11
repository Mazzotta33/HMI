"""Проверки жизненного цикла копирования и состояния меню.

В среде без графического дисплея тесты пропускаются.
"""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from menu import App


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root_directory = Path(self.temporary_directory.name)
        self.source_directory = self.root_directory / 'Исходные'
        self.destination_directory = self.root_directory / 'Результат'
        self.source_directory.mkdir()
        self.destination_directory.mkdir()
        (self.source_directory / 'пример.txt').write_text('Проверка', encoding='utf-8')
        try:
            self.app = App(str(self.source_directory))
        except tk.TclError as error:
            self.skipTest(f'Графический дисплей недоступен: {error}')
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.update()

    def test_sorting_is_unchanged_during_copy(self):
        previous_order = self.app.file_list.get_children()
        self.app.copy_in_progress = True
        # Имитируем автоматическое изменение переключателя до его обработчика.
        self.app.sort_column_choice.set('size')
        self.app.sort('size')
        self.assertEqual(self.app.sort_column, 'name')
        self.assertFalse(self.app.sort_descending)
        self.assertEqual(self.app.sort_column_choice.get(), 'name')
        self.assertEqual(self.app.file_list.get_children(), previous_order)

    def test_selected_file_is_copied_and_controls_are_restored(self):
        self.assertEqual(str(self.app.copy_button['state']), 'disabled')
        self.app.select_all()
        self.app.update()
        self.assertEqual(str(self.app.copy_button['state']), 'normal')
        with (
            patch('menu.filedialog.askdirectory', return_value=str(self.destination_directory)),
            patch('menu.messagebox.askokcancel', return_value=True),
            patch('menu.messagebox.showinfo') as show_result,
        ):
            self.app.copy_dialog()
            self.assertTrue(self.app.copy_in_progress)
            self.assertEqual(str(self.app.copy_button['state']), 'disabled')
            deadline = time.monotonic() + 10
            while self.app.copy_in_progress and time.monotonic() < deadline:
                self.app.update()
                time.sleep(0.01)
            self.assertFalse(self.app.copy_in_progress, 'Копирование не завершилось за 10 секунд')
            show_result.assert_called_once()
        copied_file = self.destination_directory / 'пример.txt'
        self.assertEqual(copied_file.read_text(encoding='utf-8'), 'Проверка')
        self.assertEqual(str(self.app.copy_button['state']), 'normal')


if __name__ == '__main__':
    unittest.main()
