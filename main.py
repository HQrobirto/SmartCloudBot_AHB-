import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import os
from groq import Groq

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYMBOL = "GC=F"
INTERVAL = "5m"

INITIAL_BALANCE = 50.0
SL_MULTIPLIER = 1.5
TP1_MULTIPLIER = 2.0
TP2_MULTIPLIER = 4.0
TRAILING_ACTIVATION = 1.5

groq = Groq(api_key=GROQ_API_KEY)

class SmartCloudBot:
    def __init__(self):
        self.balance = INITIAL_BALANCE
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.trades = []

        self.send_msg(f"🧠 SmartCloudBot v6.9 | EMA100 + Donchian 15 | Debug Mode | Balance: ${self.balance:.0f}")

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              data={'chat_id': CHAT_ID, 'text': text}, timeout=10)
            except: pass

    def send_chart(self, df, title):
        try:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, df['Close'], label='Close', color='blue')
            plt.plot(df.index, df['EMA100'], label='EMA100', color='orange')
            plt.fill_between(df.index, df['Don_Low'], df['Don_High'], color='gray', alpha=0.25)
            plt.title(title)
            plt.legend()
            plt.grid(True)
            chart_path = "chart.png"
            plt.savefig(chart_path)
            plt.close()

            if TELEGRAM_TOKEN and CHAT_ID:
                with open(chart_path, 'rb') as photo:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                                  data={'chat_id': CHAT_ID, 'caption': title}, files={'photo': photo})
                os.remove(chart_path)
        except: pass

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        df['EMA100'] = close.ewm(span=100, adjust=False).mean()          # ← تم التغيير إلى 100
        df['ATR'] = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1).rolling(14).mean()
        df['Don_High'] = high.rolling(15).max()                         # ← تم التغيير إلى 15
        df['Don_Low']  = low.rolling(15).min()                          # ← تم التغيير إلى 15
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
        if row['Close'] <= row['EMA100']: 
            print("Skipped LONG: Below EMA100")
            return False
        if row['Close'] <= row['Don_High']:
            print("Skipped LONG: No Donchian Breakout")
            return False
        if row['Volume'] <= row['Vol_MA'] * 1.2:
            print("Skipped LONG: Volume too low")
            return False
        if row['ATR'] < 0.8:
            print("Skipped LONG: ATR too low")
            return False
        if row['RSI'] > 75:
            print("Skipped LONG: RSI Overbought")
            return False
        if row['ADX'] < 18:
            print("Skipped LONG: ADX too weak")
            return False
        if row['MACD'] <= row['MACD_Signal']:
            print("Skipped LONG: MACD not bullish")
            return False

        print("✅ LONG Signal Accepted!")
        return True

    def layered_smart_short(self, row):
        if row['Close'] >= row['EMA100']:
            print("Skipped SHORT: Above EMA100")
            return False
        if row['Close'] >= row['Don_Low']:
            print("Skipped SHORT: No Donchian Breakout")
            return False
        if row['Volume'] <= row['Vol_MA'] * 1.2:
            print("Skipped SHORT: Volume too low")
            return False
        if row['ATR'] < 0.8:
            print("Skipped SHORT: ATR too low")
            return False
        if row['RSI'] < 25:
            print("Skipped SHORT: RSI Oversold")
            return False
        if row['ADX'] < 18:
            print("Skipped SHORT: ADX too weak")
            return False
        if row['MACD'] >= row['MACD_Signal']:
            print("Skipped SHORT: MACD not bearish")
            return False

        print("✅ SHORT Signal Accepted!")
        return True

    def run_backtest(self, days=30):
        self.send_msg(f"🔄 بدء Backtest لـ {days} يوم | رصيد: ${self.balance:.0f}")

        df = yf.download(SYMBOL, interval=INTERVAL, period=f"{days}d", progress=False)
        self.send_msg(f"✅ تم تحميل {len(df)} شمعة")

        if len(df) < 100:
            self.send_msg("❌ بيانات قليلة")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)

        df = self.calculate_indicators(df)

        for i in range(50, len(df)):
            row = df.iloc[i]
            close = float(row['Close'])
            atr = float(row['ATR'])

            if self.state == "IDLE":
                if self.layered_smart_long(row):
                    self.entry_price = close
                    self.sl_price = close - (atr * SL_MULTIPLIER)
                    self.tp1_price = close + (atr * TP1_MULTIPLIER)
                    self.tp2_price = close + (atr * TP2_MULTIPLIER)
                    self.send_msg(f"🚀 LONG Breakout @ {close:.2f}")
                    self.send_chart(df.iloc[:i+1], f"Backtest LONG - {close:.2f}")
                    self.state = "IN_LONG"

                elif self.layered_smart_short(row):
                    self.entry_price = close
                    self.sl_price = close + (atr * SL_MULTIPLIER)
                    self.tp1_price = close - (atr * TP1_MULTIPLIER)
                    self.tp2_price = close - (atr * TP2_MULTIPLIER)
                    self.send_msg(f"🔻 SHORT Breakout @ {close:.2f}")
                    self.send_chart(df.iloc[:i+1], f"Backtest SHORT - {close:.2f}")
                    self.state = "IN_SHORT"

            elif self.state == "IN_LONG":
                if close >= self.tp1_price and self.tp1_price != 0:
                    partial_pnl = (self.tp1_price - self.entry_price) * 100 * 0.5
                    self.balance += partial_pnl
                    self.send_msg(f"✅ Partial Close LONG | +${partial_pnl:.2f} | Balance: ${self.balance:.2f}")
                    self.tp1_price = 0

                if close - self.entry_price > atr * TRAILING_ACTIVATION:
                    new_sl = close - (atr * 1.2)
                    if new_sl > self.sl_price:
                        self.sl_price = new_sl

                if close <= self.sl_price or close >= self.tp2_price:
                    pnl = (close - self.entry_price) * 100
                    self.balance += pnl
                    self.trades.append({'pnl': pnl, 'type': 'LONG'})
                    self.send_msg(f"📉 خروج كامل LONG | P&L: {pnl:.2f}$ | Balance: ${self.balance:.2f}")
                    self.state = "IDLE"

            elif self.state == "IN_SHORT":
                if close <= self.tp1_price and self.tp1_price != 0:
                    partial_pnl = (self.entry_price - self.tp1_price) * 100 * 0.5
                    self.balance += partial_pnl
                    self.send_msg(f"✅ Partial Close SHORT | +${partial_pnl:.2f} | Balance: ${self.balance:.2f}")
                    self.tp1_price = 0

                if self.entry_price - close > atr * TRAILING_ACTIVATION:
                    new_sl = close + (atr * 1.2)
                    if new_sl < self.sl_price:
                        self.sl_price = new_sl

                if close >= self.sl_price or close <= self.tp2_price:
                    pnl = (self.entry_price - close) * 100
                    self.balance += pnl
                    self.trades.append({'pnl': pnl, 'type': 'SHORT'})
                    self.send_msg(f"📈 خروج كامل SHORT | P&L: {pnl:.2f}$ | Balance: ${self.balance:.2f}")
                    self.state = "IDLE"

        total_pnl = sum(t.get('pnl', 0) for t in self.trades)
        winrate = (sum(1 for t in self.trades if t.get('pnl', 0) > 0) / len(self.trades) * 100) if self.trades else 0
        
        self.send_msg(f"""
🎯 نهاية Backtest
────────────────
الرصيد النهائي: ${self.balance:.2f}
إجمالي P&L: ${total_pnl:.2f}
عدد الصفقات: {len(self.trades)}
Winrate: {winrate:.1f}%
""")

if __name__ == "__main__":
    bot = SmartCloudBot()
    bot.run_backtest(days=30)
