# VPN Key Manager

Полнофункциональное веб-приложение для управления VPN ключами через **XUI Panel** с использованием библиотеки **py3xui**.

## Возможности

- ✅ Регистрация и аутентификация пользователей
- ✅ Генерация VPN ключей через XUI Panel
- ✅ Поддержка протоколов: VLESS, VMess, Trojan, Shadowsocks
- ✅ Управление ключами (просмотр, отзыв, статистика)
- ✅ PostgreSQL для хранения данных
- ✅ Redis для кеширования
- ✅ Jinja2 шаблоны для веб-страниц
- ✅ JWT токены для API доступа
- ✅ Защита паролей с bcrypt
- ✅ Docker и docker-compose поддержка

## Структура проекта

```
backend/
├── app/
│   ├── main.py              # Точка входа FastAPI
│   ├── config.py            # Настройки приложения
│   ├── database.py          # SQLAlchemy конфигурация
│   ├── redis_client.py      # Redis клиент
│   ├── xui_client.py        # XUI Panel клиент (py3xui)
│   ├── dependencies.py      # FastAPI зависимости
│   ├── models/
│   │   ├── user.py          # Модель пользователя
│   │   └── vpn_key.py       # Модель VPN ключа
│   ├── schemas/
│   │   ├── user.py          # Pydantic схемы пользователя
│   │   └── vpn_key.py       # Pydantic схемы VPN ключей
│   ├── crud/
│   │   ├── user.py          # CRUD для пользователей
│   │   └── vpn_key.py       # CRUD для VPN ключей
│   ├── routers/
│   │   ├── auth.py          # API аутентификации
│   │   ├── web.py           # Веб-страницы
│   │   └── vpn.py           # VPN операции
│   └── templates/
│       ├── base.html        # Базовый шаблон
│       ├── register.html    # Регистрация
│       ├── login.html       # Вход
│       ├── profile.html     # Профиль
│       ├── vpn_panel.html   # VPN панель
│       └── vpn_new.html     # Создание ключа
├── .env                     # Переменные окружения
├── .env.example             # Шаблон окружения
├── pyproject.toml
├── docker-compose.yml
└── README.md
```

## Установка и запуск

### 1. Установка зависимостей

```bash
uv sync
```

### 2. Настройка переменных окружения

Файл `.env` уже создан с вашими учетными данными XUI:

```env
XUI_HOST=https://194.87.25.149:21346
XUI_USERNAME=8PpR8fSJfS
XUI_PASSWORD=***
```

При необходимости отредактируйте другие параметры.

### 3. Запуск баз данных

**Вариант A: Docker Compose (рекомендуется)**

```bash
docker-compose up -d postgres redis
```

**Вариант B: Локальная установка**

Установите PostgreSQL и Redis локально.

### 4. Запуск приложения

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Или через Docker Compose (всё в контейнерах):

```bash
docker-compose up --build
```

Приложение будет доступно: http://localhost:8000

## Использование

### Веб-интерфейс

1. **Регистрация**: http://localhost:8000/register
2. **Вход**: http://localhost:8000/login
3. **VPN панель**: http://localhost:8000/vpn/panel
4. **Создать ключ**: http://localhost:8000/vpn/new

### API Endpoints

#### Аутентификация

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход (получение JWT) |
| GET | `/auth/me` | Данные пользователя |
| PUT | `/auth/me` | Обновление данных |
| POST | `/auth/logout` | Выход |

#### VPN Управление

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/vpn/inbounds` | Список серверов (inbounds) |
| GET | `/vpn/stats` | Статистика сервера |
| POST | `/vpn/generate` | Генерация нового ключа |
| GET | `/vpn/keys` | Мои VPN ключи |
| GET | `/vpn/keys/all` | Все ключи (admin) |
| GET | `/vpn/keys/{id}` | Информация о ключе |
| DELETE | `/vpn/keys/{id}` | Отозвать ключ |
| GET | `/vpn/keys/{id}/traffic` | Статистика трафика |
| POST | `/vpn/keys/{id}/reset-traffic` | Сбросить трафик |

#### Веб-страницы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Главная |
| GET/POST | `/register` | Регистрация |
| GET/POST | `/login` | Вход |
| GET/POST | `/profile` | Профиль |
| GET | `/vpn/panel` | VPN панель |
| GET/POST | `/vpn/new` | Создать ключ |
| GET | `/logout` | Выход |

#### Системные

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка состояния |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |

## Примеры использования API

### 1. Регистрация пользователя

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user1",
    "email": "user1@example.com",
    "password": "securepass123"
  }'
```

### 2. Вход и получение токена

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user1",
    "password": "securepass123"
  }'
```

Ответ:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 3. Получение списка серверов

```bash
curl -X GET http://localhost:8000/vpn/inbounds \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. Генерация VPN ключа

```bash
curl -X POST http://localhost:8000/vpn/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "email": "my-vpn-key",
    "inbound_id": 1,
    "protocol": "vless",
    "limit_ip": 0,
    "total_gb": 10,
    "expire_days": 30,
    "flow": "xtls-rprx-vision"
  }'
```

Ответ:
```json
{
  "id": 1,
  "email": "my-vpn-key",
  "uuid": "abc123-def456-...",
  "inbound_id": 1,
  "protocol": "vless",
  "connection_link": "vless://uuid@host:port?type=...",
  "subscription_url": "https://...",
  "limit_ip": 0,
  "total_gb": 10737418240,
  "expire_time": 1712345678000,
  "is_active": true,
  "created_at": "2026-04-03T..."
}
```

### 5. Получение моих ключей

```bash
curl -X GET http://localhost:8000/vpn/keys \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6. Отзыв ключа

```bash
curl -X DELETE http://localhost:8000/vpn/keys/1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| POSTGRES_USER | Пользователь PostgreSQL | postgres |
| POSTGRES_PASSWORD | Пароль PostgreSQL | postgres |
| POSTGRES_SERVER | Хост PostgreSQL | localhost |
| POSTGRES_PORT | Порт PostgreSQL | 5432 |
| POSTGRES_DB | Имя базы данных | vpn_app |
| REDIS_HOST | Хост Redis | localhost |
| REDIS_PORT | Порт Redis | 6379 |
| REDIS_DB | Номер БД Redis | 0 |
| SECRET_KEY | Секретный ключ JWT | your-secret-key... |
| ALGORITHM | Алгоритм JWT | HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | Время жизни токена (мин) | 30 |
| **XUI_HOST** | URL XUI Panel | https://194.87.25.149:21346 |
| **XUI_USERNAME** | Логин XUI Panel | 8PpR8fSJfS |
| **XUI_PASSWORD** | Пароль XUI Panel | LvmfZ3JPdO |
| APP_NAME | Название приложения | VPN Key Manager |
| DEBUG | Режим отладки | true |

## Поддерживаемые протоколы

- **VLESS** - современный протокол с поддержкой XTLS
- **VMess** - классический протокол V2Ray
- **Trojan** - легковесный протокол
- **Shadowsocks** - быстрый прокси-протокол

## Технологии

- **[FastAPI](https://fastapi.tiangolo.com/)** - веб-фреймворк
- **[SQLAlchemy](https://www.sqlalchemy.org/)** - ORM
- **[PostgreSQL](https://www.postgresql.org/)** - база данных
- **[Redis](https://redis.io/)** - кеширование
- **[Jinja2](https://jinja.palletsprojects.com/)** - шаблонизатор
- **[py3xui](https://github.com/Rzecki/py3xui)** - клиент для XUI Panel
- **[Passlib](https://passlib.readthedocs.io/)** - хеширование паролей
- **[Python-JOSE](https://python-jose.readthedocs.io/)** - JWT токены
- **[Pydantic](https://docs.pydantic.dev/)** - валидация данных

## Безопасность

- Пароли хешируются через bcrypt
- JWT токены с ограниченным временем жизни
- Валидация всех данных через Pydantic
- CORS middleware
- Каждый пользователь видит только свои ключи

## Тестирование

```bash
pytest -v
```

## Возможные проблемы

### XUI Panel не подключается

- Проверьте настройки в `.env` (XUI_HOST, XUI_USERNAME, XUI_PASSWORD)
- Убедитесь, что XUI Panel доступен по указанному URL
- Проверьте, что сертификат SSL действителен (или используйте `use_tls_verify=False`)

### PostgreSQL/Redis не подключаются

```bash
# Проверьте, что контейнеры запущены
docker-compose ps

# Перезапустите сервисы
docker-compose restart postgres redis
```

### Ошибки импорта

```bash
uv sync --reinstall
```

## Лицензия

MIT
