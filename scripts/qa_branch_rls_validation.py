#!/usr/bin/env python3
import os, sys, json, time
import requests

def read_env(name, required=False, default=None):
    val = os.getenv(name, default)
    if required and (val is None or (isinstance(val, str) and not val.strip())):
        print(f"[CONFIG] Missing required environment variable: {name}")
        return None
    return val

def auth_headers(token):
    tok = token
    if tok and tok.startswith("Bearer "):
        tok = tok[7:]
    return {"Authorization": f"Bearer {tok}"}

def post_json(url, token, payload):
    try:
        resp = requests.post(url, headers={**auth_headers(token), "Content-Type":"application/json"}, json=payload, timeout=30)
        return resp
    except requests.RequestException as e:
        print(f"[HTTP] POST error {url}: {e}")
        return None

def get_json(url, token, params=None):
    try:
        resp = requests.get(url, headers=auth_headers(token), params=params, timeout=30)
        return resp
    except requests.RequestException as e:
        print(f"[HTTP] GET error {url}: {e}")
        return None

def print_resp(resp):
    if resp is None:
        print("No response")
        return
    print(f"Status: {resp.status_code}")
    try:
        print("Body:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print("Body (text):", resp.text[:500])

def build_sale_payload(item_kind, item_id, qty, price, cliente_id=None, observaciones="QA RLS test"):
    items = [{
        "id": item_id,
        "tipo": item_kind,
        "cantidad": qty,
        "precio": price
    }]
    payload = {
        "items": items,
        "cliente_id": cliente_id,
        "metodo_pago": "efectivo",
        "observaciones": observaciones
    }
    return payload

def expect(status_code, expected, label):
    ok = (status_code == expected) or (expected == 200 and 200 <= status_code < 300)
    print(f"[ASSERT] {label}: {'OK' if ok else 'FAIL'} (got {status_code}, expected {expected})")
    return ok

def test_write_success(base, business_id, branch_id_assigned, token, item_kind, item_id, qty, price):
    url = f"{base}/businesses/{business_id}/branches/{branch_id_assigned}/ventas/record-sale"
    payload = build_sale_payload(item_kind, item_id, qty, price, observaciones="QA write success")
    print(f"\n[TEST] Branch-scoped write should SUCCEED at assigned branch\nPOST {url}")
    resp = post_json(url, token, payload)
    print_resp(resp)
    return resp is not None and expect(resp.status_code if resp else 0, 200, "write success on assigned branch")

def test_write_failure(base, business_id, branch_id_unassigned, token, item_kind, item_id, qty, price):
    url = f"{base}/businesses/{business_id}/branches/{branch_id_unassigned}/ventas/record-sale"
    payload = build_sale_payload(item_kind, item_id, qty, price, observaciones="QA write failure")
    print(f"\n[TEST] Branch-scoped write should FAIL at unassigned branch\nPOST {url}")
    resp = post_json(url, token, payload)
    print_resp(resp)
    # Expect 403 Forbidden due to RLS/business-branch guard; could be 401 if token invalid
    return resp is not None and expect(resp.status_code if resp else 0, 403, "write failure on unassigned branch")

def test_cross_business_read_denial(base, other_business_id, token):
    url = f"{base}/businesses/{other_business_id}/ventas/sales"
    print(f"\n[TEST] Cross-business read denial (should be denied or empty)\nGET {url}")
    resp = get_json(url, token)
    print_resp(resp)
    if resp is None:
        return False
    if resp.status_code in (401,403):
        print("[ASSERT] Read denied by RLS or auth: OK")
        return True
    try:
        data = resp.json()
        ventas = data.get("ventas") if isinstance(data, dict) else None
        if isinstance(ventas, list) and len(ventas) == 0:
            print("[ASSERT] Read returned 0 rows: OK")
            return True
    except Exception:
        pass
    print("[ASSERT] Unexpected read result: FAIL")
    return False

def main():
    base = read_env("QA_BASE_URL", default="http://localhost:8000")
    token = read_env("QA_USER_TOKEN", required=True)
    business_id_a = read_env("QA_BUSINESS_ID_A", required=True)
    branch_assigned = read_env("QA_BRANCH_ASSIGNED_ID", required=True)
    branch_unassigned = read_env("QA_BRANCH_UNASSIGNED_ID", required=True)
    other_business_id = read_env("QA_BUSINESS_ID_B", required=False)

    item_kind = read_env("QA_ITEM_KIND", default="servicio")  # 'producto' or 'servicio'
    item_id = read_env("QA_ITEM_ID", required=True)
    qty = int(read_env("QA_ITEM_QTY", default="1"))
    price = float(read_env("QA_ITEM_PRICE", default="100.0"))

    missing = [n for n in ["QA_USER_TOKEN","QA_BUSINESS_ID_A","QA_BRANCH_ASSIGNED_ID","QA_BRANCH_UNASSIGNED_ID","QA_ITEM_ID"] if not os.getenv(n)]
    if missing:
        print(f"[CONFIG] Missing required env vars: {', '.join(missing)}")
        print("Set them, e.g.:")
        print("  set QA_BASE_URL=http://localhost:8000")
        print("  set QA_USER_TOKEN=Bearer eyJhbGciOi...")
        print("  set QA_BUSINESS_ID_A=...")
        print("  set QA_BRANCH_ASSIGNED_ID=...")
        print("  set QA_BRANCH_UNASSIGNED_ID=...")
        print("  set QA_ITEM_KIND=servicio")
        print("  set QA_ITEM_ID=...")
        print("  set QA_ITEM_QTY=1")
        print("  set QA_ITEM_PRICE=100.0")
        print("Optional for cross-negocio read denial:")
        print("  set QA_BUSINESS_ID_B=...")
        sys.exit(2)

    print("\n=== QA CONFIG ===")
    safe_token = (token[:10] + "...") if token else "None"
    print(f"BASE_URL={base}")
    print(f"BUSINESS_ID_A={business_id_a}")
    print(f"BRANCH_ASSIGNED_ID={branch_assigned}")
    print(f"BRANCH_UNASSIGNED_ID={branch_unassigned}")
    print(f"ITEM_KIND={item_kind} ITEM_ID={item_id} QTY={qty} PRICE={price}")
    print(f"TOKEN={safe_token}")
    if other_business_id:
        print(f"BUSINESS_ID_B={other_business_id}")
    else:
        print("BUSINESS_ID_B not set; cross-negocio read test will be skipped.")

    start = time.time()
    ok1 = test_write_success(base, business_id_a, branch_assigned, token, item_kind, item_id, qty, price)
    ok2 = test_write_failure(base, business_id_a, branch_unassigned, token, item_kind, item_id, qty, price)
    if other_business_id:
        ok3 = test_cross_business_read_denial(base, other_business_id, token)
    else:
        ok3 = True

    elapsed = time.time() - start
    print(f"\n=== QA SUMMARY (took {elapsed:.2f}s) ===")
    print(f"Write success on assigned branch: {'OK' if ok1 else 'FAIL'}")
    print(f"Write failure on unassigned branch: {'OK' if ok2 else 'FAIL'}")
    if other_business_id:
        print(f"Cross-negocio read denial: {'OK' if ok3 else 'FAIL'}")
    else:
        print("Cross-negocio read denial: SKIPPED")

    all_ok = ok1 and ok2 and ok3
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()