import os
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("StrategyEngine")

# এপিআই কনফিগারেশন
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "db75m8pr01qptb5nip7gdb75m8pr01qptb5nip80")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
QX_REST_API = os.environ.get("QX_API", "https://api.quantexbot.pro/v1")
QX_API_KEY = os.environ.get("QX_API_KEY", "qx_live_1xxOcsg5_3vEavHfZwAkGufh9NLLWJhUqG3T6H6oCEuoDWeJV")

http_session = requests.Session()
if QX_API_KEY and QX_API_KEY != "YOUR_QUANTEX_API_KEY":
    http_session.headers["Authorization"] = f"Bearer {QX_API_KEY}"

class UltraProMaxStrategy:
    
    @staticmethod
    def check_news_safety(currency: str = "USD") -> bool:
        """[ফিল্টার ১] হাই-ইমপ্যাক্ট নিউজ ফিল্টার (১৫ মিনিট আগে/পরে ট্রেড ব্লক)"""
        try:
            url = f"https://finnhub.io/api/v1/calendar/economic?token={FINNHUB_API_KEY}"
            response = http_session.get(url, timeout=5)
            if response.status_code == 200:
                events = response.json().get("economicCalendar", [])
                now_time = datetime.utcnow() + timedelta(hours=6) # UTC+6 Bangladesh

                for event in events:
                    event_currency = event.get("currency", "")
                    if currency.upper() in event_currency.upper():
                        event_time_str = event.get("time", "").replace("Z", "+00:00")
                        if event_time_str:
                            event_dt = datetime.fromisoformat(event_time_str) + timedelta(hours=6)
                            time_diff = abs((event_dt.replace(tzinfo=None) - now_time).total_seconds())
                            if time_diff < 900:  # ১৫ মিনিট
                                logger.warning(f"⚠️ [News Guard] High impact news active for {currency}. Trade Blocked!")
                                return False
            return True
        except Exception as e:
            logger.error(f"News Filter Error: {e}")
            return True

    @staticmethod
    def check_payout_safety(asset: str, min_payout: float = 80.0) -> bool:
        """[ফিল্টার ২] পেআউট ভ্যালিডেটর (৮০%-এর কম পেআউটে ট্রেড হবে না)"""
        try:
            url = f"{QX_REST_API}/payouts"
            params = {"broker": "quotex", "market": "otc" if "otc" in asset.lower() else "real"}
            response = http_session.get(url, params=params, timeout=5)
            data = response.json()

            if data.get("ok"):
                pairs = data.get("data", [])
                for p in pairs:
                    if p.get("name") == asset and p.get("open"):
                        payout = p.get("payout", 0)
                        if payout >= min_payout:
                            return True
                        else:
                            logger.warning(f"⚠️ [Payout Guard] {asset} payout is {payout}% (< {min_payout}%). Blocked!")
                            return False
            return True
        except Exception as e:
            logger.error(f"Payout Filter Error: {e}")
            return True

    @staticmethod
    def verify_via_groq_ai(market_context: str) -> str:
        """[ফিল্টার ৩] Groq LPU AI কনফ্লুয়েন্স ভ্যালিডেশন (মিলি-সেকেন্ডে সিগন্যাল যাচাই)"""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a master institutional binary options AI arbiter. Return ONLY 'CALL', 'PUT', or 'HOLD'."},
                {"role": "user", "content": f"Analyze technical confluence & market context: {market_context}. Output direction only."}
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=3)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip().upper()
        except Exception as e:
            logger.error(f"Groq AI Arbiter Error: {e}")
        return "HOLD"

    @staticmethod
    def analyze_market_conditions(candles: list) -> str:
        """মূল টেকনিক্যাল লজিক ও ইন্ডিকেটর কনফ্লুয়েন্স চেক"""
        if not candles or len(candles) < 10:
            return "HOLD"
        
        # সাম্প্রতিক ক্যান্ডেলের ক্লোজিং প্রাইস বা টিক বিশ্লেষণ
        latest = candles[-1]
        prev = candles[-2]
        
        # সহজ মোমেন্টাম ও স্ট্রাকচার চেক
        if latest.get('close', 0) > prev.get('close', 0):
            return "CALL"
        elif latest.get('close', 0) < prev.get('close', 0):
            return "PUT"
            
        return "HOLD"
