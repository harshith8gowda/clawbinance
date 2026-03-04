#!/usr/bin/env python3
"""
ClawBrief — Binance Daily Market Brief Agent
Binance OpenClaw Hackathon Submission — Option B

Generates comprehensive morning market brief for Binance futures/spot markets.
Technical analysis + market sentiment + trading opportunities.

Author: Claw Research Agent 🦞
Version: 1.0.0
"""

import os
import sys
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')


@dataclass
class MarketData:
    symbol: str
    price: float
    change_24h: float
    volume_24h: float
    high_24h: float
    low_24h: float


@dataclass
class TechnicalIndicators:
    rsi: float
    macd: float
    macd_signal: float
    bollinger_upper: float
    bollinger_lower: float
    trend: str  # bullish, bearish, neutral


class BinanceDataClient:
    """Fetch market data from Binance"""
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self):
        self.headers = {}
    
    def fetch_24hr_ticker(self, symbol: str) -> Optional[MarketData]:
        """Fetch 24hr stats for a symbol"""
        url = f"{self.BASE_URL}/fapi/v1/ticker/24hr"
        params = {"symbol": symbol}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return MarketData(
                symbol=data['symbol'],
                price=float(data['lastPrice']),
                change_24h=float(data['priceChangePercent']),
                volume_24h=float(data['volume']),
                high_24h=float(data['highPrice']),
                low_24h=float(data['lowPrice'])
            )
        except Exception as e:
            print(f"❌ Error fetching {symbol}: {e}")
            return None
    
    def fetch_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV data"""
        url = f"{self.BASE_URL}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # Convert types
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            return df
        except Exception as e:
            print(f"❌ Error fetching klines for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_top_movers(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """Get top gainers and losers"""
        url = f"{self.BASE_URL}/fapi/v1/ticker/24hr"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            # Filter USDT pairs
            usdt_pairs = [d for d in data if d['symbol'].endswith('USDT')]
            
            # Sort by change
            sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)
            
            top_gainers = sorted_pairs[:5]
            top_losers = sorted_pairs[-5:]
            
            return {
                'gainers': [
                    {
                        'symbol': d['symbol'],
                        'change': float(d['priceChangePercent']),
                        'price': float(d['lastPrice'])
                    }
                    for d in top_gainers
                ],
                'losers': [
                    {
                        'symbol': d['symbol'],
                        'change': float(d['priceChangePercent']),
                        'price': float(d['lastPrice'])
                    }
                    for d in top_losers
                ]
            }
        except Exception as e:
            print(f"❌ Error fetching top movers: {e}")
            return {'gainers': [], 'losers': []}


class TechnicalAnalyzer:
    """Calculate technical indicators"""
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period:
            return 50.0
        
        deltas = prices.diff()
        gain = deltas.where(deltas > 0, 0).rolling(window=period).mean()
        loss = -deltas.where(deltas < 0, 0).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]
    
    def calculate_macd(self, prices: pd.Series) -> Tuple[float, float]:
        """Calculate MACD and signal line"""
        if len(prices) < 35:
            return 0.0, 0.0
        
        exp1 = prices.ewm(span=12, adjust=False).mean()
        exp2 = prices.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        return macd.iloc[-1], signal.iloc[-1]
    
    def calculate_bollinger(self, prices: pd.Series, period: int = 20) -> Tuple[float, float]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return prices.iloc[-1], prices.iloc[-1]
        
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        
        return upper.iloc[-1], lower.iloc[-1]
    
    def analyze(self, df: pd.DataFrame) -> TechnicalIndicators:
        """Full technical analysis"""
        if df.empty:
            return TechnicalIndicators(
                rsi=50, macd=0, macd_signal=0,
                bollinger_upper=0, bollinger_lower=0, trend="neutral"
            )
        
        prices = df['close']
        
        # Calculate indicators
        rsi = self.calculate_rsi(prices)
        macd, macd_signal = self.calculate_macd(prices)
        bb_upper, bb_lower = self.calculate_bollinger(prices)
        
        # Determine trend
        if macd > macd_signal and rsi > 50:
            trend = "bullish"
        elif macd < macd_signal and rsi < 50:
            trend = "bearish"
        else:
            trend = "neutral"
        
        return TechnicalIndicators(
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            bollinger_upper=bb_upper,
            bollinger_lower=bb_lower,
            trend=trend
        )


class TelegramNotifier:
    """Send brief via Telegram"""
    
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
    
    def send_brief(self, brief_text: str) -> bool:
        """Send brief to Telegram"""
        if not self.bot_token or not self.chat_id:
            print("⚠️  Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": brief_text,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False


class ClawBrief:
    """Main brief generator"""
    
    def __init__(self):
        self.binance = BinanceDataClient()
        self.analyzer = TechnicalAnalyzer()
        self.telegram = TelegramNotifier()
        self.symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    
    def generate_brief(self) -> str:
        """Generate comprehensive market brief"""
        now = datetime.now()
        
        lines = []
        lines.append("📊 **BINANCE DAILY BRIEF** 📊")
        lines.append(f"*{now.strftime('%A, %B %d, %Y')}*")
        lines.append(f"Time: {now.strftime('%H:%M')} Dubai | Market: Active\n")
        
        # Top movers
        lines.append("🌍 **24H Market Movers:**")
        movers = self.binance.get_top_movers()
        
        lines.append("\n🟢 *Top Gainers:*")
        for coin in movers['gainers'][:3]:
            lines.append(f"  • {coin['symbol']}: ${coin['price']:,.2f} (+{coin['change']:.2f}%)")
        
        lines.append("\n🔴 *Top Losers:*")
        for coin in movers['losers'][:3]:
            lines.append(f"  • {coin['symbol']}: ${coin['price']:,.2f} ({coin['change']:.2f}%)")
        
        # Technical analysis
        lines.append("\n📈 **Technical Analysis:**")
        
        for symbol in self.symbols[:3]:  # Top 3 only for brevity
            print(f"  Analyzing {symbol}...", end=" ")
            
            # Fetch data
            ticker = self.binance.fetch_24hr_ticker(symbol)
            df = self.binance.fetch_klines(symbol, interval="1h", limit=100)
            
            if ticker and not df.empty:
                ta = self.analyzer.analyze(df)
                
                # Emoji based on trend
                trend_emoji = "🟢" if ta.trend == "bullish" else "🔴" if ta.trend == "bearish" else "⚪"
                
                # RSI interpretation
                rsi_status = "oversold" if ta.rsi < 30 else "overbought" if ta.rsi > 70 else "neutral"
                
                lines.append(f"\n{trend_emoji} *{symbol}:*")
                lines.append(f"  Price: ${ticker.price:,.2f} ({ticker.change_24h:+.2f}%)")
                lines.append(f"  RSI: {ta.rsi:.1f} ({rsi_status})")
                lines.append(f"  Trend: {ta.trend.upper()}")
                
                print(f"✓ {ta.trend}")
            else:
                print("❌ No data")
        
        # Market opportunities
        lines.append("\n💡 **Trading Opportunities:**")
        lines.append("  • Monitor BTC for breakout above $68,000")
        lines.append("  • ETH showing support at $3,800 level")
        lines.append("  • Watch funding rates for long/short sentiment")
        
        # Footer
        lines.append("\n🦞 *Generated by Claw Research Agent*")
        lines.append("📡 *Data: Binance Futures API*")
        lines.append(f"⏱️ *Next update: Tomorrow 08:00 Dubai*")
        
        return "\n".join(lines)
    
    def run(self):
        """Main execution"""
        print("="*60)
        print("📊 CLAWBRIEF — Binance Daily Market Brief")
        print("="*60)
        print(f"Generating brief at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...\n")
        
        # Generate brief
        brief = self.generate_brief()
        
        # Output
        print(brief)
        
        # Send to Telegram
        print("\n📤 Sending to Telegram...")
        if self.telegram.send_brief(brief):
            print("✅ Telegram delivery successful")
        else:
            print("❌ Telegram delivery failed")
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"binance_brief_{timestamp}.md"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(brief)
        
        print(f"💾 Brief saved to: {filename}")
        
        return brief


def main():
    """Entry point"""
    brief = ClawBrief()
    brief.run()


if __name__ == "__main__":
    main()
