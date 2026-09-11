"""품고 재고 2시간마다 수집 → Even 스프레드시트 '품고재고' 탭에 스냅샷 append.

사무실 맥에서 launchd(2h)로 실행. env 필요:
  POOMGO_TOKEN          품고 API 토큰
  EVEN_SHEET_ID         Even 스프레드시트 ID
  GSHEET_SA_TOML/KEY    서비스 계정 (ring_verify 와 동일 재사용)

'품고재고' 탭(wide): [수집시각, R1 6, ..., 클립 B 그린] = 총재고 — 실행마다 한 행 추가.
'출고후재고' 탭: 같은 구조로 출고 후 예상재고(총재고 - 미출고 할당) 스냅샷.
앱은 평소 품고 API 를 실시간으로 읽고, 이 탭들은 추이·폴백용이다.
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import poomgo
import sheets

STOCK_TAB = os.environ.get("EVEN_POOMGO_TAB", "품고재고")
EXPECTED_TAB = os.environ.get("EVEN_EXPECTED_TAB", "출고후재고")
KST = datetime.timezone(datetime.timedelta(hours=9))


def main() -> None:
    token = os.environ.get("POOMGO_TOKEN") or sys.exit("ERROR: POOMGO_TOKEN 미설정")
    sheet_id = os.environ.get("EVEN_SHEET_ID") or sys.exit("ERROR: EVEN_SHEET_ID 미설정")

    stock, pending, expected = poomgo.fetch_stock_all(token)
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    sh = sheets.open_sheet(sheet_id)
    headers = ["수집시각"] + poomgo.EVEN_OPTION_ORDER
    for tab, data in ((STOCK_TAB, stock), (EXPECTED_TAB, expected)):
        ws = sheets.get_or_create_tab(sh, tab, headers)
        # 헤더가 비어 있으면(빈 탭) 채운다
        if not (ws.row_values(1) or []):
            ws.update([headers], "A1", value_input_option="RAW")
        row = [stamp] + [data[opt] for opt in poomgo.EVEN_OPTION_ORDER]
        ws.append_row(row, value_input_option="USER_ENTERED")

    print(f"[{stamp}] 스냅샷 기록 — 총재고 {sum(stock.values())}개 / "
          f"미출고 {sum(pending.values())}개 / 출고후 {sum(expected.values())}개 / SKU {len(stock)}종")


if __name__ == "__main__":
    main()
