"""주문 시트 → 미출고(출고 대기) 수량.

품고 `/wms/operations` 는 **실제 출고가 끝난 뒤에야** 행을 쓴다(2026-09-11 실측:
13:43 지시 → 15:12 출고 건이, 그 사이 3분 간격 24회 조회에서 한 번도 안 잡힘).
그래서 품고 화면의 '출고 후 예상재고'를 API 로 실시간 재현할 수 없다.

대신 우리 시트에서 아직 안 나간 물량을 세서 총재고에서 뺀다.
품고보다 이르게(출고 지시 전) 잡히므로 품고 화면 숫자와는 다를 수 있다.

  주문캐시            발송일 공란 + 취소/반품/교환 아닌 건 → 옵션키·수량 그대로.
                      스마트스토어 + Cafe24 가 함께 들어 있다(ring_verify 가 Cafe24주문 탭을
                      같은 형식으로 합쳐 넣음) — Cafe24주문 탭을 따로 읽으면 이중 차감된다.
  설문지 응답 시트1   사이즈키트 구매자가 폼으로 확정한 링 호수. 출고여부 '출고가능' +
                      송장 열 공란 → R1 {호수} 1개씩. 품고 링 업로드·링 송장 양식과 같은 조건.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import sheets

ORDER_TAB = "주문캐시"
FORM_TAB = "설문지 응답 시트1"

# 발송일이 비었어도 아래 문구가 들어간 상태는 재고를 안 잡는다.
DEAD_STATUS = ("취소", "반품", "교환")
RING_SIZES = {str(n) for n in range(6, 16)}


def _to_int(v, d: int = 0) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return d


def _add(pending: Dict[str, int], opt: str, qty: int) -> None:
    pending[opt] = pending.get(opt, 0) + qty


def _grid(sh, tab: str) -> List[List[str]]:
    return sh.worksheet(tab).get_all_values()


def _order_pending(grid: List[List[str]], pending: Dict[str, int]) -> None:
    if len(grid) < 2:
        return
    head = grid[0]
    for r in grid[1:]:
        row = dict(zip(head, r + [""] * (len(head) - len(r))))
        if str(row.get("발송일", "")).strip():
            continue
        if any(x in str(row.get("주문상태", "")) for x in DEAD_STATUS):
            continue
        opt = str(row.get("옵션키", "")).strip()
        if opt:
            _add(pending, opt, _to_int(row.get("수량"), 0))


def _form_pending(grid: List[List[str]], pending: Dict[str, int]) -> None:
    """설문지: 출고가능 + 송장 공란 → R1 {호수}.

    송장 열은 머리글이 비어 있어서 '송장입력일시' 바로 왼쪽 열로 찾는다
    (ring_verify 도 같은 배치: 송장 N · 송장입력일시 O). 열이 밀려도 따라간다.
    """
    if len(grid) < 2:
        return
    head = [h.strip() for h in grid[0]]
    size_i = next((i for i, h in enumerate(head) if "호수" in h), -1)
    verdict_i = head.index("출고여부") if "출고여부" in head else -1
    ts_i = head.index("송장입력일시") if "송장입력일시" in head else -1
    if min(size_i, verdict_i, ts_i) < 1:
        raise RuntimeError(f"{FORM_TAB}: 호수/출고여부/송장입력일시 열을 못 찾음 — 머리글 확인")
    ship_i = ts_i - 1
    for r in grid[1:]:
        r = r + [""] * (len(head) - len(r))
        if not r[verdict_i].strip().startswith("출고가능"):
            continue
        if r[ship_i].strip():
            continue
        size = "".join(re.findall(r"\d+", r[size_i]))
        if size in RING_SIZES:
            _add(pending, f"R1 {size}", 1)


def pending_out(sheet_id: str, creds_info: Optional[Dict[str, Any]] = None,
                order_tab: str = ORDER_TAB, form_tab: str = FORM_TAB) -> Dict[str, int]:
    """Even 옵션키 → 아직 안 나간 수량(주문캐시 + 설문지 확정 링)."""
    # 예외는 삼키지 않는다 — 탭 이름·머리글이 바뀌면 조용히 0 이 되는 게 제일 위험하다.
    sh = sheets.open_sheet(sheet_id, creds_info or None)
    pending: Dict[str, int] = {}
    _order_pending(_grid(sh, order_tab), pending)
    _form_pending(_grid(sh, form_tab), pending)
    return pending


def pending_by_source(sheet_id: str, creds_info: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, int]]:
    """확인용 — 소스별로 나눠서."""
    sh = sheets.open_sheet(sheet_id, creds_info or None)
    a: Dict[str, int] = {}
    b: Dict[str, int] = {}
    _order_pending(_grid(sh, ORDER_TAB), a)
    _form_pending(_grid(sh, FORM_TAB), b)
    return {ORDER_TAB: a, FORM_TAB: b}
