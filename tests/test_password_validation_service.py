import pytest

from ayvalikbank_la.exception import PasswordValidationException
from ayvalikbank_la.service import PasswordValidationService


@pytest.fixture
def service() -> PasswordValidationService:
    return PasswordValidationService()


def test_accepts_valid_password(service):
    service.validate("Goodpass1!")


@pytest.mark.parametrize("password", ["Short1!", "ThisIsWayTooLong1!"])
def test_rejects_out_of_range_length(service, password):
    with pytest.raises(PasswordValidationException, match="length"):
        service.validate(password)


def test_rejects_missing_digit(service):
    with pytest.raises(PasswordValidationException, match="digit"):
        service.validate("Password!")


def test_rejects_missing_uppercase(service):
    with pytest.raises(PasswordValidationException, match="uppercase"):
        service.validate("password1!")


def test_rejects_missing_special_character(service):
    with pytest.raises(PasswordValidationException, match="special"):
        service.validate("Password1")
