"""Optional: create a clearly-labelled demo account with realistic sample data."""
from datetime import date, timedelta
from decimal import Decimal
from app.main import SessionLocal, User, Transaction, Budget, Goal, AdvisorLink, ph
from sqlalchemy import select

db=SessionLocal()
email='demo@finsight.app'
u=db.scalar(select(User).where(User.email==email))
if not u:
    u=User(name='Alex Morgan',email=email,password_hash=ph.hash('DemoPass123!'))
    db.add(u);db.commit();db.refresh(u)
    today=date.today()
    samples=[
      (-24,'income','Salary','Monthly salary'),(-18,'expense','Housing','Hostel rent'),(-15,'expense','Food','Groceries and meals'),(-12,'expense','Transport','Metro recharge'),(-10,'expense','Entertainment','Streaming subscription'),(-7,'expense','Education','Course material'),(-4,'expense','Food','Cafe and lunch'),(-2,'expense','Shopping','Everyday essentials'),(0,'income','Freelance','Project payment'),(0,'expense','Health','Gym membership')]
    for offset,kind,cat,note in samples:
      amount = {'Salary':Decimal('52000'),'Freelance':Decimal('6800'),'Housing':Decimal('10500'),'Food':Decimal('1650') if 'Groceries' in note else Decimal('680'),'Transport':Decimal('850'),'Entertainment':Decimal('499'),'Education':Decimal('1200'),'Shopping':Decimal('1890'),'Health':Decimal('999')}[cat]
      db.add(Transaction(user_id=u.id,kind=kind,amount=amount,category=cat,note=note,trans_date=today+timedelta(days=offset)))
    for cat,lim,period in [('Food','6500','monthly'),('Transport','2500','monthly'),('Shopping','5000','monthly'),('Entertainment','1500','monthly')]:db.add(Budget(user_id=u.id,category=cat,limit_amount=Decimal(lim),period=period))
    db.add(Goal(user_id=u.id,name='Emergency fund',target_amount=Decimal('100000'),saved_amount=Decimal('42500'),target_date=today+timedelta(days=180)))
    db.commit()
print('Demo account ready: demo@finsight.app / DemoPass123!')
db.close()
