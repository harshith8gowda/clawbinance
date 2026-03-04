#!/usr/bin/env python3
"""
ClawTrader — Binance Futures Trading Signal Generator
Binance OpenClaw Hackathon Submission — Option A

Z-Score based trading strategy adapted from QT Power Gold/Silver system.
Generates LONG/SHORT signals for Binance futures with Telegram + X alerts.

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
from enum import Enum

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')


class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    symbol: str  # BTCUSDT, ETHUSDT, etc.
    signal_type: SignalType
    price: float
    zscore: float
    confidence: str  # HIGH, MEDIUM, LOW
    position_size: float  # Recommended position size
    expected_return: float  # Expected % return
    timestamp: str
    reasoning: str


class BinanceFuturesClient:
    """Binance Futures API client"""
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.headers = {}
        if self.api_key:
            self.headers["X-MBX-APIKEY"] = self.api_key
    
    def fetch_klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV data from Binance Futures"""
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
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            return df
        except Exception as e:
            print(f"❌ Error fetching {symbol}: {e}")
            return pd.DataFrame()
    
    def get_top_volume_symbols(self, limit: int = 10) -> List[str]:
        """Get top volume futures symbols"""
        url = f"{self.BASE_URL}/fapi/v1/ticker/24hr"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            # Filter USDT pairs and sort by volume
            usdt_pairs = [d for d in data if d['symbol'].endswith('USDT')]
            sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['volume']), reverse=True)
            
            return [p['symbol'] for p in sorted_pairs[:limit]]
        except Exception as e:
            print(f"❌ Error fetching top symbols: {e}")
            return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # Fallback


class ZScoreStrategy:
    """Z-Score based mean reversion strategy"""
    
    def __init__(self, lookback_period: int = 50, zscore_threshold: float = 2.0):
        self.lookback_period = lookback_period
        self.zscore_threshold = zscore_threshold
    
    def calculate_zscore(self, prices: pd.Series) -> float:
        """Calculate current Z-Score"""
        if len(prices) < self.lookback_period:
            return 0.0
        
        recent_prices = prices.iloc[-self.lookback_period:]
        mean = recent_prices.mean()
        std = recent_prices.std()
        
        if std == 0:
            return 0.0
        
        current_price = prices.iloc[-1]
        zscore = (current_price - mean) / std
        
        return zscore
    
    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Optional[TradingSignal]:
        """Generate trading signal based on Z-Score"""
        if df.empty or len(df) < self.lookback_period:
            return None
        
        prices = df['close']
        current_price = prices.iloc[-1]
        zscore = self.calculate_zscore(prices)
        
        # Determine signal
        if zscore < -self.zscore_threshold:
            signal_type = SignalType.LONG
            confidence = "HIGH" if zscore < -2.5 else "MEDIUM"
            reasoning = f"Price {abs(zscore):.2f}σ below mean. Oversold bounce likely."
            expected_return = abs(zscore) * 0.5  # 1% per sigma
            
        elif zscore > self.zscore_threshold:
            signal_type = SignalType.SHORT
            confidence = "HIGH" if zscore > 2.5 else "MEDIUM"
            reasoning = f"Price {zscore:.2f}σ above mean. Overextended pullback likely."
            expected_return = zscore * 0.5
            
        else:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_price,
                zscore=zscore,
                confidence="NONE",
                position_size=0,
                expected_return=0,
                timestamp=datetime.now().isoformat(),
                reasoning=f"Z-Score {zscore:.2f} within normal range. No signal."
            )
        
        # Calculate position size (1% risk)
        position_size = 100  # $100 per trade (adjustable)
        
        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            price=current_price,
            zscore=zscore,
            confidence=confidence,
            position_size=position_size,
            expected_return=expected_return,
            timestamp=datetime.now().isoformat(),
            reasoning=reasoning
        )


class TelegramNotifier:
    """Send signals via Telegram"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
    
    def send_signal(self, signal: TradingSignal) -> bool:
        """Format and send signal to Telegram"""
        if not self.bot_token or not self.chat_id:
            print("     ⚠️  Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
            return False
        
        if signal.signal_type == SignalType.HOLD:
            return False  # Don't send hold signals
        
        emoji = "🟢" if signal.signal_type == SignalType.LONG else "🔴"
        
        message = f"""
{emoji} **CLAWTRADER SIGNAL — {datetime.now().strftime('%H:%M')} Dubai**

**{signal.symbol}** — {signal.signal_type.value} ENTRY

Price: ${signal.price:,.2f}
Z-Score: {signal.zscore:+.2f} (need ±{2.0})
Confidence: {signal.confidence}
Position: ${signal.position_size:,.0f}
Expected: +{signal.expected_return:.1f}%

{signal.reasoning}

Execute on Binance Futures NOW! 🚀
        """
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False


class ClawTrader:
    """Main trading agent"""
    
    def __init__(self):
        self.binance = BinanceFuturesClient()
        self.strategy = ZScoreStrategy()
        self.telegram = TelegramNotifier()
        self.symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    
    def scan_markets(self) -> List[TradingSignal]:
        """Scan all markets for signals"""
        signals = []
        
        print("🔍 Scanning Binance Futures markets...\n")
        
        for symbol in self.symbols:
            print(f"  Analyzing {symbol}...", end=" ")
            
            # Fetch data
            df = self.binance.fetch_klines(symbol, interval="15m", limit=100)
            
            if df.empty:
                print("❌ No data")
                continue
            
            # Generate signal
            signal = self.strategy.generate_signal(symbol, df)
            
            if signal:
                signals.append(signal)
                
                if signal.signal_type != SignalType.HOLD:
                    print(f"🚨 {signal.signal_type.value} SIGNAL (Z: {signal.zscore:+.2f})")
                    
                    # Send to Telegram
                    if self.telegram.send_signal(signal):
                        print("     ✅ Telegram alert sent")
                else:
                    print(f"✓ Hold (Z: {signal.zscore:+.2f})")
        
        return signals
    
    def run(self):
        """Main execution loop"""
        print("="*60)
        print("🦞 CLAWTRADER — Binance Futures Signal Generator")
        print("="*60)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Dubai")
        print(f"Monitoring: {', '.join(self.symbols)}")
        print("-"*60)
        
        signals = self.scan_markets()
        
        # Summary
        entry_signals = [s for s in signals if s.signal_type != SignalType.HOLD]
        
        print("\n" + "="*60)
        print(f"📊 SCAN COMPLETE — {len(entry_signals)} signals found")
        print("="*60)
        
        for signal in entry_signals:
            print(f"\n{signal.symbol}: {signal.signal_type.value}")
            print(f"  Price: ${signal.price:,.2f}")
            print(f"  Z-Score: {signal.zscore:+.2f}")
            print(f"  Confidence: {signal.confidence}")
        
        # Save results
        output = {
            "timestamp": datetime.now().isoformat(),
            "signals": [
                {
                    "symbol": s.symbol,
                    "type": s.signal_type.value,
                    "price": s.price,
                    "zscore": s.zscore,
                    "confidence": s.confidence
                }
                for s in signals
            ]
        }
        
        with open("clawtrader_signals.json", "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Results saved to clawtrader_signals.json")
        
        return signals


def main():
    """Entry point"""
    trader = ClawTrader()
    signals = trader.run()
    
    # Exit code based on signals found
    entry_count = len([s for s in signals if s.signal_type != SignalType.HOLD])
    sys.exit(0 if entry_count > 0 else 0)


if __name__ == "__main__":
    main()
