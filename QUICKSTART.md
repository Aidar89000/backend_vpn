# Быстрый старт

## Запуск приложения

### 1. Запуск PostgreSQL и Redis

**Вариант A: Docker Compose (рекомендуется)**

```bash
# Запуск всех сервисов (PostgreSQL, Redis, App)
docker-compose up --build

# Или запустить только базы данных
docker-compose up -d postgres redis
```

**Вариант B: Локальная установка**

Если Docker недоступен, установите PostgreSQL и Redis локально:

1. **PostgreSQL**: https://www.postgresql.org/download/
2. **Redis**: https://redis.io/download/

Затем обновите `.env` файл с правильными данными подключения.

### 2. Установка зависимостей

```bash
uv sync
```

### 3. Настройка окружения

```bash
# Файл .env уже создан, при необходимости отредактируйте
cp .env.example .env  # если нужно создать заново
```

### 4. Запуск приложения

```bash
# С автоматической перезагрузкой при изменениях
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Или через Python
python -m uvicorn app.main:app --reload
```

### 5. Откройте браузер

- Главная страница: http://localhost:8000
- Регистрация: http://localhost:8000/register
- Вход: http://localhost:8000/login
- API документация: http://localhost:8000/docs

## Тестирование

```bash
# Запуск тестов
pytest -v

# Запуск с выводом информации
pytest -v -s
```

## Проверка здоровья сервисов

```bash
curl http://localhost:8000/health
```

## Возможные проблемы

### PostgreSQL не подключается

- Убедитесь, что PostgreSQL запущен
- Проверьте настройки в `.env` (POSTGRES_SERVER, POSTGRES_PORT, и т.д.)
- По умолчанию: localhost:5432

### Redis не подключается

- Убедитесь, что Redis запущен
- Приложение продолжит работу даже без Redis, но кеширование не будет работать
- По умолчанию: localhost:6379

### Ошибки импорта

```bash
# Переустановите зависимости
uv sync --reinstall
```
