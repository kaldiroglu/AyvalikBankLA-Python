from __future__ import annotations

from decimal import Decimal

from ..exception import LimitExceededException
from ..model import CustomerTier


class TransferService:
    def calculate_fee(
        self,
        amount: Decimal,
        same_customer: bool,
        fee_percent: Decimal,
        source_tier: CustomerTier,
    ) -> Decimal:
        if same_customer:
            return Decimal("0.00")
        scaled_percent = fee_percent * source_tier.fee_multiplier()
        return (amount * scaled_percent / Decimal(100)).quantize(Decimal("0.01"))

    def require_transfer_within_limit(self, amount: Decimal, tier: CustomerTier) -> None:
        cap = tier.max_per_transfer()
        if cap is not None and amount > cap:
            raise LimitExceededException(
                f"Transfer amount {amount} exceeds {tier.value} tier limit of {cap}"
            )

    def require_withdrawal_within_limit(self, amount: Decimal, tier: CustomerTier) -> None:
        cap = tier.max_per_withdrawal()
        if cap is not None and amount > cap:
            raise LimitExceededException(
                f"Withdrawal amount {amount} exceeds {tier.value} tier limit of {cap}"
            )
