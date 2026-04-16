import os
import time

import requests

CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "b5f55aaf-f257-4946-b34b-6157c3cd4f9a")
CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "ur8f7kwy7w")
REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
ORDER_URL = "https://api.upstox.com/v2/order/place"
OPTION_CONTRACT_URL = "https://api.upstox.com/v2/option/contract"
OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"

tokens = {
    "access_token": None,
    "refresh_token": None,
    "expires_at": 0,
}


def get_login_url():
    return (
        "https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    )


def generate_token(code: str) -> dict:
    res = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )

    data = res.json()
    print("TOKEN RESPONSE:", data)

    tokens["access_token"] = data.get("access_token")
    tokens["refresh_token"] = data.get("refresh_token")
    tokens["expires_at"] = time.time() + data.get("expires_in", 86400)
    return data


def refresh_token():
    if tokens.get("access_token") and time.time() < tokens["expires_at"] - 60:
        return tokens["access_token"]

    if not tokens.get("refresh_token"):
        return tokens.get("access_token")

    res = requests.post(
        TOKEN_URL,
        data={
            "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )

    data = res.json()
    tokens["access_token"] = data.get("access_token")
    tokens["refresh_token"] = data.get("refresh_token", tokens["refresh_token"])
    tokens["expires_at"] = time.time() + data.get("expires_in", 86400)
    return tokens["access_token"]


def get_connection_status() -> dict:
    return {
        "connected": bool(tokens.get("access_token")),
        "client_id_present": bool(CLIENT_ID),
        "redirect_uri": REDIRECT_URI,
        "expires_at": tokens["expires_at"],
    }


def get_auth_headers() -> dict | None:
    access_token = refresh_token()
    if not access_token:
        return None

    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def fetch_option_contracts(instrument_key: str, expiry_date: str | None = None) -> dict:
    headers = get_auth_headers()
    if not headers:
        return {"error": "Upstox login required", "data": []}

    params = {"instrument_key": instrument_key}
    if expiry_date:
        params["expiry_date"] = expiry_date

    try:
        response = requests.get(OPTION_CONTRACT_URL, params=params, headers=headers, timeout=10)
        return response.json()
    except Exception as exc:
        return {"error": "Unable to fetch option contracts", "details": str(exc), "data": []}


def fetch_option_chain(instrument_key: str, expiry_date: str) -> dict:
    headers = get_auth_headers()
    if not headers:
        return {"error": "Upstox login required", "data": []}

    try:
        response = requests.get(
            OPTION_CHAIN_URL,
            params={"instrument_key": instrument_key, "expiry_date": expiry_date},
            headers=headers,
            timeout=10,
        )
        return response.json()
    except Exception as exc:
        return {"error": "Unable to fetch option chain", "details": str(exc), "data": []}


def place_market_order(symbol: str, qty: int, instrument_token: str) -> dict:
    access_token = refresh_token()
    if not access_token:
        return {
            "error": "Upstox login required",
            "details": "Use /login first to connect your Upstox account.",
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "quantity": qty,
        "product": "D",
        "validity": "DAY",
        "price": 0,
        "instrument_token": instrument_token,
        "order_type": "MARKET",
        "transaction_type": "BUY",
        "trigger_price": 0,
        "disclosed_quantity": 0,
        "is_amo": False,
    }

    try:
        response = requests.post(ORDER_URL, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as exc:
        return {"error": f"Order failed for {symbol}", "details": str(exc)}
