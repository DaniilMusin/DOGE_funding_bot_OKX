# Подробный гайд по запуску DOGE Carry Bot

## Описание проекта

DOGE Carry Bot - это асинхронный торговый бот для выполнения арбитражных операций (carry trades) с парой DOGE-USDT на бирже OKX. Бот работает со спотовыми и фьючерсными позициями, использует WebSocket для мониторинга и сохраняет состояние в SQLite базе данных.

## Системные требования

- **Docker** и **Docker Compose** (рекомендуемый способ)
- **Python 3.11+** (для локального запуска)
- **Poetry** (для управления зависимостями Python)
- Аккаунт на бирже **OKX** с API ключами
- (Опционально) **Telegram бот** для уведомлений

## Подготовка к запуску

### 1. Клонирование и подготовка проекта

```bash
# Перейдите в директорию проекта (если еще не в ней)
cd /workspace

# Убедитесь, что все файлы на месте
ls -la
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта со следующими параметрами:

```bash
# Создать файл .env
cat > .env << 'EOF'
# === OKX API Настройки (ОБЯЗАТЕЛЬНО) ===
OKX_KEY=your_okx_api_key
OKX_SECRET=your_okx_secret_key
OKX_PASS=your_okx_passphrase

# === Настройки торговли ===
# Режим симуляции (1 = включен, 0 = реальная торговля)
OKX_SIM=1
# Начальный капитал в USDT (по умолчанию 1000)
EQUITY_USDT=1000

# === Telegram уведомления (ОПЦИОНАЛЬНО) ===
TG_TOKEN=your_telegram_bot_token
TG_CHAT=your_chat_id

EOF
```

### 3. Получение OKX API ключей

1. Зайдите на [OKX](https://www.okx.com)
2. Перейдите в **Account** → **API**
3. Создайте новый API ключ с правами:
   - **Trade** (торговля)
   - **Read** (чтение)
4. **Важно**: Для начала установите `OKX_SIM=1` для тестирования в режиме симуляции

### 4. Настройка Telegram (опционально)

Если хотите получать уведомления в Telegram:

1. Создайте бота через [@BotFather](https://t.me/botfather)
2. Получите токен бота (TG_TOKEN)
3. Узнайте ваш chat ID:
   - Напишите боту `/start`
   - Откройте `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Найдите ваш chat ID в ответе

## Способы запуска

### Способ 1: Docker Compose (рекомендуемый)

Это самый простой и надежный способ запуска:

```bash
# Собрать образ
docker compose build

# Запустить бота в фоновом режиме
docker compose up -d

# Посмотреть логи
docker compose logs -f bot

# Остановить бота
docker compose down
```

### Способ 2: Локальный запуск с Poetry

```bash
# Установить Poetry (если не установлен)
curl -sSL https://install.python-poetry.org | python3 -

# Установить зависимости
poetry install

# Запустить бота
poetry run doge-runner

# Или активировать виртуальное окружение и запустить
poetry shell
doge-runner
```

### Способ 3: Локальный запуск с pip

```bash
# Создать виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install --upgrade pip
pip install -e .

# Запустить бота
doge-runner
```

## Мониторинг и контроль

### Prometheus метрики

Бот предоставляет метрики для мониторинга на порту 9090:

```bash
# Проверить метрики
curl http://localhost:9090/metrics
```

### Логи

```bash
# Docker логи
docker compose logs -f bot

# Логи с фильтрацией
docker compose logs bot | grep ERROR
docker compose logs bot | grep INIT
```

### База данных

База данных SQLite хранится в Docker volume `dbdata` и монтируется в `/app/src/db`:

```bash
# Посмотреть содержимое volume
docker compose exec bot ls -la /app/src/db

# Создать бекап базы данных
docker compose exec bot cp /app/src/db/state.db /app/backup_$(date +%Y%m%d_%H%M%S).db
```

## Логика работы бота

1. **Инициализация**: Бот получает начальные позиции или создает новые
2. **Carry Trade**: 
   - Покупает DOGE на споте (с займом USDT)
   - Открывает короткую позицию на фьючерсах DOGE-USDT-SWAP
3. **Мониторинг**:
   - Отслеживает фандинг на фьючерсах
   - Контролирует риски ликвидации
   - Мониторит P&L
   - Выполняет ребалансировку позиций

## Безопасность и риски

### ⚠️ Важные предупреждения

1. **Начните с симуляции**: Всегда тестируйте с `OKX_SIM=1`
2. **Небольшой капитал**: Начните с малых сумм (например, `EQUITY_USDT=100`)
3. **Понимание рисков**: Carry trade содержит риски ликвидации и изменения фандинга
4. **Мониторинг**: Следите за позициями и логами бота

### Настройки безопасности

```bash
# Режим симуляции (безопасно для тестирования)
OKX_SIM=1

# Небольшая сумма для начала
EQUITY_USDT=100

# Включить все уведомления Telegram
TG_TOKEN=your_token
TG_CHAT=your_chat_id
```

## Устранение неполадок

### Проблема: Ошибка "Missing OKX credentials"

```bash
# Проверьте файл .env
cat .env | grep OKX

# Убедитесь, что все три переменные заданы
echo $OKX_KEY
echo $OKX_SECRET  
echo $OKX_PASS
```

### Проблема: Ошибка подключения к OKX

```bash
# Проверьте интернет соединение
curl -I https://www.okx.com

# Проверьте правильность API ключей в панели OKX
```

### Проблема: Бот не запускается в Docker

```bash
# Пересобрать образ
docker compose build --no-cache

# Проверить логи при запуске
docker compose up

# Проверить переменные окружения
docker compose exec bot env | grep OKX
```

### Проблема: Нет уведомлений в Telegram

```bash
# Проверить токен и chat ID
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
curl "https://api.telegram.org/bot<YOUR_TOKEN>/sendMessage?chat_id=<YOUR_CHAT_ID>&text=test"
```

## Полезные команды

```bash
# Перезапуск бота
docker compose restart bot

# Обновление кода (после изменений)
docker compose build
docker compose up -d

# Очистка Docker ресурсов
docker compose down -v  # ВНИМАНИЕ: удалит базу данных!

# Бекап базы данных
docker compose exec bot cp /app/src/db/state.db /tmp/backup.db
docker cp $(docker compose ps -q bot):/tmp/backup.db ./backup_$(date +%Y%m%d).db

# Мониторинг ресурсов
docker stats $(docker compose ps -q bot)
```

## Структура проекта

```
.
├── Dockerfile              # Docker образ
├── docker-compose.yml      # Docker Compose конфигурация
├── pyproject.toml          # Python зависимости (Poetry)
├── .env                    # Переменные окружения (создать самостоятельно)
├── src/
│   ├── runner.py           # Главная точка входа
│   ├── core/
│   │   └── gateway.py      # OKX API клиент
│   ├── executors/          # Исполнители торговых операций
│   ├── db/                 # База данных и состояние
│   ├── alerts/
│   │   └── telegram.py     # Telegram уведомления
│   ├── monitors.py         # Мониторинг позиций и рисков
│   ├── rebalance.py        # Ребалансировка портфеля
│   └── borrow.py           # Управление займами
└── README.md               # Краткое описание
```

## Поддержка

При возникновении проблем:

1. Проверьте логи: `docker compose logs -f bot`
2. Убедитесь в правильности настройки .env файла
3. Начните с режима симуляции (`OKX_SIM=1`)
4. Используйте небольшие суммы для тестирования

---

**Удачной торговли! 🚀**