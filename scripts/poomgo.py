"""품고(Poomgo) WMS Open API 클라이언트 — Even 전용.

  재고조회  POST /open-api/wms/resources/quantity-at   (시점 총재고, 재고 있는 것만)
  재고변동  POST /open-api/wms/operations              (IN/OUT/MV 원장 — 미출고 할당 계산용)
  SKU목록   POST /open-api/wms/resources               (전체 등록 SKU)
  입고등록  PUT  /open-api/wms/receiving-sheets
  입고취소  DELETE /open-api/wms/receiving-sheets/{id}

품고 화면의 '출고 후 예상재고' = 총재고 - 미출고 할당.
미출고 할당 = operations 의 OUT 중 created_at(출고지시) <= 지금 < execute_at(실제출고).

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


def _get(token: str, path: str, params: dict, timeout: int = 30) -> Any:
    url = f"{BASE}{path}"
    resp = requests.get(url, headers=_headers(token), params=params, timeout=timeout)
    if resp.status_code in (401, 403) and not token.lower().startswith("bearer "):
        resp = requests.get(url, headers=_headers(f"Bearer {token}"), params=params, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"poomgo GET {path} -> {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.text else {}


def list_resources(token: str) -> List[Dict[str, Any]]:
    """등록된 전체 SKU 목록(재고 유무 무관)."""
    data = _post(token, "/resources", {"page": 1, "pageSize": 200})
    return data.get("rows") or data.get("collection") or []


def list_receivings(token: str, page_size: int = 50) -> List[Dict[str, Any]]:
    """최근 입고예정서 목록 — Even SKU 가 포함된 건만 최신순으로."""
    data = _get(token, "/receiving-sheets", {"page": 1, "pageSize": page_size})
    rows = data.get("rows") or data.get("collection") or []
    even = set(EVEN_SKU_BY_CODE.keys())
    out = []
    for r in rows:
        res = r.get("resources") or []
        if any(str(x.get("barcode", "")).strip() in even for x in res):
            out.append(r)
    return out


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def fetch_stock(token: str) -> Dict[str, int]:
    """Even 옵션키 → 총재고(로케이션 실물 합). 재고 0 도 0 으로 채운다.

    품고 시점재고 DB 는 UTC 기준이라 executeAt 도 UTC 로 보낸다.
    """
    body = {"page": 1, "pageSize": 500,
            "executeAt": _utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")}
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


def fetch_pending_out(token: str, days: int = 10) -> Dict[str, int]:
    """Even 옵션키 → 미출고 할당 수량(출고 지시는 났고 아직 안 나간 것).

    품고 SKU별재고조회 화면의 (총재고 - 출고 후 예상재고) 와 같은 값.
    Even 실측 기준 지시→출고 간격 중앙값 12.8시간, 최대 41시간이라 days=10 이면 충분.
    """
    now = _utcnow()
    cut = now.strftime("%Y-%m-%dT%H:%M:%S")
    window = {"$gte": (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
              "$lte": (now + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")}
    pending = {opt: 0 for opt in EVEN_OPTION_ORDER}
    page, seen, total = 1, 0, None
    while True:
        data = _post(token, "/operations",
                     {"page": page, "pageSize": 200, "createdAt": window})
        rows = data.get("rows") or []
        if total is None:
            total = int(data.get("total") or 0)
        for it in rows:
            if it.get("type") != "OUT":
                continue
            opt = EVEN_SKU_BY_CODE.get(str(it.get("resource_code", "")).strip())
            if not opt:
                continue
            created = str(it.get("created_at") or "")[:19]
            executed = str(it.get("execute_at") or "")[:19] or "9999"
            if created <= cut < executed:            # 지시됨 + 아직 미출고
                pending[opt] += int(it.get("quantity") or 0)
        seen += len(rows)
        if not rows or seen >= total:
            break
        page += 1
    return pending


def fetch_stock_all(token: str):
    """(총재고, 미출고할당, 출고 후 예상재고) 3종을 한 번에."""
    total = fetch_stock(token)
    pending = fetch_pending_out(token)
    expected = {o: total.get(o, 0) - pending.get(o, 0) for o in EVEN_OPTION_ORDER}
    return total, pending, expected


def create_receiving(token: str, *, name: str, depart_at: str, arrive_at: str,
                     schedule_form_code_key: str, delivery_type: str,
                     pallet_count: int, box_count: int,
                     destination_warehouse: str,
                     resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """입고등록(입고예정서 생성). resources = [{code, quantity, ...}] 형식."""
    # 창고 코드가 비었거나 'null'이면 실제 null 로 보낸다(PLAUD 계정과 동일 구조)
    dw = destination_warehouse
    if not dw or str(dw).strip().lower() in ("null", "none"):
        dw = None
    payload = {
        "name": name, "depart_at": depart_at, "arrive_at": arrive_at,
        "schedule_form_code_key": schedule_form_code_key, "delivery_type": delivery_type,
        "pallet_count": pallet_count, "box_count": box_count,
        "destination_warehouse": dw, "resources": resources,
    }
    return _post(token, "/receiving-sheets", payload, method="PUT", timeout=180)


def cancel_receiving(token: str, receiving_id: str) -> None:
    _post(token, f"/receiving-sheets/{receiving_id}", {}, method="DELETE", timeout=60)
