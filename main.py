"""
Business Growth Tracker AI — Backend
=====================================

A single-file FastAPI backend that implements every endpoint the frontend
(index.html) calls:

  Auth:            POST /register, POST /login, GET/PUT /me
  Businesses:      GET/POST /businesses, PUT/DELETE /businesses/{id}
  Transactions:    GET/POST /transactions, PUT/DELETE /transactions/{id}
  Savings:         GET/POST /savings
  Hotspots:        GET/POST /hotspots, DELETE /hotspots/{id}, GET /hotspots/projection
  Investments:     GET/POST /investments, DELETE /investments/{id}
  Assets:          GET/POST /assets, DELETE /assets/{id}
  Goals:           GET/POST /goals, PUT/DELETE /goals/{id}
  Notifications:   GET /notifications, PUT /notifications/{id}/read
  Dashboard:       GET /dashboard, GET /dashboard/charts
  AI Advisor:      GET /ai/advice, GET /ai/insights/history
  Reports:         GET /reports/summary

Storage: SQLite (via SQLAlchemy). Auth: JWT bearer tokens.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload

Deploy (e.g. Render):
    Start command: uvicorn main:app --host 0.0.0.0 --port $PORT

Environment variables:
    SECRET_KEY          — JWT signing secret (set a strong random value in prod)
    DATABASE_URL         — defaults to sqlite:///./growth_tracker.db
    ANTHROPIC_API_KEY    — optional. If set, the AI Advisor calls Claude for
                           richer insights. If unset, a built-in rule-based
                           advisor is used instead (no external calls at all).
"""

import os
import hmac
import hashlib
import secrets
import json
from datetime import datetime, date, timedelta, timezone
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
# Config
# ----------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_plvPhjQ4GFE8@ep-polished-sound-aypwc5kt-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

CURRENCIES = {"UGX", "USD", "KES", "EUR", "GBP"}

# ----------------------------------------------------------------------------
# Database setup
# ----------------------------------------------------------------------------

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


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

    businesses = relationship("Business", back_populates="owner", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="owner", cascade="all, delete-orphan")
    savings = relationship("Savings", back_populates="owner", cascade="all, delete-orphan")
    hotspots = relationship("Hotspot", back_populates="owner", cascade="all, delete-orphan")
    investments = relationship("Investment", back_populates="owner", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="owner", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="owner", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="owner", cascade="all, delete-orphan")
    insight_history = relationship("AIInsightHistory", back_populates="owner", cascade="all, delete-orphan")


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
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="notifications")


class AIInsightHistory(Base):
    __tablename__ = "ai_insight_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="insight_history")


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
# Pydantic schemas
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
    date: Optional[date] = None

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
    date: Optional[date] = None


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
    date: Optional[date] = None


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
    projection_6_months: int
    projection_1_year: int
    projection_2_years: int


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


class GoalOut(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    deadline: Optional[date]
    status: str
    progress_percent: float
    amount_remaining: float


class NotificationOut(BaseModel):
    id: int
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------

app = FastAPI(title="Business Growth Tracker AI API", version="1.0.0")

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

def _check_goal_milestones(db: Session, user: User):
    """Create a notification if any active goal just crossed 50/100%."""
    for g in db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").all():
        if g.target_amount <= 0:
            continue
        pct = g.current_amount / g.target_amount * 100
        if pct >= 100:
            g.status = "completed"
            db.add(Notification(user_id=user.id, message=f"Goal '{g.name}' reached! 🎉"))
    db.commit()


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
    db.add(Notification(user_id=user.id, message=f"Saved {amount_saved:,.0f} — balance now {balance_after:,.0f}."))
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
    # Assumption: a modest 15% expansion every 6 months, driven by reinvested profit.
    growth_per_half_year = 0.15
    return HotspotProjectionOut(
        current=current,
        projection_6_months=round(current * (1 + growth_per_half_year)),
        projection_1_year=round(current * (1 + growth_per_half_year) ** 2),
        projection_2_years=round(current * (1 + growth_per_half_year) ** 4),
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
# Goals
# ----------------------------------------------------------------------------

def _goal_out(g: Goal) -> GoalOut:
    pct = min(100.0, round((g.current_amount / g.target_amount * 100), 1)) if g.target_amount else 0.0
    remaining = max(0.0, g.target_amount - g.current_amount)
    return GoalOut(
        id=g.id, name=g.name, target_amount=g.target_amount, current_amount=g.current_amount,
        deadline=g.deadline, status=g.status, progress_percent=pct, amount_remaining=remaining,
    )


@app.get("/goals", response_model=List[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at.desc()).all()
    return [_goal_out(g) for g in rows]


@app.post("/goals", response_model=GoalOut)
def create_goal(body: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = Goal(
        user_id=user.id, name=body.name.strip(), target_amount=body.target_amount,
        current_amount=body.current_amount, deadline=body.deadline,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_out(g)


@app.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found.")
    for field in ("name", "target_amount", "deadline", "status"):
        val = getattr(body, field)
        if val is not None:
            setattr(g, field, val)
    if body.current_amount is not None:
        g.current_amount = body.current_amount
    if g.target_amount and g.current_amount >= g.target_amount and g.status == "active":
        g.status = "completed"
        db.add(Notification(user_id=user.id, message=f"Goal '{g.name}' reached! 🎉"))
    db.commit()
    db.refresh(g)
    return _goal_out(g)


@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found.")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Notifications
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

    # Cumulative savings balance over the same window.
    savings_rows = db.query(Savings).filter(Savings.user_id == user.id).order_by(Savings.date.asc()).all()
    savings_growth = []
    for lbl in labels:
        d = date.fromisoformat(lbl)
        matching = [s.balance_after for s in savings_rows if s.date <= d]
        savings_growth.append(matching[-1] if matching else 0.0)

    # Business comparison: total profit per business over the window.
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


def _sum_business_tx(db, user, business_id, type_, start, end):
    q = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user.id, Transaction.business_id == business_id,
        Transaction.type == type_, Transaction.date >= start, Transaction.date <= end,
    )
    return float(q.scalar() or 0.0)


# ----------------------------------------------------------------------------
# AI Advisor
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

    return insights[:6] or ["Keep logging transactions — insights get sharper with more data."]


def _claude_insights(db: Session, user: User, fallback: List[str]) -> List[str]:
    """Optional: use the Anthropic API for richer insights if a key is configured."""
    if not ANTHROPIC_API_KEY:
        return fallback
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        today = date.today()
        month_start = today.replace(day=1)
        businesses = db.query(Business).filter(Business.user_id == user.id).all()
        summary = {
            "currency": user.currency,
            "businesses": [
                {
                    "name": b.name,
                    "category": b.category,
                    "revenue_mtd": _sum_business_tx(db, user, b.id, "revenue", month_start, today),
                    "expense_mtd": _sum_business_tx(db, user, b.id, "expense", month_start, today),
                }
                for b in businesses
            ],
            "goals": [
                {"name": g.name, "target": g.target_amount, "current": g.current_amount}
                for g in db.query(Goal).filter(Goal.user_id == user.id, Goal.status == "active").all()
            ],
        }
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "You are a business advisor. Given this JSON snapshot of a small business "
                    "owner's finances, respond ONLY with a JSON array of 3-5 short, concrete, "
                    "actionable insight strings (no preamble, no markdown fences).\n\n"
                    + json.dumps(summary)
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        cleaned = text.strip().strip("`")
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed
    except Exception:
        pass
    return fallback


@app.get("/ai/advice")
def ai_advice(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fallback = _rule_based_insights(db, user)
    insights = _claude_insights(db, user, fallback)
    combined = " | ".join(insights)
    db.add(AIInsightHistory(user_id=user.id, content=combined))
    # keep history bounded
    count = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).count()
    if count > 100:
        oldest = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).order_by(AIInsightHistory.created_at.asc()).first()
        if oldest:
            db.delete(oldest)
    db.commit()
    return {"insights": insights}


@app.get("/ai/insights/history")
def ai_insights_history(limit: int = 25, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AIInsightHistory).filter(AIInsightHistory.user_id == user.id).order_by(AIInsightHistory.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "content": r.content, "created_at": r.created_at} for r in rows]


# ----------------------------------------------------------------------------
# Reports
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
