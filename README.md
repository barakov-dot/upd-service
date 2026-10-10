# УПД Сервис — Распознавание бухгалтерских документов

Веб-сервис для автоматического распознавания российских бухгалтерских документов из PDF и генерации XML-файлов для загрузки в **1С:Бухгалтерия**.

Работает через **Groq API** — быстро (~3 сек/документ), бесплатно в базовом тире, без GPU на сервере.

---

## Возможности

- 📄 **Распознавание УПД** (Универсальный передаточный документ, Функция=СЧФДОП)
- 🧾 **Распознавание счёт-фактуры** (Функция=СЧФ)
- 🔍 **Автодетекция типа документа** — не нужно выбирать вручную
- ✅ **Математическая валидация** таблицы товаров (кол-во × цена = сумма, НДС, итого)
- 🎨 **Редактор XML** с подсветкой синтаксиса и нумерацией строк
- 📐 **Просмотр PDF** с зумом и поворотом (↺ ↻)
- 🔄 **Авто-коррекция ориентации** сканов через vision-модель
- 📦 **Плагин-архитектура** — легко добавить новые типы документов

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Бэкенд | Python 3.11+, FastAPI, Uvicorn |
| PDF | PyMuPDF (fitz) |
| AI / OCR | [Groq API](https://console.groq.com) — Llama 4 Scout (vision) + Llama 3.3 70B (text) |
| Фронтенд | Vanilla JS, Apple-style UI |
| XML | Схема ФНС ON_NSCHFDOPPR v5.03, кодировка windows-1251 |

---

## Быстрый старт

### 1. Клонируй репозиторий

```bash
git clone https://github.com/ТВО_ИМЯ/upd-service.git
cd upd-service
```

### 2. Установи зависимости

```bash
pip install fastapi uvicorn pymupdf groq python-multipart
```

### 3. Получи API ключ Groq

Зарегистрируйся на [console.groq.com](https://console.groq.com) → API Keys → Create API Key.

Бесплатный уровень: **30 запросов/минуту** — хватит для рабочего использования.

### 4. Запусти сервис

```bash
GROQ_API_KEY=gsk_твой_ключ uvicorn app:app --host 0.0.0.0 --port 8000
```

Или создай файл `.env` (он в `.gitignore`, в GitHub не попадёт):

```bash
echo "GROQ_API_KEY=gsk_твой_ключ" > .env
```

И запускай через:

```bash
export $(cat .env) && uvicorn app:app --host 0.0.0.0 --port 8000
```

Открой браузер: **http://localhost:8000**

---

## Структура проекта

```
upd-service/
├── app.py              # FastAPI бэкенд — API эндпоинты
├── doc_registry.py     # Реестр плагинов — автозагрузка из doc_types/
├── doc_types/
│   ├── __init__.py
│   ├── upd.py          # Плагин УПД (СЧФДОП) — промпт + XML builder
│   └── schf.py         # Плагин Счёт-фактура (СЧФ) — промпт + XML builder
├── index.html          # Веб-интерфейс (single-page, без фреймворков)
├── .gitignore
└── README.md
```

---

## API эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| `POST` | `/api/recognize` | PDF → JSON с данными + превью |
| `POST` | `/api/preview-xml` | JSON → UTF-8 строка XML для отображения |
| `POST` | `/api/generate-xml` | JSON → windows-1251 файл для 1С |
| `POST` | `/api/encode-xml` | Перекодировать отредактированный XML в windows-1251 |
| `GET`  | `/api/doc-types` | Список поддерживаемых типов документов |
| `GET`  | `/` | Веб-интерфейс |

---

## Как добавить новый тип документа

Создай файл `doc_types/новый_тип.py` с четырьмя обязательными атрибутами:

```python
DOC_TYPE = "ТОРГ12"                    # уникальный идентификатор
LABEL    = "Товарная накладная ТОРГ-12"  # отображаемое название

def DETECT(text: str) -> bool:
    """Определить тип по тексту PDF"""
    return "товарная накладная" in text.lower()

PROMPT = """Это товарная накладная ТОРГ-12.
Прочитай все поля и верни JSON...
"""

def build_xml(data: dict) -> str:
    """Построить XML для 1С"""
    ...
    return xml_string
```

Реестр подхватит плагин автоматически при следующем запуске — без изменений в остальном коде.

---

## Запуск как системный сервис (Ubuntu)

Чтобы сервис работал постоянно и перезапускался после перезагрузки:

```bash
sudo nano /etc/systemd/system/upd-service.service
```

```ini
[Unit]
Description=УПД Сервис распознавания документов
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/upd-service
Environment="GROQ_API_KEY=gsk_твой_ключ"
ExecStart=/usr/local/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable upd-service
sudo systemctl start upd-service
sudo systemctl status upd-service
```

---

## Nginx (опционально)

Если хочешь открыть сервис по доменному имени с HTTPS:

```nginx
server {
    listen 80;
    server_name твой-домен.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50M;
    }
}
```

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo certbot --nginx -d твой-домен.ru
```

---

## Стоимость использования

| Тип документа | Groq модель | Время | Цена |
|---------------|-------------|-------|------|
| Текстовый PDF | Llama 3.3 70B | ~2 сек | ~$0.0002 |
| Скан (vision) | Llama 4 Scout | ~4 сек | ~$0.0003 |

При 1000 документов в месяц — **≈ $0.20–0.30**.

Бесплатный уровень Groq: 30 запросов/мин, 14 400 запросов/день.

---

## Поддерживаемые документы

| Документ | Статус | Функция XML |
|----------|--------|-------------|
| УПД | ✅ Работает | `СЧФДОП` |
| Счёт-фактура | ✅ Работает | `СЧФ` |
| ТОРГ-12 | 🔜 Планируется | — |
| Акт выполненных работ | 🔜 Планируется | — |

---

## Требования к серверу

- Ubuntu 20.04+ (или любой Linux)
- Python 3.11+
- RAM: 512 МБ минимум
- CPU: любой (распознавание на стороне Groq API)
- Интернет: нужен для Groq API (работает из ЕС, РФ и большинства стран)

> **Примечание:** Groq API **не работает** напрямую из Испании и ряда стран ЕС через Google AI Studio free tier. Используйте Groq (console.groq.com) — он работает из ЕС без ограничений.

---

## Лицензия

MIT — используй свободно.
