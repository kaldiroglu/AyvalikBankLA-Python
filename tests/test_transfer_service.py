from decimal import Decimal

import pytest

from ayvalikbank_la.exception import LimitExceededException
from ayvalikbank_la.model import CustomerTier
from ayvalikbank_la.service import TransferService


@pytest.fixture
def service() -> TransferService:
    return TransferService()


def test_same_customer_transfer_is_free_regardless_of_tier(service):
    assert service.calculate_fee(Decimal("1000"), True, Decimal("1.0"), CustomerTier.STANDARD) == Decimal("0.00")


def test_standard_tier_pays_full_fee(service):
    assert service.calculate_fee(Decimal("200"), False, Decimal("1.0"), CustomerTier.STANDARD) == Decimal("2.00")


def test_premium_tier_pays_half_fee(service):
    assert service.calculate_fee(Decimal("200"), False, Decimal("1.0"), CustomerTier.PREMIUM) == Decimal("1.00")


def test_private_tier_pays_no_fee(service):
    assert service.calculate_fee(Decimal("10000"), False, Decimal("1.0"), CustomerTier.PRIVATE) == Decimal("0.00")


def test_rejects_transfer_above_standard_cap(service):
    with pytest.raises(LimitExceededException, match="5000"):
        service.require_transfer_within_limit(Decimal("5001"), CustomerTier.STANDARD)


def test_allows_transfer_at_exactly_the_cap(service):
    service.require_transfer_within_limit(Decimal("5000"), CustomerTier.STANDARD)


def test_private_tier_transfer_is_unlimited(service):
    service.require_transfer_within_limit(Decimal("10000000"), CustomerTier.PRIVATE)


def test_rejects_withdrawal_above_premium_cap(service):
    with pytest.raises(LimitExceededException, match="25000"):
        service.require_withdrawal_within_limit(Decimal("25001"), CustomerTier.PREMIUM)
