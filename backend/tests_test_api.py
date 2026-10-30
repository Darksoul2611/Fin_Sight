"""Quick API smoke test; run after installing backend requirements."""
from fastapi.testclient import TestClient
import uuid
from app.main import app
client = TestClient(app)
def test_health():
    r=client.get('/api/health'); assert r.status_code==200 and r.json()['status']=='ok'
def test_auth_and_transaction_flow():
    email='smoke-test@example.com'
    # remove fixed account collision by register-or-login
    r=client.post('/api/auth/register',json={'name':'Smoke Tester','email':email,'password':'StrongTest123!'})
    if r.status_code==409:r=client.post('/api/auth/login',json={'email':email,'password':'StrongTest123!'})
    assert r.status_code in (200,201)
    h={'Authorization':'Bearer '+r.json()['token']}
    tx=client.post('/api/transactions',headers=h,json={'kind':'expense','amount':'425.50','note':'lunch at cafe','trans_date':'2026-10-25'})
    assert tx.status_code==201 and tx.json()['category']=='Food'
    assert client.get('/api/dashboard',headers=h).status_code==200


def test_advisor_access_is_read_only_and_explicit():
    suffix = uuid.uuid4().hex[:12]
    owner_email = f'advisor-owner-{suffix}@example.com'
    advisor_email = f'advisor-{suffix}@example.com'
    owner = client.post('/api/auth/register', json={'name':'Advisor Owner','email':owner_email,'password':'StrongTest123!'})
    advisor = client.post('/api/auth/register', json={'name':'Advisor Tester','email':advisor_email,'password':'StrongTest123!'})
    assert owner.status_code == 200 and advisor.status_code == 200
    owner_h = {'Authorization':'Bearer '+owner.json()['token']}
    advisor_h = {'Authorization':'Bearer '+advisor.json()['token']}
    user_id = owner.json()['user']['id']
    denied = client.get(f'/api/advisor?user_id={user_id}', headers=advisor_h)
    assert denied.status_code == 403
    linked = client.post('/api/advisor/links', headers=owner_h, json={'email':advisor_email})
    assert linked.status_code == 201
    summary = client.get(f'/api/advisor?user_id={user_id}', headers=advisor_h)
    assert summary.status_code == 200 and summary.json()['read_only'] is True
    assert client.delete(f"/api/transactions/1", headers=advisor_h).status_code in (404, 403)
