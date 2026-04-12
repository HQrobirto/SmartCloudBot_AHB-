import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import os
from groq import Groq

# ── إعدادات ──
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYMBOL = "GC=F"
INTERVAL = "5m"
TEST_DAYS = 30

# إعدادات الصفقات
SL_MULTIPLIER = 1.5     # Stop Loss = 1.5 × ATR
TP_MULTIPLIER = 3.0     # Take Profit = 3.0 × ATR

groq_client = Groq(api_key=GROQ_API_KEY)

class SmartCloudBot:
    def __init__(self):
        self.start_time = datetime.datetime.now()
        self.target_seconds = TEST_DAYS * 24 * 3600
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []
        self.last_ai_call = datetime.datetime.now()

        self.send_msg("🛡️ SmartCloudBot v5.7 | SL & TP مفعلين | Nenuo AI")

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}", timeout=10)
            except: pass

    def get_data(self):
        try:
            df = yf.download(SYMBOL, interval=INTERVAL, period="5d", progress=False)
            if len(df) < 60:
                return None
                
            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(1, axis=1)
                
            df = df.copy()
            df = df .ewm(span=200, adjust=False).mean()
            
            # ATR
            tr = pd.concat( - df ,
                abs(df - df .shift()),
                abs(df - df .shift())
            ], axis=1).max(axis=1)
            df = tr.rolling(14).mean()
            
            return df.iloc[-1]
        except:
            return None

    def calculate_pnl(self, entry, exit_price, is_long):
        multiplier = 100  # كل نقطة في الذهب ≈ 100 دولار
        if is_long:
            return (exit_price - entry) * multiplier
        return (entry - exit_price) * multiplier

    def self_correct_with_nenuo(self):
        if len(self.trades) < 5: return
        winrate = sum(1 for t in self.trades[-20:] if t.get('pnl', 0) > 0) / len(self.trades[-20:]) * 100
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": f"Winrate: {winrate:.1f}%. اقترح تحسين لـ Scalping على الذهب 5m"}],
                model="llama-3.3-70b-versatile",
                max_tokens=120
            )
            self.send_msg(f"🧠 Nenuo AI: {response.choices[0 :180]}")
        except: pass
        self.last_ai_call = datetime.datetime.now()

    def run(self):
        self.send_msg("📡 SmartCloudBot v5.7 شغال | مع Stop Loss و Take Profit")
        
        while True:
            now = datetime.datetime.now()
            if (now - self.start_time).total_seconds() >= self.target_seconds:
                self.send_msg("🎯 انتهى الاختبار")
                break

            row = self.get_data()
            if row is None:
                time.sleep(30)
                continue

            close = float(row )
            atr = float(row )
            ema200 = float(row )

            # ================== دخول ==================
            if self.state == "IDLE":
                if close > ema200 and close > row .rolling(20).max().iloc[-1]:
                    sl = close - (atr * SL_MULTIPLIER)
                    tp = close + (atr * TP_MULTIPLIER)
                    self.send_msg(f"🚀 LONG | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.state = "IN_LONG"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

                elif close < ema200 and close < row .rolling(20).min().iloc[-1]:
                    sl = close + (atr * SL_MULTIPLIER)
                    tp = close - (atr * TP_MULTIPLIER)
                    self.send_msg(f"🔻 SHORT | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.state = "IN_SHORT"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

            # ================== خروج ==================
            elif self.state == "IN_LONG":
                if close <= self.sl_price or close >= self.tp_price:
                    pnl = self.calculate_pnl(self.entry_price, close, True)
                    self.trades.append({'pnl': pnl, 'type': 'LONG'})
                    self.send_msg(f"📉 خروج LONG | P&L: {pnl:.0f}$ | سعر الخروج: {close:.2f}")
                    self.state = "IDLE"

            elif self.state == "IN_SHORT":
                if close >= self.sl_price or close <= self.tp_price:
                    pnl = self.calculate_pnl(self.entry_price, close, False)
                    self.trades.append({'pnl': pnl, 'type': 'SHORT'})
                    self.send_msg(f"📈 خروج SHORT | P&L: {pnl:.0f}$ | سعر الخروج: {close:.2f}")
                    self.state = "IDLE"

            # Nenuo AI
            if (now - self.last_ai_call).total_seconds() > 3600:
                self.self_correct_with_nenuo()

            time.sleep(30)

if __name__ == "__main__":
    bot = SmartCloudBot()
    bot.run()
