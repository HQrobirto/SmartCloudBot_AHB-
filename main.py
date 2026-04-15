import time
import datetime
import requests
import pandas as pd
import os
import json
from binance import Client

# ── الإعدادات ──
BINANCE_API_KEY    = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID            = os.environ.get("CHAT_ID")

SYMBOL = "PAXGUSDT" # الذهب على بينانس (أو استخدم رمز العقود الآجلة الخاص بك)
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
QUANTITY = 0.02 # الكمية الكلية (للسماح بإغلاق جزئي 0.01)

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

class SmartCloudBot:
    def __init__(self):
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.load_position()
        self.send_msg("🤖 Bot v7.2 Online | Binance Data Stream Connected")

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data={'chat_id': CHAT_ID, 'text': text}, timeout=10)
            except: pass

    def get_live_data(self):
        try:
            # سحب البيانات مباشرة من بينانس لضمان دقة الأسعار
            klines = client.get_klines(symbol=SYMBOL, interval=INTERVAL, limit=150)
            df = pd.DataFrame(klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df[['Open', 'High', 'Low', 'Close', 'Volume']] = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric)
            return df
        except Exception as e:
            self.send_msg(f"⚠️ Data Error: {e}")
            return None

    def calculate_indicators(self, df):
        # (نفس منطق الحساب الخاص بك لكن ببيانات بينانس الحية)
        df['EMA100'] = df['Close'].ewm(span=100, adjust=False).mean()
        high_low = df['High'] - df['Low']
        high_cp = abs(df['High'] - df['Close'].shift())
        low_cp = abs(df['Low'] - df['Close'].shift())
        df['ATR'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(14).mean()
        # ... يمكنك إضافة باقي المؤشرات هنا ...
        return df

    def execute_trade(self, side, qty):
        try:
            # تنفيذ حقيقي على Binance Futures
            order = client.futures_create_order(symbol=SYMBOL, side=side, type='MARKET', quantity=qty)
            return True
        except Exception as e:
            self.send_msg(f"❌ Order Error: {e}")
            return False

    def run(self):
        while True:
            df = self.get_live_data()
            if df is None:
                time.sleep(30) ; continue

            df = self.calculate_indicators(df)
            row = df.iloc[-1]
            close = float(row['Close'])
            atr = float(row['ATR'])

            if self.state == "IDLE":
                # منطق الدخول (كما في كودك مع تحسين الشروط)
                if close > row['EMA100'] and close > row['High'] - (atr*0.5): # مثال لشرط اختراق
                    if self.execute_trade('BUY', QUANTITY):
                        self.state = "IN_LONG"
                        self.entry_price = close
                        self.sl_price = close - (atr * 1.5)
                        self.tp1_price = close + (atr * 2.0)
                        self.tp2_price = close + (atr * 4.0)
                        self.save_position()
                        self.send_msg(f"🚀 BUY {SYMBOL} @ {close}")

            elif self.state == "IN_LONG":
                # 1. إغلاق جزئي حقيقي (TP1)
                if self.tp1_price != 0 and close >= self.tp1_price:
                    if self.execute_trade('SELL', QUANTITY/2):
                        self.tp1_price = 0 # لعدم تكرار الإغلاق
                        self.send_msg(f"💰 TP1 Hit! Closed 50%")
                        self.save_position()

                # 2. خروج كامل (SL أو TP2)
                if close <= self.sl_price or close >= self.tp2_price:
                    remaining_qty = QUANTITY/2 if self.tp1_price == 0 else QUANTITY
                    if self.execute_trade('SELL', remaining_qty):
                        self.state = "IDLE"
                        self.send_msg(f"🚪 Trade Closed @ {close}")
                        self.save_position()

            time.sleep(10) # تحديث أسرع للمراقبة

    # (أضف دالات save_position و load_position هنا كما في كودك)
