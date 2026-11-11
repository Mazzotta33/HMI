import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fileops import FileError, copy_files, list_directory, matches_mask, select_file_names
from shell import Shell, tokenize


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source_directory, self.destination_directory = self.root / 'Исходные', self.root / 'Результат'
        self.source_directory.mkdir()
        self.destination_directory.mkdir()
        (self.source_directory / 'one.txt').write_bytes(b'one\x00\xff')
        (self.source_directory / 'two.TXT').write_bytes(b'two')
        (self.source_directory / 'мой файл.csv').write_text('a,b', encoding='utf-8')
        (self.source_directory / 'folder.txt').mkdir()

    def test_single_copy_preserves_source_and_binary_content(self):
        copy_files(self.source_directory, ['one.txt'], self.destination_directory)
        self.assertEqual((self.destination_directory / 'one.txt').read_bytes(), b'one\x00\xff')
        self.assertEqual((self.source_directory / 'one.txt').read_bytes(), b'one\x00\xff')

    def test_group_mask_excludes_directories(self):
        names = select_file_names(self.source_directory, '*.txt')
        self.assertEqual(set(names), {'one.txt', 'two.TXT'})
        self.assertEqual(len(copy_files(self.source_directory, names, self.destination_directory)), 2)

    def test_conflict_cancels_whole_plan(self):
        (self.destination_directory / 'two.TXT').write_bytes(b'original')
        with self.assertRaises(FileError):
            copy_files(self.source_directory, ['one.txt', 'two.TXT'], self.destination_directory)
        self.assertFalse((self.destination_directory / 'one.txt').exists())
        self.assertEqual((self.destination_directory / 'two.TXT').read_bytes(), b'original')

    def test_case_insensitive_conflict(self):
        (self.destination_directory / 'ONE.TXT').write_bytes(b'original')
        with self.assertRaises(FileError):
            copy_files(self.source_directory, ['one.txt'], self.destination_directory)

    def test_same_directory_rejected(self):
        with self.assertRaises(FileError):
            copy_files(self.source_directory, ['one.txt'], self.source_directory)

    def test_missing_target_rejected(self):
        with self.assertRaises(FileError):
            copy_files(self.source_directory, ['one.txt'], self.root / 'missing')

    def test_directory_as_target_file_rejected(self):
        with self.assertRaises(FileError):
            copy_files(self.source_directory, ['one.txt'], self.source_directory / 'two.TXT')

    def test_no_matches(self):
        with self.assertRaises(FileError):
            select_file_names(self.source_directory, '*.pdf')

    def test_path_in_mask_rejected(self):
        with self.assertRaises(FileError):
            select_file_names(self.source_directory, '../*')

    def test_directories_and_traversal_rejected(self):
        for name in ('folder.txt', '../one.txt'):
            with self.subTest(name=name), self.assertRaises(FileError):
                copy_files(self.source_directory, [name], self.destination_directory)

    def test_relative_target_and_progress(self):
        events = []
        copy_files(self.source_directory, ['мой файл.csv'], '../Результат', lambda *a: events.append(a))
        self.assertEqual(events, [(1, 1, 'мой файл.csv')])
        self.assertEqual((self.destination_directory / 'мой файл.csv').read_text(encoding='utf-8'), 'a,b')

    def test_mid_copy_failure_removes_incomplete_output(self):
        def fail(reader, writer, **kwargs):
            writer.write(b'partial')
            raise OSError('disk full')
        with patch('fileops.shutil.copyfileobj', side_effect=fail):
            with self.assertRaisesRegex(FileError, 'Завершено файлов: 0'):
                copy_files(self.source_directory, ['one.txt'], self.destination_directory)
        self.assertFalse((self.destination_directory / 'one.txt').exists())

    def test_race_does_not_overwrite_new_file(self):
        from fileops import build_copy_plan
        original = build_copy_plan(self.source_directory, ['one.txt'], self.destination_directory)
        (self.destination_directory / 'one.txt').write_bytes(b'new owner')
        with patch('fileops.build_copy_plan', return_value=original):
            with self.assertRaises(FileError):
                copy_files(self.source_directory, ['one.txt'], self.destination_directory)
        self.assertEqual((self.destination_directory / 'one.txt').read_bytes(), b'new owner')

    def test_completed_files_survive_later_failure(self):
        import shutil
        real = shutil.copyfileobj
        calls = []
        def fail_second(reader, writer, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('disk full')
            real(reader, writer, **kwargs)
        with patch('fileops.shutil.copyfileobj', side_effect=fail_second):
            with self.assertRaisesRegex(FileError, 'Завершено файлов: 1'):
                copy_files(self.source_directory, ['one.txt', 'two.TXT'], self.destination_directory)
        self.assertEqual((self.destination_directory / 'one.txt').read_bytes(), b'one\x00\xff')
        self.assertFalse((self.destination_directory / 'two.TXT').exists())

    def test_listing_directories_first(self):
        self.assertTrue(list_directory(self.source_directory)[0].is_dir)

    def test_shell_end_to_end(self):
        shell = Shell(str(self.source_directory))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            shell.execute('copy "мой файл.csv" "../Результат"')
            shell.execute('dir *.csv')
            shell.execute('cd ..')
        self.assertIn('Скопировано файлов: 1', output.getvalue())
        self.assertEqual(shell.current_directory, self.root.resolve())
        self.assertTrue((self.destination_directory / 'мой файл.csv').is_file())
        self.assertFalse(shell.execute('exit'))

    def test_shell_invalid_commands(self):
        shell = Shell(str(self.source_directory))
        for command in ('unknown', 'copy *.txt', 'exit extra', 'cd "open', 'help unknown'):
            with self.subTest(command=command), self.assertRaises(FileError):
                shell.execute(command)


class LanguageTests(unittest.TestCase):
    def test_windows_paths_and_spaces(self):
        self.assertEqual(tokenize(r'copy "мой файл.txt" "D:\Мои файлы\"'),
                         ['copy', 'мой файл.txt', 'D:\\Мои файлы\\'])

    def test_only_star_and_question_are_special(self):
        self.assertTrue(matches_mask('Report_1.TXT', 'report_?.txt'))
        self.assertTrue(matches_mask('abc', '*'))
        self.assertFalse(matches_mask('ab', '?'))
        self.assertTrue(matches_mask('[a].txt', '[a].txt'))
        self.assertFalse(matches_mask('a.txt', '[a].txt'))


if __name__ == '__main__':
    unittest.main()
