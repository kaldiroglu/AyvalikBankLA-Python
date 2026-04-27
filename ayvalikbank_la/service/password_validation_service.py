import re

from ..exception import PasswordValidationException


class PasswordValidationService:
    _SPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]")

    def validate(self, password: str) -> None:
        if not (8 <= len(password) <= 16):
            raise PasswordValidationException("Password length must be between 8 and 16 characters")
        if not any(c.isdigit() for c in password):
            raise PasswordValidationException("Password must contain at least one digit")
        if not any(c.isupper() for c in password):
            raise PasswordValidationException("Password must contain at least one uppercase letter")
        if not self._SPECIAL.search(password):
            raise PasswordValidationException("Password must contain at least one special character")
