#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Optional, Any, Union, List, Tuple
import sys
import os
import time
import requests
import re
import numpy as np
from datetime import datetime, timedelta
import anthropic
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import random
import statistics

from utils.logger import logger
from utils.browser import browser
from config import config
from coingecko_handler import CoinGeckoHandler
from mood_config import MoodIndicators, determine_advanced_mood, Mood, MemePhraseGenerator
from meme_phrases import MEME_PHRASES, KAITO_MEME_PHRASES

class KaitoAnalysisBot:
    def __init__(self) -> None:
        self.browser = browser
        self.config = config
        self.claude_client = anthropic.Client(api_key=self.config.CLAUDE_API_KEY)
        self.past_predictions = []
        self.meme_phrases = MEME_PHRASES
        self.kaito_meme_phrases = KAITO_MEME_PHRASES
        self.last_check_time = datetime.now()
        self.last_market_data = {}
        
        # Initialize CoinGecko handler with 60s cache duration
        self.coingecko = CoinGeckoHandler(
            base_url=self.config.COINGECKO_BASE_URL,
            cache_duration=60
        )
        
        # Primary token to focus on
        self.primary_token = 'KAITO'
        
        # Target chains - KAITO and reference Layer 1s
        self.target_chains = {
            'KAITO': 'kaito',  # Primary focus
            'SOL': 'solana',   # Layer 1 reference
            'ETH': 'ethereum', # Layer 1 reference
            'AVAX': 'avalanche-2', # Layer 1 reference
            'DOT': 'polkadot'  # Layer 1 reference
        }

        # Layer 1 reference tokens for comparison
        self.reference_tokens = ['SOL', 'ETH', 'AVAX', 'DOT']
        
        # Chain name mapping for display
        self.chain_name_mapping = {
            'KAITO': 'kaito',
            'SOL': 'solana',
            'ETH': 'ethereum',
            'AVAX': 'avalanche-2',
            'DOT': 'polkadot'
        }
        
        self.CORRELATION_THRESHOLD = 0.75  
        self.VOLUME_THRESHOLD = 0.60  
        self.TIME_WINDOW = 24
        
        # Smart money thresholds
        self.SMART_MONEY_VOLUME_THRESHOLD = 1.5  # 50% above average
        self.SMART_MONEY_ZSCORE_THRESHOLD = 2.0  # 2 standard deviations
        
        logger.log_startup()

    def _get_historical_volume_data(self, chain: str, minutes: int = None) -> List[Dict[str, Any]]:
        """
        Get historical volume data for the specified window period
        """
        try:
            # Use config's window minutes if not specified
            if minutes is None:
                minutes = self.config.VOLUME_WINDOW_MINUTES
                
            window_start = datetime.now() - timedelta(minutes=minutes)
            query = """
                SELECT timestamp, volume
                FROM market_data
                WHERE chain = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """
            
            conn = self.config.db.conn
            cursor = conn.cursor()
            cursor.execute(query, (chain, window_start))
            results = cursor.fetchall()
            
            volume_data = [
                {
                    'timestamp': datetime.fromisoformat(row[0]),
                    'volume': float(row[1])
                }
                for row in results
            ]
            
            logger.logger.debug(
                f"Retrieved {len(volume_data)} volume data points for {chain} "
                f"over last {minutes} minutes"
            )
            
            return volume_data
            
        except Exception as e:
            logger.log_error(f"Historical Volume Data - {chain}", str(e))
            return []

    def _analyze_volume_trend(self, current_volume: float, historical_data: List[Dict[str, Any]]) -> Tuple[float, str]:
        """
        Analyze volume trend over the window period
        Returns (percentage_change, trend_description)
        """
        if not historical_data:
            return 0.0, "insufficient_data"
            
        try:
            # Calculate average volume excluding the current volume
            historical_volumes = [entry['volume'] for entry in historical_data]
            avg_volume = statistics.mean(historical_volumes) if historical_volumes else current_volume
            
            # Calculate percentage change
            volume_change = ((current_volume - avg_volume) / avg_volume) * 100
            
            # Determine trend
            if volume_change >= self.config.VOLUME_TREND_THRESHOLD:
                trend = "significant_increase"
            elif volume_change <= -self.config.VOLUME_TREND_THRESHOLD:
                trend = "significant_decrease"
            elif volume_change >= 5:  # Smaller but notable increase
                trend = "moderate_increase"
            elif volume_change <= -5:  # Smaller but notable decrease
                trend = "moderate_decrease"
            else:
                trend = "stable"
                
            logger.logger.debug(
                f"Volume trend analysis: {volume_change:.2f}% change from average. "
                f"Current: {current_volume:,.0f}, Avg: {avg_volume:,.0f}, "
                f"Trend: {trend}"
            )
            
            return volume_change, trend
            
        except Exception as e:
            logger.log_error("Volume Trend Analysis", str(e))
            return 0.0, "error"

    def _analyze_smart_money_indicators(self, kaito_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze potential smart money movements in KAITO token
        Look for unusual volume spikes, price-volume divergence, and accumulation patterns
        """
        try:
            # Get historical data over multiple timeframes
            hourly_data = self._get_historical_volume_data('KAITO', minutes=60)
            daily_data = self._get_historical_volume_data('KAITO', minutes=1440)
            
            current_volume = kaito_data['volume']
            current_price = kaito_data['current_price']
            
            # Volume anomaly detection
            hourly_volumes = [entry['volume'] for entry in hourly_data]
            daily_volumes = [entry['volume'] for entry in daily_data]
            
            # Calculate baselines
            avg_hourly_volume = statistics.mean(hourly_volumes) if hourly_volumes else current_volume
            avg_daily_volume = statistics.mean(daily_volumes) if daily_volumes else current_volume
            
            # Volume Z-score (how many standard deviations from mean)
            hourly_std = statistics.stdev(hourly_volumes) if len(hourly_volumes) > 1 else 1
            volume_z_score = (current_volume - avg_hourly_volume) / hourly_std if hourly_std != 0 else 0
            
            # Price-volume divergence
            # (Price going down while volume increasing suggests accumulation)
            price_direction = 1 if kaito_data['price_change_percentage_24h'] > 0 else -1
            volume_direction = 1 if current_volume > avg_daily_volume else -1
            
            # Divergence detected when price and volume move in opposite directions
            divergence = (price_direction != volume_direction)
            
            # Check for abnormal volume with minimal price movement (potential accumulation)
            stealth_accumulation = (abs(kaito_data['price_change_percentage_24h']) < 2) and (current_volume > avg_daily_volume * 1.5)
            
            # Calculate volume profile - percentage of volume in each hour
            volume_profile = {}
            if hourly_data:
                for i in range(24):
                    hour_window = datetime.now() - timedelta(hours=i+1)
                    hour_volume = sum(entry['volume'] for entry in hourly_data if hour_window <= entry['timestamp'] <= hour_window + timedelta(hours=1))
                    volume_profile[f"hour_{i+1}"] = hour_volume
            
            # Detect unusual trading hours (potential institutional activity)
            total_volume = sum(volume_profile.values()) if volume_profile else 0
            unusual_hours = []
            
            if total_volume > 0:
                for hour, vol in volume_profile.items():
                    hour_percentage = (vol / total_volume) * 100
                    if hour_percentage > 15:  # More than 15% of daily volume in a single hour
                        unusual_hours.append(hour)
            
            # Detect volume clusters (potential accumulation zones)
            volume_cluster_detected = False
            if len(hourly_volumes) >= 3:
                for i in range(len(hourly_volumes)-2):
                    if all(vol > avg_hourly_volume * 1.3 for vol in hourly_volumes[i:i+3]):
                        volume_cluster_detected = True
                        break
            
            # Results
            return {
                'volume_z_score': volume_z_score,
                'price_volume_divergence': divergence,
                'stealth_accumulation': stealth_accumulation,
                'abnormal_volume': abs(volume_z_score) > self.SMART_MONEY_ZSCORE_THRESHOLD,
                'volume_vs_hourly_avg': (current_volume / avg_hourly_volume) - 1,
                'volume_vs_daily_avg': (current_volume / avg_daily_volume) - 1,
                'unusual_trading_hours': unusual_hours,
                'volume_cluster_detected': volume_cluster_detected
            }
        except Exception as e:
            logger.log_error("Smart Money Analysis", str(e))
            return {}

    def _analyze_kaito_vs_layer1s(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze KAITO performance relative to major Layer 1 blockchains
        """
        try:
            kaito_data = market_data.get('KAITO', {})
            if not kaito_data:
                return {}
                
            # Compare 24h performance
            layer1_avg_change = statistics.mean([
                market_data.get(token, {}).get('price_change_percentage_24h', 0) 
                for token in self.reference_tokens
                if token in market_data
            ])
            
            performance_diff = kaito_data['price_change_percentage_24h'] - layer1_avg_change
            
            # Compare volume growth
            layer1_avg_volume_change = statistics.mean([
                self._analyze_volume_trend(
                    market_data.get(token, {}).get('volume', 0),
                    self._get_historical_volume_data(token)
                )[0]
                for token in self.reference_tokens
                if token in market_data
            ])
            
            kaito_volume_change = self._analyze_volume_trend(
                kaito_data['volume'],
                self._get_historical_volume_data('KAITO')
            )[0]
            
            volume_growth_diff = kaito_volume_change - layer1_avg_volume_change
            
            # Calculate correlation with each L1
            correlations = {}
            for token in self.reference_tokens:
                if token in market_data:
                    # Simple correlation based on 24h change direction
                    kaito_direction = 1 if kaito_data['price_change_percentage_24h'] > 0 else -1
                    token_direction = 1 if market_data[token]['price_change_percentage_24h'] > 0 else -1
                    correlated = kaito_direction == token_direction
                    
                    correlations[token] = {
                        'correlated': correlated,
                        'kaito_change': kaito_data['price_change_percentage_24h'],
                        'token_change': market_data[token]['price_change_percentage_24h']
                    }
            
            # Determine if KAITO is outperforming the L1 market
            outperforming = performance_diff > 0
            
            return {
                'vs_layer1_avg_change': performance_diff,
                'vs_layer1_volume_growth': volume_growth_diff,
                'correlations': correlations,
                'outperforming_layer1s': outperforming
            }
            
        except Exception as e:
            logger.log_error("KAITO vs Layer1 Analysis", str(e))
            return {}

    def start(self) -> None:
        """Main bot execution loop"""
        try:
            retry_count = 0
            max_setup_retries = 3
            
            while retry_count < max_setup_retries:
                if not self.browser.initialize_driver():
                    retry_count += 1
                    logger.logger.warning(f"Browser initialization attempt {retry_count} failed, retrying...")
                    time.sleep(10)
                    continue
                    
                if not self._login_to_twitter():
                    retry_count += 1
                    logger.logger.warning(f"Twitter login attempt {retry_count} failed, retrying...")
                    time.sleep(15)
                    continue
                    
                break
            
            if retry_count >= max_setup_retries:
                raise Exception("Failed to initialize bot after maximum retries")

            logger.logger.info("Bot initialized successfully")

            while True:
                try:
                    self._run_analysis_cycle()
                    
                    # Calculate sleep time until next regular check
                    time_since_last = (datetime.now() - self.last_check_time).total_seconds()
                    sleep_time = max(0, self.config.BASE_INTERVAL - time_since_last)
                    
                    logger.logger.debug(f"Sleeping for {sleep_time:.1f}s until next check")
                    time.sleep(sleep_time)
                    
                    self.last_check_time = datetime.now()
                    
                except Exception as e:
                    logger.log_error("Analysis Cycle", str(e), exc_info=True)
                    time.sleep(60)  # Shorter sleep on error
                    continue

        except KeyboardInterrupt:
            logger.logger.info("Bot stopped by user")
        except Exception as e:
            logger.log_error("Bot Execution", str(e))
        finally:
            self._cleanup()

    def _should_post_update(self, new_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if we should post an update based on market changes
        Returns (should_post, trigger_reason)
        """
        if not self.last_market_data:
            self.last_market_data = new_data
            return True, "initial_post"

        trigger_reason = None

        # First check KAITO for significant changes
        if 'KAITO' in new_data and 'KAITO' in self.last_market_data:
            # Calculate immediate price change since last check
            price_change = abs(
                (new_data['KAITO']['current_price'] - self.last_market_data['KAITO']['current_price']) /
                self.last_market_data['KAITO']['current_price'] * 100
            )
            
            # Calculate immediate volume change since last check
            immediate_volume_change = abs(
                (new_data['KAITO']['volume'] - self.last_market_data['KAITO']['volume']) /
                self.last_market_data['KAITO']['volume'] * 100
            )

            logger.logger.debug(
                f"KAITO immediate changes - Price: {price_change:.2f}%, Volume: {immediate_volume_change:.2f}%"
            )

            # Check immediate price change
            if price_change >= self.config.PRICE_CHANGE_THRESHOLD:
                trigger_reason = "price_change_kaito"
                logger.logger.info(f"Significant price change detected for KAITO: {price_change:.2f}%")
                
            # Check immediate volume change
            elif immediate_volume_change >= self.config.VOLUME_CHANGE_THRESHOLD:
                trigger_reason = "volume_change_kaito"
                logger.logger.info(f"Significant immediate volume change detected for KAITO: {immediate_volume_change:.2f}%")
                
            # Check rolling window volume trend
            else:
                historical_volume = self._get_historical_volume_data('KAITO')
                if historical_volume:
                    volume_change_pct, trend = self._analyze_volume_trend(
                        new_data['KAITO']['volume'],
                        historical_volume
                    )
                    
                    # Log the volume trend
                    logger.logger.debug(
                        f"KAITO rolling window volume trend: {volume_change_pct:.2f}% ({trend})"
                    )
                    
                    # Check if trend is significant enough to trigger
                    if trend in ["significant_increase", "significant_decrease"]:
                        trigger_reason = f"volume_trend_kaito_{trend}"
                        logger.logger.info(
                            f"Significant volume trend detected for KAITO: "
                            f"{volume_change_pct:.2f}% over {self.config.VOLUME_WINDOW_MINUTES} minutes"
                        )
            
            # Check for smart money indicators
            if not trigger_reason:
                smart_money = self._analyze_smart_money_indicators(new_data['KAITO'])
                if smart_money.get('abnormal_volume') or smart_money.get('stealth_accumulation'):
                    trigger_reason = "smart_money_kaito"
                    logger.logger.info(f"Smart money movement detected for KAITO")
            
            # Check for significant outperformance vs L1s
            if not trigger_reason:
                vs_l1 = self._analyze_kaito_vs_layer1s(new_data)
                if vs_l1.get('outperforming_layer1s') and abs(vs_l1.get('vs_layer1_avg_change', 0)) > 5.0:
                    trigger_reason = "kaito_outperforming_l1s"
                    logger.logger.info(f"KAITO significantly outperforming Layer 1s")

        # Check if regular interval has passed
        if not trigger_reason:
            time_since_last = (datetime.now() - self.last_check_time).total_seconds()
            if time_since_last >= self.config.BASE_INTERVAL:
                trigger_reason = "regular_interval"
                logger.logger.debug("Regular interval check triggered")

        should_post = trigger_reason is not None
        if should_post:
            self.last_market_data = new_data
            logger.logger.info(f"Update triggered by: {trigger_reason}")
        else:
            logger.logger.debug("No triggers activated, skipping update")

        return should_post, trigger_reason

    def _get_crypto_data(self) -> Optional[Dict[str, Any]]:
        """Fetch KAITO and Layer 1 data from CoinGecko with retries"""
        try:
            params = {
                **self.config.get_coingecko_params(),
                'ids': ','.join(self.target_chains.values()), 
                'sparkline': True 
            }
            
            data = self.coingecko.get_market_data(params)
            if not data:
                logger.logger.error("Failed to fetch market data from CoinGecko")
                return None
                
            formatted_data = {
                coin['symbol'].upper(): {
                    'current_price': coin['current_price'],
                    'volume': coin['total_volume'],
                    'price_change_percentage_24h': coin['price_change_percentage_24h'],
                    'sparkline': coin.get('sparkline_in_7d', {}).get('price', []),
                    'market_cap': coin['market_cap'],
                    'market_cap_rank': coin['market_cap_rank'],
                    'total_supply': coin.get('total_supply'),
                    'max_supply': coin.get('max_supply'),
                    'circulating_supply': coin.get('circulating_supply'),
                    'ath': coin.get('ath'),
                    'ath_change_percentage': coin.get('ath_change_percentage')
                } for coin in data
            }
            
            # Log API usage statistics
            stats = self.coingecko.get_request_stats()
            logger.logger.debug(
                f"CoinGecko API stats - Daily requests: {stats['daily_requests']}, "
                f"Failed: {stats['failed_requests']}, Cache size: {stats['cache_size']}"
            )
            
            # Store market data in database
            for chain, chain_data in formatted_data.items():
                self.config.db.store_market_data(chain, chain_data)
            
            # Check if KAITO data is present
            if 'KAITO' not in formatted_data:
                logger.log_error("Crypto Data", f"Missing data for KAITO")
                return None
                
            logger.logger.info(f"Successfully fetched crypto data for {', '.join(formatted_data.keys())}")
            return formatted_data
                
        except Exception as e:
            logger.log_error("CoinGecko API", str(e))
            return None

    def _calculate_correlations(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate KAITO correlations with Layer 1s"""
        try:
            kaito_data = market_data['KAITO']
            
            correlations = {}
            
            # Calculate correlation with each Layer 1
            for l1 in self.reference_tokens:
                if l1 not in market_data:
                    continue
                    
                l1_data = market_data[l1]
                
                # Price correlation (simplified)
                price_correlation = abs(
                    kaito_data['price_change_percentage_24h'] - 
                    l1_data['price_change_percentage_24h']
                ) / max(abs(kaito_data['price_change_percentage_24h']), 
                       abs(l1_data['price_change_percentage_24h']))
                
                # Volume correlation (simplified)
                volume_correlation = abs(
                    (kaito_data['volume'] - l1_data['volume']) / 
                    max(kaito_data['volume'], l1_data['volume'])
                )
                
                correlations[f'price_correlation_{l1}'] = 1 - price_correlation
                correlations[f'volume_correlation_{l1}'] = 1 - volume_correlation
            
            # Calculate average L1 correlations
            price_correlations = [v for k, v in correlations.items() if 'price_correlation_' in k]
            volume_correlations = [v for k, v in correlations.items() if 'volume_correlation_' in k]
            
            correlations['avg_price_correlation'] = statistics.mean(price_correlations) if price_correlations else 0
            correlations['avg_volume_correlation'] = statistics.mean(volume_correlations) if volume_correlations else 0
            
            # Store correlation data
            self.config.db.store_correlation_analysis(correlations)
            
            logger.logger.debug(
                f"KAITO correlations calculated - Avg Price: {correlations['avg_price_correlation']:.2f}, "
                f"Avg Volume: {correlations['avg_volume_correlation']:.2f}"
            )
            
            return correlations
            
        except Exception as e:
            logger.log_error("Correlation Calculation", str(e))
            return {
                'avg_price_correlation': 0.0,
                'avg_volume_correlation': 0.0
            }

    def _analyze_market_sentiment(self, crypto_data: Dict[str, Any], trigger_type: str) -> Optional[str]:
        """Generate KAITO-specific market analysis with focus on volume and smart money"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.logger.debug(f"Starting KAITO market sentiment analysis (attempt {retry_count + 1})")
                
                # Get KAITO data
                kaito_data = crypto_data.get('KAITO', {})
                if not kaito_data:
                    logger.log_error("Market Analysis", "Missing KAITO data")
                    return None
                
                # Calculate correlations with Layer 1s
                correlations = self._calculate_correlations(crypto_data)
                
                # Get smart money indicators
                smart_money = self._analyze_smart_money_indicators(kaito_data)
                
                # Get KAITO vs Layer 1 performance
                vs_layer1 = self._analyze_kaito_vs_layer1s(crypto_data)
                
                # Get spicy callback for previous predictions
                callback = self._get_spicy_callback({sym: data['current_price'] 
                                                   for sym, data in crypto_data.items()})
                
                # Analyze KAITO mood
                indicators = MoodIndicators(
                    price_change=kaito_data['price_change_percentage_24h'],
                    trading_volume=kaito_data['volume'],
                    volatility=abs(kaito_data['price_change_percentage_24h']) / 100,
                    social_sentiment=None,
                    funding_rates=None,
                    liquidation_volume=None
                )
                
                mood = determine_advanced_mood(indicators)
                kaito_mood = {
                    'mood': mood.value,
                    'change': kaito_data['price_change_percentage_24h'],
                    'ath_distance': kaito_data['ath_change_percentage']
                }
                
                # Store mood data
                self.config.db.store_mood('KAITO', mood.value, indicators)
                
                # Generate KAITO-specific meme phrase
                meme_context = MemePhraseGenerator.generate_meme_phrase(
                    chain='KAITO',
                    mood=Mood(mood.value)
                )
                
                # Get volume trend for additional context
                historical_volume = self._get_historical_volume_data('KAITO')
                if historical_volume:
                    volume_change_pct, trend = self._analyze_volume_trend(
                        kaito_data['volume'],
                        historical_volume
                    )
                    volume_trend = {
                        'change_pct': volume_change_pct,
                        'trend': trend
                    }
                else:
                    volume_trend = {'change_pct': 0, 'trend': 'stable'}

                # Get historical context from database
                stats = self.config.db.get_chain_stats('KAITO', hours=24)
                if stats:
                    historical_context = f"24h Avg: ${stats['avg_price']:,.2f}, "
                    historical_context += f"High: ${stats['max_price']:,.2f}, "
                    historical_context += f"Low: ${stats['min_price']:,.2f}"
                else:
                    historical_context = "No historical data"
                
                # Check if this is a volume trend trigger
                volume_context = ""
                if "volume_trend" in trigger_type:
                    change = volume_trend['change_pct']
                    direction = "increase" if change > 0 else "decrease"
                    volume_context = f"\nVolume Analysis:\nKAITO showing {abs(change):.1f}% {direction} in volume over last hour. This is a significant {volume_trend['trend']}."

                # Smart money context
                smart_money_context = ""
                if smart_money.get('abnormal_volume'):
                    smart_money_context += f"\nAbnormal volume detected: {smart_money['volume_z_score']:.1f} standard deviations from mean."
                if smart_money.get('stealth_accumulation'):
                    smart_money_context += f"\nPotential stealth accumulation detected with minimal price movement and elevated volume."
                if smart_money.get('volume_cluster_detected'):
                    smart_money_context += f"\nVolume clustering detected, suggesting possible institutional activity."
                if smart_money.get('unusual_trading_hours'):
                    smart_money_context += f"\nUnusual trading hours detected: {', '.join(smart_money['unusual_trading_hours'])}."

                # Layer 1 comparison context
                l1_context = ""
                if vs_layer1.get('outperforming_layer1s'):
                    l1_context += f"\nKAITO outperforming Layer 1 average by {vs_layer1['vs_layer1_avg_change']:.1f}%"
                else:
                    l1_context += f"\nKAITO underperforming Layer 1 average by {abs(vs_layer1['vs_layer1_avg_change']):.1f}%"

                prompt = f"""Write a witty market analysis focusing on KAITO token with attention to volume changes and smart money movements. Format as a single paragraph. Market data:
                
                KAITO Performance:
                - Price: ${kaito_data['current_price']:,.4f}
                - 24h Change: {kaito_mood['change']:.1f}% ({kaito_mood['mood']})
                - Volume: ${kaito_data['volume']:,.0f}
                
                Historical Context:
                - KAITO: {historical_context}
                
                Volume Analysis:
                - 24h trend: {volume_trend['change_pct']:.1f}% over last hour ({volume_trend['trend']})
                - vs hourly avg: {smart_money.get('volume_vs_hourly_avg', 0)*100:.1f}%
                - vs daily avg: {smart_money.get('volume_vs_daily_avg', 0)*100:.1f}%
                {volume_context}
                
                Smart Money Indicators:
                - Volume Z-score: {smart_money.get('volume_z_score', 0):.2f}
                - Price-Volume Divergence: {smart_money.get('price_volume_divergence', False)}
                - Stealth Accumulation: {smart_money.get('stealth_accumulation', False)}
                - Abnormal Volume: {smart_money.get('abnormal_volume', False)}
                - Volume Clustering: {smart_money.get('volume_cluster_detected', False)}
                {smart_money_context}
                
                Layer 1 Comparison:
                - vs L1 avg change: {vs_layer1.get('vs_layer1_avg_change', 0):.1f}%
                - vs L1 volume growth: {vs_layer1.get('vs_layer1_volume_growth', 0):.1f}%
                - Outperforming L1s: {vs_layer1.get('outperforming_layer1s', False)}
                {l1_context}
                
                ATH Distance:
                - KAITO: {kaito_mood['ath_distance']:.1f}%
                
                KAITO-specific context:
                - Meme: {meme_context}
                
                Trigger Type: {trigger_type}
                
                Past Context: {callback if callback else 'None'}
                
                Note: Focus on volume patterns, smart money movements, and how KAITO is performing relative to Layer 1s. Keep the analysis fresh and varied. Avoid repetitive phrases."""
                
                logger.logger.debug("Sending analysis request to Claude")
                response = self.claude_client.messages.create(
                    model=self.config.CLAUDE_MODEL,
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                analysis = response.content[0].text
                logger.logger.debug("Received analysis from Claude")
                
                # Store prediction data
                prediction_data = {
                    'analysis': analysis,
                    'sentiment': {'KAITO': kaito_mood['mood']},
                    **{f"{sym.upper()}_price": data['current_price'] for sym, data in crypto_data.items()}
                }
                self._track_prediction(prediction_data, ['KAITO'])
                
                formatted_tweet = self._format_tweet_analysis(analysis, crypto_data)
                
                # Check for content similarity
                if self.config.db.check_content_similarity(formatted_tweet):
                    logger.logger.info("Similar content detected, retrying analysis")
                    retry_count += 1
                    continue
                
                # Store the content if it's unique
                self.config.db.store_posted_content(
                    content=formatted_tweet,
                    sentiment={'KAITO': kaito_mood},
                    trigger_type=trigger_type,
                    price_data={'KAITO': {'price': kaito_data['current_price'], 
                                      'volume': kaito_data['volume']}},
                    meme_phrases={'KAITO': meme_context}
                )
                return formatted_tweet
                
            except Exception as e:
                retry_count += 1
                wait_time = retry_count * 10
                logger.logger.error(f"Analysis error details: {str(e)}", exc_info=True)
                logger.logger.warning(f"Analysis error, attempt {retry_count}, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
        
        logger.log_error("Market Analysis", "Maximum retries reached")
        return None
