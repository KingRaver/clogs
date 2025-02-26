# mood_config.py
import random
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional

class Mood(Enum):
    BULLISH = 'bullish'
    BEARISH = 'bearish'
    NEUTRAL = 'neutral'
    VOLATILE = 'volatile'
    RECOVERING = 'recovering'

@dataclass
class MoodIndicators:
    """
    Comprehensive mood indicators for crypto market sentiment
    """
    price_change: float
    trading_volume: float
    volatility: float
    social_sentiment: Optional[float] = None
    funding_rates: Optional[float] = None
    liquidation_volume: Optional[float] = None

def determine_advanced_mood(indicators: MoodIndicators) -> Mood:
    """
    Advanced mood determination using multiple market indicators
    
    Args:
        indicators (MoodIndicators): Comprehensive market indicators
    
    Returns:
        Mood: Classified market mood
    """
    # Mood logic with multiple factor weighting
    mood_scores = {
        Mood.BULLISH: 0,
        Mood.BEARISH: 0,
        Mood.NEUTRAL: 0,
        Mood.VOLATILE: 0,
        Mood.RECOVERING: 0
    }
    
    # Price change scoring
    if indicators.price_change > 5:
        mood_scores[Mood.BULLISH] += 3
    elif indicators.price_change < -5:
        mood_scores[Mood.BEARISH] += 3
    elif -2 <= indicators.price_change <= 2:
        mood_scores[Mood.NEUTRAL] += 2
    elif -5 <= indicators.price_change < -2:
        mood_scores[Mood.RECOVERING] += 2
    
    # Volatility scoring
    if indicators.volatility > 0.1:  # 10% volatility threshold
        mood_scores[Mood.VOLATILE] += 3
    elif 0.05 < indicators.volatility <= 0.1:
        mood_scores[Mood.VOLATILE] += 1
        
    # Volume impact
    if indicators.trading_volume > 1.5e9:  # High volume threshold
        mood_scores[Mood.VOLATILE] += 1
        if indicators.price_change > 0:
            mood_scores[Mood.BULLISH] += 1
        else:
            mood_scores[Mood.BEARISH] += 1
            
    # Recovery patterns
    if -8 <= indicators.price_change < -2 and indicators.volatility < 0.08:
        mood_scores[Mood.RECOVERING] += 2
    
    # Optional indicators when available
    if indicators.social_sentiment is not None:
        if indicators.social_sentiment > 0.7:
            mood_scores[Mood.BULLISH] += 1
        elif indicators.social_sentiment < 0.3:
            mood_scores[Mood.BEARISH] += 1
    
    if indicators.funding_rates is not None:
        if abs(indicators.funding_rates) > 0.01:  # 1% threshold
            mood_scores[Mood.VOLATILE] += 1
    
    if indicators.liquidation_volume is not None:
        if indicators.liquidation_volume > 100e6:  # $100M threshold
            mood_scores[Mood.VOLATILE] += 2
            mood_scores[Mood.BEARISH] += 1
    
    # Determine final mood
    return max(mood_scores.items(), key=lambda x: x[1])[0]

class MemePhraseGenerator:
    """
    Generates chain-specific meme phrases based on market mood
    """
    
    MEME_TEMPLATE_LIBRARY = {
        Mood.BULLISH: [
            "{chain} is MOONING! Diamond hands activated!",
            "Bulls are running wild for {chain}! All aboard the rocket!",
            "Massive green candles lighting up {chain}'s chart!",
            "{chain} looking THICC and ready to break resistance!"
        ],
        Mood.BEARISH: [
            "{chain} taking a brutal beating right now",
            "Massive liquidation incoming for {chain} holders",
            "Crypto gods are NOT happy with {chain} today",
            "{chain} chart looking like a cliff dive"
        ],
        Mood.NEUTRAL: [
            "{chain} chillin' like a villain",
            "Sideways action for {chain} - patience is key",
            "Nothing to see here, just {chain} doing its thing",
            "{chain} playing it cool in the crypto playground"
        ],
        Mood.VOLATILE: [
            "{chain} on a WILD rollercoaster ride!",
            "Buckle up {chain} fam, it's gonna be a BUMPY ride!",
            "Massive swings incoming for {chain} - traders' nightmare!",
            "{chain} chart looking like an EKG on caffeine! ⚡"
        ],
        Mood.RECOVERING: [
            "{chain} bouncing back like a BOSS!",
            "Phoenix mode activated for {chain}! Rising from the ashes",
            "Dip buyers saving {chain}'s day!",
            "{chain} showing true resilience!"
        ]
    }

    @classmethod
    def generate_meme_phrase(cls, chain: str, mood: Mood) -> str:
        """
        Generate a dynamic meme phrase based on chain and mood
        
        Args:
            chain (str): Cryptocurrency chain
            mood (Mood): Current market mood
        
        Returns:
            str: Formatted meme phrase
        """
        templates = cls.MEME_TEMPLATE_LIBRARY.get(mood, cls.MEME_TEMPLATE_LIBRARY[Mood.NEUTRAL])
        return random.choice(templates).format(chain=chain)
