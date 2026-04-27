from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..repository.db import Base


class Settings(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
