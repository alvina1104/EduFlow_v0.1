# EduFlow: последовательные платежи, колледж и ментор

Изменения добавлены поверх существующего FastAPI / SQLAlchemy 2.x кода.
Прежние платежи не переписываются, а API и логика Finik используют одну
функцию распределения.

## Академия

Контракт с `monthly_payment=15000`, `duration_months=10`:

- 10 000 сом: 10 000 на первый неоплаченный месяц;
- затем 20 000 сом: 5 000 на остаток первого и 15 000 на второй;
- сразу 30 000 сом: 15 000 на первый и 15 000 на второй;
- сразу 45 000 сом: три месяца по 15 000.

Параметр `payment_month` необязателен: при его отсутствии первый
неоплаченный месяц выбирается автоматически. Если передан следующий месяц,
а предыдущий ещё не оплачен, API отвечает HTTP 409.

Пример запроса **администратора** `POST /payments/`:

```json
{
  "request_id": "16a83783-4547-45cc-89f4-ea3ef025f1a4",
  "contract_id": 17,
  "amount": "30000.00",
  "payment_method": "cash",
  "payment_month": null
}
```

Ответ включает `allocations`:

```json
[
  {"period_index": 0, "payment_month": "2026-01", "amount": "15000.00"},
  {"period_index": 1, "payment_month": "2026-02", "amount": "15000.00"}
]
```

В схеме ответа также приходит `id` каждой записи распределения.

## Колледж

При создании контракта `POST /contracts/` укажите
`type="college"` и `installment_count=2` или `3`. По умолчанию — 2.

```json
{
  "student_id": 12,
  "type": "college",
  "installment_count": 3,
  "total_amount": "100000.00",
  "monthly_payment": "10000.00",
  "duration_months": 10,
  "start_date": "2026-01-01"
}
```

100 000 / 3 распределяется без потери копеек:
33 333.33 + 33 333.33 + 33 333.34.
Можно перечислить несколько взносов одним платежом или оплатить часть
взноса, но следующий взнос не получит денег до закрытия предыдущего.
Взносы колледжа — части общей суммы; отдельные даты/семестры пока не
настраиваются. Существующие колледж-контракты автоматически получают
2 взноса через миграцию.

## Группы и профили

`POST /groups/` и `PUT /groups/{group_id}` принимают `mentor_name`:

```json
{
  "name": "Python 26",
  "course_name": "Backend Python",
  "mentor_name": "Айбек",
  "start_date": "2026-09-01",
  "end_date": null
}
```

`GET /groups/{id}` возвращает `mentor_name`, а
`GET /students/{id}` и `GET /students/me` возвращают имя ментора
текущей группы как `mentor_name`. Пока это поле с именем,
**не отдельный аккаунт Mentor и не новая роль**.

## Оплата, время и безопасность

- На один `payments.id` приходится одна запись о платеже и несколько
  `payment_allocations`. Записи распределения содержат `period_index`,
  `payment_month` и `amount`.
- При создании Finik QR распределение резервируется, но в баланс
  попадают только платежи со статусом `confirmed`.
- Webhook и ручная сверка пересчитывают план под блокировкой контракта;
  при конфликте Finik платеж попадает на ручную проверку, а не
  автоматически зачисляется.
- Повтор того же `request_id` возвращает тот же платёж.
  Повторный успешный Finik webhook не зачисляет деньги заново.
- Пока есть `pending` оплата по контракту, новая транзакция по тому
  же контракту не создаётся.
- `payments.created_at` хранит день и время создания, `paid_at`
  хранит день и время подтверждения. `finik_transactions.confirmed_at`
  хранит время успешной сверки. Текущий Backend сохраняет UTC в
  `timestamp without time zone`. Новый Frontend должен переводить UTC
  в `Asia/Bishkek` при отображении. Изменение типа существующих полей времени требует
  отдельной проверенной миграции.
- Старые подтверждённые платежи без `payment_allocations` продолжают
  учитываться при расчётах. Для академии — по `payment_month`,
  для колледжа — последовательно по общей сумме.
- Для оплаты Finik используйте существующий `POST /finik/payments`
  c `payment_month=null`; подключение к реальному провайдеру
  зависит от настройки ключей и провайдера.

## Миграция / проверка

1. Сначала сохраните резервную копию базы данных.
2. В тестовом окружении с настроенным `.env` выполните:
   `alembic upgrade head`
3. Убедитесь, что `groups.mentor_name`,
   `contracts.installment_count`, `payment_allocations` существуют.
4. Для тестов используйте **отдельную локальную** `eduflow_test`
   (не production и не туннель на production):

```bash
pytest -q tests/test_payment_allocations.py
pytest -q tests/test_payments_httpx.py tests/test_finik.py tests/test_api.py
```

Эти тесты **добавлены/обновлены в репозитории, но не выполнялись**
на реальной PostgreSQL в этой сессии. Перед объединением с `main`
обязательно протестируйте миграции, исторические транзакции и
повторные вызовы Finik на отдельной тестовой базе.

## Изменённые файлы

- `myproject/services/payment_allocation.py` — новые функции распределения.
- `myproject/api/payments.py` — создание, баланс, подтверждение.
- `myproject/api/finik.py` — единое подтверждение для Finik.
- `myproject/database/models.py` — Mentor, installment_count, PaymentAllocation.
- `myproject/database/schemas.py` — новые поля API.
- `migrations/versions/c4af9e8d2a61_add_mentor_and_payment_allocations.py` — миграция.
- `tests/test_payment_allocations.py` — новые проверки.
- `tests/test_api.py`, `tests/test_finik.py`,
  `tests/test_payments_httpx.py` — тестовые данные для последовательной оплаты.
