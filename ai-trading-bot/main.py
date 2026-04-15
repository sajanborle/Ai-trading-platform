import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from bot import scan_stocks, backtest_all
from fastapi.responses import FileResponse
import requests


app = FastAPI()


API_KEY = "b5f55aaf-f257-4946-b34b-6157c3cd4f9a"
API_SECRET = "ur8f7kwy7w"
REDIRECT_URI = "http://localhost:8000/callback"


@app.get("/")
def home():
    return {"message": "AI Trading Bot Running 🚀"}

@app.get("/scan")
def get_signals():
    return {"results": scan_stocks()}

@app.get("/dashboard")
def dashboard():
    return FileResponse("templates/dashboard.html")

@app.get("/backtest-all")
def run_backtest_all():
    return backtest_all()

@app.get("/login")
def login():
    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}"
    return {"login_url": url}

@app.get("/callback")
def callback(code: str):

    url = "https://api.upstox.com/v2/login/authorization/token"

    data = {
        "code": code,
        "client_id": API_KEY,
        "client_secret": API_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    res = requests.post(url, data=data, headers=headers)

    token_data = res.json()

    print("ACCESS TOKEN:", token_data)

    return token_data