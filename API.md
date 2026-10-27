# API EduFlow

Справочник по API проекта EduFlow. Составлен строго по коду (`main.py`, `myproject/api/*`, `myproject/database/schemas.py`, `myproject/core/dependencies.py`). Все URL, методы, поля и статусы соответствуют реальной реализации.

---

## 1. Общая информация

| Параметр | Значение |
|---|---|
| Base URL | `http://127.0.0.1:8000` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI (JSON) | `http://127.0.0.1:8000/openapi.json` |
| Админ-панель (SQLAdmin) | `http://127.0.0.1:8000/admin` |
| Название приложения | `EduFlow for Motion` |
| Формат данных | `application/json` |

**Форматы значений:**
- дата — `"2026-09-15"`, дата-время — `"2026-10-21T12:30:00"`, время — `"18:00:00"`;
- денежные суммы — `Decimal`; принимаются как число (`15000.00`) или строка (`"15000.00"`).

### JWT-токен: получение и передача

- Токен выдаётся через `POST /auth/login` — пара **access_token** и **refresh_token**.
- **access_token** живёт 30 минут, **refresh_token** — 7 дней.
- Передаётся в заголовке каждого защищённого запроса:

  ```
  Authorization: Bearer <access_token>
  ```

- Обновление пары токенов — `POST /auth/refresh` (старый refresh отзывается).
- Если токен отсутствует, неверен или просрочен — **401**.

### Роли и доступ

| Роль | Кто это | Что доступно |
|---|---|---|
| `admin` | администратор | полный CRUD: users, students, personal-info, groups, contracts; список платежей и подтверждение/отклонение |
| `student` | студент с профилем | свои данные: `/students/me`, `/personal-info/me`, `/groups/my`, `/contracts/my`, свои платежи и баланс, создание платежа |
| неавторизованный | без токена | только `POST /auth/login`, `POST /auth/refresh`, `GET /health` |

Правила доступа описываются зависимостями:
- `get_current_user` — любой аутентифицированный пользователь (иначе **401**);
- `get_current_admin` — только `admin` (иначе **403** `Требуются права администратора`);
- `get_current_student` — роль `student` с записью в таблице `students` (иначе **403** `Профиль студента не найден`).

### Enum-значения

| Enum | Значения |
|---|---|
| `UserRole` | `admin`, `student` |
| `PaymentStatus` | `pending`, `confirmed`, `rejected` |
| `ContractStatus` | `active`, `completed`, `cancelled` |

---

## 2. Список всех API endpoints

### Auth

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/auth/login` | Все | Вход в систему, выдача пары токенов |
| POST | `/auth/refresh` | Все | Обновление пары токенов по refresh-токену |
| POST | `/auth/logout` | Авторизованный | Отзыв refresh-токена |

### Users

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/users/` | Admin | Создать пользователя |
| GET | `/users/` | Admin | Список всех пользователей |
| GET | `/users/{user_id}` | Admin | Пользователь по ID |
| PUT | `/users/{user_id}` | Admin | Изменить пользователя |
| DELETE | `/users/{user_id}` | Admin | Удалить пользователя |

### Students

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/students/` | Admin | Создать студента (пользователь + студент + личные данные) |
| GET | `/students/` | Admin | Список всех студентов |
| GET | `/students/me` | Student | Свой профиль студента |
| GET | `/students/{student_id}` | Admin | Студент по ID |
| DELETE | `/students/{student_id}` | Admin | Удалить студента |

### Personal Info

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/personal-info/{student_id}` | Admin | Создать личные данные студента |
| GET | `/personal-info/me` | Student | Свои личные данные |
| GET | `/personal-info/{student_id}` | Admin | Личные данные студента |
| PUT | `/personal-info/me` | Student | Изменить свои личные данные |
| PUT | `/personal-info/{student_id}` | Admin | Изменить личные данные студента |
| DELETE | `/personal-info/{student_id}` | Admin | Удалить личные данные студента |

### Groups

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/groups/` | Admin | Создать группу |
| GET | `/groups/` | Admin | Список групп |
| GET | `/groups/my` | Student | Своя группа |
| GET | `/groups/{group_id}` | Admin | Группа по ID |
| PUT | `/groups/{group_id}` | Admin | Изменить группу |
| DELETE | `/groups/{group_id}` | Admin | Удалить группу |

### Contracts

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/contracts/` | Admin | Создать контракт |
| GET | `/contracts/` | Admin | Список контрактов |
| GET | `/contracts/my` | Student | Свои контракты |
| GET | `/contracts/{contract_id}` | Авторизованный | Контракт по ID (студент — только свой) |
| PUT | `/contracts/{contract_id}` | Admin | Изменить контракт |
| DELETE | `/contracts/{contract_id}` | Admin | Удалить контракт |

### Payments

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| POST | `/payments/` | Student | Создать платёж по своему контракту |
| GET | `/payments/` | Admin | Список всех платежей |
| GET | `/payments/my` | Student | Свои платежи |
| GET | `/payments/my/balance` | Student | Баланс по своим контрактам |
| GET | `/payments/{payment_id}` | Авторизованный | Платёж по ID (студент — только свой) |
| PATCH | `/payments/{payment_id}/status` | Admin | Подтвердить / отклонить платёж |
| DELETE | `/payments/{payment_id}` | Admin | Удалить платёж |

### Health

| Метод | Endpoint | Доступ | Назначение |
|---|---|---|---|
| GET | `/health` | Все | Проверка приложения и БД |

---

## 3. Подробные примеры

### Health

#### GET /health
Полный URL: `http://127.0.0.1:8000/health` — авторизация не нужна.

```json
{ "status": "ok", "database": "up" }
```
Ошибка: **503** — `{ "status": "unavailable", "database": "down" }`.

---

### Auth

#### POST /auth/login
Полный URL: `http://127.0.0.1:8000/auth/login` — доступ: все.

Request Body:
```json
{ "username": "student_ivan", "password": "Student1234" }
```
Response 200:
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```
Ошибки: **401** `Неверный логин или пароль`, **403** `Аккаунт деактивирован`, **422** (нет `username`/`password`).

#### POST /auth/refresh
Полный URL: `http://127.0.0.1:8000/auth/refresh` — доступ: все.

Request Body:
```json
{ "refresh_token": "eyJhbGciOi..." }
```
Response 200 — новая пара токенов (`access_token`, `refresh_token`, `token_type`).

Ошибки: **401** `Недействительный refresh-токен` / `Недействительный или просроченный refresh-токен` / `Refresh-токен недействителен или истёк` / `Пользователь не найден или аккаунт деактивирован`.

#### POST /auth/logout
Полный URL: `http://127.0.0.1:8000/auth/logout` — доступ: авторизованный.

Request Body:
```json
{ "refresh_token": "eyJhbGciOi..." }
```
Response 200:
```json
{ "message": "Вы успешно вышли из системы" }
```
Ошибки: **401**, **404** `Активный refresh-токен не найден`, **422**.

---

### Users (доступ: Admin)

#### POST /users/
URL: `http://127.0.0.1:8000/users/`

Request Body (`role` необязателен, по умолчанию `student`):
```json
{ "username": "student_petrova", "password": "Student12345", "role": "student" }
```
Response 201:
```json
{ "id": 12, "username": "student_petrova", "role": "student", "is_active": true }
```
Ошибки: **400** `Такой пользователь уже существует`, **401**, **403**, **422** (username 3–50, password 8–128).

#### GET /users/
Response 200:
```json
[
  { "id": 1, "username": "admin", "role": "admin", "is_active": true },
  { "id": 3, "username": "student_ivan", "role": "student", "is_active": true }
]
```

#### GET /users/{user_id}
URL: `http://127.0.0.1:8000/users/3`

Response 200:
```json
{ "id": 3, "username": "student_ivan", "role": "student", "is_active": true }
```
Ошибки: **401**, **403**, **404** `Пользователь не найден`, **422**.

#### PUT /users/{user_id}
URL: `http://127.0.0.1:8000/users/3` — обновляются только переданные поля.

Request Body:
```json
{ "is_active": false }
```
Response 200:
```json
{ "id": 3, "username": "student_ivan", "role": "student", "is_active": false }
```
Ошибки: **400** `Такой логин уже занят` / `Не удалось обновить пользователя`, **401**, **403**, **404**, **422**.

#### DELETE /users/{user_id}
URL: `http://127.0.0.1:8000/users/12`

Response 200:
```json
{ "message": "Пользователь успешно удалён" }
```
Ошибки: **400** `Нельзя удалить свой аккаунт`, **401**, **403**, **404**, **409** `Нельзя удалить пользователя: с ним связаны другие данные`, **422**.

---

### Students

#### POST /students/ (Admin)
URL: `http://127.0.0.1:8000/students/`

Request Body:
```json
{
  "username": "student_azamat",
  "password": "Student12345",
  "student_number": "ST-2026-03",
  "group_id": 4,
  "personal_info": {
    "first_name": "Азамат",
    "last_name": "Абдиев",
    "phone": "+996 555 100 001",
    "birth_date": "2000-01-01",
    "address": "г. Бишкек, ул. Демо, 1"
  }
}
```
Response 201:
```json
{
  "id": 4,
  "user_id": 5,
  "group_id": 4,
  "student_number": "ST-2026-03",
  "personal_info": {
    "id": 3,
    "student_id": 4,
    "first_name": "Азамат",
    "last_name": "Абдиев",
    "phone": "+996 555 100 001",
    "birth_date": "2000-01-01",
    "address": "г. Бишкек, ул. Демо, 1"
  }
}
```
Ошибки: **401**, **403**, **404** `Группа не найдена`, **409** `Такой username уже существует` / `Такой номер студента уже существует`, **422**.

#### GET /students/ (Admin)
Response 200 — массив студентов (структура как выше).

#### GET /students/me (Student)
URL: `http://127.0.0.1:8000/students/me`

Response 200:
```json
{
  "id": 1,
  "user_id": 3,
  "group_id": 1,
  "student_number": "ST-2026-01",
  "personal_info": {
    "id": 1,
    "student_id": 1,
    "first_name": "Иван",
    "last_name": "Иванов",
    "phone": "+79001112244",
    "birth_date": "2001-05-20",
    "address": "ул. Мира, 5"
  }
}
```
Ошибки: **401**, **403** `Профиль студента не найден`.

#### GET /students/{student_id} (Admin)
URL: `http://127.0.0.1:8000/students/1` — Response 200: как `GET /students/me`. Ошибки: **401**, **403**, **404** `Студент не найден`.

#### DELETE /students/{student_id} (Admin)
URL: `http://127.0.0.1:8000/students/4` — Response **204** (пустое тело).

Ошибки: **401**, **403**, **404**, **409** `Студента нельзя удалить: есть связанные данные`.

---

### Personal Info

#### POST /personal-info/{student_id} (Admin)
URL: `http://127.0.0.1:8000/personal-info/4`

Request Body:
```json
{
  "first_name": "Анна",
  "last_name": "Смирнова",
  "phone": "+996 555 200 001",
  "birth_date": "2002-03-03",
  "address": "г. Бишкек, ул. Демо, 2"
}
```
Response 201:
```json
{
  "id": 9, "student_id": 4, "first_name": "Анна", "last_name": "Смирнова",
  "phone": "+996 555 200 001", "birth_date": "2002-03-03", "address": "г. Бишкек, ул. Демо, 2"
}
```
Ошибки: **401**, **403**, **404** `Студент не найден`, **409** `Личные данные уже существуют`, **422**.

#### GET /personal-info/me (Student)
Response 200 — объект личных данных (как выше). Ошибки: **401**, **403**, **404** `Личные данные не найдены`.

#### GET /personal-info/{student_id} (Admin)
URL: `http://127.0.0.1:8000/personal-info/1` — Response 200. Ошибки: **401**, **403**, **404** `Личные данные не найдены`.

#### PUT /personal-info/me (Student)
Request Body: как у `POST /personal-info/{student_id}` (полная замена). Response 200 — обновлённый объект. Ошибки: **401**, **403**, **404**, **422**.

#### PUT /personal-info/{student_id} (Admin)
Request Body: как у `POST`. Response 200 — обновлённый объект. Ошибки: **401**, **403**, **404**, **422**.

#### DELETE /personal-info/{student_id} (Admin)
URL: `http://127.0.0.1:8000/personal-info/4` — Response **204**. Ошибки: **401**, **403**, **404**.

---

### Groups

#### POST /groups/ (Admin)
URL: `http://127.0.0.1:8000/groups/`

Request Body:
```json
{ "name": "Группа B-2", "course_name": "Frontend (React)",
  "start_date": "2026-09-15", "end_date": "2027-03-15" }
```
Response 201:
```json
{ "id": 4, "name": "Группа B-2", "course_name": "Frontend (React)",
  "start_date": "2026-09-15", "end_date": "2027-03-15" }
```
Ошибки: **400** `Дата окончания не может быть раньше даты начала`, **401**, **403**, **422**.

#### GET /groups/ (Admin)
Response 200 — массив групп.

#### GET /groups/my (Student)
Response 200:
```json
{ "id": 1, "name": "Группа A-1 (поток 2)", "course_name": "Python Basic",
  "start_date": "2026-09-01", "end_date": "2027-03-01" }
```
Ошибки: **401**, **403**, **404** `Студент не привязан к группе` / `Группа не найдена`.

#### GET /groups/{group_id} (Admin)
URL: `http://127.0.0.1:8000/groups/1` — Response 200. Ошибки: **401**, **403**, **404** `Группа не найдена`.

#### PUT /groups/{group_id} (Admin)
Request Body: как у `POST /groups/` (полная замена). Response 200 — обновлённая группа.

Ошибки: **400** (даты), **401**, **403**, **404**, **422**.

#### DELETE /groups/{group_id} (Admin)
URL: `http://127.0.0.1:8000/groups/4` — Response **204**.

Ошибки: **401**, **403**, **404**, **409** `Нельзя удалить группу, в которой есть студенты`.

---

### Contracts

#### POST /contracts/ (Admin)
URL: `http://127.0.0.1:8000/contracts/`

Request Body (`total_amount`, `monthly_payment` > 0; `duration_months` > 0):
```json
{ "student_id": 4, "total_amount": "90000.00", "monthly_payment": "15000.00",
  "duration_months": 6, "start_date": "2026-09-15" }
```
Response 201 (`status` создаётся как `active`):
```json
{
  "id": 4, "student_id": 4, "total_amount": "90000.00", "monthly_payment": "15000.00",
  "duration_months": 6, "start_date": "2026-09-15", "status": "active",
  "created_at": "2026-10-21T12:30:00"
}
```
Ошибки: **400** `Суммы и срок должны быть положительными`, **401**, **403**, **404** `Студент не найден`, **422**.

#### GET /contracts/ (Admin)
Response 200 — массив контрактов.

#### GET /contracts/my (Student)
Response 200 — массив контрактов студента:
```json
[
  { "id": 1, "student_id": 1, "total_amount": "100000.00", "monthly_payment": "25000.00",
    "duration_months": 4, "start_date": "2026-09-01", "status": "active",
    "created_at": "2026-10-21T12:30:00" }
]
```

#### GET /contracts/{contract_id} (Авторизованный)
URL: `http://127.0.0.1:8000/contracts/1` — студент может получить только свой контракт.

Response 200 — объект контракта. Ошибки: **401**, **403** `Нет доступа к этому контракту`, **404** `Контракт не найден`, **422**.

#### PUT /contracts/{contract_id} (Admin)
Request Body: как у `POST /contracts/`. Response 200 — обновлённый контракт.

Ошибки: **400**, **401**, **403**, **404**, **422**.

#### DELETE /contracts/{contract_id} (Admin)
URL: `http://127.0.0.1:8000/contracts/4` — Response **204**. Ошибки: **401**, **403**, **404**.

---

### Payments

#### POST /payments/ (Student)
URL: `http://127.0.0.1:8000/payments/` — создаёт платёж по своему контракту, статус `pending`.

Request Body:
```json
{ "contract_id": 1, "amount": "25000.00", "payment_method": "card", "payment_month": "2026-12" }
```
Response 201:
```json
{
  "id": 4, "contract_id": 1, "amount": "25000.00", "status": "pending",
  "payment_method": "card", "created_at": "2026-10-21T12:35:00",
  "paid_at": null, "confirmed_by_admin_id": null, "payment_month": "2026-12"
}
```
Ошибки: **400** `Сумма платежа должна быть положительной`, **401**, **403** `Профиль студента не найден`, **404** `Контракт не найден`, **422**.

#### GET /payments/ (Admin)
Response 200 — массив всех платежей.

#### GET /payments/my (Student)
Response 200 — массив платежей студента.

#### GET /payments/my/balance (Student)
URL: `http://127.0.0.1:8000/payments/my/balance`

Учитываются только платежи со статусом `confirmed`. `paid_months = paid_amount // monthly_payment`.
У этого endpoint нет `response_model`, поэтому суммы приходят числами, а не строками.

Response 200:
```json
[
  { "contract_id": 1, "total_amount": 100000.0, "paid_amount": 50000.0,
    "remaining_amount": 50000.0, "paid_months": 2, "duration_months": 4 }
]
```
Ошибки: **401**, **403** `Профиль студента не найден`.

#### GET /payments/{payment_id} (Авторизованный)
URL: `http://127.0.0.1:8000/payments/4` — студент видит только свой платёж.

Response 200 — объект платежа. Ошибки: **401**, **403** `Нет доступа к этому платежу`, **404** `Платёж не найден`, **422**.

#### PATCH /payments/{payment_id}/status (Admin)
URL: `http://127.0.0.1:8000/payments/4/status` — разрешены только `confirmed` и `rejected`.

Request Body:
```json
{ "status": "confirmed" }
```
Response 200:
```json
{
  "id": 4, "contract_id": 1, "amount": "25000.00", "status": "confirmed",
  "payment_method": "card", "created_at": "2026-10-21T12:35:00",
  "paid_at": "2026-10-21T12:40:00", "confirmed_by_admin_id": 1, "payment_month": "2026-12"
}
```
Ошибки: **400** `Подтверждённый платёж нельзя изменить` / `Можно только подтвердить или отклонить платёж` / `Сумма платежа превышает остаток контракта`, **401**, **403**, **404**, **422**.

#### DELETE /payments/{payment_id} (Admin)
URL: `http://127.0.0.1:8000/payments/4` — Response **204**.

Ошибки: **400** `Подтверждённый платёж нельзя удалить`, **401**, **403**, **404**, **422**.

---

## 4. Основные сценарии использования

### Сценарий 1. Авторизация и получение токена

```http
POST /auth/login
Content-Type: application/json

{ "username": "admin", "password": "Admin12345" }
```
```json
{ "access_token": "eyJhbGciOi...", "refresh_token": "eyJhbGciOi...", "token_type": "bearer" }
```
Сохраните `access_token` и `refresh_token` на клиенте.

### Сценарий 2. Передача токена в защищённом запросе

```http
GET /users/
Authorization: Bearer <access_token>
```
Если access-токен истёк (ответ **401**), обновите его:
```http
POST /auth/refresh
Content-Type: application/json

{ "refresh_token": "<refresh_token>" }
```
и повторите исходный запрос с новым `access_token`.

### Сценарий 3. Получение профиля студента

```http
GET /students/me
Authorization: Bearer <student_access_token>
```
```json
{
  "id": 1, "user_id": 3, "group_id": 1, "student_number": "ST-2026-01",
  "personal_info": {
    "id": 1, "student_id": 1, "first_name": "Иван", "last_name": "Иванов",
    "phone": "+79001112244", "birth_date": "2001-05-20", "address": "ул. Мира, 5"
  }
}
```

### Сценарий 4. Получение контрактов и баланса

Контракты:
```http
GET /contracts/my
Authorization: Bearer <student_access_token>
```
```json
[
  { "id": 1, "student_id": 1, "total_amount": "100000.00", "monthly_payment": "25000.00",
    "duration_months": 4, "start_date": "2026-09-01", "status": "active",
    "created_at": "2026-10-21T12:30:00" }
]
```
Баланс:
```http
GET /payments/my/balance
Authorization: Bearer <student_access_token>
```
```json
[
  { "contract_id": 1, "total_amount": 100000.0, "paid_amount": 50000.0,
    "remaining_amount": 50000.0, "paid_months": 2, "duration_months": 4 }
]
```

### Сценарий 5. Создание платежа студентом

```http
POST /payments/
Authorization: Bearer <student_access_token>
Content-Type: application/json

{ "contract_id": 1, "amount": "25000.00", "payment_method": "card", "payment_month": "2026-12" }
```
```json
{
  "id": 4, "contract_id": 1, "amount": "25000.00", "status": "pending",
  "payment_method": "card", "created_at": "2026-10-21T12:35:00",
  "paid_at": null, "confirmed_by_admin_id": null, "payment_month": "2026-12"
}
```
Платёж создаётся со статусом `pending` и ожидает решения администратора.

### Сценарий 6. Подтверждение или отклонение платежа администратором

Подтверждение:
```http
PATCH /payments/4/status
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{ "status": "confirmed" }
```
```json
{
  "id": 4, "contract_id": 1, "amount": "25000.00", "status": "confirmed",
  "payment_method": "card", "created_at": "2026-10-21T12:35:00",
  "paid_at": "2026-10-21T12:40:00", "confirmed_by_admin_id": 1, "payment_month": "2026-12"
}
```
Отклонение — тем же запросом с `{ "status": "rejected" }` (при этом `paid_at` и `confirmed_by_admin_id` остаются/сбрасываются по логике кода).

Ограничения: подтверждённый платёж изменить нельзя; сумма подтверждаемого платежа не может превышать остаток контракта.

### Готовый сценарий на JavaScript

```js
const BASE = "http://127.0.0.1:8000";
const token = localStorage.getItem("access_token");

const res = await fetch(`${BASE}/students/me`, {
  headers: { "Authorization": `Bearer ${token}` },
});
if (res.status === 401) { /* обновить токен через /auth/refresh или выполнить вход */ }
const student = await res.json();
```

---

## 5. Что ещё не реализовано

Для следующих возможностей в проекте **нет API endpoints** — во frontend их использовать нельзя:

- **Schedules (расписание):** модель `Schedule` и схемы `ScheduleCreateSchema` / `ScheduleResponseSchema` есть, но ни одного роута нет. Управления расписанием через API не существует.
- **Students:** `PATCH /students/{student_id}` доступен администратору; обновляет группу и/или номер студента с сохранением истории.
- **Payments:** нет `PUT` — изменение только через `PATCH /payments/{payment_id}/status`.
- **Personal Info:** нет `DELETE /personal-info/me` — удаление доступно только администратору по `student_id`.
- **Auth:** нет смены пароля и восстановления пароля.
- **Списки:** нет query-параметров для пагинации и фильтрации.
- **Root endpoint:** нет `/`, есть только `/health`.

---

### Изменения: смена группы и история переводов

- `PATCH /students/{student_id}` (Admin): частично обновляет `group_id` (включая `null`) и/или `student_number`. Пустое тело допустимо.
- `GET /students/me/groups` (Student): собственная история групп.
- `GET /students/{student_id}/groups` (Admin): история групп выбранного студента.
- Ответ PATCH: обычный `StudentResponseSchema`. Ошибки: 401, 403, 404 (студент или группа), 409 (номер студента либо конфликт истории), 422.
- История содержит `kind` = `enrollment` / `transfer`, `from_date`, `to_date`, `reason` и `group` с названием и курсом.
- При переводе сохраняются студент, контракт и платежи. Повторное назначение той же группы не создаёт новую запись.
- Для существующих студентов миграция сохраняет их текущую группу; `from_date: null` означает, что фактическая дата поступления неизвестна.
- Удаление группы с историей переводов запрещено (409).

## 6. Проверка через Swagger UI

1. Запустите приложение:
   ```bash
   .venv/bin/python -m uvicorn main:edu_app --host 127.0.0.1 --port 8000
   ```
2. Откройте `http://127.0.0.1:8000/docs`.
3. Выполните `POST /auth/login` (**Try it out** → ввести данные → **Execute**), скопируйте `access_token`.
4. Нажмите **Authorize** вверху страницы, вставьте токен в поле Value → **Authorize**. Swagger добавит заголовок `Authorization: Bearer <token>` автоматически.
5. Откройте нужный endpoint → **Try it out** → заполните параметры/тело → **Execute**.

Примеры через `curl`:
```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin12345"}'

curl http://127.0.0.1:8000/users/ -H "Authorization: Bearer <access_token>"
curl http://127.0.0.1:8000/health
```
