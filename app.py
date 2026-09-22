import os
from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET", "")

# Основной Bybit — НЕ testnet
session = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)


@app.get("/")
def home():
    return "Bybit RSI Bot is running", 200


@app.get("/check-bybit")
def check_bybit():
    try:
        balance = session.get_wallet_balance(
            accountType="UNIFIED"
        )

        return jsonify({
            "status": "ok",
            "bybit": "connected",
            "retMsg": balance.get("retMsg")
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


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
