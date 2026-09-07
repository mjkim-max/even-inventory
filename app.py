"""Even 재고 대시보드 (Streamlit).

  재고수량      ← 품고재고 탭(2h 스냅샷)의 마지막 행
  일평균 출고량  ← 기존 Even 스프레드시트 '매출' 탭 (최근 N일 판매량 평균)
  입고등록      → 품고 receiving-sheets API

시크릿(.streamlit/secrets.toml):
  [poomgo] token, receiving.*(창고·배송 파라미터)
  [even] sheet_id, poomgo_tab, sales_tab
  [google_sheets_service_account] {...}
"""
from __future__ import annotations

import datetime
from typing import Dict, List

import streamlit as st

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
import poomgo
import sheets

KST = datetime.timezone(datetime.timedelta(hours=9))
SHEET_BASE = datetime.date(1899, 12, 30)


def _cfg():
    even = st.secrets.get("even", {})
    return {
        "token": st.secrets.get("poomgo", {}).get("token", ""),
        "sheet_id": even.get("sheet_id", ""),
        "poomgo_tab": even.get("poomgo_tab", "품고재고"),
        "sales_tab": even.get("sales_tab", "매출"),
        "sa": dict(st.secrets.get("google_sheets_service_account", {})),
        "recv": dict(st.secrets.get("poomgo", {}).get("receiving", {})),
    }


def _col(idx: int) -> str:
    s, idx = "", idx + 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _to_int(v, d=0):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return d


@st.cache_data(ttl=300)
def load_stock(sheet_id: str, tab: str, sa: dict):
    """품고재고 탭 마지막 행 → {옵션키: 재고}, 수집시각."""
    sh = sheets.open_sheet(sheet_id, sa or None)
    ws = sh.worksheet(tab)
    vals = ws.get_all_values()
    if len(vals) < 2:
        return {}, ""
    header, last = vals[0], vals[-1]
    stamp = last[0]
    stock = {}
    for i, h in enumerate(header[1:], 1):
        if h.strip():
            stock[h.strip()] = _to_int(last[i]) if i < len(last) else 0
    return stock, stamp


@st.cache_data(ttl=300)
def load_daily_avg(sheet_id: str, tab: str, sa: dict, days: int = 14) -> Dict[str, float]:
    """매출 탭 → 옵션키별 최근 N일 판매량 평균."""
    sh = sheets.open_sheet(sheet_id, sa or None)
    ws = sh.worksheet(tab)
    grid = ws.get_values("A10:C200")
    rowmap = {}
    fam = ""
    for i, r in enumerate(grid):
        r = (r + ["", "", ""])[:3]
        fam = r[0].strip() or fam
        sub, kind = r[1].strip(), r[2].strip()
        if kind != "판매량" or not fam or not sub:
            continue
        key = f"R1 {sub.replace(' ', '')}" if fam == "R1" else f"{fam} {sub}"
        rowmap[10 + i] = key
    if not rowmap:
        return {}
    header = ws.get_values("E1:NE1", value_render_option="UNFORMATTED_VALUE")[0]
    base = SHEET_BASE + datetime.timedelta(days=_to_int(header[0]))
    today = datetime.datetime.now(KST).date()
    end = min(len(header) - 1, (today - base).days)
    start = max(0, end - days + 1)
    if end < start:
        return {}
    c0, c1 = _col(4 + start), _col(4 + end)
    last_row = max(rowmap)
    data = ws.get_values(f"{c0}2:{c1}{last_row}", value_render_option="UNFORMATTED_VALUE")
    ndays = end - start + 1
    out = {}
    for r, key in rowmap.items():
        row = data[r - 2] if r - 2 < len(data) else []
        total = sum(_to_int(x) for x in row)
        out[key] = round(total / ndays, 2)
    return out


# ── 화면 ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Even 재고 대시보드", layout="wide")
st.title("Even 재고 대시보드")

cfg = _cfg()
if not cfg["token"] or not cfg["sheet_id"]:
    st.error("secrets 에 [poomgo] token 과 [even] sheet_id 를 설정하세요.")
    st.stop()

try:
    stock, stamp = load_stock(cfg["sheet_id"], cfg["poomgo_tab"], cfg["sa"])
except Exception as e:
    stock, stamp = {}, ""
    st.warning(f"품고재고 탭을 못 읽었습니다: {e}")
try:
    avg = load_daily_avg(cfg["sheet_id"], cfg["sales_tab"], cfg["sa"])
except Exception as e:
    avg = {}
    st.warning(f"매출 탭을 못 읽었습니다: {e}")

st.caption(f"품고 재고 수집: {stamp or '아직 없음'}  ·  일평균 출고량: 매출 탭 최근 14일 기준")

rows = []
for opt in poomgo.EVEN_OPTION_ORDER:
    qty = stock.get(opt, 0)
    a = avg.get(opt, 0.0)
    days_left = round(qty / a, 1) if a > 0 else None
    rows.append({"품목(옵션)": opt, "재고수량": qty, "일평균 출고량": a,
                 "소진 예상일수": days_left if days_left is not None else "—"})
st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("품고 입고등록")
with st.form("receiving"):
    name = st.text_input("입고명(name)", value=f"Even 입고 {datetime.date.today()}")
    c1, c2 = st.columns(2)
    depart = c1.date_input("출고일(depart_at)", value=datetime.date.today())
    arrive = c2.date_input("도착예정일(arrive_at)", value=datetime.date.today())
    c3, c4 = st.columns(2)
    pallet = c3.number_input("파렛트 수", min_value=0, value=0, step=1)
    box = c4.number_input("박스 수", min_value=0, value=1, step=1)
    st.markdown("**입고 수량** (0 은 제외됩니다)")
    qty_inputs = {}
    cols = st.columns(4)
    for i, opt in enumerate(poomgo.EVEN_OPTION_ORDER):
        qty_inputs[opt] = cols[i % 4].number_input(opt, min_value=0, value=0, step=1, key=f"q_{opt}")
    submitted = st.form_submit_button("품고에 입고등록")

if submitted:
    resources = [{"code": poomgo.EVEN_CODE_BY_OPTION[opt], "quantity": int(q)}
                 for opt, q in qty_inputs.items() if int(q) > 0]
    if not resources:
        st.error("입고 수량을 하나 이상 입력하세요.")
    else:
        recv = cfg["recv"]
        try:
            res = poomgo.create_receiving(
                cfg["token"],
                name=name,
                depart_at=str(depart), arrive_at=str(arrive),
                schedule_form_code_key=recv.get("schedule_form_code_key", ""),
                delivery_type=recv.get("delivery_type", ""),
                pallet_count=int(pallet), box_count=int(box),
                destination_warehouse=recv.get("destination_warehouse", ""),
                resources=resources,
            )
            st.success(f"입고등록 완료: {res}")
        except Exception as e:
            st.error(f"입고등록 실패: {e}")
