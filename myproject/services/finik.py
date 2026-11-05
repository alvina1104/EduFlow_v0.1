import base64
import binascii
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from myproject.config import (
    FINIK_ENV, FINIK_API_KEY, FINIK_ACCOUNT_ID,
    FINIK_PRIVATE_KEY_PATH, FINIK_PUBLIC_KEY_PATH,
    FINIK_WEBHOOK_URL, FINIK_REDIRECT_URL
)


FINIK_HOSTS = {
    "beta": "beta.api.acquiring.averspay.kg",
    "production": "api.acquiring.averspay.kg"
}


def ensure_config():
    if (
        FINIK_ENV not in FINIK_HOSTS
        or not FINIK_API_KEY
        or not FINIK_ACCOUNT_ID
        or not FINIK_PRIVATE_KEY_PATH
        or not FINIK_PUBLIC_KEY_PATH
        or not FINIK_WEBHOOK_URL.startswith("https://")
        or not FINIK_REDIRECT_URL.startswith("https://")
    ):
        raise ValueError("Finik не настроен")

    if not Path(FINIK_PRIVATE_KEY_PATH).is_file():
        raise ValueError("Не найден приватный ключ")

    if not Path(FINIK_PUBLIC_KEY_PATH).is_file():
        raise ValueError("Не найден публичный ключ Finik")


def canonical(method: str, path: str, headers: dict, body: dict) -> bytes:
    signed = {
        k.lower(): str(v)
        for k, v in headers.items()
        if k.lower() == "host" or k.lower().startswith("x-api-")
    }

    header_text = "&".join(
        f"{k}:{v}" for k, v in sorted(signed.items())
    )
    body_text = json.dumps(
        dict(sorted(body.items())),
        ensure_ascii=False,
        separators=(",", ":")
    )

    return f"{method.lower()}\n{path}\n{header_text}\n{body_text}".encode()


def sign_payment(body: dict, timestamp: str) -> str:
    headers = {
        "Host": FINIK_HOSTS[FINIK_ENV],
        "x-api-key": FINIK_API_KEY,
        "x-api-timestamp": timestamp
    }

    key = serialization.load_pem_private_key(
        Path(FINIK_PRIVATE_KEY_PATH).read_bytes(),
        password=None
    )

    signature = key.sign(
        canonical("POST", "/v1/payment", headers, body),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode()


def verify_webhook(headers: dict, body: dict, path: str) -> bool:
    headers = {k.lower(): v for k, v in headers.items()}

    try:
        stamp = int(headers.get("x-api-timestamp", ""))
        if abs(int(time.time() * 1000) - stamp) > 300000:
            return False

        signature = base64.b64decode(
            headers.get("signature", ""), validate=True
        )

        key = serialization.load_pem_public_key(
            Path(FINIK_PUBLIC_KEY_PATH).read_bytes()
        )

        key.verify(
            signature,
            canonical("POST", path, headers, body),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True

    except (ValueError, TypeError, InvalidSignature, OSError, binascii.Error):
        return False


def create_finik_payment(payment_id: str, amount, contract_id: int) -> str:
    ensure_config()

    host = FINIK_HOSTS[FINIK_ENV]

    body = {
        "Amount": float(amount),
        "CardType": "FINIK_QR",
        "PaymentId": payment_id,
        "RedirectUrl": FINIK_REDIRECT_URL,
        "Lang": "ru",
        "Data": {
            "accountId": FINIK_ACCOUNT_ID,
            "name_en": "Motion Web",
            "webhookUrl": FINIK_WEBHOOK_URL,
            "description": f"EduFlow contract #{contract_id}"
        }
    }

    timestamp = str(int(time.time() * 1000))
    signature = sign_payment(body, timestamp)

    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            f"https://{host}/v1/payment",
            json=body,
            headers={
                "x-api-key": FINIK_API_KEY,
                "x-api-timestamp": timestamp,
                "signature": signature
            }
        )

    url = response.headers.get("location", "")

    if response.status_code != 302 or urlsplit(url).scheme != "https":
        raise ValueError(f"Finik HTTP {response.status_code}")

    return url