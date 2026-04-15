import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import os
import json
from binance import Client
from groq import Groq

# ── إعدادات Binance ──
BINANCE_API_KEY    = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")

SYMBOL = "XAUUSDT"
INTERVAL = "5m"

INITIAL_BALANCE = 5000.0
SL_MULTIPLIER = 1.5
TP1_MULTIPLIER = 2.0
TP2_MULTIPLIER = 4.0
TRAILING_ACTIVATION = 1.5

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

class SmartCloudBot:
    def __init__(self):
        self.balance = INITIAL_BALANCE
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.trades = []
        self.position_side = None

        self.load_position()

        self.send_msg(f"🚀 SmartCloudBot v7.1 | Binance Live + Position Save")

    def save_position(self):
        if self.state == "IDLE":
            if os.path.exists("position.json"):
                os.remove("position.json")
            return
        data = {
            "state": self.state,
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "position_side": self.position_side
        }
        with open("position.json", "w") as f:
            json.dump(data, f)

    def load_position(self):
        if not os.path.exists("position.json"):
            return
        try:
            with open("position.json", "r") as f:
                data = json.load(f)
            self.state = data["state"]
            self.entry_price = data["entry_price"]
            self.sl_price = data["sl_price"]
            self.tp1_price = data["tp1_price"]
            self.tp2_price = data["tp2_price"]
            self.position_side = data.get("position_side")
            self.send_msg(f"🔄 تم تحميل صفقة مفتوحة سابقاً: {self.state}")
        except:
            pass

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data={'chat_id': CHAT_ID, 'text': text}, timeout=10)
            except: pass

    def get_data(self):
        df = yf.download("GC=F", interval=INTERVAL, period="1d", progress=False)
        if len(df) < 100: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        return df.copy()

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        df['EMA100'] = close.ewm(span=100, adjust=False).mean()
        df['ATR'] = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1).rolling(14).mean()
        df['Don_High'] = high.rolling(15).max()
        df['Don_Low'] = low.rolling(15).min()
        df['Vol_MA'] = volume.rolling(20).mean()

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        plus_dm = high.diff()
        minus_dm = low.diff()
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(14).mean()

        return df

    def layered_smart_long(self, row):
        if row['Close'] <= row['EMA100']: return False
        if row['Close'] <= row['Don_High']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.1: return False
        if row['ATR'] < 0.6: return False
        if row['RSI'] > 78: return False
        if row['ADX'] < 15: return False
        if row['MACD'] <= row['MACD_Signal']: return False
        return True

    def layered_smart_short(self, row):
        if row['Close'] >= row['EMA100']: return False
        if row['Close'] >= row['Don_Low']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.1: return False
        if row['ATR'] < 0.6: return False
        if row['RSI'] < 22: return False
        if row['ADX'] < 15: return False
        if row['MACD'] >= row['MACD_Signal']: return False
        return True

    def open_position(self, side):
        try:
            order = client.futures_create_order(
                symbol=SYMBOL,
                side=side,
                type='MARKET',
                quantity=0.01
            )
            self.send_msg(f"✅ تم فتح صفقة {side} على Binance")
            self.position_side = side
            self.save_position()
            return order
        except Exception as e:
            self.send_msg(f"❌ خطأ في فتح الصفقة: {e}")
            return None

    def run(self):
        self.send_msg("📡 SmartCloudBot v7.1 شغال على Binance Futures")

        while True:
            df = self.get_data()
            if df is None:
                time.sleep(30)
                continue

            full_df = self.calculate_indicators(df)
            row = full_df.iloc[-1]

            close = float(row['Close'])
            atr = float(row['ATR'])

            if self.state == "IDLE":
                if self.layered_smart_long(row):
                    self.entry_price = close
                    self.sl_price = close - (atr * SL_MULTIPLIER)
                    self.tp1_price = close + (atr * TP1_MULTIPLIER)
                    self.tp2_price = close + (atr * TP2_MULTIPLIER)
                    self.send_msg(f"🚀 LONG Breakout @ {close:.2f} → يتم التنفيذ")
                    self.open_position("BUY")
                    self.state = "IN_LONG"

                elif self.layered_smart_short(row):
                    self.entry_price = close
                    self.sl_price = close + (atr * SL_MULTIPLIER)
                    self.tp1_price = close - (atr * TP1_MULTIPLIER)
                    self.tp2_price = close - (atr * TP2_MULTIPLIER)
                    self.send_msg(f"🔻 SHORT Breakout @ {close:.2f} → يتم التنفيذ")
                    self.open_position("SELL")
                    self.state = "IN_SHORT"

            elif self.state == "IN_LONG":
                if close >= self.tp1_price and self.tp1_price != 0:
                    partial_pnl = (self.tp1_price - self.entry_price) * 100 * 0.5
                    self.balance += partial_pnl
                    self.send_msg(f"✅ Partial Close LONG 50% | +${partial_pnl:.2f}")
                    self.tp1_price = 0
                    self.save_position()

                if close - self.entry_price > atr * TRAILING_ACTIVATION:
                    new_sl = close - (atr * 1.2)
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl
                        self.save_position()

                if close <= self.sl_price or close >= self.tp2_price:
                    pnl = (close - self.entry_price) * 100
                    self.balance += pnl
                    self.trades.append({'pnl': pnl, 'type': 'LONG'})
                    self.send_msg(f"📉 خروج كامل LONG | P&L: {pnl:.2f}$")
                    self.state = "IDLE"
                    self.save_position()

            elif self.state == "IN_SHORT":
                if close <= self.tp1_price and self.tp1_price != 0:
                    partial_pnl = (self.entry_price - self.tp1_price) * 100 * 0.5
                    self.balance += partial_pnl
                    self.send_msg(f"✅ Partial Close SHORT 50% | +${partial_pnl:.2f}")
                    self.tp1_price = 0
                    self.save_position()

                if self.entry_price - close > atr * TRAILING_ACTIVATION:
                    new_sl = close + (atr * 1.2)
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl
                        self.save_position()

                if close >= self.sl_price or close <= self.tp2_price:
                    pnl = (self.entry_price - close) * 100
                    self.balance += pnl
                    self.trades.append({'pnl': pnl, 'type': 'SHORT'})
                    self.send_msg(f"📈 خروج كامل SHORT | P&L: {pnl:.2f}$")
                    self.state = "IDLE"
                    self.save_position()

            time.sleep(30)

if __name__ == "__main__":
    bot = SmartCloudBot()
    bot.run()
