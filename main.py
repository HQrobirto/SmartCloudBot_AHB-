import os
import time
import pandas as pd
import pandas_ta as ta
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


# ====================== CONFIG ======================
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

TESTNET = True                    # ←←← مهم: True = Testnet | False = Real
SYMBOL = "XAUUSDT"
LEVERAGE = 10
INTERVAL = "1m"
KLINES_LIMIT = 200

# شروط خفيفة
ENTRY_ADX = 20
ENTRY_RSI_LONG = 35
ENTRY_RSI_SHORT = 65

TP1_PERCENT = 0.004   # 0.4%
TP2_PERCENT = 0.008   # 0.8%
SL_PERCENT = 0.003    # 0.3%

# إعدادات الكمية الديناميكية (جديدة)
RISK_PERCENT = 0.01   # 1% من الرصيد لكل صفقة (يمكنك تغييره)
MIN_QUANTITY = 0.01
MAX_QUANTITY = 5.0

# ===================================================
def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Telegram Error: {e}")
        
# إنشاء العميل مع دعم Testnet
client = Client(API_KEY, API_SECRET, testnet=TESTNET)

def get_usdt_balance():
    """جلب الرصيد المتاح في USDT (Testnet أو Real)"""
    try:
        account = client.futures_account()
        for asset in account.get('assets', []):
            if asset['asset'] == 'USDT':
                return float(asset['availableBalance'])
        return 0.0
    except Exception as e:
        print(f"⚠️ خطأ في جلب الرصيد: {e}")
        return 0.0

def get_klines():
    klines = client.futures_klines(symbol=SYMBOL, interval=INTERVAL, limit=KLINES_LIMIT)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    df['ema50'] = ta.ema(df['close'], length=50)
    df['ema200'] = ta.ema(df['close'], length=200)
    df['rsi'] = ta.rsi(df['close'], length=14)
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    df = pd.concat([df, adx_df], axis=1)
    return df

def get_current_position():
    try:
        positions = client.futures_position_information(symbol=SYMBOL)
        for pos in positions:
            amt = float(pos['positionAmt'])
            if amt != 0:
                return {'positionAmt': amt, 'entryPrice': float(pos['entryPrice'])}
        return None
    except Exception as e:
        print(f"خطأ في جلب المركز: {e}")
        return None

def close_position(quantity_to_close: float):
    if quantity_to_close == 0:
        return False
    side = "SELL" if quantity_to_close > 0 else "BUY"
    try:
        order = client.futures_create_order(
            symbol=SYMBOL,
            side=side,
            type="MARKET",
            quantity=abs(quantity_to_close),
            reduceOnly=True
        )
        print(f"✅ إغلاق جزئي/كامل: {abs(quantity_to_close)} عقد | Order ID: {order.get('orderId')}")
        return True
    except BinanceAPIException as e:
        print(f"❌ Binance Error: {e}")
        return False

# ====================== MAIN LOOP ======================
def main():
    mode = "🧪 TESTNET" if TESTNET else "🔥 LIVE"
    print(f"🚀 البوت يعمل الآن على {mode} - XAUUSDT (كمية ديناميكية + 1% مخاطرة)")

    try:
        client.futures_change_leverage(symbol=SYMBOL, leverage=LEVERAGE)
        print(f"✅ Leverage = {LEVERAGE}x")
    except:
        pass

    partial_closed = False

    while True:
        try:
            df = get_klines()
            df = calculate_indicators(df)
            latest = df.iloc[-1]

            ticker = client.futures_ticker(symbol=SYMBOL)
            current_price = float(ticker['lastPrice'])

            position = get_current_position()
            balance = get_usdt_balance()

            # ==================== لا يوجد مركز → حساب كمية ديناميكية + دخول ====================
            if position is None:
                partial_closed = False

                if balance <= 10:
                    print(f"⚠️ رصيد منخفض ({balance:.2f} USDT) → لا صفقات جديدة")
                else:
                    # حساب الكمية الديناميكية
                    risk_amount = balance * RISK_PERCENT
                    sl_distance = current_price * SL_PERCENT
                    quantity = risk_amount / sl_distance
                    quantity = max(MIN_QUANTITY, min(MAX_QUANTITY, round(quantity, 3)))

                    print(f"📊 رصيد: {balance:.2f} USDT | مخاطرة: {risk_amount:.2f} | كمية الدخول: {quantity} XAU")
 
                    # إشارة شراء
                    if (send_telegram_msg(f"✅ تم فتح صفقة شراء ذهب بسعر: {current_price}")
                        
                    if( latest['ema50'] > latest['ema200'] and
                        latest['rsi'] < ENTRY_RSI_LONG and
                        latest['ADX_14'] > ENTRY_ADX and
                        latest['DMP_14'] > latest['DMN_14']):

                        order = client.futures_create_order(
                            symbol=SYMBOL,
                            side="BUY",
                            type="MARKET",
                            quantity=quantity
                        )
                        print(f"🟢 صفقة شراء فتحت | كمية: {quantity} | سعر: {current_price}")

                    # إشارة بيع
                    elif (latest['ema50'] < latest['ema200'] and
                          latest['rsi'] > ENTRY_RSI_SHORT and
                          latest['ADX_14'] > ENTRY_ADX and
                          latest['DMN_14'] > latest['DMP_14']):

                        order = client.futures_create_order(
                            symbol=SYMBOL,
                            side="SELL",
                            type="MARKET",
                            quantity=quantity
                        )
                        print(f"🔴 صفقة بيع فتحت | كمية: {quantity} | سعر: {current_price}")

            # ==================== يوجد مركز → إدارة TP/SL ====================
            else:
                entry = position['entryPrice']
                qty = position['positionAmt']

                if qty > 0:  # Long
                    tp1 = entry * (1 + TP1_PERCENT)
                    tp2 = entry * (1 + TP2_PERCENT)
                    sl = entry * (1 - SL_PERCENT)

                    if current_price >= tp1 and not partial_closed:
                        if close_position(qty / 2):
                            partial_closed = True
                    elif current_price >= tp2 and partial_closed:
                        close_position(qty)
                        partial_closed = False
                    elif current_price <= sl:
                        close_position(qty)
                        partial_closed = False

                else:  # Short
                    tp1 = entry * (1 - TP1_PERCENT)
                    tp2 = entry * (1 - TP2_PERCENT)
                    sl = entry * (1 + SL_PERCENT)

                    if current_price <= tp1 and not partial_closed:
                        if close_position(-qty / 2):
                            partial_closed = True
                    elif current_price <= tp2 and partial_closed:
                        close_position(qty)
                        partial_closed = False
                    elif current_price >= sl:
                        close_position(qty)
                        partial_closed = False

        except Exception as e:
            print(f"⚠️ خطأ عام: {e}")

        time.sleep(30)

if __name__ == "__main__":
    main()
