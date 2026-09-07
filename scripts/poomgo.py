"""품고(Poomgo) WMS Open API 클라이언트 — Even 전용.

  재고조회  POST /open-api/wms/resources/quantity-at   (재고 있는 것만)
  SKU목록   POST /open-api/wms/resources               (전체 등록 SKU)
  입고등록  PUT  /open-api/wms/receiving-sheets
  입고취소  DELETE /open-api/wms/receiving-sheets/{id}

토큰은 코드에 넣지 않는다 — 환경변수 POOMGO_TOKEN 또는 secrets 로 주입.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List

import requests

BASE = "https://api.poomgo.com/open-api/wms"

# 품고 SKU code → Even 옵션키 (재고입력/주문캐시 옵션키와 동일 표기)
EVEN_SKU_BY_CODE: Dict[str, str] = {
    "6977390120608": "R1 6", "6977390120615": "R1 7", "6977390120622": "R1 8",
    "6977390120639": "R1 9", "6977390120646": "R1 10", "6977390120653": "R1 11",
    "6977390120660": "R1 12", "6977390120677": "R1 13", "6977390120684": "R1 14",
    "6977390120691": "R1 15",
    "6977390120844": "R1 사이즈키트",
    "6977390120400": "G2 A 그레이", "6977390120417": "G2 A 브라운", "6977390120424": "G2 A 그린",
    "6977390120431": "G2 B 그레이", "6977390120448": "G2 B 브라운", "6977390120455": "G2 B 그린",
    "6977390120462": "클립 A 그레이", "6977390120479": "클립 A 브라운", "6977390120486": "클립 A 그린",
    "6977390120493": "클립 B 그레이", "6977390120509": "클립 B 브라운", "6977390120516": "클립 B 그린",
}
# 대시보드 표시 순서
EVEN_OPTION_ORDER: List[str] = list(dict.fromkeys(EVEN_SKU_BY_CODE.values()))
EVEN_CODE_BY_OPTION: Dict[str, str] = {v: k for k, v in EVEN_SKU_BY_CODE.items()}


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": token}


def _post(token: str, path: str, body: dict, method: str = "POST", timeout: int = 30) -> Any:
    """401/403 이면 Bearer 접두어를 붙여 한 번 더 시도."""
    url = f"{BASE}{path}"
    resp = requests.request(method, url, headers=_headers(token), json=body, timeout=timeout)
    if resp.status_code in (401, 403) and not token.lower().startswith("bearer "):
        resp = requests.request(method, url, headers=_headers(f"Bearer {token}"),
                                json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"poomgo {method} {path} -> {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.text else {}


def list_resources(token: str) -> List[Dict[str, Any]]:
    """등록된 전체 SKU 목록(재고 유무 무관)."""
    data = _post(token, "/resources", {"page": 1, "pageSize": 200})
    return data.get("rows") or data.get("collection") or []


def fetch_stock(token: str) -> Dict[str, int]:
    """Even 옵션키 → 현재 재고 수량. 재고 0(quantity-at 에 없음)도 0 으로 채운다."""
    body = {"page": 1, "pageSize": 200, "executeAt": datetime.datetime.now().isoformat()}
    data = _post(token, "/resources/quantity-at", body)
    rows = data.get("rows") or data.get("collection") or data.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("collection") or rows.get("items") or []
    stock = {opt: 0 for opt in EVEN_OPTION_ORDER}   # 전 SKU 0 으로 시작
    for it in rows:
        code = str(it.get("code", "")).strip()
        opt = EVEN_SKU_BY_CODE.get(code)
        if not opt:
            continue
        qty = it.get("result_quantity")
        if qty is None:
            for k in ("available_quantity", "availableQuantity", "total_quantity",
                      "totalQuantity", "quantity"):
                if k in it:
                    qty = it.get(k)
                    break
        try:
            stock[opt] += int(float(qty))
        except (TypeError, ValueError):
            pass
    return stock


def create_receiving(token: str, *, name: str, depart_at: str, arrive_at: str,
                     schedule_form_code_key: str, delivery_type: str,
                     pallet_count: int, box_count: int,
                     destination_warehouse: str,
                     resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """입고등록(입고예정서 생성). resources = [{code, quantity, ...}] 형식."""
    payload = {
        "name": name, "depart_at": depart_at, "arrive_at": arrive_at,
        "schedule_form_code_key": schedule_form_code_key, "delivery_type": delivery_type,
        "pallet_count": pallet_count, "box_count": box_count,
        "destination_warehouse": destination_warehouse, "resources": resources,
    }
    return _post(token, "/receiving-sheets", payload, method="PUT", timeout=180)


def cancel_receiving(token: str, receiving_id: str) -> None:
    _post(token, f"/receiving-sheets/{receiving_id}", {}, method="DELETE", timeout=60)
