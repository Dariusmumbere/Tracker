import os
import hmac
import hashlib
import secrets
import json
import logging
import calendar
import datetime
from datetime import datetime as dt, date, timedelta, timezone
from typing import Optional, List

import jwt
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, Boolean,
    ForeignKey, func
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

# ----------------------------------------------------------------------------
# Logging — AI call failures are logged loudly instead of being swallowed,
# so a misconfigured/retired model or bad API key is visible in the logs
# instead of silently falling back with no trace.
# ----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("growth_tracker.ai")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_plvPhjQ4GFE8@ep-polished-sound-aypwc5kt-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "llama-3.1-8b-instant")

CURRENCIES = {"UGX", "USD", "KES", "EUR", "GBP"}

MOTIVATION_QUOTES = [
    "Discipline is choosing what you want most over what you want now.",
    "Small daily wins compound into financial freedom.",
    "You don't need more hours — you need a better routine.",
    "Every shilling recorded today is a decision made for future-you.",
    "Consistency beats intensity. Show up again today.",
    "The business that gets attention is the business that grows.",
    "Your mission doesn't need perfect days — it needs consistent ones.",
    "Track it, trend it, trust it.",
    "Wealth is built in the boring, repeated actions.",
    "One more hotspot, one more habit, one more day closer.",
]

# ----------------------------------------------------------------------------
# Database setup
# ----------------------------------------------------------------------------

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return dt.now(timezone.utc)


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    currency = Column(String, default="UGX")
    created_at = Column(DateTime, default=utcnow)

    # Mission Control fields
    mission_title = Column(String, default="My Financial Freedom Mission")
    mission_start_date = Column(Date, nullable=True)
    mission_end_date = Column(Date, nullable=True)
    target_hotspot_count = Column(Integer, default=7)

    businesses = relationship("Business", back_populates="owner", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="owner", cascade="all, delete-orphan")
    savings = relationship("Savings", back_populates="owner", cascade="all, delete-orphan")
    hotspots = relationship("Hotspot", back_populates="owner", cascade="all, delete-orphan")
    investments = relationship("Investment", back_populates="owner", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="owner", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="owner", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="owner", cascade="all, delete-orphan")
    insight_history = relationship("AIInsightHistory", back_populates="owner", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="owner", cascade="all, delete-orphan")
    milestones = relationship("Milestone", back_populates="owner", cascade="all, delete-orphan")
    execution_scores = relationship("ExecutionScore", back_populates="owner", cascade="all, delete-orphan")
    todos = relationship("Todo", back_populates="owner", cascade="all, delete-orphan")
    daily_scores = relationship("DailyScore", back_populates="owner", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="owner", cascade="all, delete-orphan")


class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="General")
    start_date = Column(Date, default=lambda: date.today())
    description = Column(String, default="")
    status = Column(String, default="active")  # active | paused | closed
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="businesses")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    type = Column(String, nullable=False)  # revenue | expense
    amount = Column(Float, nullable=False)
    category = Column(String, default="Other")
    description = Column(String, default="")
    date = Column(Date, default=lambda: date.today(), index=True)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="transactions")


class Savings(Base):
    __tablename__ = "savings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, default=lambda: date.today())
    profit_amount = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    amount_saved = Column(Float, nullable=False)
    remaining_cash = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    note = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="savings")


class Hotspot(Base):
    __tablename__ = "hotspots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    location = Column(String, nullable=False)
    installation_cost = Column(Float, default=0)
    installation_date = Column(Date, default=lambda: date.today())
    monthly_data_cost = Column(Float, default=0)
    monthly_electricity_cost = Column(Float, default=0)
    daily_average_revenue = Column(Float, default=0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="hotspots")


class Investment(Base):
    __tablename__ = "investments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    name = Column(String, nullable=False)
    cost = Column(Float, nullable=False)
    purchase_date = Column(Date, default=lambda: date.today())
    notes = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="investments")


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    purchase_price = Column(Float, default=0)
    current_value = Column(Float, default=0)
    purchase_date = Column(Date, default=lambda: date.today())
    notes = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="assets")


class Goal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0)
    deadline = Column(Date, nullable=True)
    status = Column(String, default="active")  # active | completed | abandoned
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="goals")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(String, nullable=False)
    kind = Column(String, default="info")  # info | success | warning
    created_at = Column(DateTime, default=utcnow)
    is_read = Column(Boolean, default=False)

    owner = relationship("User", back_populates="notifications")


class AIInsightHistory(Base):
    __tablename__ = "ai_insight_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="insight_history")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, default=lambda: date.today(), index=True)
    accomplished = Column(String, default="")
    challenges = Column(String, default="")
    learned = Column(String, default="")
    improve_tomorrow = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="journal_entries")


class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    milestone_date = Column(Date, default=lambda: date.today(), index=True)
    title = Column(String, nullable=False)
    notes = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="milestones")


class ExecutionScore(Base):
    """One row per user per day — snapshot of that day's execution score."""
    __tablename__ = "execution_scores"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, default=lambda: date.today(), index=True)
    score = Column(Float, default=0)
    breakdown_json = Column(String, default="{}")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="execution_scores")


class Todo(Base):
    """A single task. Tasks are the atomic unit the daily score is graded on."""
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    notes = Column(String, default="")
    priority = Column(String, default="medium")  # low | medium | high
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    due_date = Column(Date, default=lambda: date.today(), index=True)
    status = Column(String, default="pending")  # pending | in_progress | completed | abandoned
    ai_feedback = Column(String, default="")
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="todos")


class DailyScore(Base):
    """Persisted daily score record — one row per user per day, kept
    permanently as a historical log (separate from the live-recomputed
    ExecutionScore snapshot, this is the immutable end-of-day record)."""
    __tablename__ = "daily_scores"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, default=lambda: date.today(), index=True)
    score = Column(Float, default=0)
    tasks_total = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    breakdown_json = Column(String, default="{}")
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="daily_scores")


class ChatMessage(Base):
    """Persisted AI Advisor chat history, per user."""
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="chat_messages")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Password hashing (PBKDF2 — no extra native deps required)
# ----------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return digest, salt


def verify_password(password: str, digest: str, salt: str) -> bool:
    check, _ = hash_password(password, salt)
    return hmac.compare_digest(check, digest)


# ----------------------------------------------------------------------------
# JWT helpers
# ----------------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        "iat": utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ----------------------------------------------------------------------------
# Pydantic schemas — auth / core entities (unchanged from original)
# ----------------------------------------------------------------------------

class RegisterIn(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    currency: str = "UGX"

    @field_validator("password")
    @classmethod
    def password_len(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("currency")
    @classmethod
    def currency_valid(cls, v):
        return v if v in CURRENCIES else "UGX"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    currency: str

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MeUpdateIn(BaseModel):
    full_name: Optional[str] = None
    currency: Optional[str] = None
    password: Optional[str] = None


class BusinessIn(BaseModel):
    name: str
    category: str = "General"
    start_date: Optional[date] = None
    description: str = ""


class BusinessUpdateIn(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None


class BusinessOut(BaseModel):
    id: int
    name: str
    category: str
    start_date: Optional[date]
    description: str
    status: str

    class Config:
        from_attributes = True


class TransactionIn(BaseModel):
    business_id: int
    type: str
    amount: float
    category: str = "Other"
    description: str = ""
    date: Optional[datetime.date] = None

    @field_validator("type")
    @classmethod
    def type_valid(cls, v):
        if v not in ("revenue", "expense"):
            raise ValueError("type must be 'revenue' or 'expense'")
        return v


class TransactionUpdateIn(BaseModel):
    type: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date: Optional[datetime.date] = None


class TransactionOut(BaseModel):
    id: int
    business_id: int
    type: str
    amount: float
    category: str
    description: str
    date: date

    class Config:
        from_attributes = True


class SavingsIn(BaseModel):
    profit_amount: float
    percentage: float
    note: str = ""
    date: Optional[datetime.date] = None


class SavingsOut(BaseModel):
    id: int
    date: date
    profit_amount: float
    percentage: float
    amount_saved: float
    remaining_cash: float
    balance_after: float
    note: str

    class Config:
        from_attributes = True


class HotspotIn(BaseModel):
    location: str
    installation_cost: float = 0
    installation_date: Optional[date] = None
    monthly_data_cost: float = 0
    monthly_electricity_cost: float = 0
    daily_average_revenue: float = 0
    business_id: Optional[int] = None


class HotspotOut(BaseModel):
    id: int
    location: str
    installation_cost: float
    installation_date: Optional[date]
    monthly_revenue: float
    monthly_profit: float
    roi_percent: float
    payback_months: Optional[float]
    status: str


class HotspotProjectionOut(BaseModel):
    current: int
    target: int
    completion_percent: float
    projection_6_months: int
    projection_1_year: int
    projection_2_years: int
    days_until_target: Optional[int] = None


class InvestmentIn(BaseModel):
    name: str
    cost: float
    purchase_date: Optional[date] = None
    business_id: Optional[int] = None
    notes: str = ""


class InvestmentOut(BaseModel):
    id: int
    business_id: Optional[int]
    name: str
    cost: float
    purchase_date: Optional[date]
    notes: str

    class Config:
        from_attributes = True


class AssetIn(BaseModel):
    name: str
    purchase_price: float = 0
    current_value: float = 0
    purchase_date: Optional[date] = None
    notes: str = ""


class AssetOut(BaseModel):
    id: int
    name: str
    purchase_price: float
    current_value: float
    purchase_date: Optional[date]
    notes: str

    class Config:
        from_attributes = True


class GoalIn(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0
    deadline: Optional[date] = None


class GoalUpdateIn(BaseModel):
    current_amount: Optional[float] = None
    name: Optional[str] = None
    target_amount: Optional[float] = None
    deadline: Optional[date] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v):
        if v is not None and v not in ("active", "completed", "abandoned"):
            raise ValueError("status must be one of: active, completed, abandoned")
        return v


class GoalOut(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    deadline: Optional[date]
    status: str
    progress_percent: float
    amount_remaining: float
    estimated_completion_date: Optional[date] = None


class NotificationOut(BaseModel):
    id: int
    message: str
    kind: str
    is_read: bool
    created_at: dt

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------------
# Pydantic schemas — BOS additions
# ----------------------------------------------------------------------------

class MissionOut(BaseModel):
    title: str
    start_date: Optional[date]
    end_date: Optional[date]
    total_days: Optional[int] = None
    days_completed: Optional[int] = None
    days_remaining: Optional[int] = None
    percent_complete: Optional[float] = None
    current_phase: Optional[str] = None
    phase_number: Optional[int] = None
    total_phases: int = 3


class MissionUpdateIn(BaseModel):
    title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_hotspot_count: Optional[int] = None


class JournalIn(BaseModel):
    date: Optional[datetime.date] = None
    accomplished: str = ""
    challenges: str = ""
    learned: str = ""
    improve_tomorrow: str = ""


class JournalOut(BaseModel):
    id: int
    date: date
    accomplished: str
    challenges: str
    learned: str
    improve_tomorrow: str

    class Config:
        from_attributes = True


class MilestoneIn(BaseModel):
    milestone_date: date
    title: str
    notes: str = ""


class MilestoneOut(BaseModel):
    id: int
    milestone_date: date
    title: str
    notes: str

    class Config:
        from_attributes = True


class ExecutionScoreOut(BaseModel):
    date: date
    score: float
    breakdown: dict
    suggestions: List[str]


# ----------------------------------------------------------------------------
# Pydantic schemas — Todos / Daily Score / Chat
# ----------------------------------------------------------------------------

class TodoIn(BaseModel):
    title: str
    notes: str = ""
    priority: str = "medium"
    business_id: Optional[int] = None
    due_date: Optional[date] = None

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v):
        return v if v in ("low", "medium", "high") else "medium"


class TodoUpdateIn(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None
    business_id: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v):
        if v is not None and v not in ("low", "medium", "high"):
            raise ValueError("priority must be one of: low, medium, high")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v):
        if v is not None and v not in ("pending", "in_progress", "completed", "abandoned"):
            raise ValueError("status must be one of: pending, in_progress, completed, abandoned")
        return v


class TodoOut(BaseModel):
    id: int
    title: str
    notes: str
    priority: str
    business_id: Optional[int]
    due_date: Optional[date]
    status: str
    ai_feedback: str
    created_at: dt
    completed_at: Optional[dt]

    class Config:
        from_attributes = True


class DailyScoreOut(BaseModel):
    date: date
    score: float
    tasks_total: int
    tasks_completed: int
    breakdown: dict


class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str


class ChatHistoryOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: dt

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------

app = FastAPI(title="Business Growth Tracker AI API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "time": utcnow().isoformat()}


# ----------------------------------------------------------------------------
# Auth endpoints
# ----------------------------------------------------------------------------

@app.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    digest, salt = hash_password(body.password)
    user = User(
        full_name=body.full_name.strip(),
        email=body.email.lower(),
        password_hash=digest,
        password_salt=salt,
        currency=body.currency,
        mission_start_date=date.today(),
        mission_end_date=date.today() + timedelta(days=730),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@app.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash, user.password_salt):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@app.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@app.put("/me", response_model=UserOut)
def update_me(body: MeUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name:
        user.full_name = body.full_name.strip()
    if body.currency:
        user.currency = body.currency if body.currency in CURRENCIES else user.currency
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        digest, salt = hash_password(body.password)
        user.password_hash, user.password_salt = digest, salt
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


# ----------------------------------------------------------------------------
# Businesses
# ----------------------------------------------------------------------------

def _get_owned_business(db, user, biz_id):
    biz = db.query(Business).filter(Business.id == biz_id, Business.user_id == user.id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found.")
    return biz


@app.get("/businesses", response_model=List[BusinessOut])
def list_businesses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Business).filter(Business.user_id == user.id).order_by(Business.created_at.desc()).all()


@app.post("/businesses", response_model=BusinessOut)
def create_business(body: BusinessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    biz = Business(
        user_id=user.id, name=body.name.strip(), category=body.category or "General",
        start_date=body.start_date or date.today(), description=body.description or "",
    )
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


@app.put("/businesses/{biz_id}", response_model=BusinessOut)
def update_business(biz_id: int, body: BusinessUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    biz = _get_owned_business(db, user, biz_id)
    for field in ("name", "category", "status", "description", "start_date"):
        val = getattr(body, field)
        if val is not None:
            setattr(biz, field, val)
    db.commit()
    db.refresh(biz)
    return biz


@app.delete("/businesses/{biz_id}")
def delete_business(biz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    biz = _get_owned_business(db, user, biz_id)
    db.query(Transaction).filter(Transaction.business_id == biz_id, Transaction.user_id == user.id).delete()
    db.delete(biz)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Transactions
# ----------------------------------------------------------------------------

@app.get("/transactions", response_model=List[TransactionOut])
def list_transactions(
    business_id: Optional[int] = None,
    type: Optional[str] = None,
    limit: int = Query(150, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)
    if business_id:
        q = q.filter(Transaction.business_id == business_id)
    if type:
        q = q.filter(Transaction.type == type)
    return q.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).all()


@app.post("/transactions", response_model=TransactionOut)
def create_transaction(body: TransactionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_business(db, user, body.business_id)
    tx = Transaction(
        user_id=user.id, business_id=body.business_id, type=body.type, amount=body.amount,
        category=body.category or "Other", description=body.description or "",
        date=body.date or date.today(),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@app.put("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, body: TransactionUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user.id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    for field in ("type", "amount", "category", "description", "date"):
        val = getattr(body, field)
        if val is not None:
            setattr(tx, field, val)
    db.commit()
    db.refresh(tx)
    return tx


@app.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user.id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    db.delete(tx)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Savings
# ----------------------------------------------------------------------------

@app.get("/savings", response_model=List[SavingsOut])
def list_savings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Savings).filter(Savings.user_id == user.id).order_by(Savings.date.asc(), Savings.id.asc()).all()


@app.post("/savings", response_model=SavingsOut)
def create_savings(body: SavingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pct = max(0.0, min(100.0, body.percentage))
    amount_saved = body.profit_amount * (pct / 100.0)
    remaining_cash = body.profit_amount - amount_saved
    prev_balance = db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(Savings.user_id == user.id).scalar()
    balance_after = float(prev_balance) + amount_saved
    rec = Savings(
        user_id=user.id, date=body.date or date.today(), profit_amount=body.profit_amount,
        percentage=pct, amount_saved=amount_saved, remaining_cash=remaining_cash,
        balance_after=balance_after, note=body.note or "",
    )
    db.add(rec)
    db.add(Notification(user_id=user.id, kind="success", message=f"Saved {amount_saved:,.0f} — balance now {balance_after:,.0f}."))
    db.commit()
    db.refresh(rec)
    return rec


# ----------------------------------------------------------------------------
# Hotspots
# ----------------------------------------------------------------------------

def _hotspot_metrics(h: Hotspot):
    monthly_revenue = h.daily_average_revenue * 30
    monthly_profit = monthly_revenue - h.monthly_data_cost - h.monthly_electricity_cost
    roi_percent = (monthly_profit * 12 / h.installation_cost * 100) if h.installation_cost else 0.0
    payback_months = (h.installation_cost / monthly_profit) if monthly_profit > 0 else None
    return monthly_revenue, monthly_profit, roi_percent, payback_months


@app.get("/hotspots", response_model=List[HotspotOut])
def list_hotspots(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Hotspot).filter(Hotspot.user_id == user.id).order_by(Hotspot.created_at.desc()).all()
    out = []
    for h in rows:
        mr, mp, roi, payback = _hotspot_metrics(h)
        out.append(HotspotOut(
            id=h.id, location=h.location, installation_cost=h.installation_cost,
            installation_date=h.installation_date, monthly_revenue=mr, monthly_profit=mp,
            roi_percent=roi, payback_months=payback, status=h.status,
        ))
    return out


@app.get("/hotspots/projection", response_model=HotspotProjectionOut)
def hotspot_projection(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current = db.query(Hotspot).filter(Hotspot.user_id == user.id, Hotspot.status == "active").count()
    target = user.target_hotspot_count or 7
    growth_per_half_year = 0.15
    completion_percent = round(min(100.0, (current / target * 100) if target else 0), 1)

    # Days until affordable next hotspot, estimated from average monthly net profit
    # vs the average cost of an existing hotspot (a proxy "next hotspot budget").
    days_until_target = None
    hotspots = db.query(Hotspot).filter(Hotspot.user_id == user.id).all()
    if hotspots and current < target:
        avg_cost = sum(h.installation_cost for h in hotspots) / len(hotspots)
        today = date.today()
        month_start = today.replace(day=1)
        monthly_profit = _tx_sum(db, user, "revenue", month_start, today) - _tx_sum(db, user, "expense", month_start, today)
        daily_savings_rate = max(monthly_profit, 0) / 30 * 0.3  # assume 30% of profit reinvested
        if daily_savings_rate > 0 and avg_cost > 0:
            days_until_target = int(round(avg_cost / daily_savings_rate))

    return HotspotProjectionOut(
        current=current,
        target=target,
        completion_percent=completion_percent,
        projection_6_months=round(current * (1 + growth_per_half_year)),
        projection_1_year=round(current * (1 + growth_per_half_year) ** 2),
        projection_2_years=round(current * (1 + growth_per_half_year) ** 4),
        days_until_target=days_until_target,
    )


@app.post("/hotspots", response_model=HotspotOut)
def create_hotspot(body: HotspotIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.business_id:
        _get_owned_business(db, user, body.business_id)
    h = Hotspot(
        user_id=user.id, business_id=body.business_id, location=body.location.strip(),
        installation_cost=body.installation_cost, installation_date=body.installation_date or date.today(),
        monthly_data_cost=body.monthly_data_cost, monthly_electricity_cost=body.monthly_electricity_cost,
        daily_average_revenue=body.daily_average_revenue,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    mr, mp, roi, payback = _hotspot_metrics(h)
    return HotspotOut(
        id=h.id, location=h.location, installation_cost=h.installation_cost,
        installation_date=h.installation_date, monthly_revenue=mr, monthly_profit=mp,
        roi_percent=roi, payback_months=payback, status=h.status,
    )


@app.delete("/hotspots/{hotspot_id}")
def delete_hotspot(hotspot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.query(Hotspot).filter(Hotspot.id == hotspot_id, Hotspot.user_id == user.id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Hotspot not found.")
    db.delete(h)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Investments
# ----------------------------------------------------------------------------

@app.get("/investments", response_model=List[InvestmentOut])
def list_investments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Investment).filter(Investment.user_id == user.id).order_by(Investment.purchase_date.desc()).all()


@app.post("/investments", response_model=InvestmentOut)
def create_investment(body: InvestmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.business_id:
        _get_owned_business(db, user, body.business_id)
    inv = Investment(
        user_id=user.id, business_id=body.business_id, name=body.name.strip(), cost=body.cost,
        purchase_date=body.purchase_date or date.today(), notes=body.notes or "",
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@app.delete("/investments/{inv_id}")
def delete_investment(inv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.query(Investment).filter(Investment.id == inv_id, Investment.user_id == user.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Investment not found.")
    db.delete(inv)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Assets
# ----------------------------------------------------------------------------

@app.get("/assets", response_model=List[AssetOut])
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Asset).filter(Asset.user_id == user.id).order_by(Asset.purchase_date.desc()).all()


@app.post("/assets", response_model=AssetOut)
def create_asset(body: AssetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = Asset(
        user_id=user.id, name=body.name.strip(), purchase_price=body.purchase_price,
        current_value=body.current_value, purchase_date=body.purchase_date or date.today(),
        notes=body.notes or "",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found.")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Goals — with estimated completion date + status
#
# NOTE: update_goal / delete_goal below both filter strictly on
# (Goal.id == goal_id, Goal.user_id == user.id). If a goal fails to update
# or delete from the UI, it is almost always because the goal_id being sent
# no longer matches a row owned by the logged-in user (stale client-side
# cache) — the routes themselves accept partial updates and always commit.
# Both endpoints below now also return a clear 404 message and the update
# endpoint accepts every editable field, including status transitions.
# ----------------------------------------------------------------------------

def _estimate_goal_completion(db: Session, user: User, g: Goal) -> Optional[date]:
    """Rough estimate based on the account's recent average monthly net profit,
    assuming a portion of it flows toward open goals. This is a heuristic,
    not a guarantee — it gives the user a directional target date."""
    if g.status != "active" or g.target_amount <= 0:
        return None
    remaining = g.target_amount - g.current_amount
    if remaining <= 0:
        return date.today()
    today = date.today()
    three_months_ago = today - timedelta(days=90)
    profit_90d = _tx_sum(db, user, "revenue", three_months_ago, today) - _tx_sum(db, user, "expense", three_months_ago, today)
    monthly_profit = profit_90d / 3
    monthly_contribution = max(monthly_profit, 0) * 0.25  # assume 25% of profit toward goals
    if monthly_contribution <= 0:
        return None
    months_needed = remaining / monthly_contribution
    if months_needed > 600:  # cap absurd estimates (50 years)
        return None
    return today + timedelta(days=int(round(months_needed * 30.44)))


def _goal_out(db: Session, user: User, g: Goal) -> GoalOut:
    pct = min(100.0, round((g.current_amount / g.target_amount * 100), 1)) if g.target_amount else 0.0
    remaining = max(0.0, g.target_amount - g.current_amount)
    est = _estimate_goal_completion(db, user, g)
    return GoalOut(
        id=g.id, name=g.name, target_amount=g.target_amount, current_amount=g.current_amount,
        deadline=g.deadline, status=g.status, progress_percent=pct, amount_remaining=remaining,
        estimated_completion_date=est,
    )


@app.get("/goals", response_model=List[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at.desc()).all()
    return [_goal_out(db, user, g) for g in rows]


@app.post("/goals", response_model=GoalOut)
def create_goal(body: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = Goal(
        user_id=user.id, name=body.name.strip(), target_amount=body.target_amount,
        current_amount=body.current_amount, deadline=body.deadline,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_out(db, user, g)


@app.get("/goals/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found for this account.")
    return _goal_out(db, user, g)


@app.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found for this account.")
    if body.name is not None:
        name = body.name.strip()
        if name:
            g.name = name
    if body.target_amount is not None:
        if body.target_amount <= 0:
            raise HTTPException(status_code=400, detail="Target amount must be greater than zero.")
        g.target_amount = body.target_amount
    if body.deadline is not None:
        g.deadline = body.deadline
    if body.current_amount is not None:
        g.current_amount = max(0.0, body.current_amount)
    if body.status is not None:
        g.status = body.status
    # Auto-complete when the target is reached, unless the user explicitly
    # set a different status in this same request.
    if g.target_amount and g.current_amount >= g.target_amount and g.status == "active" and body.status is None:
        g.status = "completed"
        db.add(Notification(user_id=user.id, kind="success", message=f"Goal '{g.name}' reached! \U0001F389"))
    db.commit()
    db.refresh(g)
    return _goal_out(db, user, g)


@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found for this account.")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Mission Control
# ----------------------------------------------------------------------------

def _phase_for(pct: float):
    if pct < 33.4:
        return "Phase 1 — Foundation", 1
    if pct < 66.7:
        return "Phase 2 — Growth", 2
    return "Phase 3 — Freedom", 3


@app.get("/mission", response_model=MissionOut)
def get_mission(user: User = Depends(get_current_user)):
    start, end = user.mission_start_date, user.mission_end_date
    if not start or not end or end <= start:
        return MissionOut(title=user.mission_title, start_date=start, end_date=end)
    today = date.today()
    total_days = (end - start).days
    days_completed = max(0, min(total_days, (today - start).days))
    days_remaining = max(0, (end - today).days)
    pct = round(min(100.0, max(0.0, days_completed / total_days * 100)), 1) if total_days else 0.0
    phase_name, phase_num = _phase_for(pct)
    return MissionOut(
        title=user.mission_title, start_date=start, end_date=end, total_days=total_days,
        days_completed=days_completed, days_remaining=days_remaining, percent_complete=pct,
        current_phase=phase_name, phase_number=phase_num,
    )


@app.put("/mission", response_model=MissionOut)
def update_mission(body: MissionUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.title is not None:
        user.mission_title = body.title.strip()
    if body.start_date is not None:
        user.mission_start_date = body.start_date
    if body.end_date is not None:
        user.mission_end_date = body.end_date
    if body.target_hotspot_count is not None:
        user.target_hotspot_count = max(1, body.target_hotspot_count)
    db.commit()
    db.refresh(user)
    return get_mission(user)


# ----------------------------------------------------------------------------
# Daily Journal
# ----------------------------------------------------------------------------

@app.get("/journal", response_model=List[JournalOut])
def list_journal(limit: int = Query(60, le=500), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(JournalEntry).filter(JournalEntry.user_id == user.id).order_by(JournalEntry.date.desc()).limit(limit).all()


@app.get("/journal/search", response_model=List[JournalOut])
def search_journal(q: str = Query(..., min_length=1), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    like = f"%{q}%"
    rows = db.query(JournalEntry).filter(
        JournalEntry.user_id == user.id,
        (JournalEntry.accomplished.ilike(like)) |
        (JournalEntry.challenges.ilike(like)) |
        (JournalEntry.learned.ilike(like)) |
        (JournalEntry.improve_tomorrow.ilike(like)),
    ).order_by(JournalEntry.date.desc()).limit(100).all()
    return rows


@app.post("/journal", response_model=JournalOut)
def create_journal(body: JournalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry_date = body.date or date.today()
    existing = db.query(JournalEntry).filter(JournalEntry.user_id == user.id, JournalEntry.date == entry_date).first()
    if existing:
        existing.accomplished = body.accomplished
        existing.challenges = body.challenges
        existing.learned = body.learned
        existing.improve_tomorrow = body.improve_tomorrow
        db.commit()
        db.refresh(existing)
        return existing
    entry = JournalEntry(
        user_id=user.id, date=entry_date, accomplished=body.accomplished, challenges=body.challenges,
        learned=body.learned, improve_tomorrow=body.improve_tomorrow,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.put("/journal/{entry_id}", response_model=JournalOut)
def update_journal(entry_id: int, body: JournalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id, JournalEntry.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found.")
    entry.accomplished = body.accomplished
    entry.challenges = body.challenges
    entry.learned = body.learned
    entry.improve_tomorrow = body.improve_tomorrow
    if body.date:
        entry.date = body.date
    db.commit()
    db.refresh(entry)
    return entry


@app.delete("/journal/{entry_id}")
def delete_journal(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id, JournalEntry.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found.")
    db.delete(entry)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Timeline / Milestones
# ----------------------------------------------------------------------------

@app.get("/timeline", response_model=List[MilestoneOut])
def list_timeline(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Milestone).filter(Milestone.user_id == user.id).order_by(Milestone.milestone_date.asc()).all()


@app.post("/timeline", response_model=MilestoneOut)
def create_milestone(body: MilestoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = Milestone(user_id=user.id, milestone_date=body.milestone_date, title=body.title.strip(), notes=body.notes or "")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@app.delete("/timeline/{milestone_id}")
def delete_milestone(milestone_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Milestone).filter(Milestone.id == milestone_id, Milestone.user_id == user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found.")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Todos — tasks the daily score is graded against
# ----------------------------------------------------------------------------

def _todo_out(t: Todo) -> TodoOut:
    return TodoOut(
        id=t.id, title=t.title, notes=t.notes, priority=t.priority, business_id=t.business_id,
        due_date=t.due_date, status=t.status, ai_feedback=t.ai_feedback or "",
        created_at=t.created_at, completed_at=t.completed_at,
    )


@app.get("/todos", response_model=List[TodoOut])
def list_todos(
    due_date: Optional[date] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    business_id: Optional[int] = None,
    limit: int = Query(200, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Todo).filter(Todo.user_id == user.id)
    if due_date:
        q = q.filter(Todo.due_date == due_date)
    if status_filter:
        q = q.filter(Todo.status == status_filter)
    if business_id:
        q = q.filter(Todo.business_id == business_id)
    rows = q.order_by(Todo.due_date.asc(), Todo.created_at.desc()).limit(limit).all()
    return [_todo_out(t) for t in rows]


def _generate_todo_feedback(db: Session, user: User, t: Todo) -> str:
    """Short, immediate AI-style feedback on a single newly-created task,
    using Gemini (with full account context) if available, else a
    rule-based heuristic."""
    if GEMINI_API_KEY:
        snapshot = _build_full_system_snapshot(db, user, light=False)
        prompt = (
            "You are a business task coach. A user just added this task to their todo list: "
            + json.dumps({"title": t.title, "notes": t.notes, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None})
            + ". Here is the user's full current business/account data for context: "
            + json.dumps(snapshot, default=str)
            + ". Respond with ONE short sentence (max 25 words) of direct, useful feedback or "
              "advice on this specific task — no preamble, no markdown, plain text only."
        )
        text = _call_gemini(prompt, context="todo_feedback")
        if text:
            return text.strip().strip('"')
    # Rule-based fallback
    title_lower = t.title.lower()
    if t.priority == "high":
        return "Marked high priority — tackle this first today before anything else slips."
    if any(k in title_lower for k in ("call", "follow up", "follow-up", "meet", "visit")):
        return "A people-facing task — do it earlier in the day while energy and availability are highest."
    if any(k in title_lower for k in ("pay", "invoice", "expense", "record", "log")):
        return "A record-keeping task — small but it keeps your numbers accurate, don't let it slide."
    return "Added to today's list — break it down further if it feels too big to start."


@app.post("/todos", response_model=TodoOut)
def create_todo(body: TodoIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.business_id:
        _get_owned_business(db, user, body.business_id)
    t = Todo(
        user_id=user.id, title=body.title.strip(), notes=body.notes or "", priority=body.priority,
        business_id=body.business_id, due_date=body.due_date or date.today(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    try:
        t.ai_feedback = _generate_todo_feedback(db, user, t)
        db.commit()
        db.refresh(t)
    except Exception:
        pass
    return _todo_out(t)


@app.put("/todos/{todo_id}", response_model=TodoOut)
def update_todo(todo_id: int, body: TodoUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    if body.title is not None:
        t.title = body.title.strip()
    if body.notes is not None:
        t.notes = body.notes
    if body.priority is not None:
        t.priority = body.priority
    if body.business_id is not None:
        if body.business_id:
            _get_owned_business(db, user, body.business_id)
        t.business_id = body.business_id
    if body.due_date is not None:
        t.due_date = body.due_date
    if body.status is not None:
        was_completed = t.status == "completed"
        t.status = body.status
        if t.status == "completed" and not was_completed:
            t.completed_at = utcnow()
        elif t.status != "completed":
            t.completed_at = None
    db.commit()
    db.refresh(t)
    return _todo_out(t)


@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user.id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    db.delete(t)
    db.commit()
    return {"ok": True}


@app.get("/ai/todo-feedback")
def ai_todo_feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Feedback and advice across the user's current open task list."""
    today = date.today()
    open_todos = db.query(Todo).filter(
        Todo.user_id == user.id, Todo.status.in_(["pending", "in_progress"]), Todo.due_date <= today
    ).order_by(Todo.due_date.asc()).all()

    if not open_todos:
        return {"feedback": ["You have no open tasks — add today's tasks so the AI can help you plan and score the day."]}

    if GEMINI_API_KEY:
        snapshot = _build_full_system_snapshot(db, user, light=False)
        payload = {
            "open_tasks": [
                {"title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat(), "status": t.status}
                for t in open_todos
            ],
            "full_account_context": snapshot,
        }
        prompt = (
            "You are a task-management coach for a busy entrepreneur. Given their open task list "
            "and their full current business/account data, respond ONLY with a JSON array of 3-5 "
            "short, specific feedback/advice strings about how they're managing their tasks — flag "
            "overdue items, too many high-priority items, tasks with no clear next step, or good "
            "patterns to keep. No preamble, no markdown fences.\n\n" + json.dumps(payload, default=str)
        )
        text = _call_gemini(prompt, context="todo_list_feedback")
        parsed = _parse_json_array(text) if text else None
        if parsed and all(isinstance(x, str) for x in parsed):
            return {"feedback": parsed}

    # Rule-based fallback
    fb = []
    overdue = [t for t in open_todos if t.due_date < today]
    if overdue:
        fb.append(f"You have {len(overdue)} overdue task(s) — clear or reschedule them before adding new ones.")
    high = [t for t in open_todos if t.priority == "high"]
    if len(high) > 3:
        fb.append(f"{len(high)} tasks are marked high priority — that's too many to truly prioritize. Pick your top 1-3 for today.")
    if len(open_todos) > 10:
        fb.append("Your open task list is long. Consider batching or delegating the smaller ones.")
    if not fb:
        fb.append("Your task list looks manageable — good pace, keep completing them as you go.")
    return {"feedback": fb}


# ----------------------------------------------------------------------------
# Daily Execution Score (auto-computed from real data, including task
# completion) — no manual checklist required.
# ----------------------------------------------------------------------------

def _compute_execution_score(db: Session, user: User, on_date: date):
    breakdown = {}
    today = on_date
    week_start = today - timedelta(days=today.weekday())

    rev_today = _tx_sum(db, user, "revenue", today, today)
    exp_today = _tx_sum(db, user, "expense", today, today)
    breakdown["revenue_recorded"] = rev_today > 0
    breakdown["expenses_recorded"] = exp_today > 0

    savings_this_week = db.query(Savings).filter(Savings.user_id == user.id, Savings.date >= week_start, Savings.date <= today).count()
    breakdown["savings_updated"] = savings_this_week > 0

    journal_today = db.query(JournalEntry).filter(JournalEntry.user_id == user.id, JournalEntry.date == today).first()
    breakdown["journal_completed"] = bool(journal_today)

    active_businesses = db.query(Business).filter(Business.user_id == user.id, Business.status == "active").all()
    three_days_ago = today - timedelta(days=3)
    engaged = 0
    for b in active_businesses:
        has_tx = db.query(Transaction).filter(
            Transaction.business_id == b.id, Transaction.user_id == user.id,
            Transaction.date >= three_days_ago, Transaction.date <= today,
        ).first()
        if has_tx:
            engaged += 1
    breakdown["businesses_updated"] = f"{engaged}/{len(active_businesses)}" if active_businesses else "0/0"
    business_engagement_ratio = (engaged / len(active_businesses)) if active_businesses else 1.0

    # Task completion for the day — tasks due today only.
    tasks_due_today = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date == today).all()
    tasks_total = len(tasks_due_today)
    tasks_completed = len([t for t in tasks_due_today if t.status == "completed"])
    task_ratio = (tasks_completed / tasks_total) if tasks_total else 1.0
    breakdown["tasks_completed"] = f"{tasks_completed}/{tasks_total}" if tasks_total else "0/0"

    weights = {
        "revenue_recorded": 15,
        "expenses_recorded": 10,
        "savings_updated": 10,
        "journal_completed": 15,
        "business_engagement": 20,
        "tasks_completed": 30,
    }
    score = 0.0
    score += weights["revenue_recorded"] if breakdown["revenue_recorded"] else 0
    score += weights["expenses_recorded"] if breakdown["expenses_recorded"] else 0
    score += weights["savings_updated"] if breakdown["savings_updated"] else 0
    score += weights["journal_completed"] if breakdown["journal_completed"] else 0
    score += weights["business_engagement"] * business_engagement_ratio
    score += weights["tasks_completed"] * task_ratio
    score = round(min(100.0, score), 1)

    suggestions = []
    if tasks_total and tasks_completed < tasks_total:
        suggestions.append(f"You've completed {tasks_completed} of {tasks_total} tasks due today — finish the rest before the day ends.")
    if not tasks_total:
        suggestions.append("You have no tasks scheduled for today — add a few in the Todo list so progress is trackable.")
    if not breakdown["revenue_recorded"]:
        suggestions.append("Log today's revenue, even if it's small — consistency matters more than size.")
    if not breakdown["expenses_recorded"]:
        suggestions.append("Record any expenses from today so tomorrow's profit numbers stay accurate.")
    if not breakdown["savings_updated"]:
        suggestions.append("Set aside a percentage of this week's profit into savings.")
    if not breakdown["journal_completed"]:
        suggestions.append("Write a quick journal entry — what you did, learned, and will improve.")
    if business_engagement_ratio < 1.0:
        suggestions.append("Touch base with every active business at least every few days, even briefly.")
    if not suggestions:
        suggestions.append("Great work today — keep the same routine tomorrow.")

    return score, breakdown, suggestions, tasks_total, tasks_completed


@app.get("/execution-score/today", response_model=ExecutionScoreOut)
def execution_score_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    score, breakdown, suggestions, tasks_total, tasks_completed = _compute_execution_score(db, user, today)

    existing = db.query(ExecutionScore).filter(ExecutionScore.user_id == user.id, ExecutionScore.date == today).first()
    if existing:
        existing.score = score
        existing.breakdown_json = json.dumps(breakdown)
    else:
        db.add(ExecutionScore(user_id=user.id, date=today, score=score, breakdown_json=json.dumps(breakdown)))

    # Persist the permanent daily-score record too, so history survives even
    # if ExecutionScore rows are ever pruned.
    existing_daily = db.query(DailyScore).filter(DailyScore.user_id == user.id, DailyScore.date == today).first()
    if existing_daily:
        existing_daily.score = score
        existing_daily.tasks_total = tasks_total
        existing_daily.tasks_completed = tasks_completed
        existing_daily.breakdown_json = json.dumps(breakdown)
    else:
        db.add(DailyScore(
            user_id=user.id, date=today, score=score, tasks_total=tasks_total,
            tasks_completed=tasks_completed, breakdown_json=json.dumps(breakdown),
        ))
    db.commit()

    return ExecutionScoreOut(date=today, score=score, breakdown=breakdown, suggestions=suggestions)


@app.get("/execution-score/history")
def execution_score_history(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start = date.today() - timedelta(days=days - 1)
    rows = db.query(ExecutionScore).filter(ExecutionScore.user_id == user.id, ExecutionScore.date >= start).order_by(ExecutionScore.date.asc()).all()
    return [{"date": r.date.isoformat(), "score": r.score} for r in rows]


@app.get("/daily-scores", response_model=List[DailyScoreOut])
def list_daily_scores(days: int = Query(60, le=1000), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanent historical record of daily scores and task completion."""
    start = date.today() - timedelta(days=days - 1)
    rows = db.query(DailyScore).filter(DailyScore.user_id == user.id, DailyScore.date >= start).order_by(DailyScore.date.desc()).all()
    out = []
    for r in rows:
        try:
            breakdown = json.loads(r.breakdown_json or "{}")
        except Exception:
            breakdown = {}
        out.append(DailyScoreOut(
            date=r.date, score=r.score, tasks_total=r.tasks_total,
            tasks_completed=r.tasks_completed, breakdown=breakdown,
        ))
    return out


# ----------------------------------------------------------------------------
# Business Empire — full per-business rollup
# ----------------------------------------------------------------------------

def _sum_business_tx(db, user, business_id, type_, start, end):
    q = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user.id, Transaction.business_id == business_id,
        Transaction.type == type_, Transaction.date >= start, Transaction.date <= end,
    )
    return float(q.scalar() or 0.0)


@app.get("/business-empire")
def business_empire(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    inception = date(2000, 1, 1)

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    out = []
    for b in businesses:
        revenue_all = _sum_business_tx(db, user, b.id, "revenue", inception, today)
        expense_all = _sum_business_tx(db, user, b.id, "expense", inception, today)
        profit_all = revenue_all - expense_all

        profit_this_month = (_sum_business_tx(db, user, b.id, "revenue", month_start, today)
                              - _sum_business_tx(db, user, b.id, "expense", month_start, today))
        profit_last_month = (_sum_business_tx(db, user, b.id, "revenue", last_month_start, last_month_end)
                              - _sum_business_tx(db, user, b.id, "expense", last_month_start, last_month_end))
        growth = (round((profit_this_month - profit_last_month) / abs(profit_last_month) * 100, 1)
                  if profit_last_month else (100.0 if profit_this_month > 0 else 0.0))

        investment_total = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(
            Investment.user_id == user.id, Investment.business_id == b.id).scalar() or 0.0)
        hotspot_cost_total = float(db.query(func.coalesce(func.sum(Hotspot.installation_cost), 0.0)).filter(
            Hotspot.user_id == user.id, Hotspot.business_id == b.id).scalar() or 0.0)
        total_invested = investment_total + hotspot_cost_total
        roi = round(profit_all / total_invested * 100, 1) if total_invested else None

        last_activity = db.query(func.max(Transaction.date)).filter(
            Transaction.user_id == user.id, Transaction.business_id == b.id).scalar()
        days_inactive = (today - last_activity).days if last_activity else None

        out.append({
            "id": b.id, "name": b.name, "category": b.category, "status": b.status,
            "revenue": revenue_all, "expenses": expense_all, "profit": profit_all,
            "growth_percent": growth, "investment": total_invested, "roi_percent": roi,
            "days_inactive": days_inactive,
        })
    out.sort(key=lambda x: x["profit"], reverse=True)
    return out


@app.get("/income-distribution")
def income_distribution(days: int = 90, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=days - 1)
    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    rows = []
    total_revenue = 0.0
    for b in businesses:
        rev = _sum_business_tx(db, user, b.id, "revenue", start, today)
        rows.append({"name": b.name, "revenue": rev})
        total_revenue += rev
    for r in rows:
        r["percent"] = round(r["revenue"] / total_revenue * 100, 1) if total_revenue else 0.0
    rows.sort(key=lambda x: x["revenue"], reverse=True)
    return {"period_days": days, "total_revenue": total_revenue, "businesses": rows}


# ----------------------------------------------------------------------------
# Notifications — Smart Notifications engine
# ----------------------------------------------------------------------------

@app.get("/notifications", response_model=List[NotificationOut])
def list_notifications(unread_only: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    return q.order_by(Notification.created_at.desc()).limit(50).all()


@app.put("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == user.id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found.")
    n.is_read = True
    db.commit()
    return {"ok": True}


def _recent_notification_exists(db, user, fragment: str, within_days: int = 1) -> bool:
    since = utcnow() - timedelta(days=within_days)
    return db.query(Notification).filter(
        Notification.user_id == user.id, Notification.created_at >= since,
        Notification.message.ilike(f"%{fragment}%"),
    ).first() is not None


@app.post("/notifications/check")
def run_smart_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs all smart-notification rules and creates any new notifications.
    Safe to call on every login / dashboard load — de-duplicates same-day alerts."""
    created = []
    today = date.today()

    # Daily entry missing (no transactions logged today, and it's afternoon-or-later in spirit)
    if _tx_sum(db, user, "revenue", today, today) == 0 and _tx_sum(db, user, "expense", today, today) == 0:
        if not _recent_notification_exists(db, user, "haven't logged anything today"):
            msg = "You haven't logged anything today — record at least one transaction before the day ends."
            db.add(Notification(user_id=user.id, kind="warning", message=msg))
            created.append(msg)

    # Tasks due today not yet completed, flagged in the afternoon-equivalent check
    open_tasks_today = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date == today, Todo.status.in_(["pending", "in_progress"])).count()
    if open_tasks_today > 0 and not _recent_notification_exists(db, user, "task(s) due today still open"):
        msg = f"You have {open_tasks_today} task(s) due today still open — check your Todo list."
        db.add(Notification(user_id=user.id, kind="warning", message=msg))
        created.append(msg)

    # Weekly review due (Sunday)
    if today.weekday() == 6 and not _recent_notification_exists(db, user, "Weekly review is ready"):
        msg = "Weekly review is ready — check your Reports page for this week's summary."
        db.add(Notification(user_id=user.id, kind="info", message=msg))
        created.append(msg)

    # Monthly review due (1st of month)
    if today.day == 1 and not _recent_notification_exists(db, user, "Monthly review is ready"):
        msg = "Monthly review is ready — see how last month compared."
        db.add(Notification(user_id=user.id, kind="info", message=msg))
        created.append(msg)

    # Business inactive (no transactions in 14+ days)
    businesses = db.query(Business).filter(Business.user_id == user.id, Business.status == "active").all()
    for b in businesses:
        last = db.query(func.max(Transaction.date)).filter(Transaction.business_id == b.id, Transaction.user_id == user.id).scalar()
        if last and (today - last).days >= 14:
            frag = f"{b.name}' has not"
            if not _recent_notification_exists(db, user, frag, within_days=7):
                msg = f"'{b.name}' has not had any activity in {(today - last).days} days — check in on it."
                db.add(Notification(user_id=user.id, kind="warning", message=msg))
                created.append(msg)

    # New hotspot affordable
    try:
        proj = hotspot_projection(user=user, db=db)
        if proj.days_until_target is not None and proj.days_until_target <= 3 and proj.current < proj.target:
            frag = "afford another hotspot"
            if not _recent_notification_exists(db, user, frag, within_days=3):
                msg = f"You can afford another hotspot in about {proj.days_until_target} day(s) at your current savings rate."
                db.add(Notification(user_id=user.id, kind="success", message=msg))
                created.append(msg)
    except Exception:
        pass

    # Savings target reached — proxy: savings balance crossed a round number milestone
    balance = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(Savings.user_id == user.id).scalar() or 0.0)
    milestone = 1_000_000
    if balance >= milestone:
        crossed = int(balance // milestone) * milestone
        frag = f"savings balance passed {crossed:,.0f}"
        if not _recent_notification_exists(db, user, frag, within_days=9999):
            msg = f"Your savings balance passed {crossed:,.0f} {user.currency} — a real milestone."
            db.add(Notification(user_id=user.id, kind="success", message=msg))
            created.append(msg)

    db.commit()
    return {"created": created}


# ----------------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------------

def _tx_sum(db, user, type_, start=None, end=None):
    q = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user.id, Transaction.type == type_
    )
    if start:
        q = q.filter(Transaction.date >= start)
    if end:
        q = q.filter(Transaction.date <= end)
    return float(q.scalar() or 0.0)


@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    today_revenue = _tx_sum(db, user, "revenue", today, today)
    today_expense = _tx_sum(db, user, "expense", today, today)
    monthly_revenue = _tx_sum(db, user, "revenue", month_start, today)
    monthly_expense = _tx_sum(db, user, "expense", month_start, today)
    monthly_profit = monthly_revenue - monthly_expense

    last_month_revenue = _tx_sum(db, user, "revenue", last_month_start, last_month_end)
    last_month_expense = _tx_sum(db, user, "expense", last_month_start, last_month_end)
    last_month_profit = last_month_revenue - last_month_expense
    monthly_growth_percent = (
        round((monthly_profit - last_month_profit) / abs(last_month_profit) * 100, 1)
        if last_month_profit else (100.0 if monthly_profit > 0 else 0.0)
    )

    savings_balance = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(Savings.user_id == user.id).scalar() or 0.0)
    total_investments = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(Investment.user_id == user.id).scalar() or 0.0)
    total_assets = float(db.query(func.coalesce(func.sum(Asset.current_value), 0.0)).filter(Asset.user_id == user.id).scalar() or 0.0)
    net_worth = savings_balance + total_assets + total_investments

    business_count = db.query(Business).filter(Business.user_id == user.id).count()
    active_goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").count()

    quote = MOTIVATION_QUOTES[today.toordinal() % len(MOTIVATION_QUOTES)]
    priorities = [
        "Record every transaction, revenue and expense.",
        "Move one business forward, however small.",
        "Save consistently from today's profit.",
        "Write tonight's journal entry before you stop working.",
    ]

    return {
        "today_revenue": today_revenue,
        "today_profit": today_revenue - today_expense,
        "monthly_revenue": monthly_revenue,
        "monthly_profit": monthly_profit,
        "monthly_growth_percent": monthly_growth_percent,
        "savings_balance": savings_balance,
        "total_investments": total_investments,
        "total_assets": total_assets,
        "net_worth": net_worth,
        "business_count": business_count,
        "active_goals": active_goals,
        "motivation_quote": quote,
        "todays_priorities": priorities,
        "mission_objective": "Build Financial Freedom",
    }


@app.get("/dashboard/charts")
def dashboard_charts(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=days - 1)
    labels, revenue, expense, profit = [], [], [], []

    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= today
    ).all()
    by_day = {}
    for t in txs:
        d = by_day.setdefault(t.date, {"revenue": 0.0, "expense": 0.0})
        d[t.type] += t.amount

    cur = start
    while cur <= today:
        labels.append(cur.isoformat())
        rev = by_day.get(cur, {}).get("revenue", 0.0)
        exp = by_day.get(cur, {}).get("expense", 0.0)
        revenue.append(rev)
        expense.append(exp)
        profit.append(rev - exp)
        cur += timedelta(days=1)

    savings_rows = db.query(Savings).filter(Savings.user_id == user.id).order_by(Savings.date.asc()).all()
    savings_growth = []
    for lbl in labels:
        d = date.fromisoformat(lbl)
        matching = [s.balance_after for s in savings_rows if s.date <= d]
        savings_growth.append(matching[-1] if matching else 0.0)

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    business_comparison = []
    for b in businesses:
        rev = _sum_business_tx(db, user, b.id, "revenue", start, today)
        exp = _sum_business_tx(db, user, b.id, "expense", start, today)
        business_comparison.append({"name": b.name, "profit": rev - exp})
    business_comparison.sort(key=lambda x: x["profit"], reverse=True)

    return {
        "labels": labels, "revenue": revenue, "expense": expense, "profit": profit,
        "savings_growth": savings_growth, "business_comparison": business_comparison,
    }


@app.get("/analytics/forecast")
def analytics_forecast(months_history: int = 6, months_forward: int = 12,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Simple linear trend forecast of monthly net profit, based on recent history."""
    today = date.today()
    history = []
    cursor = today.replace(day=1)
    for i in range(months_history - 1, -1, -1):
        y, m = cursor.year, cursor.month
        for _ in range(i):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        start = date(y, m, 1)
        end_day = calendar.monthrange(y, m)[1]
        end = date(y, m, end_day)
        if end > today:
            end = today
        rev = _tx_sum(db, user, "revenue", start, end)
        exp = _tx_sum(db, user, "expense", start, end)
        history.append({"month": start.strftime("%Y-%m"), "profit": rev - exp})

    n = len(history)
    xs = list(range(n))
    ys = [h["profit"] for h in history]
    if n >= 2:
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n)) or 1
        slope = num / den
        intercept = y_mean - slope * x_mean
    else:
        slope, intercept = 0.0, (ys[0] if ys else 0.0)

    forecast = []
    y, m = today.year, today.month
    for i in range(1, months_forward + 1):
        m += 1
        if m > 12:
            m = 1
            y += 1
        projected = intercept + slope * (n - 1 + i)
        forecast.append({"month": f"{y:04d}-{m:02d}", "projected_profit": round(projected, 0)})

    return {"history": history, "forecast": forecast, "monthly_trend": round(slope, 0)}


# ----------------------------------------------------------------------------
# AI Advisor — Gemini-powered (sole AI provider), with rule-based fallback
# ----------------------------------------------------------------------------

def _rule_based_insights(db: Session, user: User) -> List[str]:
    insights = []
    today = date.today()
    month_start = today.replace(day=1)

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    if not businesses:
        return ["Add your first business to start getting personalized insights."]

    perf = []
    for b in businesses:
        rev = _sum_business_tx(db, user, b.id, "revenue", month_start, today)
        exp = _sum_business_tx(db, user, b.id, "expense", month_start, today)
        perf.append((b.name, rev - exp, rev))
    perf.sort(key=lambda x: x[1], reverse=True)

    if perf:
        best = perf[0]
        insights.append(f"{best[0]} is your top performer this month with {best[1]:,.0f} {user.currency} in profit — consider reinvesting some of that back into it.")
        if len(perf) > 1:
            worst = perf[-1]
            if worst[1] < 0:
                insights.append(f"{worst[0]} is running at a loss this month ({worst[1]:,.0f} {user.currency}). Review its expenses or consider pausing it if the trend continues.")

    savings_rows = db.query(Savings).filter(Savings.user_id == user.id).order_by(Savings.date.desc()).all()
    if savings_rows:
        avg_pct = sum(s.percentage for s in savings_rows) / len(savings_rows)
        if avg_pct < 15:
            insights.append(f"You're saving an average of {avg_pct:.0f}% of profit. Bumping this toward 20-30% would build your safety net faster.")
        else:
            insights.append(f"Solid savings discipline — averaging {avg_pct:.0f}% of profit saved. Keep it up.")
    else:
        insights.append("You haven't recorded any savings yet. Setting aside even 10% of profit builds a real cushion over time.")

    hotspots = db.query(Hotspot).filter(Hotspot.user_id == user.id, Hotspot.status == "active").all()
    if hotspots:
        best_h = max(hotspots, key=lambda h: _hotspot_metrics(h)[2])
        mr, mp, roi, payback = _hotspot_metrics(best_h)
        if roi > 0:
            insights.append(f"Your hotspot at {best_h.location} has the strongest ROI ({roi:.0f}% annualized). A similar setup elsewhere could replicate that return.")

    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").all()
    if goals:
        nearest = max(goals, key=lambda g: (g.current_amount / g.target_amount if g.target_amount else 0))
        pct = (nearest.current_amount / nearest.target_amount * 100) if nearest.target_amount else 0
        insights.append(f"You're {pct:.0f}% of the way to '{nearest.name}'. {nearest.target_amount - nearest.current_amount:,.0f} {user.currency} to go.")

    today_open_tasks = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date == today, Todo.status.in_(["pending", "in_progress"])).count()
    if today_open_tasks:
        insights.append(f"You have {today_open_tasks} open task(s) due today — clearing them will directly raise today's execution score.")

    return insights[:6] or ["Keep logging transactions — insights get sharper with more data."]


def _build_full_system_snapshot(db: Session, user: User, light: bool = False) -> dict:
    """Builds a comprehensive snapshot of EVERYTHING the AI can see about
    this user's account — every module in the system, pulled fresh from the
    database. This is the single source of truth handed to Gemini for every
    AI feature (advice, daily recommendations, todo feedback, chat) so
    responses are always grounded in the user's real, current data rather
    than guesses. `light=True` trims the heavier historical lists for
    smaller/cheaper calls, but always includes current totals and balances.
    """
    today = date.today()
    month_start = today.replace(day=1)

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    biz_snapshot = []
    for b in businesses:
        biz_snapshot.append({
            "id": b.id, "name": b.name, "category": b.category, "status": b.status,
            "revenue_mtd": _sum_business_tx(db, user, b.id, "revenue", month_start, today),
            "expense_mtd": _sum_business_tx(db, user, b.id, "expense", month_start, today),
        })

    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    goal_snapshot = [
        {"name": g.name, "target": g.target_amount, "current": g.current_amount, "status": g.status,
         "deadline": g.deadline.isoformat() if g.deadline else None}
        for g in goals
    ]

    savings_balance = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(Savings.user_id == user.id).scalar() or 0.0)
    total_investments = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(Investment.user_id == user.id).scalar() or 0.0)
    total_assets = float(db.query(func.coalesce(func.sum(Asset.current_value), 0.0)).filter(Asset.user_id == user.id).scalar() or 0.0)

    hotspots = db.query(Hotspot).filter(Hotspot.user_id == user.id).all()
    hotspot_snapshot = []
    for h in hotspots:
        mr, mp, roi, payback = _hotspot_metrics(h)
        hotspot_snapshot.append({"location": h.location, "status": h.status, "monthly_profit": mp, "roi_percent": round(roi, 1)})

    mission = get_mission(user)

    todos_today = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date == today).all()
    todo_snapshot = [{"title": t.title, "priority": t.priority, "status": t.status} for t in todos_today]

    score, breakdown, _, tasks_total, tasks_completed = _compute_execution_score(db, user, today)

    snapshot = {
        "currency": user.currency,
        "today": today.isoformat(),
        "mission": {"title": mission.title, "phase": mission.current_phase, "percent_complete": mission.percent_complete},
        "businesses": biz_snapshot,
        "goals": goal_snapshot,
        "savings_balance": savings_balance,
        "total_investments": total_investments,
        "total_assets": total_assets,
        "net_worth": savings_balance + total_investments + total_assets,
        "active_hotspots": hotspot_snapshot,
        "todays_tasks": todo_snapshot,
        "todays_execution_score": score,
        "execution_breakdown": breakdown,
    }

    # Always include this extra depth too — "light" only exists to keep a
    # couple of very small, latency-sensitive calls cheaper; every AI call
    # in this app still gets the full financial picture above plus the
    # following historical context unless explicitly trimmed.
    if not light:
        recent_journal = db.query(JournalEntry).filter(JournalEntry.user_id == user.id).order_by(JournalEntry.date.desc()).limit(5).all()
        snapshot["recent_journal"] = [
            {"date": j.date.isoformat(), "accomplished": j.accomplished, "challenges": j.challenges, "learned": j.learned}
            for j in recent_journal
        ]
        recent_tx = db.query(Transaction).filter(Transaction.user_id == user.id).order_by(Transaction.date.desc()).limit(20).all()
        snapshot["recent_transactions"] = [
            {"date": t.date.isoformat(), "type": t.type, "amount": t.amount, "category": t.category, "business_id": t.business_id}
            for t in recent_tx
        ]
        milestones = db.query(Milestone).filter(Milestone.user_id == user.id).order_by(Milestone.milestone_date.desc()).limit(10).all()
        snapshot["recent_milestones"] = [{"date": m.milestone_date.isoformat(), "title": m.title} for m in milestones]
        unread_notifs = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).order_by(Notification.created_at.desc()).limit(10).all()  # noqa: E712
        snapshot["unread_notifications"] = [n.message for n in unread_notifs]
        all_open_todos = db.query(Todo).filter(Todo.user_id == user.id, Todo.status.in_(["pending", "in_progress"])).order_by(Todo.due_date.asc()).limit(30).all()
        snapshot["all_open_tasks"] = [
            {"title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat(), "status": t.status}
            for t in all_open_todos
        ]
        daily_scores = db.query(DailyScore).filter(DailyScore.user_id == user.id).order_by(DailyScore.date.desc()).limit(14).all()
        snapshot["recent_daily_scores"] = [{"date": d.date.isoformat(), "score": d.score} for d in daily_scores]
        savings_rows = db.query(Savings).filter(Savings.user_id == user.id).order_by(Savings.date.desc()).limit(10).all()
        snapshot["recent_savings"] = [
            {"date": s.date.isoformat(), "percentage": s.percentage, "amount_saved": s.amount_saved, "balance_after": s.balance_after}
            for s in savings_rows
        ]

    return snapshot


def _gemini_financial_insights(db: Session, user: User, fallback: List[str]) -> List[str]:
    snapshot = _build_full_system_snapshot(db, user, light=False)
    prompt = (
        "You are a sharp, encouraging business advisor for a small entrepreneur running "
        "multiple side businesses. Given this JSON snapshot of their FULL current account data "
        "(businesses, goals, savings, investments, assets, hotspots, tasks, recent transactions, "
        "recent journal entries, and daily scores), respond ONLY with a JSON array of 3-6 short, "
        "concrete, specific insight strings (no preamble, no markdown fences, no numbering). "
        "Mention business names and real numbers where useful. Cover: performance comparisons, "
        "savings trend, goal progress, and any risk to flag.\n\n" + json.dumps(snapshot, default=str)
    )
    text = _call_gemini(prompt, context="financial_insights")
    parsed = _parse_json_array(text) if text else None
    if parsed and all(isinstance(x, str) for x in parsed):
        return parsed
    return fallback


@app.get("/ai/advice")
def ai_advice(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fallback = _rule_based_insights(db, user)
    insights = _gemini_financial_insights(db, user, fallback) if GEMINI_API_KEY else fallback
    combined = " | ".join(insights)
    db.add(AIInsightHistory(user_id=user.id, content=combined))
    count = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).count()
    if count > 100:
        oldest = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).order_by(AIInsightHistory.created_at.asc()).first()
        if oldest:
            db.delete(oldest)
    db.commit()
    return {"insights": insights}


_DEFAULT_DAILY_ROUTINES = [
    "Log every sale and expense the moment it happens — don't rely on memory at day's end.",
    "Spend 10 focused minutes on your lowest-performing business today.",
    "Set aside a fixed percentage of today's profit before you spend any of it.",
    "Write a 4-line journal entry tonight: what you did, a challenge, a lesson, one improvement for tomorrow.",
    "Check in briefly on every active hotspot or business location at least every 3 days.",
]


@app.get("/ai/daily-recommendations")
def ai_daily_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Gemini-powered daily activities, behaviors, habits and routines,
    personalized from the user's FULL current account data (mission,
    execution score, tasks, businesses, goals, savings, recent journal)."""
    if not GEMINI_API_KEY:
        return {"source": "rule_based", "recommendations": _DEFAULT_DAILY_ROUTINES}

    snapshot = _build_full_system_snapshot(db, user, light=False)
    prompt = (
        "You are a disciplined personal-operations coach for an entrepreneur running several "
        "small businesses toward a long-term financial mission. Given this JSON snapshot of their "
        "FULL current account data, respond ONLY with a JSON array of 5-7 short, specific, "
        "actionable daily activities, behaviors, habits, or routines the person should follow "
        "TODAY to move their mission forward and raise tomorrow's execution score. No preamble, "
        "no markdown fences, no numbering.\n\n" + json.dumps(snapshot, default=str)
    )
    text = _call_gemini(prompt, context="daily_recommendations")
    parsed = _parse_json_array(text) if text else None
    if parsed and all(isinstance(x, str) for x in parsed):
        return {"source": "gemini", "recommendations": parsed}
    return {"source": "rule_based", "recommendations": _DEFAULT_DAILY_ROUTINES}


@app.get("/ai/insights/history")
def ai_insights_history(limit: int = 25, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).order_by(AIInsightHistory.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "content": r.content, "created_at": r.created_at} for r in rows]


# ----------------------------------------------------------------------------
# Gemini client — single shared client + helpers, with real error logging
# and a small in-memory "last error" record exposed via GET /ai/status so
# failures (bad key, retired model, quota, network) are easy to diagnose
# instead of silently falling back with no trace.
# ----------------------------------------------------------------------------

_gemini_client = None
_GEMINI_LAST_ERROR: dict = {"context": None, "message": None, "at": None}
_GEMINI_LAST_SUCCESS: dict = {"context": None, "at": None}


def _get_gemini_client():
    global _gemini_client
    if not GEMINI_API_KEY:
        return None
    if _gemini_client is None:
        from google import genai  # google-genai SDK (current, unified client)
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _record_gemini_error(context: str, exc: Exception):
    _GEMINI_LAST_ERROR["context"] = context
    _GEMINI_LAST_ERROR["message"] = f"{type(exc).__name__}: {exc}"
    _GEMINI_LAST_ERROR["at"] = utcnow().isoformat()
    logger.error("Gemini call failed [%s]: %s", context, exc, exc_info=True)


def _record_gemini_success(context: str):
    _GEMINI_LAST_SUCCESS["context"] = context
    _GEMINI_LAST_SUCCESS["at"] = utcnow().isoformat()


def _call_gemini(prompt: str, context: str = "generic") -> Optional[str]:
    """Single-turn Gemini call used by the advisor/insights/recommendations
    endpoints. Returns None (never raises) if Gemini is unavailable or the
    call fails — callers fall back to rule-based output — but every failure
    is logged and recorded for GET /ai/status."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set — skipping Gemini call [%s].", context)
        return None
    try:
        client = _get_gemini_client()
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            logger.warning("Gemini [%s] returned an empty response (prompt length %d).", context, len(prompt))
            return None
        _record_gemini_success(context)
        return text
    except Exception as exc:
        _record_gemini_error(context, exc)
        return None


def _call_gemini_chat(system_context: str, history: List[dict], message: str) -> Optional[str]:
    """Multi-turn Gemini call used by the AI Chat assistant. Sends the full
    conversation history plus the current message, with the full system
    snapshot injected as a system instruction so every reply is grounded in
    the user's live account data."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set — skipping Gemini chat call.")
        return None
    try:
        from google import genai
        from google.genai import types

        client = _get_gemini_client()
        contents = []
        for h in history[-12:]:
            role = "user" if h["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=h["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_context),
        )
        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            logger.warning("Gemini chat returned an empty response.")
            return None
        _record_gemini_success("chat")
        return text
    except Exception as exc:
        _record_gemini_error("chat", exc)
        return None


def _parse_json_array(text: str) -> Optional[list]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1) if cleaned.lower().startswith("json") else cleaned
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return None


@app.get("/ai/status")
def ai_status(user: User = Depends(get_current_user)):
    """Diagnostic endpoint — check this first if AI features seem to be
    silently falling back to rule-based output. Shows whether Gemini is
    configured, which model is targeted, and the last error/success."""
    return {
        "gemini_configured": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "last_error": _GEMINI_LAST_ERROR,
        "last_success": _GEMINI_LAST_SUCCESS,
    }


# ----------------------------------------------------------------------------
# AI Chat — full-system-aware conversational advisor (Gemini only)
# ----------------------------------------------------------------------------

def _rule_based_chat_reply(snapshot: dict, message: str) -> str:
    """A minimal offline fallback so the chat still responds usefully if
    Gemini is not configured or a call fails."""
    lower = message.lower()
    if "task" in lower or "todo" in lower:
        tasks = snapshot.get("all_open_tasks", [])
        if not tasks:
            return "You have no open tasks right now — add some in the Todo list and I can help you prioritize them."
        top = ", ".join(t["title"] for t in tasks[:3])
        return f"You have {len(tasks)} open task(s), including: {top}. Want help prioritizing them?"
    if "score" in lower:
        return f"Today's execution score is {snapshot.get('todays_execution_score', 0)}%. Complete your open tasks and log today's numbers to raise it."
    if "goal" in lower:
        goals = snapshot.get("goals", [])
        if not goals:
            return "You don't have any goals set yet — add one from the Goals page and I can track progress with you."
        lines = [f"{g['name']}: {g['current']:,.0f}/{g['target']:,.0f}" for g in goals[:3]]
        return "Here's where your goals stand — " + "; ".join(lines)
    if "business" in lower or "profit" in lower:
        biz = snapshot.get("businesses", [])
        if not biz:
            return "You haven't added any businesses yet — add one and I can start comparing performance."
        lines = [f"{b['name']}: revenue {b['revenue_mtd']:,.0f}, expenses {b['expense_mtd']:,.0f}" for b in biz[:3]]
        return "This month so far — " + "; ".join(lines)
    if not GEMINI_API_KEY:
        return (
            "Gemini isn't configured for this account yet (no GEMINI_API_KEY set on the backend), "
            "so I can only give you basic offline answers right now. Ask about your tasks, goals, "
            "businesses, savings, or today's score."
        )
    return (
        f"I'm tracking your full system — {len(snapshot.get('businesses', []))} business(es), "
        f"{len(snapshot.get('goals', []))} goal(s), and today's execution score of "
        f"{snapshot.get('todays_execution_score', 0)}%. Ask me about your tasks, goals, businesses, "
        "savings, or what to focus on today."
    )


@app.post("/ai/chat", response_model=ChatOut)
def ai_chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Conversational AI Advisor that is aware of everything running in the
    system for this user: every business, transaction summary, goal, savings
    balance, hotspot, task, journal note, notification, mission status and
    daily score. The full snapshot is rebuilt fresh from the database on
    every message, and the recent conversation history is sent alongside it,
    so Gemini is always grounded in current data and stays context-aware
    across turns. Gemini is the sole AI provider — if it's unavailable or a
    call fails, a lightweight rule-based reply is used instead so the chat
    never hard-fails."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    snapshot = _build_full_system_snapshot(db, user, light=False)
    history_rows = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at.desc()).limit(12).all()
    history = [{"role": h.role, "content": h.content} for h in reversed(history_rows)]

    system_context = (
        "You are the AI Advisor inside this user's Business Growth Tracker app. You are fully "
        "aware of everything running in their system — every business, every transaction summary, "
        "every goal, savings balance, active hotspots, today's tasks, all currently open tasks, "
        "recent journal entries, recent savings deposits, unread notifications, mission status, "
        "and recent daily execution scores. Use this JSON snapshot of their live data, pulled "
        "fresh from the database for this message, to answer specifically and accurately, "
        "referencing real numbers and names where relevant. Be direct, encouraging, and concise "
        "(usually under 120 words unless the question needs more). If asked to analyze the whole "
        "system, walk through the key modules briefly. If data for something is missing, say so "
        "plainly instead of guessing. Keep track of the conversation so far and stay consistent "
        "with anything you or the user said earlier in this chat.\n\n"
        "CURRENT SYSTEM SNAPSHOT (JSON, live from the database):\n" + json.dumps(snapshot, default=str)
    )

    reply = _call_gemini_chat(system_context, history, message)
    if not reply:
        reply = _rule_based_chat_reply(snapshot, message)

    db.add(ChatMessage(user_id=user.id, role="user", content=message))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
    count = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).count()
    if count > 200:
        oldest = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at.asc()).limit(count - 200).all()
        for o in oldest:
            db.delete(o)
    db.commit()

    return ChatOut(reply=reply)


@app.get("/ai/chat/history", response_model=List[ChatHistoryOut])
def ai_chat_history(limit: int = Query(60, le=500), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(ChatMessage.created_at.asc()).limit(limit).all()
    return rows


@app.delete("/ai/chat/history")
def clear_ai_chat_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Reports (daily / weekly / monthly / yearly summary) + Weekly & Monthly Review
# ----------------------------------------------------------------------------

@app.get("/reports/summary")
def reports_summary(period: str = "monthly", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    if period == "daily":
        start = today
    elif period == "weekly":
        start = today - timedelta(days=today.weekday())
    elif period == "yearly":
        start = today.replace(month=1, day=1)
    else:
        period = "monthly"
        start = today.replace(day=1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= today
    ).order_by(Transaction.date.desc()).all()

    total_revenue = sum(t.amount for t in txs if t.type == "revenue")
    total_expense = sum(t.amount for t in txs if t.type == "expense")

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "total_profit": total_revenue - total_expense,
        "transactions": [
            {
                "id": t.id, "business_id": t.business_id, "type": t.type, "amount": t.amount,
                "category": t.category, "description": t.description, "date": t.date.isoformat(),
            }
            for t in txs
        ],
    }


@app.get("/reviews/weekly")
def weekly_review(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    revenue = _tx_sum(db, user, "revenue", week_start, today)
    expense = _tx_sum(db, user, "expense", week_start, today)

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    perf = []
    for b in businesses:
        rev = _sum_business_tx(db, user, b.id, "revenue", week_start, today)
        exp = _sum_business_tx(db, user, b.id, "expense", week_start, today)
        perf.append({"name": b.name, "profit": rev - exp})
    perf.sort(key=lambda x: x["profit"], reverse=True)

    savings_this_week = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(
        Savings.user_id == user.id, Savings.date >= week_start, Savings.date <= today).scalar() or 0.0)
    investments_this_week = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(
        Investment.user_id == user.id, Investment.purchase_date >= week_start, Investment.purchase_date <= today).scalar() or 0.0)

    tx_days = db.query(Transaction.date).filter(
        Transaction.user_id == user.id, Transaction.date >= week_start, Transaction.date <= today).distinct().count()
    tasks_completed = tx_days

    scores = db.query(ExecutionScore).filter(
        ExecutionScore.user_id == user.id, ExecutionScore.date >= week_start, ExecutionScore.date <= today).all()
    avg_score = round(sum(s.score for s in scores) / len(scores), 1) if scores else None

    week_tasks_total = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date >= week_start, Todo.due_date <= today).count()
    week_tasks_done = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date >= week_start, Todo.due_date <= today, Todo.status == "completed").count()

    journal_entries = db.query(JournalEntry).filter(
        JournalEntry.user_id == user.id, JournalEntry.date >= week_start, JournalEntry.date <= today).order_by(JournalEntry.date.asc()).all()
    lessons = [j.learned for j in journal_entries if j.learned]

    return {
        "week_start": week_start.isoformat(), "week_end": today.isoformat(),
        "total_revenue": revenue, "total_expense": expense, "total_profit": revenue - expense,
        "best_business": perf[0]["name"] if perf else None,
        "worst_business": perf[-1]["name"] if len(perf) > 1 else None,
        "business_performance": perf,
        "savings_this_week": savings_this_week,
        "investments_this_week": investments_this_week,
        "tasks_completed_days": tasks_completed,
        "week_tasks_total": week_tasks_total,
        "week_tasks_done": week_tasks_done,
        "avg_execution_score": avg_score,
        "lessons_learned": lessons,
    }


@app.get("/reviews/monthly")
def monthly_review(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    revenue = _tx_sum(db, user, "revenue", month_start, today)
    expense = _tx_sum(db, user, "expense", month_start, today)
    profit = revenue - expense

    savings_balance = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(Savings.user_id == user.id).scalar() or 0.0)
    savings_last_month_end = float(db.query(func.coalesce(func.sum(Savings.amount_saved), 0.0)).filter(
        Savings.user_id == user.id, Savings.date <= last_month_end).scalar() or 0.0)

    assets_now = float(db.query(func.coalesce(func.sum(Asset.current_value), 0.0)).filter(Asset.user_id == user.id).scalar() or 0.0)
    investments_now = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(Investment.user_id == user.id).scalar() or 0.0)
    investments_last_month = float(db.query(func.coalesce(func.sum(Investment.cost), 0.0)).filter(
        Investment.user_id == user.id, Investment.purchase_date <= last_month_end).scalar() or 0.0)

    net_worth = savings_balance + assets_now + investments_now

    businesses = db.query(Business).filter(Business.user_id == user.id).all()
    comparison = []
    for b in businesses:
        rev = _sum_business_tx(db, user, b.id, "revenue", month_start, today)
        exp = _sum_business_tx(db, user, b.id, "expense", month_start, today)
        comparison.append({"name": b.name, "revenue": rev, "expense": exp, "profit": rev - exp})
    comparison.sort(key=lambda x: x["profit"], reverse=True)

    month_tasks_total = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date >= month_start, Todo.due_date <= today).count()
    month_tasks_done = db.query(Todo).filter(Todo.user_id == user.id, Todo.due_date >= month_start, Todo.due_date <= today, Todo.status == "completed").count()

    return {
        "month": month_start.strftime("%Y-%m"),
        "revenue": revenue, "expense": expense, "profit": profit,
        "net_worth": net_worth,
        "savings_balance": savings_balance,
        "savings_growth": savings_balance - savings_last_month_end,
        "asset_value": assets_now,
        "investment_total": investments_now,
        "investment_growth": investments_now - investments_last_month,
        "business_comparison": comparison,
        "month_tasks_total": month_tasks_total,
        "month_tasks_done": month_tasks_done,
    }
