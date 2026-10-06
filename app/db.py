"""Database models. SQLite in development, Postgres in production.

Every table that holds customer data has company_id. Every query filters on it.
Records and signatures are append-only: a correction is a new record.
"""
import secrets
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def new_id() -> str:
    return secrets.token_hex(8)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    reg_no: Mapped[str] = mapped_column(String(60), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    coid_no: Mapped[str] = mapped_column(String(60), default="")
    logo_file: Mapped[str] = mapped_column(String(200), default="")
    induction_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), default="")
    role: Mapped[str] = mapped_column(String(20))        # owner | safety | foreman | auditor
    sacpcmp_no: Mapped[str] = mapped_column(String(60), default="")
    pw_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text, default="")
    client: Mapped[str] = mapped_column(String(200), default="")
    client_agent: Mapped[str] = mapped_column(String(200), default="")
    emergency: Mapped[str] = mapped_column(Text, default="")   # nearest hospital, numbers
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")   # active | closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    id_number: Mapped[str] = mapped_column(String(40), default="")   # personal info (POPIA)
    trade: Mapped[str] = mapped_column(String(100), default="")
    employer: Mapped[str] = mapped_column(String(200), default="")   # blank = own staff
    phone: Mapped[str] = mapped_column(String(40), default="")
    emergency_contact: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(20), default="en")
    photo_file: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    credentials: Mapped[list["Credential"]] = relationship(back_populates="worker",
                                                           cascade="all, delete-orphan")


class Credential(Base):
    """A medical certificate, training certificate, licence or similar."""
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))          # medical | training | licence | first_aid | other
    title: Mapped[str] = mapped_column(String(200))
    issued: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires: Mapped[date | None] = mapped_column(Date, nullable=True)
    file: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    worker: Mapped[Worker] = relationship(back_populates="credentials")


class SiteWorker(Base):
    __tablename__ = "site_workers"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RiskItem(Base):
    """One activity in the risk assessment: hazards with controls, and PPE.

    The AI may only pick these items. Only an approved item counts as assessed.
    An edit clears the approval.
    """
    __tablename__ = "risk_items"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    activity: Mapped[str] = mapped_column(String(200))
    hazards: Mapped[list] = mapped_column(JSON, default=list)   # [{hazard, risk, controls: []}]
    ppe: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20), default="manual")   # starter | ai_draft | manual
    approved_by: Mapped[str] = mapped_column(String(200), default="")   # name + SACPCMP number
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Plant(Base):
    __tablename__ = "plant"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    template: Mapped[str] = mapped_column(String(40))       # key in library.CHECKLISTS
    ident: Mapped[str] = mapped_column(String(100), default="")   # registration or serial
    qr_token: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: secrets.token_urlsafe(9))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Doc(Base):
    """An uploaded document for one section of the safety file."""
    __tablename__ = "docs"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    section: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    file: Mapped[str] = mapped_column(String(200))
    expires: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Record(Base):
    """A signed site record. Immutable once stored; part of the hash chain."""
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("company_id", "client_id"),
                      UniqueConstraint("company_id", "seq"))
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    client_id: Mapped[str] = mapped_column(String(64))       # set by the device; makes sync idempotent
    record_date: Mapped[date] = mapped_column(Date, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    transcript: Mapped[str] = mapped_column(Text, default="")   # derived; outside the hash
    audio_file: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(16))
    created_name: Mapped[str] = mapped_column(String(200))
    device_time: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    seq: Mapped[int] = mapped_column(Integer)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    signatures: Mapped[list["Signature"]] = relationship(back_populates="record",
                                                         order_by="Signature.order")


class Signature(Base):
    __tablename__ = "signatures"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(60))           # worker | supervisor | operator | presenter | inductor
    image_file: Mapped[str] = mapped_column(String(200), default="")
    photo_file: Mapped[str] = mapped_column(String(200), default="")
    signed_at: Mapped[str] = mapped_column(String(40), default="")   # device clock
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    record: Mapped[Record] = relationship(back_populates="signatures")


engine = create_engine(config.DATABASE_URL, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {})

if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
