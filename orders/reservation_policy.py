"""Effective platform expiry, separate from preserved merchant configuration."""
from dataclasses import asdict, dataclass
from decimal import Decimal

from .models import ReservationPolicy


STANDARD_RESERVATION_TTL_SECONDS = 900


@dataclass(frozen=True)
class EffectiveReservationPolicy:
    max_unpaid_quantity: int
    max_unpaid_amount: Decimal
    max_stock_percent: int
    configured_ttl_seconds: int | None
    ttl_seconds: int = STANDARD_RESERVATION_TTL_SECONDS
    ttl_source: str = 'platform_fixed_900_v1'
    ttl_editable: bool = False

    def as_payload(self):
        payload = asdict(self)
        payload['max_unpaid_amount'] = format(self.max_unpaid_amount, '.2f')
        return payload


def effective_policy(merchant_id, configured=None):
    """Copy merchant limits while applying the fixed expiry only to new orders.

    Never mutate or save the configured model: its TTL is historical evidence,
    not the effective platform deadline. A missing policy remains unsaved.
    """
    if configured is None:
        configured = ReservationPolicy.objects.filter(merchant_id=merchant_id).first()
    configured_ttl = configured.ttl_seconds if configured is not None else None
    limits = configured if configured is not None else ReservationPolicy(merchant_id=merchant_id)
    return EffectiveReservationPolicy(
        max_unpaid_quantity=limits.max_unpaid_quantity,
        max_unpaid_amount=Decimal(str(limits.max_unpaid_amount)),
        max_stock_percent=limits.max_stock_percent,
        configured_ttl_seconds=configured_ttl,
    )
