import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PlategaError(Exception):
    pass


class PlategaConfigurationError(PlategaError):
    pass


class PlategaService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _base_url(self) -> str:
        return self.settings.PLATEGA_BASE_URL.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        merchant_id = self.settings.PLATEGA_MERCHANT_ID.strip()
        secret = self.settings.PLATEGA_SECRET.strip()
        if not merchant_id or not secret:
            raise PlategaConfigurationError("Platega credentials are not configured")
        return {
            "X-MerchantId": merchant_id,
            "X-Secret": secret,
            "Content-Type": "application/json",
        }

    async def create_payment(
        self,
        *,
        amount: int,
        currency: str,
        description: str,
        return_url: str,
        failed_url: str,
        payload: str,
        payment_method: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "paymentDetails": {
                "amount": amount,
                "currency": currency,
            },
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
            "payload": payload,
        }
        if payment_method is not None:
            body["paymentMethod"] = payment_method

        return await self._request("POST", "/transaction/process", json=body)

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/transaction/{transaction_id}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.request(method, url, headers=self._headers, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("Platega API error %s for %s: %s", exc.response.status_code, url, exc.response.text)
                detail = exc.response.text.strip() or f"HTTP {exc.response.status_code}"
                raise PlategaError(detail) from exc
            except httpx.HTTPError as exc:
                logger.error("Platega request failed for %s: %s", url, exc)
                raise PlategaError("Unable to reach Platega API") from exc


platega_service = PlategaService()
