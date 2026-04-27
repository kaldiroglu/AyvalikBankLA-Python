from decimal import Decimal

from ayvalikbank_la.model import CustomerTier


def test_standard_has_full_fee_and_modest_caps():
    assert CustomerTier.STANDARD.fee_multiplier() == Decimal("1.00")
    assert CustomerTier.STANDARD.max_per_transfer() == Decimal("5000")
    assert CustomerTier.STANDARD.max_per_withdrawal() == Decimal("5000")


def test_premium_halves_fee_and_raises_caps():
    assert CustomerTier.PREMIUM.fee_multiplier() == Decimal("0.50")
    assert CustomerTier.PREMIUM.max_per_transfer() == Decimal("50000")
    assert CustomerTier.PREMIUM.max_per_withdrawal() == Decimal("25000")


def test_private_is_free_and_unlimited():
    assert CustomerTier.PRIVATE.fee_multiplier() == Decimal("0.00")
    assert CustomerTier.PRIVATE.max_per_transfer() is None
    assert CustomerTier.PRIVATE.max_per_withdrawal() is None
