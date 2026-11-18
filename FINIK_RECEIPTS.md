# Finik төлөмүнүн электрондук квитанциясы / подтверждение оплаты

**Бул EduFlow түзгөн электрондук подтверждение, расмий фискалдык чек эмес.**
Finik'тин документтеринде расмий PDF чекти жүктөй турган текшерилген
API көрсөтүлгөн жок, ошондуктан расмий чек бар деп жаңылыш билдирбейбиз.

## Эмне сакталат?

Ийгиликтүү кол коюлган webhook же администратор Finik кабинетинен
далил менен текшерип ырастаган төлөм үчүн `finik_receipts` таблицасына:

- `payment_id` (unique), EduFlow квитанция номери `EDU-FINIK-0000000001`;
- сумма, валюта (KGS);
- Finik'тин `provider_transaction_id` жана, бар болсо, `provider_operation_id`;
- `confirmed_at` — EduFlow боюнча тастыкталган убакыт (учурда UTC);
- `verification_source` — `signed_webhook` же `admin_reconciliation`;
- `allocation_snapshot` — ушул бир төлөм кайсы айларга/взносторго бөлүнгөнү;
- `created_at` — квитанциянын жазылган убактысы.

`provider_paid_at` азыр null: Finik callback расмий төлөө убактысын
ишенимдүү берери далилденген жок. Эгер кийин API'ден текшерилген
timestamp алынса, өзүнчө интеграция менен жазууга болот.

Квитанция **төлөм confirmed болгондо гана** түзүлөт. Бир эле төлөмгө
экинчи квитанция жазылбайт (`payment_id` unique). Бул жазуу төлөмдү
кайра эсептебейт; эсепти `payments` таблицасы чыгарат.

## API

`GET /finik/receipts/{payment_id}`

JWT талап кылынат. Студент өз контрагынын гана квитанциясын көрөт,
администратор көрө алат.

HTTP 409 — төлөм али тастыктала элек.
HTTP 404 — төлөм Finik эмес же квитанция жок.
HTTP 403 — башка студенттин төлөмү.

Мисал жооп:

```json
{
  "id": 1,
  "receipt_number": "EDU-FINIK-0000000042",
  "payment_id": 42,
  "amount": "30000.00",
  "currency": "KGS",
  "provider_transaction_id": "tx-from-finik",
  "provider_operation_id": "operation-from-finik",
  "provider_paid_at": null,
  "confirmed_at": "2026-11-13T09:30:00",
  "verification_source": "signed_webhook",
  "allocation_snapshot": [
    {"period_index": 0, "payment_month": "2026-01", "amount": "15000.00"},
    {"period_index": 1, "payment_month": "2026-02", "amount": "15000.00"}
  ],
  "created_at": "2026-11-13T09:30:00"
}
```

## Тест жана миграция

Адегенде өзүнчө PostgreSQL 18 `eduflow_test` базасында:

```bash
alembic upgrade head
python -m pytest -q tests/test_finik_receipts.py tests/test_payment_allocations.py
python -m pytest -q tests/test_payments_httpx.py tests/test_finik.py tests/test_api.py
```

Жаңы ревизия: `d6b309e67142`, мурдагы `c4af9e8d2a61`.
PR'ды текшербей `main`'ге бириктирбөө.

Эски тастыкталган төлөмдөр үчүн автоматтык түрдө жасалма чек түзүлбөйт;
аларды Finik маалыматтары менен өзүнчө текшерип backfill кылуу керек.

## Өзгөргөн файлдар

- `myproject/database/models.py` — FinikReceipt модели
- `myproject/database/schemas.py` — FinikReceiptResponseSchema
- `myproject/services/finik_receipts.py` — идемпотенттүү сактоо
- `myproject/api/finik.py` — webhook/manual confirmation жана GET
- `migrations/versions/d6b309e67142_add_finik_receipts.py` — Alembic
- `tests/test_finik_receipts.py` — API/privacy/idempotency тесттери
