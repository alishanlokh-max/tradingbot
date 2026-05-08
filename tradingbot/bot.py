import pandas as pd
import yfinance as yf
import requests
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

# =========================
# 🔧 EDIT THESE 2 VALUES
# =========================
TELEGRAM_TOKEN = "8742396807:AAGxCeDamZ826zL6UJus6K9Xl5aZ4DipJOk"
CHAT_ID = "7488526623"
# =========================

SYMBOLS = ["SPY", "QQQ", "TSLA"]


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)


def get_data(symbol):
    df = yf.download(
        symbol,
        interval="5m",
        period="1d",
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=True
    )

    if df is None or df.empty:
        return None

    # FLATTEN ANY MULTIINDEX (THIS IS THE ACTUAL ISSUE)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()

    # STANDARDIZE COLUMN NAMES SAFELY
    df.columns = [str(c).strip() for c in df.columns]

    # Ensure required columns exist
    required = ["Open", "High", "Low", "Close", "Volume"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise Exception(f"Missing columns: {missing} | Got: {df.columns}")

    df = df[required].copy()

    # Force numeric clean
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna()

    return df


def add_indicators(df):
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()

    df["ema9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["ema20"] = EMAIndicator(close=close, window=20).ema_indicator()
    df["rsi"] = RSIIndicator(close=close, window=14).rsi()

    typical_price = (high + low + close) / 3
    df["vwap"] = (volume * typical_price).cumsum() / volume.cumsum()

    return df


def volume_spike(df):
    vol = df["Volume"].squeeze()
    avg_vol = vol.rolling(20).mean().iloc[-1]
    return vol.iloc[-1] > avg_vol


def trend_filter(df):
    last = df.iloc[-1].copy()

    bullish = last["ema9"] > last["ema20"] and last["Close"] > last["vwap"]
    bearish = last["ema9"] < last["ema20"] and last["Close"] < last["vwap"]

    return bullish, bearish


def entry_signal(df):
    last = df.iloc[-1].copy()
    prev = df.iloc[-2].copy()

    bullish, bearish = trend_filter(df)

    vol_ok = volume_spike(df)

    rsi_ok_long = 40 < last["rsi"] < 65
    rsi_ok_short = 35 < last["rsi"] < 60

    vwap_reclaim = prev["Close"] < prev["vwap"] and last["Close"] > last["vwap"]
    vwap_breakdown = prev["Close"] > prev["vwap"] and last["Close"] < last["vwap"]

    if bullish and vol_ok and rsi_ok_long and vwap_reclaim:
        return "CALL"

    if bearish and vol_ok and rsi_ok_short and vwap_breakdown:
        return "PUT"

    return None


def build_signal(symbol, direction, price):
    if direction == "CALL":
        return f"""
🚨 {symbol} 0DTE CALL SETUP

Entry Zone: {price:.2f}
Contract: ATM CALL (0DTE)
Bias: Bullish momentum + VWAP reclaim
Hold Time: 10–45 min
"""

    if direction == "PUT":
        return f"""
🚨 {symbol} 0DTE PUT SETUP

Entry Zone: {price:.2f}
Contract: ATM PUT (0DTE)
Bias: Bearish momentum + VWAP breakdown
Hold Time: 10–45 min
"""

    return None


def run_bot():
    print("\n=== SCANNING MARKET ===\n")

    for symbol in SYMBOLS:
        try:
            df = get_data(symbol)

            if len(df) < 30:
                print(f"{symbol}: Not enough data")
                continue

            df = add_indicators(df)
            signal = entry_signal(df)
            price = df["Close"].iloc[-1]

            if signal:
                msg = build_signal(symbol, signal, price)
                print(msg)
                send_telegram(msg)
            else:
                print(f"{symbol}: No A+ setup")

        except Exception as e:
            print(f"{symbol}: ERROR -> {e}")


if __name__ == "__main__":
    run_bot()
