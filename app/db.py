"""Database models. SQLite in development, Postgres in production.

Every table that holds customer data has company_id. Every query filters on it.
Records and signatures are append-only: a correction is a new record.
"""
import secrets
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, create_engine, event, inspect, text)
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
    esign_accepted_by: Mapped[str] = mapped_column(String(200), default="")   # ECT s13(3) agreement
    esign_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)          # platform admin can switch off
    invite: Mapped[str] = mapped_column(String(60), default="")          # invite code used at sign-up
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InviteCode(Base):
    """Pilot sign-up codes, managed in the admin page."""
    __tablename__ = "invite_codes"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class PasswordReset(Base):
    """A forgot-password request. The link holds the token; the table holds only its hash."""
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)


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
    features: Mapped[dict] = mapped_column(JSON, default=dict)          # library.SITE_FEATURES -> bool
    print_required: Mapped[bool] = mapped_column(Boolean, default=False)  # client wants paper copies
    settings: Mapped[dict] = mapped_column(JSON, default=dict)   # spec, ra_only, facilities
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Contractor(Base):
    """A subcontractor on one site: reg 7(1)(c) and 7(1)(f)."""
    __tablename__ = "contractors"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    reg_no: Mapped[str] = mapped_column(String(60), default="")
    scope: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    coid_expires: Mapped[date | None] = mapped_column(Date, nullable=True)
    coid_file: Mapped[str] = mapped_column(String(200), default="")
    appointed_on: Mapped[date | None] = mapped_column(Date, nullable=True)     # appointed in writing
    hs_plan_ok: Mapped[bool] = mapped_column(Boolean, default=False)          # plan received and approved
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AesDoc(Base):
    """A document that needs an advanced electronic signature (or wet ink).

    The app issues the PDF; the signer signs it with an accredited AES
    (LAWtrust AeSign, for example through SigniFlow) or by hand; the signed
    PDF comes back and the server records what it finds in it.
    """
    __tablename__ = "aes_docs"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    record_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contractor_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    signers: Mapped[list] = mapped_column(JSON, default=list)          # names expected to sign
    original_file: Mapped[str] = mapped_column(String(200), default="")
    signed_file: Mapped[str] = mapped_column(String(200), default="")
    method: Mapped[str] = mapped_column(String(20), default="")        # aes | wet_ink
    status: Mapped[str] = mapped_column(String(20), default="awaiting")   # awaiting | signed
    signatures: Mapped[list] = mapped_column(JSON, default=list)        # what the PDF check found
    note: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    id_number: Mapped[str] = mapped_column(String(40), default="")   # personal info (POPIA)
    trade: Mapped[str] = mapped_column(String(100), default="")
    employer: Mapped[str] = mapped_column(String(200), default="")   # blank = own staff
    contractor_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
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
    source: Mapped[str] = mapped_column(String(20), default="manual")   # starter | ai_draft | manual | consultant_ra
    ref: Mapped[str] = mapped_column(String(200), default="")             # e.g. "RA 1 rev 00 · item 5"
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Additive schema changes for existing databases: add new columns.

    create_all() makes new tables but never changes old ones. Until the first
    real migration needs Alembic, new columns must be nullable or have a
    simple default, and this adds them.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                default = ""
                d = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if isinstance(d, bool):
                    default = f" DEFAULT {'TRUE' if d else 'FALSE'}" if engine.dialect.name == "postgresql" else f" DEFAULT {int(d)}"
                elif isinstance(d, (int, float)):
                    default = f" DEFAULT {d}"
                elif isinstance(d, str):
                    default = " DEFAULT '" + d.replace("'", "''") + "'"
                elif col.name in ("features", "settings"):
                    default = " DEFAULT '{}'"
                elif col.name in ("signers", "signatures"):
                    default = " DEFAULT '[]'"
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}{default}'))


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
