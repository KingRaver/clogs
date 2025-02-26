# meme_phrases.py
# Contains meme phrases for crypto market analysis

from enum import Enum
from typing import Dict, List, Optional

# Original meme phrases
MEME_PHRASES = {
    'bullish': [
        "Going to the moon!",
        "Diamond hands activated!",
        "Bears getting rekt!",
        "Pump it up!",
        "Green candles incoming!"
    ],
    'bearish': [
        "This is fine. (It's not fine)",
        "Bear market things",
        "Buying the dip... again",
        "Pain.",
        "Liquidation cascade incoming"
    ],
    'neutral': [
        "Boring market is boring",
        "Crab market continues",
        "Sideways action forever",
        "Waiting for volatility",
        "Consolidation phase"
    ],
    'volatile': [
        "Hold onto your hats!",
        "Traders' nightmare",
        "Epic volatility",
        "Rollercoaster mode activated",
        "Chop city"
    ],
    'recovering': [
        "Finding a bottom",
        "Green shoots appearing",
        "Relief rally time",
        "Bottom fishers rewarded",
        "Comeback season"
    ]
}

# KAITO-specific meme phrases
KAITO_MEME_PHRASES = {
    'bullish': [
        "KAITO taking off like a rocket!",
        "KAITO bulls feasting today!",
        "Smart money loading up on KAITO!",
        "KAITO showing massive strength!",
        "KAITO breaking through resistance like it's nothing!",
        "KAITO whales accumulating hard!",
        "Imagine not having KAITO in your portfolio right now!",
        "KAITO outperforming everything in sight!"
    ],
    'bearish': [
        "KAITO taking a breather after its epic run",
        "KAITO discount sale! Everything must go!",
        "KAITO testing HODLer conviction",
        "Paper hands shaking out of KAITO",
        "KAITO hitting support levels - time to buy?",
        "Weak hands folding on KAITO",
        "KAITO whales creating liquidity for a bigger move",
        "KAITO bear trap in progress"
    ],
    'neutral': [
        "KAITO accumulation phase in progress",
        "KAITO coiling for the next big move",
        "Smart money quietly accumulating KAITO",
        "KAITO volume drying up - calm before the storm?",
        "KAITO trading in a tight range",
        "KAITO consolidating after recent volatility",
        "Patience is key with KAITO right now",
        "KAITO building a solid base"
    ],
    'volatile': [
        "KAITO going absolutely crazy right now!",
        "KAITO shorts and longs getting liquidated!",
        "KAITO volatility through the roof!",
        "KAITO making traders dizzy with these swings!",
        "KAITO showing peak volatility!",
        "KAITO traders need motion sickness pills!",
        "KAITO chart looking like an EKG!",
        "KAITO bouncing around like a pinball!"
    ],
    'recovering': [
        "KAITO showing signs of life!",
        "KAITO recovery phase initiated!",
        "KAITO bouncing back from the lows!",
        "KAITO refusing to stay down!",
        "KAITO resilience on display!",
        "KAITO finding its footing after the dip!",
        "KAITO's recovery catching everyone by surprise!",
        "Dip buyers saving KAITO!"
    ],
    'smart_money': [
        "Unusual KAITO volume detected - someone knows something",
        "KAITO smart money flow indicator flashing!",
        "Institutional accumulation pattern on KAITO",
        "KAITO showing classic smart money footprints",
        "Whale alert on KAITO - big money moving in",
        "KAITO showing textbook accumulation patterns",
        "Smart money divergence on KAITO",
        "KAITO order flow showing hidden accumulation"
    ]
}

# Volume-specific phrases for KAITO
KAITO_VOLUME_PHRASES = {
    'significant_increase': [
        "KAITO volume exploding! Something big brewing?",
        "Massive KAITO volume spike detected!",
        "KAITO volume through the roof - institutions loading up?",
        "Unprecedented KAITO volume surge!",
        "KAITO trading volume on steroids today!"
    ],
    'moderate_increase': [
        "KAITO volume picking up steam",
        "Growing interest in KAITO with rising volumes",
        "KAITO volume ticking up - early sign of momentum?",
        "Steady increase in KAITO trading activity",
        "KAITO volume starting to build"
    ],
    'significant_decrease': [
        "KAITO volume falling off a cliff",
        "KAITO interest waning with plummeting volume",
        "KAITO volume disappearing - traders moving elsewhere?",
        "Major drop in KAITO trading activity",
        "KAITO volume drought intensifying"
    ],
    'moderate_decrease': [
        "KAITO volume cooling off slightly",
        "Modest decline in KAITO trading interest",
        "KAITO volume easing back to normal levels",
        "Traders taking a break from KAITO action",
        "KAITO volume tapering down"
    ],
    'stable': [
        "KAITO volume staying consistent",
        "Steady as she goes for KAITO volume",
        "KAITO trading at normal volume levels",
        "No major changes in KAITO trading activity",
        "KAITO volume in equilibrium"
    ]
}

# Layer 1 comparison phrases for KAITO
KAITO_VS_L1_PHRASES = {
    'outperforming': [
        "KAITO leaving Layer 1s in the dust!",
        "KAITO outshining major Layer 1s today!",
        "KAITO flexing on ETH, SOL and other L1s!",
        "KAITO showing the Layer 1s how it's done!",
        "Layer 1s can't keep up with KAITO's pace!"
    ],
    'underperforming': [
        "KAITO lagging behind Layer 1 momentum",
        "KAITO struggling while Layer 1s pump",
        "KAITO needs to catch up to Layer 1 performance",
        "Layer 1 strength overshadowing KAITO today",
        "KAITO taking a backseat to Layer 1 gains"
    ],
    'correlated': [
        "KAITO moving in lockstep with Layer 1s",
        "KAITO and Layer 1 correlation strengthening",
        "KAITO riding the Layer 1 wave",
        "Strong KAITO-Layer 1 correlation today",
        "KAITO mirroring Layer 1 price action"
    ],
    'diverging': [
        "KAITO breaking away from Layer 1 correlation",
        "KAITO charting its own path away from Layer 1s",
        "KAITO-Layer 1 correlation weakening",
        "KAITO and Layer 1s going separate ways",
        "KAITO decoupling from Layer 1 price action"
    ]
}

# Smart money indicator phrases
SMART_MONEY_PHRASES = {
    'accumulation': [
        "Classic accumulation pattern forming on KAITO",
        "Smart money quietly accumulating KAITO",
        "Institutional accumulation detected on KAITO",
        "Stealth accumulation phase underway for KAITO",
        "Wyckoff accumulation signals on KAITO chart"
    ],
    'distribution': [
        "Distribution pattern emerging on KAITO",
        "Smart money distribution phase for KAITO",
        "Institutional selling pressure on KAITO",
        "KAITO showing classic distribution signals",
        "Wyckoff distribution pattern on KAITO"
    ],
    'divergence': [
        "Price-volume divergence on KAITO - smart money move?",
        "KAITO showing bullish divergence patterns",
        "Hidden divergence on KAITO volume profile",
        "Smart money divergence signals flashing on KAITO",
        "Institutional divergence pattern on KAITO"
    ],
    'abnormal_volume': [
        "Highly unusual volume pattern on KAITO",
        "Abnormal KAITO trading activity detected",
        "KAITO volume anomaly spotted - insider action?",
        "Strange KAITO volume signature today",
        "Statistically significant volume anomaly on KAITO"
    ]
}

# Get random meme phrase based on context
def get_kaito_meme_phrase(context: str, subcontext: Optional[str] = None) -> str:
    """
    Get a random KAITO meme phrase based on context
    
    Args:
        context: Main context (mood, volume, l1_comparison, smart_money)
        subcontext: Sub-context for more specific phrases
        
    Returns:
        Random meme phrase for the given context
    """
    import random
    
    # Select appropriate phrase dictionary
    if context == 'mood':
        if subcontext and subcontext in KAITO_MEME_PHRASES:
            phrases = KAITO_MEME_PHRASES[subcontext]
        else:
            phrases = KAITO_MEME_PHRASES['neutral']
    elif context == 'volume':
        if subcontext and subcontext in KAITO_VOLUME_PHRASES:
            phrases = KAITO_VOLUME_PHRASES[subcontext]
        else:
            phrases = KAITO_VOLUME_PHRASES['stable']
    elif context == 'l1_comparison':
        if subcontext and subcontext in KAITO_VS_L1_PHRASES:
            phrases = KAITO_VS_L1_PHRASES[subcontext]
        else:
            phrases = KAITO_VS_L1_PHRASES['correlated']
    elif context == 'smart_money':
        if subcontext and subcontext in SMART_MONEY_PHRASES:
            phrases = SMART_MONEY_PHRASES[subcontext]
        else:
            phrases = SMART_MONEY_PHRASES['accumulation']
    else:
        # Default to general KAITO bullish phrases
        phrases = KAITO_MEME_PHRASES['bullish']
    
    # Return random phrase from selected list
    return random.choice(phrases)
