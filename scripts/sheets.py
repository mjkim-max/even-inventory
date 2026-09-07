"""Google Sheets 헬퍼 — 동기화 스크립트(env)와 Streamlit 앱(secrets) 양쪽에서 쓴다.

서비스 계정 자격은:
  - env:  GSHEET_SA_TOML(파일경로) 또는 GSHEET_SA_KEY(json 파일경로)
  - app:  st.secrets["google_sheets_service_account"] (dict)  → creds_info 로 직접 전달
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _creds_from_info(info: Dict[str, Any]) -> Credentials:
    info = dict(info)
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def client(creds_info: Optional[Dict[str, Any]] = None) -> gspread.Client:
    """creds_info(dict)가 오면 그걸로, 없으면 env(GSHEET_SA_*)로 클라이언트 생성."""
    if creds_info:
        return gspread.authorize(_creds_from_info(creds_info))
    j = os.environ.get("GSHEET_SA_KEY")
    t = os.environ.get("GSHEET_SA_TOML")
    if j and os.path.exists(os.path.expanduser(j)):
        cred = Credentials.from_service_account_file(os.path.expanduser(j), scopes=SCOPES)
    elif t and os.path.exists(os.path.expanduser(t)):
        import toml
        data = toml.load(os.path.expanduser(t))
        sec = os.environ.get("GSHEET_SA_SECTION", "google_sheets_service_account")
        cred = _creds_from_info(data.get(sec, data))
    else:
        raise RuntimeError("서비스계정 자격 없음 (GSHEET_SA_KEY / GSHEET_SA_TOML)")
    return gspread.authorize(cred)


def open_sheet(sheet_id: str, creds_info: Optional[Dict[str, Any]] = None):
    return client(creds_info).open_by_key(sheet_id)


def get_or_create_tab(sh, title: str, headers: list, rows: int = 2000):
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title, rows=rows, cols=max(len(headers), 26))
        ws.update([headers], "A1", value_input_option="RAW")
        return ws
