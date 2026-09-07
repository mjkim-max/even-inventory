"""Streamlit 시크릿 전체를 그대로 출력한다 — 사용자가 복사해 붙여넣기용.

맥에서 실행:  source ~/.even_ring.env; python3 print_secrets.py
서비스계정(GSHEET_SA_KEY json 또는 GSHEET_SA_TOML)과 시트ID(RING_SHEET_ID)를 읽어
[poomgo]/[even]/[google_sheets_service_account] 블록을 완성해 찍는다.
"""
import json
import os

POOMGO_TOKEN = os.environ.get("POOMGO_TOKEN", "GzDi95hy284SOW0W4Vvl")
SHEET_ID = os.environ.get("EVEN_SHEET_ID") or os.environ.get("RING_SHEET_ID", "")

# 서비스계정 로드
info = {}
p = os.environ.get("GSHEET_SA_KEY", "")
t = os.environ.get("GSHEET_SA_TOML", "")
if p and os.path.exists(os.path.expanduser(p)):
    info = json.load(open(os.path.expanduser(p), encoding="utf-8"))
elif t and os.path.exists(os.path.expanduser(t)):
    import toml
    d = toml.load(os.path.expanduser(t))
    sec = os.environ.get("GSHEET_SA_SECTION", "google_sheets_service_account")
    info = d.get(sec, d)

print("# ↓↓↓ 여기부터 전부 복사해서 Streamlit Secrets 에 붙여넣기 ↓↓↓")
print()
print("[poomgo]")
print(f'token = {json.dumps(POOMGO_TOKEN)}')
print()
print("[poomgo.receiving]")
print('destination_warehouse = "null"')
print('schedule_form_code_key = "box"')
print('delivery_type = "motorcycle"')
print()
print("[even]")
print(f'sheet_id = {json.dumps(SHEET_ID)}')
print('poomgo_tab = "품고재고"')
print('sales_tab = "매출"')
print()
print("[google_sheets_service_account]")
for k, v in info.items():
    print(f"{k} = {json.dumps(v, ensure_ascii=False)}")
print()
print("# ↑↑↑ 여기까지 복사 ↑↑↑")
