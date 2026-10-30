from __future__ import annotations
import csv, io, os, secrets, statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, Integer, Date, DateTime, Numeric, ForeignKey, Boolean, Text, select, func, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session, relationship
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import jwt
from jwt import InvalidTokenError as JWTError

APP_NAME = "FinSight API"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finsight.db")
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-this-secret-key-before-deploying")
ALGORITHM = "HS256"
TOKEN_HOURS = 24
ph = PasswordHasher()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    category: Mapped[str] = mapped_column(String(60), index=True)
    note: Mapped[str] = mapped_column(String(250), default="")
    trans_date: Mapped[date] = mapped_column(Date, index=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60))
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    period: Mapped[str] = mapped_column(String(20), default="monthly")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    saved_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    target_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AdvisorLink(Base):
    __tablename__ = "advisor_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    advisor_email: Mapped[str] = mapped_column(String(255), index=True)
    advisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)

def _migrate_advisor_links():
    insp = inspect(engine)
    if "advisor_links" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("advisor_links")}
    with engine.begin() as conn:
        if "advisor_user_id" not in cols:
            conn.execute(text("ALTER TABLE advisor_links ADD COLUMN advisor_user_id INTEGER"))
        if "status" not in cols:
            conn.execute(text("ALTER TABLE advisor_links ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            conn.execute(text("UPDATE advisor_links SET status='active' WHERE status IS NULL OR status=''"))
        if "accepted_at" not in cols:
            conn.execute(text("ALTER TABLE advisor_links ADD COLUMN accepted_at DATETIME"))
        if "revoked_at" not in cols:
            conn.execute(text("ALTER TABLE advisor_links ADD COLUMN revoked_at DATETIME"))
        conn.execute(text(
            "UPDATE advisor_links SET advisor_user_id = "
            "(SELECT users.id FROM users WHERE LOWER(users.email) = LOWER(advisor_links.advisor_email)) "
            "WHERE advisor_user_id IS NULL"
        ))

_migrate_advisor_links()

app = FastAPI(title=APP_NAME, version="1.0.0", description="Personal finance tracking, analytics, and goal management for FinSight.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
class LoginIn(BaseModel): email: EmailStr; password: str = Field(min_length=1, max_length=128)
class TxIn(BaseModel):
    kind: Literal["income", "expense"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str | None = Field(default=None, max_length=60)
    note: str = Field(default="", max_length=250)
    trans_date: date = Field(default_factory=date.today)
class BudgetIn(BaseModel): category: str = Field(min_length=1, max_length=60); limit_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2); period: Literal["monthly", "weekly"] = "monthly"
class GoalIn(BaseModel): name: str = Field(min_length=1, max_length=120); target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2); saved_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2); target_date: date
class GoalProgressIn(BaseModel): saved_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
class AdvisorIn(BaseModel): email: EmailStr

CATEGORIES = {
    "Food": ["restaurant", "cafe", "coffee", "food", "grocery", "groceries", "swiggy", "zomato", "lunch", "dinner", "snack"],
    "Transport": ["uber", "ola", "taxi", "fuel", "petrol", "metro", "bus", "train", "flight", "parking"],
    "Shopping": ["amazon", "flipkart", "clothes", "shopping", "shoes", "electronics"],
    "Bills & utilities": ["electricity", "water bill", "internet", "wifi", "phone bill", "recharge", "gas bill", "utility"],
    "Health": ["doctor", "pharmacy", "medicine", "hospital", "gym", "health"],
    "Entertainment": ["movie", "netflix", "spotify", "game", "concert", "subscription"],
    "Education": ["tuition", "college", "course", "books", "education", "exam"],
    "Housing": ["rent", "maintenance", "repair", "hostel"],
    "Salary": ["salary", "payroll", "stipend", "paycheck"],
    "Freelance": ["freelance", "client payment", "project payment"],
    "Investment returns": ["dividend", "interest", "return"],
    "Other": []
}
def suggest_category(note: str, kind: str, given: str | None) -> str:
    if given and given.strip():
        known = next((x for x in CATEGORIES if x.lower() == given.strip().lower()), None)
        return known or given.strip()
    text_ = (note or "").lower()
    for category, keywords in CATEGORIES.items():
        if any(k in text_ for k in keywords): return category
    return "Other income" if kind == "income" else "Other"

def token_for(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}, SECRET_KEY, algorithm=ALGORITHM)
def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401, "Please sign in to continue.")
    try:
        payload = jwt.decode(authorization.split(" ",1)[1], SECRET_KEY, algorithms=[ALGORITHM]); uid = int(payload["sub"])
    except (JWTError, ValueError, KeyError): raise HTTPException(401, "Your session has expired. Please sign in again.")
    user = db.get(User, uid)
    if not user: raise HTTPException(401, "Account no longer exists.")
    return user

def tx_json(t: Transaction): return {"id":t.id,"kind":t.kind,"amount":float(t.amount),"category":t.category,"note":t.note,"trans_date":t.trans_date.isoformat(),"flagged":t.flagged}
def budget_json(b: Budget, spent: float): return {"id":b.id,"category":b.category,"limit_amount":float(b.limit_amount),"period":b.period,"spent":round(spent,2),"percent":round(spent/float(b.limit_amount)*100) if b.limit_amount else 0}
def goal_json(g: Goal): return {"id":g.id,"name":g.name,"target_amount":float(g.target_amount),"saved_amount":float(g.saved_amount),"target_date":g.target_date.isoformat(),"percent":min(100,round(float(g.saved_amount)/float(g.target_amount)*100)) if g.target_amount else 0}
def get_user_transactions(db: Session, uid: int): return list(db.scalars(select(Transaction).where(Transaction.user_id==uid).order_by(Transaction.trans_date.desc(), Transaction.id.desc())))
def budget_spend(db: Session, uid: int, b: Budget) -> float:
    today = date.today()
    start = today - timedelta(days=today.weekday()) if b.period == "weekly" else today.replace(day=1)
    q = select(func.coalesce(func.sum(Transaction.amount),0)).where(Transaction.user_id==uid, Transaction.kind=="expense", Transaction.category==b.category, Transaction.trans_date>=start, Transaction.trans_date<=today)
    return float(db.scalar(q) or 0)

def make_summary(db: Session, uid: int):
    txs = get_user_transactions(db,uid); today=date.today(); month_start=today.replace(day=1); prev_end=month_start-timedelta(days=1); prev_start=prev_end.replace(day=1)
    income=sum(float(t.amount) for t in txs if t.kind=="income" and t.trans_date>=month_start and t.trans_date<=today)
    expenses=sum(float(t.amount) for t in txs if t.kind=="expense" and t.trans_date>=month_start and t.trans_date<=today)
    prev=sum(float(t.amount) for t in txs if t.kind=="expense" and prev_start<=t.trans_date<=prev_end)
    cats=defaultdict(float); monthly=defaultdict(lambda:{"income":0.0,"expenses":0.0})
    for t in txs:
        key=t.trans_date.strftime("%b %Y")
        monthly[key]["income" if t.kind=="income" else "expenses"] += float(t.amount)
        if t.kind=="expense" and t.trans_date>=month_start: cats[t.category]+=float(t.amount)
    months=[]
    for i in range(5,-1,-1):
        m=today.month-i; y=today.year
        while m<=0: m+=12; y-=1
        label=date(y,m,1).strftime("%b %Y"); val=monthly.get(label,{"income":0.0,"expenses":0.0})
        months.append({"month":date(y,m,1).strftime("%b"),"income":round(val["income"],2),"expenses":round(val["expenses"],2)})
    expense_months=[x["expenses"] for x in months if x["expenses"]>0]
    forecast=round(statistics.mean(expense_months[-3:]),2) if expense_months else round(expenses,2)
    return {"balance":round(income-expenses,2),"income":round(income,2),"expenses":round(expenses,2),"previous_expenses":round(prev,2),"expense_change_pct":round((expenses-prev)/prev*100,1) if prev else (0.0 if expenses == 0 else None),"transaction_count":len(txs),"categories":[{"category":k,"amount":round(v,2)} for k,v in sorted(cats.items(),key=lambda p:p[1],reverse=True)],"monthly":months,"forecast":forecast,"flagged_count":sum(1 for t in txs if t.flagged)}

@app.get("/")
def root(): return {"name":APP_NAME,"version":"1.0.0","status":"ok","docs":"/docs"}
@app.get("/api/health")
def health(): return {"status":"ok","service":"FinSight API"}
@app.post("/api/demo/seed")
def seed_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if os.getenv("ENABLE_DEMO_SEED", "false").lower() != "true":
        raise HTTPException(404, "Demo seeding is disabled.")
    if db.scalar(select(Transaction.id).where(Transaction.user_id == user.id).limit(1)):
        raise HTTPException(409, "This account already has transactions; sample data was not added.")
    today = date.today()
    entries = [
        ("income", Decimal("52000.00"), "Salary", "Monthly salary", -24),
        ("expense", Decimal("10500.00"), "Housing", "Hostel rent", -18),
        ("expense", Decimal("1650.00"), "Food", "Groceries and meals", -15),
        ("expense", Decimal("850.00"), "Transport", "Metro recharge", -12),
        ("expense", Decimal("499.00"), "Entertainment", "Streaming subscription", -10),
        ("expense", Decimal("1200.00"), "Education", "Course material", -7),
        ("expense", Decimal("680.00"), "Food", "Cafe and lunch", -4),
        ("expense", Decimal("1890.00"), "Shopping", "Everyday essentials", -2),
        ("income", Decimal("6800.00"), "Freelance", "Project payment", 0),
        ("expense", Decimal("999.00"), "Health", "Gym membership", 0),
    ]
    for kind, amount, category, note, offset in entries:
        db.add(Transaction(user_id=user.id, kind=kind, amount=amount, category=category, note=note, trans_date=today + timedelta(days=offset)))
    for category, limit in [("Food", "6500"), ("Transport", "2500"), ("Shopping", "5000"), ("Entertainment", "1500")]:
        db.add(Budget(user_id=user.id, category=category, limit_amount=Decimal(limit), period="monthly"))
    db.add(Goal(user_id=user.id, name="Emergency fund", target_amount=Decimal("100000"), saved_amount=Decimal("42500"), target_date=today + timedelta(days=180)))
    db.commit()
    return {"ok": True, "message": "Demo data added to your empty account."}
@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session=Depends(get_db)):
    email=data.email.lower().strip()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"An account with this email already exists.")
    user=User(name=data.name.strip(),email=email,password_hash=ph.hash(data.password)); db.add(user); db.commit(); db.refresh(user)
    return {"token":token_for(user),"user":{"id":user.id,"name":user.name,"email":user.email}}
@app.post("/api/auth/login")
def login(data: LoginIn, db: Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email.lower().strip()))
    if not user: raise HTTPException(401,"Email or password is incorrect.")
    try: ph.verify(user.password_hash,data.password)
    except (VerifyMismatchError,InvalidHashError): raise HTTPException(401,"Email or password is incorrect.")
    if ph.check_needs_rehash(user.password_hash): user.password_hash=ph.hash(data.password); db.commit()
    return {"token":token_for(user),"user":{"id":user.id,"name":user.name,"email":user.email}}
@app.get("/api/auth/me")
def me(user: User=Depends(current_user)): return {"id":user.id,"name":user.name,"email":user.email}

@app.get("/api/dashboard")
def dashboard(user: User=Depends(current_user), db: Session=Depends(get_db)):
    s=make_summary(db,user.id); txs=get_user_transactions(db,user.id)
    budgets=list(db.scalars(select(Budget).where(Budget.user_id==user.id)))
    s["recent_transactions"]=[tx_json(t) for t in txs[:8]]
    s["budgets"]=[budget_json(b,budget_spend(db,user.id,b)) for b in budgets]
    s["goals"]=[goal_json(g) for g in db.scalars(select(Goal).where(Goal.user_id==user.id).order_by(Goal.target_date))]
    alerts=[]
    for t in txs:
        if t.flagged: alerts.append({"id":f"tx-{t.id}","type":"anomaly","title":"Unusual transaction detected","message":f"{t.category} expense of ₹{float(t.amount):,.2f} is higher than your usual spending.","date":t.trans_date.isoformat()})
    for b in budgets:
        spent=budget_spend(db,user.id,b); pct=spent/float(b.limit_amount)*100 if b.limit_amount else 0
        if pct>=90: alerts.append({"id":f"budget-{b.id}","type":"budget","title":f"{b.category} budget at {round(pct)}%","message":f"₹{spent:,.2f} of ₹{float(b.limit_amount):,.2f} used this {b.period[:-2]} period.","date":date.today().isoformat()})
    s["alerts"]=alerts[:20]; return s

@app.get("/api/transactions")
def list_transactions(kind: str|None=None, search: str|None=None, user: User=Depends(current_user), db: Session=Depends(get_db)):
    q=select(Transaction).where(Transaction.user_id==user.id)
    if kind in ("income","expense"): q=q.where(Transaction.kind==kind)
    rows=list(db.scalars(q.order_by(Transaction.trans_date.desc(),Transaction.id.desc())))
    if search:
        needle=search.casefold(); rows=[t for t in rows if needle in t.category.casefold() or needle in t.note.casefold()]
    return [tx_json(t) for t in rows]
@app.post("/api/transactions",status_code=201)
def create_transaction(data: TxIn, user: User=Depends(current_user), db: Session=Depends(get_db)):
    category=suggest_category(data.note,data.kind,data.category)
    baseline=[float(t.amount) for t in db.scalars(select(Transaction).where(Transaction.user_id==user.id,Transaction.kind==data.kind,Transaction.category==category))]
    flagged=False
    if data.kind=="expense" and len(baseline)>=3:
        avg=statistics.mean(baseline); sd=statistics.pstdev(baseline) if len(baseline)>1 else 0
        flagged=float(data.amount)>max(avg*2.0,avg+2*sd,1000)
    tx=Transaction(user_id=user.id,kind=data.kind,amount=data.amount,category=category,note=data.note.strip(),trans_date=data.trans_date,flagged=flagged)
    db.add(tx); db.commit(); db.refresh(tx)
    return tx_json(tx)
@app.put("/api/transactions/{tx_id}")
def update_transaction(tx_id:int,data:TxIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tx=db.scalar(select(Transaction).where(Transaction.id==tx_id,Transaction.user_id==user.id))
    if not tx: raise HTTPException(404,"Transaction not found.")
    tx.kind=data.kind; tx.amount=data.amount; tx.category=suggest_category(data.note,data.kind,data.category); tx.note=data.note.strip(); tx.trans_date=data.trans_date; db.commit(); db.refresh(tx); return tx_json(tx)
@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tx=db.scalar(select(Transaction).where(Transaction.id==tx_id,Transaction.user_id==user.id))
    if not tx: raise HTTPException(404,"Transaction not found.")
    db.delete(tx);db.commit();return {"ok":True}
@app.post("/api/transactions/import")
def import_transactions(file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"): raise HTTPException(400,"Upload a .csv file.")
    try: content=(file.file.read()).decode("utf-8-sig"); reader=csv.DictReader(io.StringIO(content))
    except Exception: raise HTTPException(400,"Could not read this CSV. Save it as UTF-8 and try again.")
    headers={h.strip().lower():h for h in (reader.fieldnames or [])}
    amount_key=next((headers[x] for x in ["amount","value"] if x in headers),None); date_key=next((headers[x] for x in ["date","trans_date"] if x in headers),None)
    if not amount_key or not date_key: raise HTTPException(400,"CSV needs at least 'date' and 'amount' columns. Optional: type, category, note.")
    count=0; skipped=0
    for row in reader:
        try:
            amount=Decimal(str(row[amount_key]).replace(",","").replace("₹","").strip())
            if amount==0: skipped+=1;continue
            raw=(row.get(headers.get("type",""),"") or "").strip().lower()
            kind="income" if raw in ("income","credit","in") or amount<0 else "expense"
            amount=abs(amount)
            trans_date=date.fromisoformat(str(row[date_key]).strip()[:10])
            note=(row.get(headers.get("note",""),"") or row.get(headers.get("description",""),"") or "").strip()
            category=(row.get(headers.get("category",""),"") or "").strip() or suggest_category(note,kind,None)
            db.add(Transaction(user_id=user.id,kind=kind,amount=amount,category=category,note=note[:250],trans_date=trans_date));count+=1
        except Exception: skipped+=1
    db.commit(); return {"imported":count,"skipped":skipped}

@app.get("/api/budgets")
def list_budgets(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [budget_json(b,budget_spend(db,user.id,b)) for b in db.scalars(select(Budget).where(Budget.user_id==user.id).order_by(Budget.category))]
@app.post("/api/budgets",status_code=201)
def create_budget(data:BudgetIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    existing=db.scalar(select(Budget).where(Budget.user_id==user.id,Budget.category==data.category,Budget.period==data.period))
    if existing: existing.limit_amount=data.limit_amount; db.commit();db.refresh(existing);return budget_json(existing,budget_spend(db,user.id,existing))
    b=Budget(user_id=user.id,category=data.category,limit_amount=data.limit_amount,period=data.period);db.add(b);db.commit();db.refresh(b);return budget_json(b,budget_spend(db,user.id,b))
@app.delete("/api/budgets/{budget_id}")
def delete_budget(budget_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    b=db.scalar(select(Budget).where(Budget.id==budget_id,Budget.user_id==user.id))
    if not b:raise HTTPException(404,"Budget not found.")
    db.delete(b);db.commit();return {"ok":True}

@app.get("/api/goals")
def list_goals(user:User=Depends(current_user),db:Session=Depends(get_db)):return [goal_json(g) for g in db.scalars(select(Goal).where(Goal.user_id==user.id).order_by(Goal.target_date))]
@app.post("/api/goals",status_code=201)
def create_goal(data:GoalIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if data.saved_amount>data.target_amount:raise HTTPException(400,"Saved amount cannot exceed the target amount.")
    g=Goal(user_id=user.id,name=data.name.strip(),target_amount=data.target_amount,saved_amount=data.saved_amount,target_date=data.target_date);db.add(g);db.commit();db.refresh(g);return goal_json(g)
@app.patch("/api/goals/{goal_id}")
def update_goal(goal_id:int,data:GoalProgressIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    g=db.scalar(select(Goal).where(Goal.id==goal_id,Goal.user_id==user.id))
    if not g:raise HTTPException(404,"Goal not found.")
    if data.saved_amount>g.target_amount:raise HTTPException(400,"Saved amount cannot exceed the target amount.")
    g.saved_amount=data.saved_amount;db.commit();db.refresh(g);return goal_json(g)
@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    g=db.scalar(select(Goal).where(Goal.id==goal_id,Goal.user_id==user.id))
    if not g:raise HTTPException(404,"Goal not found.")
    db.delete(g);db.commit();return {"ok":True}

@app.get("/api/analytics")
def analytics(user:User=Depends(current_user),db:Session=Depends(get_db)):return make_summary(db,user.id)
@app.get("/api/alerts")
def alerts(user:User=Depends(current_user),db:Session=Depends(get_db)):
    out=[]
    for t in get_user_transactions(db,user.id):
        if t.flagged:out.append({"id":f"tx-{t.id}","type":"anomaly","title":"Unusual transaction detected","message":f"{t.category} expense of ₹{float(t.amount):,.2f} was flagged by your spending baseline.","date":t.trans_date.isoformat()})
    for b in db.scalars(select(Budget).where(Budget.user_id==user.id)):
        spent=budget_spend(db,user.id,b);pct=spent/float(b.limit_amount)*100 if b.limit_amount else 0
        if pct>=90:out.append({"id":f"budget-{b.id}","type":"budget","title":f"{b.category} budget almost reached","message":f"You've used {pct:.0f}% of this {b.period} budget.","date":date.today().isoformat()})
    return out

def _link_dict(l: AdvisorLink):
    return {
        "id": l.id,
        "advisor_email": l.advisor_email,
        "status": l.status,
        "created_at": l.created_at.isoformat(),
        "accepted_at": l.accepted_at.isoformat() if l.accepted_at else None,
    }

@app.get("/api/advisor/links")
def advisor_links(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AdvisorLink).where(
        AdvisorLink.user_id == user.id,
        AdvisorLink.status != "revoked",
    ).order_by(AdvisorLink.created_at.desc()))
    return [_link_dict(l) for l in rows]

@app.post("/api/advisor/links", status_code=201)
def link_advisor(data: AdvisorIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    email = data.email.lower().strip()
    if email == user.email.lower():
        raise HTTPException(400, "You cannot link your own account as an advisor.")
    existing = db.scalar(select(AdvisorLink).where(
        AdvisorLink.user_id == user.id,
        func.lower(AdvisorLink.advisor_email) == email,
        AdvisorLink.status != "revoked",
    ))
    if existing:
        raise HTTPException(409, "This advisor is already invited or linked.")
    declined = db.scalar(select(AdvisorLink).where(
        AdvisorLink.user_id == user.id,
        func.lower(AdvisorLink.advisor_email) == email,
        AdvisorLink.status == "declined",
    ))
    if declined:
        declined.status = "pending"
        declined.accepted_at = None
        declined.revoked_at = None
        declined.advisor_user_id = None
        db.commit(); db.refresh(declined)
        return _link_dict(declined)
    link = AdvisorLink(user_id=user.id, advisor_email=email, status="pending")
    db.add(link); db.commit(); db.refresh(link)
    return _link_dict(link)

@app.delete("/api/advisor/links/{link_id}")
def unlink_advisor(link_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    link = db.scalar(select(AdvisorLink).where(AdvisorLink.id == link_id, AdvisorLink.user_id == user.id))
    if not link: raise HTTPException(404, "Advisor link not found.")
    link.status = "revoked"
    link.revoked_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

@app.get("/api/advisor/invitations")
def advisor_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AdvisorLink).where(
        func.lower(AdvisorLink.advisor_email) == user.email.lower(),
        AdvisorLink.status == "pending",
    ).order_by(AdvisorLink.created_at.desc()))
    out = []
    for link in rows:
        owner = db.get(User, link.user_id)
        if not owner: continue
        out.append({
            "id": link.id,
            "client_name": owner.name,
            "client_email": owner.email,
            "created_at": link.created_at.isoformat(),
        })
    return out

@app.post("/api/advisor/invitations/{link_id}/accept")
def accept_invitation(link_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    link = db.get(AdvisorLink, link_id)
    if not link: raise HTTPException(404, "Invitation not found.")
    if link.advisor_email.lower() != user.email.lower():
        raise HTTPException(403, "This invitation is for a different email address.")
    if link.status == "active":
        return {"ok": True, "link_id": link.id, "status": "active"}
    if link.status in ("revoked", "declined"):
        raise HTTPException(400, "This invitation is no longer available.")
    link.advisor_user_id = user.id
    link.status = "active"
    link.accepted_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "link_id": link.id, "status": "active"}

@app.post("/api/advisor/invitations/{link_id}/decline")
def decline_invitation(link_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    link = db.get(AdvisorLink, link_id)
    if not link: raise HTTPException(404, "Invitation not found.")
    if link.advisor_email.lower() != user.email.lower():
        raise HTTPException(403, "This invitation is for a different email address.")
    if link.status != "pending":
        raise HTTPException(400, "This invitation is not pending.")
    link.status = "declined"
    db.commit()
    return {"ok": True}

@app.get("/api/advisor/clients")
def advisor_clients(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AdvisorLink).where(
        AdvisorLink.advisor_user_id == user.id,
        AdvisorLink.status == "active",
    ))
    out, seen = [], set()
    for link in rows:
        if link.user_id in seen: continue
        seen.add(link.user_id)
        owner = db.get(User, link.user_id)
        if owner:
            out.append({"id": owner.id, "name": owner.name, "email": owner.email})
    return out

@app.get("/api/advisor")
def advisor_summary(user_id: int | None = None, client_email: EmailStr | None = None,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user_id is None and client_email is None:
        raise HTTPException(400, "Provide either user_id or client_email for the linked client.")
    target = db.get(User, user_id) if user_id is not None else db.scalar(select(User).where(func.lower(User.email) == str(client_email).lower()))
    if not target: raise HTTPException(404, "Client not found.")
    linked = db.scalar(select(AdvisorLink).where(
        AdvisorLink.user_id == target.id,
        AdvisorLink.advisor_user_id == user.id,
        AdvisorLink.status == "active",
    ))
    if not linked:
        raise HTTPException(403, "You do not have read-only advisor access to this account.")
    s = make_summary(db, target.id)
    return {
        "client": {"name": target.name, "email": target.email},
        "summary": s,
        "recent_transactions": [tx_json(t) for t in get_user_transactions(db, target.id)[:10]],
        "read_only": True,
    }
