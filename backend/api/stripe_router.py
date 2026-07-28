"""
api/stripe_router.py — Stripe checkout + webhook for SUBVOX subscriptions.
"""

import stripe
from fastapi import APIRouter, HTTPException, Request
from core.config import settings
from core.db import _pool as pool

router = APIRouter(prefix="/stripe", tags=["stripe"])

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_MAP = {
    "passion_monthly": settings.STRIPE_PRICE_PASSION_MONTHLY,
    "passion_annual": settings.STRIPE_PRICE_PASSION_ANNUAL,
    "ultimate_monthly": settings.STRIPE_PRICE_ULTIMATE_MONTHLY,
    "ultimate_annual": settings.STRIPE_PRICE_ULTIMATE_ANNUAL,
}


@router.post("/create-checkout")
async def create_checkout(request: Request):
    """Crée une session Stripe Checkout. Body: {price_key, user_id, email, success_url, cancel_url}"""
    body = await request.json()
    price_key = body.get("price_key")
    user_id = body.get("user_id")
    email = body.get("email", "")
    success_url = body.get("success_url", "https://subvox.xyz/app/billing?success=1")
    cancel_url = body.get("cancel_url", "https://subvox.xyz/app/billing?canceled=1")

    price_id = PRICE_MAP.get(price_key)
    if not price_id or not user_id:
        raise HTTPException(400, "price_key et user_id requis")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email if email else None,
            client_reference_id=user_id,
            metadata={"user_id": user_id, "price_key": price_key},
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"url": session.url, "session_id": session.id}
    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Webhook Stripe — met à jour les abonnements."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(500, "Webhook secret non configuré")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Signature invalide")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        sub_id = session.get("subscription")
        customer_id = session.get("customer")
        price_key = session.get("metadata", {}).get("price_key", "")

        if user_id and sub_id:
            # Récupérer le plan depuis le price_key
            tier = "passion" if "passion" in price_key else "ultimate" if "ultimate" in price_key else "decouverte"
            interval = "annual" if "annual" in price_key else "monthly"

            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO subscriptions (user_id, plan, tier, stripe_customer_id, stripe_subscription_id, period_end)
                    VALUES ($1, $2, $3, $4, $5, NOW() + interval '1 month')
                    ON CONFLICT (user_id) DO UPDATE SET
                        plan = EXCLUDED.plan,
                        tier = EXCLUDED.tier,
                        stripe_customer_id = EXCLUDED.stripe_customer_id,
                        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                        period_end = CASE WHEN EXCLUDED.plan = 'passion' OR EXCLUDED.plan = 'ultimate'
                            THEN NOW() + CASE WHEN $6 = 'annual' THEN interval '1 year' ELSE interval '1 month' END
                            ELSE subscriptions.period_end END
                """, user_id, tier, tier, customer_id, sub_id, interval)

    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        sub_id = invoice.get("subscription")
        customer_id = invoice.get("customer")

        if sub_id:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE subscriptions SET period_end = NOW() + interval '1 month'
                    WHERE stripe_subscription_id = $1
                """, sub_id)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub.get("id")
        if sub_id:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE subscriptions SET plan = 'decouverte', tier = 'decouverte',
                        stripe_subscription_id = NULL, period_end = NULL
                    WHERE stripe_subscription_id = $1
                """, sub_id)

    return {"ok": True}
