"""품고 재고 2시간마다 수집 → Even 스프레드시트 '품고재고' 탭에 스냅샷 append.

사무실 맥에서 launchd(2h)로 실행. env 필요:
  POOMGO_TOKEN          품고 API 토큰
  EVEN_SHEET_ID         Even 스프레드시트 ID
  GSHEET_SA_TOML/KEY    서비스 계정 (ring_verify 와 동일 재사용)

'품고재고' 탭(wide): [수집시각, R1 6, ..., 클립 B 그린] = 총재고 — 실행마다 한 행 추가.
'출고후재고' 탭: 같은 구조로 가용재고(총재고 - 미출고 주문) 스냅샷.
앱은 평소 품고 API 를 실시간으로 읽고, 이 탭들은 추이·폴백용이다.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import orders
import poomgo
import sheets

STOCK_TAB = os.environ.get("EVEN_POOMGO_TAB", "품고재고")
EXPECTED_TAB = os.environ.get("EVEN_EXPECTED_TAB", "출고후재고")
KST = datetime.timezone(datetime.timedelta(hours=9))


def main() -> None:
    token = os.environ.get("POOMGO_TOKEN") or sys.exit("ERROR: POOMGO_TOKEN 미설정")
    sheet_id = os.environ.get("EVEN_SHEET_ID") or sys.exit("ERROR: EVEN_SHEET_ID 미설정")

    stock = poomgo.fetch_stock(token)
    try:
        pending = orders.pending_out(sheet_id)
    except Exception as e:                       # 주문 탭이 깨져도 총재고 스냅샷은 남긴다
        print(f"WARN 미출고 주문 집계 실패 — 출고후재고 탭 건너뜀: {e}")
        pending = None
    expected = ({o: stock[o] - (pending.get(o, 0)) for o in poomgo.EVEN_OPTION_ORDER}
                if pending is not None else None)
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    sh = sheets.open_sheet(sheet_id)
    headers = ["수집시각"] + poomgo.EVEN_OPTION_ORDER
    tabs = [(STOCK_TAB, stock)] + ([(EXPECTED_TAB, expected)] if expected is not None else [])
    for tab, data in tabs:
        ws = sheets.get_or_create_tab(sh, tab, headers)
        # 헤더가 비어 있으면(빈 탭) 채운다
        if not (ws.row_values(1) or []):
            ws.update([headers], "A1", value_input_option="RAW")
        row = [stamp] + [data[opt] for opt in poomgo.EVEN_OPTION_ORDER]
        ws.append_row(row, value_input_option="USER_ENTERED")

    print(f"[{stamp}] 스냅샷 기록 — 총재고 {sum(stock.values())}개 / "
          f"미출고 {sum(pending.values()) if pending else '—'}개 / "
          f"가용 {sum(expected.values()) if expected else '—'}개 / SKU {len(stock)}종")


if __name__ == "__main__":
    main()
