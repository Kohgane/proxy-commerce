import base64
import json
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']


def _service_account():
    b64 = os.getenv('GOOGLE_SERVICE_JSON_B64')
    if not b64:
        raise RuntimeError('GOOGLE_SERVICE_JSON_B64 missing')
    data = json.loads(base64.b64decode(b64))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(data, SCOPES)
    client = gspread.authorize(creds)
    return client


def open_sheet(sheet_id: str, worksheet: str):
    client = _service_account()
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet)
    return ws
