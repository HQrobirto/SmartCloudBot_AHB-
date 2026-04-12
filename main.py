import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import os
from groq import Groq

# ── إعدادات ──
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYMBOL = "GC=F"
INTERVAL = "5m"

groq = Groq(api_key=GROQ_API_KEY)

class SmartCloudBot:
    def __init__(self):
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []
        self.last_report = datetime.datetime.now()

        self.send_msg("🧠 SmartCloudBot v6.2 Final | Layered Smart Logic + Hourly Reports + Charts")

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    data={'chat_id': CHAT_ID, 'text': text},
                    timeout=10
                )
            except Exception as e:
                print(f"Telegram Error: {e}")

    def send_chart(self, df, title):
        try:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, df['Close'], label='Close Price', color='blue', linewidth=2)
            plt.plot(df.index, df['EMA200'], label='EMA 200', color='orange', linewidth=2)
            plt.fill_between(df.index, df['Don_Low'], df['Don_High'], color='gray', alpha=0.25)
            plt.title(title)
            plt.legend()
            plt.grid(True)
            
            chart_path = "chart.png"
            plt.savefig(chart_path)
            plt.close()

            if TELEGRAM_TOKEN and CHAT_ID:
                with open(chart_path, 'rb') as photo:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                        data={'chat_id': CHAT_ID, 'caption': title},
                        files={'photo': photo}
                    )
                os.remove(chart_path)
        except Exception as e:
            print(f"Chart Error: {e}")

    def get_data(self):
        try:
            df = yf.download(SYMBOL, interval=INTERVAL, period="5d", progress=False)
            if len(df) < 100:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(1, axis=1)
            return df.copy()
        except:
            return None

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        df['EMA200'] = close.ewm(span=200, adjust=False).mean()
        df['ATR'] = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1).rolling(14).mean()

        df['Don_High'] = high.rolling(20).max()
        df['Don_Low'] = low.rolling(20).min()
        df['Vol_MA'] = volume.rolling(20).mean()

        return df

    def layered_smart_long(self, row):
        if row['Close'] <= row['EMA200']: return False
        if row['Close'] <= row['Don_High']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.5: return False
        if row['ATR'] < 1.0: return False
        return True

    def layered_smart_short(self, row):
        if row['Close'] >= row['EMA200']: return False
        if row['Close'] >= row['Don_Low']: return False
        if row['Volume'] <= row['Vol_MA'] * 1.5: return False
        if row['ATR'] < 1.0: return False
        return True

    def send_hourly_report(self):
        if not self.trades:
            self.send_msg("📊 تقرير ساعي: لا توجد صفقات حتى الآن")
            return

        total_pnl = sum(t.get('pnl', 0) for t in self.trades)
        wins = sum(1 for t in self.trades if t.get('pnl', 0) > 0)
        winrate = (wins / len(self.trades)) * 100 if self.trades else 0

        report = f"""
📊 تقرير ساعي - {datetime.datetime.now().strftime('%H:%M')}
────────────────────
عدد الصفقات: {len(self.trades)}
إجمالي الربح/الخسارة: {total_pnl:.0f} دولار
نسبة الربح: {winrate:.1f}%
الحالة الحالية: {self.state}
"""
        self.send_msg(report)

    def run(self):
        self.send_msg("📡 SmartCloudBot v6.2 Final شغال | Layered Smart Logic + تقارير ساعية + Charts")

        while True:
            now = datetime.datetime.now()

            # تقرير ساعي + رسم بياني كل ساعة
            if (now - self.last_report).total_seconds() >= 3600:
                self.send_hourly_report()
                df = self.get_data()
                if df is not None:
                    self.send_chart(df, f"📈 تقرير ساعي - {now.strftime('%Y-%m-%d %H:%M')}")
                self.last_report = now

            # المنطق الرئيسي
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
                    sl = close - (atr * 1.5)
                    tp = close + (atr * 3.0)
                    self.send_msg(f"🚀 LONG Signal | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.send_chart(full_df, f"🟢 LONG Signal - {close:.2f}")
                    self.state = "IN_LONG"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

                elif self.layered_smart_short(row):
                    sl = close + (atr * 1.5)
                    tp = close - (atr * 3.0)
                    self.send_msg(f"🔻 SHORT Signal | سعر: {close:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                    self.send_chart(full_df, f"🔴 SHORT Signal - {close:.2f}")
                    self.state = "IN_SHORT"
                    self.entry_price = close
                    self.sl_price = sl
                    self.tp_price = tp

            # خروج من الصفقات
            elif self.state == "IN_LONG":
                if close <= self.sl_price or close >= self.tp_price:
                    pnl = (close - self.entry_price) * 100
                    self.trades.append({'pnl': pnl, 'type': 'LONG'})
                    self.send_msg(f"📉 خروج LONG | P&L: {pnl:.0f}$")
                    self.state = "IDLE"

            elif self.state == "IN_SHORT":
                if close >= self.sl_price or close <= self.tp_price:
                    pnl = (self.entry_price - close) * 100
                    self.trades.append({'pnl': pnl, 'type': 'SHORT'})
                    self.send_msg(f"📈 خروج SHORT | P&L: {pnl:.0f}$")
                    self.state = "IDLE"

            time.sleep(30)

if __name__ == "__main__":
    bot = SmartCloudBot()
    bot.run()
