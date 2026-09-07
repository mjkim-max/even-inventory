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
import pandas as pd
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


def _family(opt: str) -> str:
    if opt.startswith("G2 "):
        return "G2"
    if opt.startswith("클립 "):
        return "클립"
    return "R1"


EVEN_FAMILIES = ["G2", "R1", "클립"]


def _tbl_height(n_rows: int) -> int:
    """행 수만큼 높이를 줘서 표 내부 스크롤이 안 생기게 한다(헤더 + 행*35)."""
    return (n_rows + 1) * 35 + 3

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

def _family_rows(fam: str):
    out = []
    for opt in poomgo.EVEN_OPTION_ORDER:
        if _family(opt) != fam:
            continue
        qty = stock.get(opt, 0)
        a = avg.get(opt, 0.0)
        days_left = round(qty / a, 1) if a > 0 else None
        out.append({"품목": opt[len(fam):].strip() or opt, "재고": qty,
                    "일평균": a, "소진일수": days_left if days_left is not None else "—"})
    return out

fam_cols = st.columns(len(EVEN_FAMILIES))       # G2 · R1 · 클립 표 3개 나란히
for col, fam in zip(fam_cols, EVEN_FAMILIES):
    with col:
        st.markdown(f"**{fam}**")
        fr = _family_rows(fam)
        st.dataframe(fr, use_container_width=True, hide_index=True, height=_tbl_height(len(fr)))

st.divider()
st.subheader("품고 입고등록")
c1, c2, c3 = st.columns(3)
name = c1.text_input("입고명", value=f"Even 입고 {datetime.date.today()}")
arrive = c2.date_input("도착예정일", value=datetime.date.today())
box = c3.number_input("박스 수", min_value=0, value=1, step=1)

# G2 · R1 · 클립 표 3개 나란히 — 각 표에서 입고수량 셀에 직접 입력(+/- 없음)
edited = {}
qty_conf = {"입고수량": st.column_config.NumberColumn("입고수량", min_value=0, step=1)}
in_cols = st.columns(len(EVEN_FAMILIES))
for col, fam in zip(in_cols, EVEN_FAMILIES):
    with col:
        st.markdown(f"**{fam}**")
        opts = [o for o in poomgo.EVEN_OPTION_ORDER if _family(o) == fam]
        df = pd.DataFrame({"품목명": [o[len(fam):].strip() or o for o in opts],
                           "_opt": opts, "입고수량": [0] * len(opts)})
        ed = st.data_editor(df, key=f"ed_{fam}", hide_index=True, use_container_width=True,
                            column_config=qty_conf, disabled=["품목명"],
                            column_order=["품목명", "입고수량"], height=_tbl_height(len(opts)))
        edited[fam] = ed

_sp, _btn = st.columns([6, 1])       # 우하단으로 밀기
if _btn.button("저장", type="primary", use_container_width=True):
    resources = []
    for fam, ed in edited.items():
        for _, row in ed.iterrows():
            q = int(row["입고수량"] or 0)
            if q > 0:
                resources.append({"barcode": poomgo.EVEN_CODE_BY_OPTION[row["_opt"]], "quantity": q})
    if not resources:
        st.error("입고 수량을 하나 이상 입력하세요.")
    else:
        recv = cfg["recv"]
        try:
            poomgo.create_receiving(
                cfg["token"], name=name,
                depart_at=str(datetime.date.today()), arrive_at=str(arrive),
                schedule_form_code_key=recv.get("schedule_form_code_key", ""),
                delivery_type=recv.get("delivery_type", ""),
                pallet_count=0, box_count=int(box),
                destination_warehouse=recv.get("destination_warehouse", ""),
                resources=resources,
            )
            st.success("입고등록 완료")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"입고등록 실패: {e}")

st.divider()
st.subheader("최근 입고내역")
try:
    recvs = poomgo.list_receivings(cfg["token"], page_size=50)[:15]
except Exception as e:
    recvs = []
    st.warning(f"입고내역을 못 읽었습니다: {e}")

if not recvs:
    st.caption("Even 입고내역 없음")
def _grouped_items(resources) -> str:
    by_fam = {}
    for x in resources or []:
        opt = poomgo.EVEN_SKU_BY_CODE.get(str(x.get("barcode", "")).strip())
        if not opt:
            continue
        fam = _family(opt)
        label = opt[len(fam):].strip() or opt
        by_fam.setdefault(fam, []).append(f"{label} [{x.get('quantity')}]")
    lines = [f"**{fam}**　" + "　|　".join(by_fam[fam]) for fam in EVEN_FAMILIES if fam in by_fam]
    return "  \n".join(lines)

for r in recvs:
    rid = r.get("id")
    status = r.get("status", "")
    when = str(r.get("arrive_at") or "")[:10]
    c1, c2 = st.columns([5, 1])
    c1.markdown(f"**{r.get('name') or r.get('code') or rid}**  ·  {status}  ·  {when}  \n"
                + _grouped_items(r.get("resources")))
    if status not in ("completed", "canceled", "cancelled"):
        if c2.button("취소", key=f"cancel_{rid}"):
            try:
                poomgo.cancel_receiving(cfg["token"], str(rid))
                st.success(f"취소됨: {rid}")
                st.rerun()
            except Exception as e:
                st.error(f"취소 실패: {e}")
    else:
        c2.caption(status)
