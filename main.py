
import time
import datetime
import requests
import pandas as pd
import yfinance as yf
from groq import Groq

# ── إعدادات ──
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYMBOL = "GC=F"
INTERVAL = "5m"

SL_MULTIPLIER = 1.5
TP_MULTIPLIER = 3.0

groq = Groq(api_key=GROQ_API_KEY)

class SmartCloudBot:
    def __init__(self):
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []
        self.last_ai_call = datetime.datetime.now()

        self.send_msg("🛡️ SmartCloudBot v5.9 | Layered Logic + SL/TP مفعل")

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}", timeout=10)
            except:
                pass

    def get_data(self):
        try:
            df = yf.download(SYMBOL, interval=INTERVAL, period="5d", progress=False)
            if len(df) < 60:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(1, axis=1)

            return df.copy()
        except Exception as e:
            print(f"Data Error: {e}")
            return None

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        df['EMA200'] = close.ewm(span=200, adjust=False).mean()
        df['ATR'] = pd.concat([high - low, 
                               abs(high - close.shift()), 
                               abs(low - close.shift())], axis=1).max(axis=1).rolling(14).mean()
        df['Don_High'] = high.rolling(20).max()
        df['Don_Low'] = low.rolling(20).min()
        df['Vol_MA'] = volume.rolling(20).mean()

        return df.iloc[-1]

    def is_valid_long(self, row):
        if row['Close'] <= row['EMA200']: return False
        if row['Close'] <= row['Don_High']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.5: return False
        return True

    def is_valid_short(self, row):
        if row['Close'] >= row['EMA200']: return False
        if row['Close'] >= row['Don_Low']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.5: return False
        return True

    def run(self):
        self.send_msg("📡 SmartCloudBot v5.9 شغال | Layered Logic")

        while True:
            df = self.get_data()
            if df is None:
                time.sleep(30)
                continue

            row = self.calculate_indicators(df)
            close = float(row['Close'])
            atr = float(row['ATR'])

            if self.state == "IDLE":
                if self.is_valid_long(row):
                    sl = close - (atr * SL_MULTIPLIER)
                    tp = close + (atr * TP_MULTIPLIER)
                    self.send_msg(f"🚀 LONG | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.state = "IN_LONG"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

                elif self.is_valid_short(row):
                    sl = close + (atr * SL_MULTIPLIER)
                    tp = close - (atr * TP_MULTIPLIER)
                    self.send_msg(f"🔻 SHORT | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.state = "IN_SHORT"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

            elif self.state == "IN_LONG":
                if close <= self.sl_price or close >= self.tp_price:
                    pnl = (close - self.entry_price) * 100
                    self.trades.append({'pnl': pnl})
                    self.send_msg(f"📉 خروج LONG | P&L: {pnl:.0f}$")
                    self.state = "IDLE"

            elif self.state == "IN_SHORT":
                if close >= self.sl_price or close <= self.tp_price:
                    pnl = (self.entry_price - close) * 100
                    self.trades.append({'pnl': pnl})
                    self.send_msg(f"📈 خروج SHORT | P&L: {pnl:.0f}$")
                    self.state = "IDLE"

            time.sleep(30)

if __name__ == "__main__":
    bot = SmartCloudBot()
    bot.run()
