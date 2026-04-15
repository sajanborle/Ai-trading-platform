import yfinance as yf
import pandas as pd
import ta


# 🔥 CONFIDENCE CALCULATION (IMPROVED)
def calculate_confidence(ma50, ma200, rsi, volume, volume_ma, macd_val, macd_signal):
    score = 0

    # Trend strength
    if ma50 > ma200:
        score += 30
    else:
        score += 15

    # RSI condition
    if 45 < rsi < 60:
        score += 30
    elif 35 < rsi < 70:
        score += 20
    else:
        score += 10

    # MA distance
    diff = abs(ma50 - ma200) / ma200 * 100
    if diff > 2:
        score += 10

    # Volume confirmation
    if volume > volume_ma:
        score += 15

    # MACD confirmation
    if macd_val > macd_signal:
        score += 15

    return score


# ✅ SAFE FLOAT
def to_float(value):
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


# 🚀 MAIN SCANNER
def scan_stocks():
    stocks_list = [
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS"
    ]

    results = []

    for stock_name in stocks_list:
        try:
            data = yf.download(stock_name, period="5d", interval="5m")

            if data.empty:
                continue

            data.dropna(inplace=True)

            close = data['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]

            # Indicators
            data['MA50'] = close.rolling(50).mean()
            data['MA200'] = close.rolling(200).mean()
            data['RSI'] = ta.momentum.RSIIndicator(close).rsi()

            data['Volume_MA'] = data['Volume'].rolling(20).mean()

            macd = ta.trend.MACD(close)
            data['MACD'] = macd.macd()
            data['MACD_SIGNAL'] = macd.macd_signal()

            latest = data.iloc[-1]

            ma50 = to_float(latest['MA50'])
            ma200 = to_float(latest['MA200'])
            rsi = to_float(latest['RSI'])
            price = to_float(latest['Close'])
            volume = to_float(latest['Volume'])
            volume_ma = to_float(latest['Volume_MA'])
            macd_val = to_float(latest['MACD'])
            macd_signal = to_float(latest['MACD_SIGNAL'])

            if any(pd.isna(x) for x in [ma50, ma200, rsi, volume_ma, macd_val, macd_signal]):
                continue

            # ✅ BALANCED SIGNAL LOGIC
            if ma50 > ma200 and rsi < 65:
                signal = "BUY"

            elif ma50 < ma200 and rsi > 35:
                signal = "SELL"

            else:
                signal = "HOLD"

            confidence = calculate_confidence(
                ma50, ma200, rsi,
                volume, volume_ma,
                macd_val, macd_signal
            )

            results.append({
                "stock": stock_name,
                "price": round(price, 2),
                "rsi": round(rsi, 2),
                "signal": signal,
                "confidence": confidence
            })

        except Exception as e:
            print(f"Error in {stock_name}: {e}")
            continue

    df = pd.DataFrame(results)

    if df.empty:
        return [{"message": "No signals found"}]

    # ✅ FILTER STRONG ONLY
    df = df[df['confidence'] > 70]

    if df.empty:
        return [{"message": "No strong signals"}]

    df = df.sort_values(by="confidence", ascending=False)

    return df.head(3).to_dict(orient="records")


# 🚀 BACKTEST (IMPROVED)
def backtest_all():

    stocks_list = [
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS"
    ]

    total_trades = 0
    total_wins = 0

    for stock_name in stocks_list:

        data = yf.download(stock_name, period="1mo", interval="5m")

        if data.empty:
            continue

        data.dropna(inplace=True)

        close = data['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        data['MA50'] = close.rolling(50).mean()
        data['MA200'] = close.rolling(200).mean()
        data['RSI'] = ta.momentum.RSIIndicator(close).rsi()

        for i in range(200, len(data) - 3):
            row = data.iloc[i]

            ma50 = to_float(row['MA50'])
            ma200 = to_float(row['MA200'])
            rsi = to_float(row['RSI'])

            if pd.isna(ma50) or pd.isna(ma200) or pd.isna(rsi):
                continue

            # 🔥 BUY LOGIC
            if ma50 > ma200 and rsi < 70:
                entry = to_float(row['Close'])

                future_prices = data.iloc[i+1:i+4]['Close']
                future_prices = future_prices.dropna()
                future_prices = [float(x) for x in future_prices if str(x).replace('.', '', 1).isdigit()]

                if len(future_prices) == 0:
                    continue

                if max(future_prices) > entry * 1.002:  # 0.2% move
                    total_wins += 1

                total_trades += 1

            # 🔥 SELL LOGIC
            elif ma50 < ma200 and rsi > 30:
                entry = to_float(row['Close'])

                future_prices = data.iloc[i+1:i+4]['Close']
                future_prices = future_prices.dropna()
                future_prices = [float(x) for x in future_prices if str(x).replace('.', '', 1).isdigit()]

                if len(future_prices) == 0:
                    continue

                if min(future_prices) < entry * 0.998:
                    total_wins += 1

                total_trades += 1

    accuracy = (total_wins / total_trades * 100) if total_trades > 0 else 0

    return {
        "total_trades": total_trades,
        "wins": total_wins,
        "accuracy": round(accuracy, 2)
    }