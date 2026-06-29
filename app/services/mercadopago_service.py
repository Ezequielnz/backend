import httpx
from typing import Dict, Any, Optional
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MercadoPagoService:
    BASE_URL = "https://api.mercadopago.com"
    
    def __init__(self):
        token = (settings.MP_ACCESS_TOKEN or "").strip()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(base_url=self.BASE_URL, headers=self.headers, timeout=10.0)

    async def get_or_create_plan(self) -> str:
        """
        Creates or retrieves the main subscription plan in Mercado Pago.
        Ideally this is called once. The ID should be saved in settings.MP_PLAN_ID.
        """
        if settings.MP_PLAN_ID:
            return settings.MP_PLAN_ID
            
        payload = {
            "reason": f"Plan {settings.PROJECT_NAME} - Suscripción Mensual",
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": settings.MP_PLAN_PRICE,
                "currency_id": settings.MP_PLAN_CURRENCY,
                "free_trial": {
                    "frequency": 1,
                    "frequency_type": "months"
                }
            },
            "back_url": f"{settings.FRONTEND_URL}/suscripcion/exito",
            "payment_methods_allowed": {
                "payment_types": [{"id": "credit_card"}, {"id": "debit_card"}],
                "financial_institutions": []
            }
        }
        
        response = await self.client.post("/preapproval_plan", json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Creado plan MP: {data['id']}")
        return data["id"]

    async def create_preapproval_link(self, user_id: str, user_email: str, free_months: int = 1) -> Dict[str, Any]:
        """
        Generates a checkout link for the user.
        If free_months > 1, we create an ad-hoc preapproval instead of using the base plan.
        """
        payload = {
            "reason": f"Plan {settings.PROJECT_NAME} - Suscripción Mensual",
            "external_reference": str(user_id),
            "payer_email": user_email,
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": settings.MP_PLAN_PRICE,
                "currency_id": settings.MP_PLAN_CURRENCY,
                "free_trial": {
                    "frequency": free_months,
                    "frequency_type": "months"
                }
            },
            "back_url": f"{settings.FRONTEND_URL}/suscripcion/exito",
            "status": "pending"
        }
        
        response = await self.client.post("/preapproval", json=payload)
        response.raise_for_status()
        data = response.json()
        return {
            "init_point": data["init_point"],
            "preapproval_id": data["id"]
        }

    async def get_preapproval_status(self, preapproval_id: str) -> Dict[str, Any]:
        """Consults the status of a subscription."""
        response = await self.client.get(f"/preapproval/{preapproval_id}")
        response.raise_for_status()
        return response.json()

    async def pause_preapproval(self, preapproval_id: str) -> bool:
        """Pauses a subscription."""
        payload = {"status": "paused"}
        response = await self.client.put(f"/preapproval/{preapproval_id}", json=payload)
        return response.status_code == 200
        
    async def activate_preapproval(self, preapproval_id: str) -> bool:
        """Re-activates a paused subscription."""
        payload = {"status": "authorized"}
        response = await self.client.put(f"/preapproval/{preapproval_id}", json=payload)
        return response.status_code == 200

    async def cancel_preapproval(self, preapproval_id: str) -> bool:
        """Cancels a subscription."""
        payload = {"status": "cancelled"}
        response = await self.client.put(f"/preapproval/{preapproval_id}", json=payload)
        return response.status_code == 200
        
    async def get_payment_info(self, payment_id: str) -> Dict[str, Any]:
        """Gets detailed info about a specific payment to verify webhooks."""
        response = await self.client.get(f"/v1/payments/{payment_id}")
        response.raise_for_status()
        return response.json()

    async def transfer_commission(self, amount: float, receptor_cvu: str, description: str, external_reference: str) -> Dict[str, Any]:
        """
        Transfers money to a CVU using MP money_transfers API.
        """
        # We need idempotency key for transfers
        headers = dict(self.headers)
        headers["X-Idempotency-Key"] = f"transfer_{external_reference}"
        
        payload = {
            "amount": amount,
            "currency_id": "ARS",
            "receiver_account": {
                "cvu": receptor_cvu
            },
            "description": description,
            "external_reference": external_reference
        }
        # Note: B2B transfers might require special scopes or different API depending on account setup.
        # This uses the standard money_transfer API
        response = await self.client.post("/v1/money_transfers", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
        
    async def close(self):
        await self.client.aclose()

# Singleton instance
mp_service = MercadoPagoService()
