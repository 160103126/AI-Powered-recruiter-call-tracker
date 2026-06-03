import os
import gspread

def get_client():
    key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON') or os.path.join(os.path.dirname(__file__), '..', 'creds', 'service_account.json')
    key_path = os.path.abspath(key_path)
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Service account JSON not found at {key_path}. Set GOOGLE_SERVICE_ACCOUNT_JSON env var or place the file at creds/service_account.json")
    client = gspread.service_account(filename=key_path)
    return client

def append_row(sheet_name, row_values, worksheet=0):
    client = get_client()
    sh = client.open(sheet_name)
    if isinstance(worksheet, int):
        ws = sh.get_worksheet(worksheet)
    else:
        ws = sh.worksheet(worksheet)
    ws.append_row(row_values, value_input_option='USER_ENTERED')
