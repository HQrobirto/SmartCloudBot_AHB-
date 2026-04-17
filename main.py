import asyncio
import time
import datetime
import requests
import pandas as pd
import os
import json
from binance import AsyncClient  # تم التعديل هنا لاستخدام AsyncClient

# ── إعدادات البوت ──
BINANCE_API_KEY    = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID            = os.environ.get("CHAT_ID")

SYMBOL = "XAUUSDT"
INTERVAL = "5m"

INITIAL_BALANCE = 50.0
SL_MULTIPLIER = 1.5
TP1_MULTIPLIER = 2.0
TP2_MULTIPLIER = 4.0
TRAILING_ACTIVATION = 1.5

QUANTITY = 0.02          # حجم الصفقة الكامل
PARTIAL_QUANTITY = 0.01  # حجم الإغلاق الجزئي

class SmartCloudBot:
    def __init__(self):
        self.balance = INITIAL_BALANCE
        self.state = "IDLE"
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.quantity = QUANTITY
        self.position_side = None
        self.df = pd.DataFrame()
        self.client = None # سيتم تعريفه لاحقاً بشكل غير متزامن

        self.load_position()
        self.send_msg("🚀 SmartCloudBot v8.0 | Async Mode + Real Partial Close + Optimized")

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
            "quantity": self.quantity,
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
            self.quantity = data.get("quantity", QUANTITY)
            self.position_side = data.get("position_side")
            self.send_msg(f"🔄 تم تحميل صفقة مفتوحة: {self.state}")
        except:
            pass

    def send_msg(self, text):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}")
        if TELEGRAM_TOKEN and CHAT_ID:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID, "text": text},
                    timeout=5
                )
            except:
                pass

    async def get_latest_data(self):
        """سحب الشموع بشكل غير متزامن لتفادي التأخير"""
        klines = await self.client.futures_klines(
            symbol=SYMBOL,
            interval=INTERVAL,
            limit=1000
        )
        df = pd.DataFrame(klines, columns=[
            'open_time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
        return df

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        df['EMA100'] = close.ewm(span=100, adjust=False).mean()
        df['ATR'] = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1).rolling(14).mean()

        df['Don_High'] = high.rolling(15).max()
        df['Don_Low'] = low.rolling(15).min()
        df['Vol_MA'] = volume.rolling(20).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # ADX 
        plus_dm = high.diff()
        minus_dm = low.diff()
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(14).mean()
        
        # تم إصلاح خطأ الإزاحة (Indentation) هنا
        df.dropna(inplace=True) 
        return df

    def layered_smart_long(self, row):
        return all([
            row['Close'] > row['EMA100'],
            row['Close'] > row['Don_High'],
            row['Volume'] > row['Vol_MA'] * 1.1,
            row['ATR'] > 0.6,
            row['RSI'] < 78,
            row['ADX'] > 15,
            row['MACD'] > row['MACD_Signal']
        ])

    def layered_smart_short(self, row):
        return all([
            row['Close'] < row['EMA100'],
            row['Close'] < row['Don_Low'],
            row['Volume'] > row['Vol_MA'] * 1.1,
            row['ATR'] > 0.6,
            row['RSI'] > 22,
            row['ADX'] > 15,
            row['MACD'] < row['MACD_Signal']
        ])

    async def open_position(self, side):
        try:
            order = await self.client.futures_create_order(
                symbol=SYMBOL,
                side=side,
                type='MARKET',
                quantity=self.quantity
            )
            self.position_side = side
            self.send_msg(f"✅ تم فتح صفقة {side} | حجم: {self.quantity}")
            self.save_position()
            return order
        except Exception as e:
            self.send_msg(f"❌ خطأ فتح الصفقة: {e}")
            return None

    async def close_partial(self):
        if not self.position_side:
            return
        opposite = "SELL" if self.position_side == "BUY" else "BUY"
        try:
            await self.client.futures_create_order(
                symbol=SYMBOL,
                side=opposite,
                type='MARKET',
                quantity=PARTIAL_QUANTITY,
                reduceOnly=True
            )
            self.quantity -= PARTIAL_QUANTITY
            self.send_msg(f"✅ Partial Close 50% | تم إغلاق {PARTIAL_QUANTITY} عقد")
            self.save_position()
        except Exception as e:
            self.send_msg(f"❌ Partial Close error: {e}")

    async def run(self):
        # تهيئة الـ AsyncClient
        self.client = await AsyncClient.create(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.send_msg("📡 SmartCloudBot v8.0 شغال على Binance Futures (Async Mode)")

        try:
            while True:
                # سحب البيانات بشكل أسرع
                new_df = await self.get_latest_data()
                self.df = new_df 

                full_df = self.calculate_indicators(self.df)
                row = full_df.iloc[-1]

                close = float(row['Close'])
                atr = float(row['ATR'])

                # ── منطق الدخول ──
                if self.state == "IDLE":
                    if self.layered_smart_long(row):
                        self.entry_price = close
                        self.sl_price = close - (atr * SL_MULTIPLIER)
                        self.tp1_price = close + (atr * TP1_MULTIPLIER)
                        self.tp2_price = close + (atr * TP2_MULTIPLIER)
                        self.quantity = QUANTITY
                        self.send_msg(f"🚀 LONG Breakout @ {close:.2f}")
                        await self.open_position("BUY")
                        self.state = "IN_LONG"

                    elif self.layered_smart_short(row):
                        self.entry_price = close
                        self.sl_price = close + (atr * SL_MULTIPLIER)
                        self.tp1_price = close - (atr * TP1_MULTIPLIER)
                        self.tp2_price = close - (atr * TP2_MULTIPLIER)
                        self.quantity = QUANTITY
                        self.send_msg(f"🔻 SHORT Breakout @ {close:.2f}")
                        await self.open_position("SELL")
                        self.state = "IN_SHORT"

                # ── إدارة الصفقة LONG ──
                elif self.state == "IN_LONG":
                    if close >= self.tp1_price and self.tp1_price != 0:
                        await self.close_partial()
                        self.tp1_price = 0
                        self.save_position()

                    if close - self.entry_price > atr * TRAILING_ACTIVATION:
                        new_sl = close - (atr * 1.2)
                        if new_sl > self.sl_price:
                            self.sl_price = new_sl
                            self.save_position()

                    if close <= self.sl_price or close >= self.tp2_price:
                        pnl = (close - self.entry_price) * 100 * self.quantity
                        self.balance += pnl
                        self.send_msg(f"📉 خروج كامل LONG | P&L: {pnl:.2f}$")
                        self.state = "IDLE"
                        self.save_position()

                # ── إدارة الصفقة SHORT ──
                elif self.state == "IN_SHORT":
                    if close <= self.tp1_price and self.tp1_price != 0:
                        await self.close_partial()
                        self.tp1_price = 0
                        self.save_position()

                    if self.entry_price - close > atr * TRAILING_ACTIVATION:
                        new_sl = close + (atr * 1.2)
                        if new_sl < self.sl_price:
                            self.sl_price = new_sl
                            self.save_position()

                    if close >= self.sl_price or close <= self.tp2_price:
                        pnl = (self.entry_price - close) * 100 * self.quantity
                        self.balance += pnl
                        self.send_msg(f"📈 خروج كامل SHORT | P&L: {pnl:.2f}$")
                        self.state = "IDLE"
                        self.save_position()

                # نوم غير متزامن بدلاً من توقيف الكود بالكامل
                await asyncio.sleep(30)
                
        finally:
            await self.client.close_connection()

if __name__ == "__main__":
    bot = SmartCloudBot()
    # تشغيل الحلقة غير المتزامنة
    asyncio.run(bot.run())
