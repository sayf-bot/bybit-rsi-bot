import os
import requests
from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET", "")
ORDER_USDC = os.environ.get("ORDER_USDC", "50")
# Основной Bybit — НЕ testnet
session = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

@app.get("/check-ip")
def check_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=10)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.get("/")
def home():
    return "Bybit RSI Bot is running", 200



@app.post("/webhook")
def webhook():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    action = str(data.get("action", "")).upper()

    if action not in ("BUY", "SELL"):
        return jsonify({"error": "Unknown action"}), 400

    print(f"TradingView signal received: {action}", flush=True)

    # ВАЖНО: реальные сделки пока отключены
    return jsonify({
        "status": "ok",
        "action": action,
        "trading": "disabled"
    }), 200
