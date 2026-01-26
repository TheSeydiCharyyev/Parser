# Tests (корневая папка)

Эта папка содержит удобные команды, чтобы прогнать **все тесты** и собрать **HTML-отчёт покрытия**.

## Как прогнать всё
- Все тесты:
  - `bash tests/run_all.sh`

- Покрытие (HTML):
  - `bash tests/coverage_html.sh`

Артефакты покрытия по умолчанию кладутся в `./artifacts/coverage/` (в git не коммитятся).

## Наименование
- Файлы тестов: `test_*.py`
- Наборы тестов: `unittest.TestCase`
- Скрипты запуска: `tests/run_all.sh`, `tests/coverage_html.sh`
