"""발주(PO) 탭 → 아직 입고 안 된 PO 별 SKU 수량.

탭 구조(가로): 번호 | 날짜 | 입고여부 | PO명 | 합계 | SKU 26종 | 비고
  - '번호'가 빈 행(총 수량 합계 행)은 건너뛴다.
  - 입고여부가 '입고'인 PO 는 제외 — 나머지가 앞으로 들어올 물량.
  - 차수는 합치지 않고 PO 하나씩 돌려준다(대시보드에서 차수별 열로 보여줌).
  - 충전독·링차저처럼 대시보드 옵션키에 없는 SKU 는 버린다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import sheets

PO_TAB = "발주(PO)"
COLOR = {"grey": "그레이", "gray": "그레이", "brown": "브라운", "green": "그린"}


def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def option_key(header: str) -> Optional[str]:
    """PO 탭 SKU 머리글 → 대시보드 옵션키.
      'G2 A Grey' → 'G2 A 그레이' · '클립 B Green' → '클립 B 그린'
      'R1 No.6' → 'R1 6' · 'R1 사이즈키트' → 'R1 사이즈키트'
    """
    h = " ".join(str(header).split())
    if h == "R1 사이즈키트":
        return h
    m = re.fullmatch(r"R1 No\.?\s*(\d+)", h)
    if m:
        return f"R1 {int(m.group(1))}"
    m = re.fullmatch(r"(G2|클립) ([AB]) (\w+)", h)
    if m and m.group(3).lower() in COLOR:
        return f"{m.group(1)} {m.group(2)} {COLOR[m.group(3).lower()]}"
    return None


def incoming(sheet_id: str, creds_info: Optional[Dict[str, Any]] = None,
             valid: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """미입고 PO 목록(날짜순). 각 원소: {번호, 날짜, PO명, 비고, 수량: {옵션키: n}}."""
    sh = sheets.open_sheet(sheet_id, creds_info or None)
    grid = sh.worksheet(PO_TAB).get_all_values()
    hi = next((i for i, r in enumerate(grid) if r and r[0].strip() == "번호"), None)
    if hi is None:
        raise RuntimeError(f"{PO_TAB}: '번호' 머리글 행을 못 찾음")
    head = [h.strip() for h in grid[hi]]
    col = {h: i for i, h in enumerate(head) if h}
    for need in ("번호", "날짜", "입고여부", "PO명"):
        if need not in col:
            raise RuntimeError(f"{PO_TAB}: '{need}' 열 없음 — 머리글 확인")
    sku_cols = [(i, option_key(h)) for i, h in enumerate(head)]
    sku_cols = [(i, k) for i, k in sku_cols if k and (valid is None or k in valid)]

    out = []
    for r in grid[hi + 1:]:
        r = r + [""] * (len(head) - len(r))
        if not r[col["번호"]].strip():
            continue                                  # 총 수량 합계 행 등
        if r[col["입고여부"]].strip() == "입고":
            continue
        qty = {k: _to_int(r[i]) for i, k in sku_cols if _to_int(r[i])}
        if not qty:
            continue
        out.append({"번호": r[col["번호"]].strip(), "날짜": r[col["날짜"]].strip(),
                    "PO명": r[col["PO명"]].strip(),
                    "비고": r[col["비고"]].strip() if "비고" in col else "",
                    "수량": qty})
    out.sort(key=lambda p: (p["날짜"], _to_int(p["번호"])))
    return out
