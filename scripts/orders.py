"""주문 시트 → 미출고(출고 대기) 수량.

품고 `/wms/operations` 는 **실제 출고가 끝난 뒤에야** 행을 쓴다(2026-09-11 실측:
13:43 지시 → 15:12 출고 건이, 그 사이 3분 간격 24회 조회에서 한 번도 안 잡힘).
그래서 품고 화면의 '출고 후 예상재고'를 API 로 실시간 재현할 수 없다.

대신 우리 주문 시트에서 아직 안 나간 주문을 세서 총재고에서 뺀다.
품고보다 이르게(출고 지시 전, 주문 시점) 잡히므로 품고 화면 숫자와는 다를 수 있고,
판매 가능 재고 판단에는 이쪽이 더 보수적이다.

  주문캐시     (스마트스토어) 발송일 공란 + 취소/반품/교환 아닌 건 → 옵션키·수량 그대로
  Cafe24주문   주문상태 N10/N20/N21/N22(출고 전) → 상품번호·옵션값으로 옵션키 환산
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import sheets

ORDER_TAB = "주문캐시"
CAFE24_TAB = "Cafe24주문"

# Cafe24 출고 전 상태(= 재고를 잡아먹는 상태). N00 입금전·N30 배송중·N40 배송완료 제외,
# C* 취소 · R* 반품 · E* 교환 제외.
CAFE24_PENDING = {"N10", "N20", "N21", "N22"}
# 스마트스토어: 발송일이 비었어도 아래 문구가 들어간 상태는 재고를 안 잡는다.
NAVER_DEAD = ("취소", "반품", "교환")

COLORS = {"그레이": "그레이", "브라운": "브라운", "그린": "그린"}


def _to_int(v, d: int = 0) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return d


def cafe24_option_key(product_no: str, product_name: str, option_text: str) -> Optional[str]:
    """Cafe24 (상품번호, 상품명, 옵션값만) → Even 옵션키.

      11 Even G2           "G2 A타입 라운드프레임|그레이"          → G2 A 그레이
      13 G2 Clip & Pouch   "G2 B타입 스퀘어프레임|그레이"          → 클립 B 그레이
      12 Even R1           "10|사이징 키트 없이 바로 구매"         → R1 10
      12 Even R1           "사이징 키트 수령 후 결정 (권장)|..."   → R1 사이즈키트
    """
    parts = [p.strip() for p in str(option_text or "").split("|") if p.strip()]
    if not parts:
        return None
    head = parts[0]
    name = str(product_name or "")
    pno = str(product_no or "").strip()

    if pno == "12" or "R1" in name:
        if head.isdigit():
            return f"R1 {int(head)}"
        if "사이징" in head or "키트" in head:
            return "R1 사이즈키트"
        return None

    fam = "클립" if (pno == "13" or "clip" in name.lower()) else "G2"
    kind = "A" if "A타입" in head else ("B" if "B타입" in head else None)
    color = next((c for c in COLORS if any(c in p for p in parts[1:])), None)
    if not kind or not color:
        return None
    return f"{fam} {kind} {color}"


def _rows(sh, tab: str) -> List[Dict[str, Any]]:
    grid = sh.worksheet(tab).get_all_values()
    if len(grid) < 2:
        return []
    head = grid[0]
    return [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in grid[1:] if any(r)]


def pending_out(sheet_id: str, creds_info: Optional[Dict[str, Any]] = None,
                order_tab: str = ORDER_TAB, cafe24_tab: str = CAFE24_TAB) -> Dict[str, int]:
    """Even 옵션키 → 아직 안 나간 주문 수량. 두 탭 중 하나가 없으면 그쪽만 건너뛴다."""
    # 예외는 삼키지 않는다 — 탭 이름·헤더가 바뀌면 조용히 0 이 되는 게 제일 위험하다.
    sh = sheets.open_sheet(sheet_id, creds_info or None)
    pending: Dict[str, int] = {}

    for r in _rows(sh, order_tab):
        if str(r.get("발송일", "")).strip():
            continue
        if any(x in str(r.get("주문상태", "")) for x in NAVER_DEAD):
            continue
        opt = str(r.get("옵션키", "")).strip()
        if opt:
            pending[opt] = pending.get(opt, 0) + _to_int(r.get("수량"), 0)

    for r in _rows(sh, cafe24_tab):
        if str(r.get("주문상태", "")).strip() not in CAFE24_PENDING:
            continue
        opt = cafe24_option_key(r.get("상품번호"), r.get("상품명"),
                                r.get("옵션값만") or r.get("옵션"))
        if opt:
            pending[opt] = pending.get(opt, 0) + _to_int(r.get("수량"), 0)

    return pending
