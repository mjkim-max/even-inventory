# Even 재고 대시보드

품고(Poomgo) WMS 재고를 2시간마다 수집하고, Streamlit 대시보드로 보여준다.
입고등록도 대시보드에서 품고 API로 직접 한다. 매출/출고량은 기존 Even 스프레드시트 '매출' 탭에서 읽는다.

## 구성
- `scripts/poomgo.py` — 품고 API 클라이언트(재고조회·SKU목록·입고등록) + Even SKU 매핑
- `scripts/sheets.py` — Google Sheets 헬퍼
- `scripts/stock_sync.py` — 2h 재고 수집 → '품고재고' 탭 스냅샷
- `app.py` — Streamlit 대시보드(재고 + 일평균 출고량 + 입고등록)
- `run_stock_sync.sh` — 맥 launchd 래퍼

## 재고 수집 (사무실 맥)
`~/.even_inventory.env` 에 `POOMGO_TOKEN`, `EVEN_SHEET_ID` 설정(서비스계정은 `~/.even_ring.env` 재사용).
launchd 로 2시간마다 `run_stock_sync.sh` 실행.

## 대시보드 (Streamlit Cloud)
GitHub 연결 후 `.streamlit/secrets.toml` 에 `secrets.example.toml` 참고해 값 입력.
