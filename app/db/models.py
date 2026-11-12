"""Read-only mapping of the API's columns; the indexer owns the schema."""
from datetime import datetime
from sqlalchemy import BigInteger, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DatasetMeta(Base):
    __tablename__ = "dataset_meta"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    bumped_at: Mapped[datetime | None]


class Source(Base):
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)


ProgramType = ENUM("movie", "tv_series", name="program_type", create_type=False)


class Program(Base):
    __tablename__ = "program"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uid: Mapped[str] = mapped_column(Text)
    uri: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(ProgramType)
    source_id: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool]
