# Grant Monitor — Жовтанецька ТГ

Бекенд-сервіс моніторингу грантових можливостей для громади. MVP-версія:
каркас проєкту + один наскрізний конектор (EU Funding & Tenders Portal).

## Запуск

```bash
cd grant-monitor
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# вписати ANTHROPIC_API_KEY у .env

uvicorn app.main:app --reload
```

- Дашборд: http://localhost:8000/
- API: http://localhost:8000/api/grants
- Ручний запуск збору: `curl -X POST http://localhost:8000/api/refresh`

Фоновий збір даних також запускається автоматично кожні
`FETCH_INTERVAL_HOURS` годин (за замовчуванням 6, див. `.env`).

## Тести

```bash
pytest tests/
```

`test_eu_funding_portal.py` — smoke-тест, робить реальний запит до
зовнішнього API EU Funding & Tenders Portal (без моків).

## Деплой на VPS громади

Готові конфіги лежать у `deploy/`. Кроки на сервері (Ubuntu/Debian,
припускаємо що nginx + certbot вже налаштовані для основного сайту):

```bash
# 1. Код на сервер
sudo mkdir -p /opt/grant-monitor
sudo chown $USER:$USER /opt/grant-monitor
git clone <URL_РЕПОЗИТОРІЮ> /opt/grant-monitor
cd /opt/grant-monitor

# 2. Залежності
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Конфіг
cp .env.example .env
nano .env   # вписати ANTHROPIC_API_KEY; DATABASE_URL можна лишити sqlite:///./grants.db

# 4. Системний користувач (ізоляція процесу)
sudo useradd -r -s /usr/sbin/nologin grant-monitor
sudo chown -R grant-monitor:grant-monitor /opt/grant-monitor

# 5. systemd-сервіс
sudo cp deploy/grant-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now grant-monitor
sudo systemctl status grant-monitor   # перевірити що запустився

# 6. nginx reverse proxy
sudo cp deploy/nginx-grant-monitor.conf /etc/nginx/sites-available/grant-monitor
# відредагувати server_name на реальний (суб)домен
sudo ln -s /etc/nginx/sites-available/grant-monitor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 7. SSL
sudo certbot --nginx -d grants.ВАШ-ДОМЕН
```

Оновлення після змін у коді:
```bash
cd /opt/grant-monitor && git pull
sudo -u grant-monitor venv/bin/pip install -r requirements.txt
sudo systemctl restart grant-monitor
```

Сервіс слухає лише `127.0.0.1:8001` — назовні доступний тільки через nginx.
Фоновий APScheduler (кожні `FETCH_INTERVAL_HOURS` год) працює безперервно,
бо процес не засинає (на відміну від безкоштовних тарифів Render/Railway).

## Деплой на Railway

1. Створити git-репозиторій (якщо ще не створено) і запушити на GitHub.
2. На [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
   → обрати цей репозиторій. Railway сам визначить Python-застосунок і
   використає `Procfile` (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
3. У Variables додати:
   - `ANTHROPIC_API_KEY` — ключ Anthropic
   - `DATABASE_URL=sqlite:////data/grants.db` (чотири слеші — абсолютний шлях)
   - `FETCH_INTERVAL_HOURS` (опційно, за замовчуванням 6)
4. Додати **Volume**: Settings → Volumes → Add Volume, mount path `/data`.
   Без цього `grants.db` живе на ефемерній файловій системі і зникає при
   кожному редеплої.
5. Deploy. Публічний домен видається автоматично в Settings → Networking
   → Generate Domain.

Те саме на Render: New → Web Service → підключити репозиторій → Build
command `pip install -r requirements.txt`, Start command
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, додати Persistent Disk
(mount path `/data`) і ті самі env-змінні.

## Архітектура

- `app/sources/` — конектори джерел. Кожне нове джерело = новий файл, що
  реалізує `SourceConnector` з `app/sources/base.py`. Наразі: EU Funding &
  Tenders Portal.
- `app/pipeline/extract.py` — LLM-екстракція (Claude) структурованих полів
  з сирого тексту оголошення.
- `app/pipeline/match.py` — визначення релевантності (Львівська область,
  прийнятність ОМС як заявника, потреба в партнерській організації).
- `app/pipeline/score.py` — евристична оцінка ймовірності успіху (заглушка,
  потребує доопрацювання).
- `app/pipeline/run.py` — оркеструє весь пайплайн для всіх джерел.
- `app/api/grants.py` — REST API (`GET /api/grants`, `POST /api/refresh`).
- `app/dashboard/` — мінімальний вбудований дашборд (Jinja2), для перегляду
  результатів локально; пізніше замінюється/вбудовується в admin/ CMS
  головного сайту громади.

## Додавання нового джерела

1. Створити `app/sources/<name>.py`, реалізувати клас, що наслідує
   `SourceConnector` і повертає `list[RawItem]` з методу `fetch()`.
2. Додати екземпляр у `SOURCES` в `app/pipeline/run.py`.
3. Нічого іншого міняти не потрібно — extract/match/score/API/дашборд
   працюють з будь-яким джерелом однаково.

## Відомі обмеження MVP (наступні ітерації)

- Лише одне джерело (EU Funding & Tenders Portal). TG/FB-групи та інші
  портали (DREAM, Дія.Бізнес, USAID/UNDP/GIZ/ЄБРР тощо) — додаються по
  одному конектору за раз.
- Пошук організації-партнера (ГО/БФ) для грантів, недоступних ОМС, ще не
  реалізований — лише прапорець `needs_partner_org`.
- Скоринг ймовірності успіху — спрощена евристика, не статистична модель.
- Дашборд без автентифікації, призначений для локального перегляду.
- **EU Funding & Tenders Portal API не офіційно задокументований.** Пошук
  працює як full-text relevance-search по всьому контенту порталу (включно
  з архівом з 2016+ року), тому серед результатів трапляються вже закриті
  виклики — вони позначаються статусом `closed` (дедлайн обчислюється
  пайплайном, не відкидається на етапі fetch, щоб не губити релевантні
  записи через упередженість пошуку до старих документів). Фільтруйте
  дашборд за статусом `new`, щоб бачити тільки актуальні.
