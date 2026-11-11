"""Создаёт демонстрационные файлы, не заменяя существующие."""
from pathlib import Path


def make_demo(root=Path('demo')):
    root = Path(root)
    for folder in ('Исходные', 'Результат', 'Исходные/Фото'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for name, content in {
        'readme.txt': 'Демонстрация копирования файлов.\n',
        'список покупок.txt': 'Хлеб\nМолоко\n',
        'отчёт_1.docx.txt': 'Тестовый текстовый файл, а не документ Word.\n',
        'data_2024.csv': 'year,value\n2024,100\n',
        'data_2025.csv': 'year,value\n2025,120\n',
    }.items():
        try:
            with (root / 'Исходные' / name).open('x', encoding='utf-8') as stream:
                stream.write(content)
        except FileExistsError:
            pass
    return root.resolve()


if __name__ == '__main__':
    print(f'Демонстрационный каталог: {make_demo()}')
