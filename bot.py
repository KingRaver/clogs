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
            
    def _is_duplicate_analysis(self, new_tweet: str, last_posts: List[str]) -> bool:
        """Check if analysis is a duplicate with relaxed similarity detection"""
        try:
            # For testing: Log that we're using relaxed duplicate detection
            logger.logger.info("Using relaxed duplicate detection settings")
            
            # Only check for exact duplicates in the database
            # This still stores all analyses but is less restrictive on what's considered a duplicate
            try:
                # Check for exact matches only in recent database entries (last 3 hours)
                exact_match = self.config.db.check_exact_content_match(new_tweet)
                if exact_match:
                    logger.logger.info("Exact duplicate detected in database (relaxed check)")
                    return True
            except Exception as e:
                # If the method doesn't exist, fall back to normal check but with a time limit
                # Only consider database entries from the last 2 hours
                recent_only = True
                hours_threshold = 1  # Only check duplicates from last hour
                if hasattr(self.config.db, 'check_content_similarity_with_timeframe'):
                    is_duplicate = self.config.db.check_content_similarity_with_timeframe(
                        new_tweet, hours=hours_threshold
                    )
                    if is_duplicate:
                        logger.logger.info(f"Similar content detected in database within last {hours_threshold} hours")
                        return True
                else:
                    # Skip database check if we can't limit by time
                    pass
                
            # Check for exact matches in recent posts (still important to prevent double-posting)
            for post in last_posts:
                if post.strip() == new_tweet.strip():
                    logger.logger.info("Exact duplicate detected in recent posts")
                    return True
            
            # Use more relaxed fuzzy matching (increase similarity threshold to 90%)
            new_content = new_tweet.split("\n\n#")[0].lower() if "\n\n#" in new_tweet else new_tweet.lower()
            
            for post in last_posts:
                post_content = post.split("\n\n#")[0].lower() if "\n\n#" in post else post.lower()
                
                # Calculate a simple similarity score based on word overlap
                new_words = set(new_content.split())
                post_words = set(post_content.split())
                
                if new_words and post_words:
                    overlap = len(new_words.intersection(post_words))
                    similarity = overlap / max(len(new_words), len(post_words))
                    
                    # Increased threshold from 0.7 to 0.9 (90% similar)
                    if similarity > 0.9:
                        logger.logger.info(f"Near-duplicate detected with {similarity:.2f} similarity (relaxed threshold)")
                        return True
                    elif similarity > 0.7:
                        # Log when we would have previously detected a duplicate but now allowing it
                        logger.logger.info(f"Post with {similarity:.2f} similarity allowed (would have been blocked before)")
                    
            return False
            
        except Exception as e:
            logger.log_error("Duplicate Check", str(e))
            # For testing purposes, allow posts even if duplicate check fails
            logger.logger.warning("Duplicate check failed, allowing post for testing")
            return False
            
    def _login_to_twitter(self) -> bool:
        """Log into Twitter with enhanced verification"""
        try:
            logger.logger.info("Starting Twitter login")
            self.browser.driver.set_page_load_timeout(45)
            self.browser.driver.get('https://twitter.com/login')
            time.sleep(5)

            username_field = WebDriverWait(self.browser.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[autocomplete='username']"))
            )
            username_field.click()
            time.sleep(1)
            username_field.send_keys(self.config.TWITTER_USERNAME)
            time.sleep(2)

            next_button = WebDriverWait(self.browser.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Next']"))
            )
            next_button.click()
            time.sleep(3)

            password_field = WebDriverWait(self.browser.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            password_field.click()
            time.sleep(1)
            password_field.send_keys(self.config.TWITTER_PASSWORD)
            time.sleep(2)

            login_button = WebDriverWait(self.browser.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Log in']"))
            )
            login_button.click()
            time.sleep(10) 

            return self._verify_login()

        except Exception as e:
            logger.log_error("Twitter Login", str(e))
            return False

    def _verify_login(self) -> bool:
        """Verify Twitter login success"""
        try:
            verification_methods = [
                lambda: WebDriverWait(self.browser.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="SideNav_NewTweet_Button"]'))
                ),
                lambda: WebDriverWait(self.browser.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="AppTabBar_Profile_Link"]'))
                ),
                lambda: any(path in self.browser.driver.current_url 
                          for path in ['home', 'twitter.com/home'])
            ]
            
            for method in verification_methods:
                try:
                    if method():
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.log_error("Login Verification", str(e))
            return False
            
    def _post_analysis(self, tweet_text: str) -> bool:
        """Post analysis to Twitter with robust button handling"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.browser.driver.get('https://twitter.com/compose/tweet')
                time.sleep(3)
                
                text_area = WebDriverWait(self.browser.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
                )
                text_area.click()
                time.sleep(1)
                
                text_parts = tweet_text.split('#')
                text_area.send_keys(text_parts[0])
                time.sleep(1)
                for part in text_parts[1:]:
                    text_area.send_keys(f'#{part}')
                    time.sleep(0.5)
                
                time.sleep(2)

                post_button = None
                button_locators = [
                    (By.CSS_SELECTOR, '[data-testid="tweetButton"]'),
                    (By.XPATH, "//div[@role='button'][contains(., 'Post')]"),
                    (By.XPATH, "//span[text()='Post']")
                ]

                for locator in button_locators:
                    try:
                        post_button = WebDriverWait(self.browser.driver, 5).until(
                            EC.element_to_be_clickable(locator)
                        )
                        if post_button:
                            break
                    except:
                        continue

                if post_button:
                    self.browser.driver.execute_script("arguments[0].scrollIntoView(true);", post_button)
                    time.sleep(1)
                    self.browser.driver.execute_script("arguments[0].click();", post_button)
                    time.sleep(5)
                    logger.logger.info("Tweet posted successfully")
                    return True
                else:
                    logger.logger.error("Could not find post button")
                    retry_count += 1
                    time.sleep(2)
                    
            except Exception as e:
                logger.logger.error(f"Tweet posting error, attempt {retry_count + 1}: {str(e)}")
                retry_count += 1
                wait_time = retry_count * 10
                logger.logger.warning(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue
        
        logger.log_error("Tweet Creation", "Maximum retries reached")
        return False
        
    def _cleanup(self) -> None:
        """Cleanup resources"""
        try:
            if self.browser:
                logger.logger.info("Closing browser...")
                try:
                    self.browser.close_browser()
                    time.sleep(1)
                except Exception as e:
                    logger.logger.warning(f"Error during browser close: {str(e)}")
                    
            if self.config:
                self.config.cleanup()
                
            logger.log_shutdown()
        except Exception as e:
            logger.log_error("Cleanup", str(e))

    def _get_last_posts(self) -> List[str]:
        """Get last 10 posts to check for duplicates"""
        try:
            self.browser.driver.get(f'https://twitter.com/{self.config.TWITTER_USERNAME}')
            time.sleep(3)
            
            posts = WebDriverWait(self.browser.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="tweetText"]'))
            )
            
            return [post.text for post in posts[:10]]
        except Exception as e:
            logger.log_error("Get Last Posts", str(e))
            return []

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

    def _track_prediction(self, prediction: Dict[str, Any], relevant_chains: List[str]) -> None:
        """Track predictions for future spicy callbacks"""
        MAX_PREDICTIONS = 20  
        current_prices = {chain: prediction.get(f'{chain.upper()}_price', 0) for chain in relevant_chains if f'{chain.upper()}_price' in prediction}
        
        self.past_predictions.append({
            'timestamp': datetime.now(),
            'prediction': prediction['analysis'],
            'prices': current_prices,
            'sentiment': prediction['sentiment'],
            'outcome': None
        })
        
        # Keep only predictions from the last 24 hours, up to MAX_PREDICTIONS
        self.past_predictions = [p for p in self.past_predictions 
                               if (datetime.now() - p['timestamp']).total_seconds() < 86400]
        
        # Trim to max predictions if needed
        if len(self.past_predictions) > MAX_PREDICTIONS:
            self.past_predictions = self.past_predictions[-MAX_PREDICTIONS:]
            
    def _validate_past_prediction(self, prediction: Dict[str, Any], current_prices: Dict[str, float]) -> str:
        """Check if a past prediction was hilariously wrong"""
        sentiment_map = {
            'bullish': 1,
            'bearish': -1,
            'neutral': 0,
            'volatile': 0,
            'recovering': 0.5
        }
        
        wrong_chains = []
        for chain, old_price in prediction['prices'].items():
            if chain in current_prices and old_price > 0:
                price_change = ((current_prices[chain] - old_price) / old_price) * 100
                
                # Get sentiment for this chain
                chain_sentiment_key = chain.upper() if chain.upper() in prediction['sentiment'] else chain
                chain_sentiment_value = prediction['sentiment'].get(chain_sentiment_key)
                
                # Handle nested dictionary structure
                if isinstance(chain_sentiment_value, dict) and 'mood' in chain_sentiment_value:
                    chain_sentiment = sentiment_map.get(chain_sentiment_value['mood'], 0)
                else:
                    chain_sentiment = sentiment_map.get(chain_sentiment_value, 0)
                
                # A prediction is wrong if:
                # 1. Bullish but price dropped more than 2%
                # 2. Bearish but price rose more than 2%
                if (chain_sentiment * price_change) < -2:
                    wrong_chains.append(chain)
        
        return 'wrong' if wrong_chains else 'right'
        
    def _get_spicy_callback(self, current_prices: Dict[str, float]) -> Optional[str]:
        """Generate witty callbacks to past terrible predictions"""
        recent_predictions = [p for p in self.past_predictions 
                            if p['timestamp'] > (datetime.now() - timedelta(hours=24))]
        
        if not recent_predictions:
            return None
            
        for pred in recent_predictions:
            if pred['outcome'] is None:
                pred['outcome'] = self._validate_past_prediction(pred, current_prices)
                
        wrong_predictions = [p for p in recent_predictions if p['outcome'] == 'wrong']
        if wrong_predictions:
            worst_pred = wrong_predictions[-1]
            time_ago = int((datetime.now() - worst_pred['timestamp']).total_seconds() / 3600)
            
            # If time_ago is 0, set it to 1 to avoid awkward phrasing
            if time_ago == 0:
                time_ago = 1
            
            # KAITO-specific callbacks
            callbacks = [
                f"(Unlike my galaxy-brain take {time_ago}h ago about {worst_pred['prediction'].split('.')[0]}... this time I'm sure!)",
                f"(Looks like my {time_ago}h old prediction about KAITO aged like milk. But trust me bro!)",
                f"(That awkward moment when your {time_ago}h old KAITO analysis was completely wrong... but this one's different!)",
                f"(My KAITO trading bot would be down bad after that {time_ago}h old take. Good thing I'm just an analyst!)",
                f"(Excuse the {time_ago}h old miss on KAITO. Even the best crypto analysts are wrong sometimes... just not usually THIS wrong!)"
            ]
            return callbacks[hash(str(datetime.now())) % len(callbacks)]
            
        return None
        
    def _format_tweet_analysis(self, analysis: str, crypto_data: Dict[str, Any]) -> str:
        """Format analysis for Twitter with KAITO-specific hashtags"""
        analysis_lower = analysis.lower()
        
        # 1. STATIC HASHTAGS - Always included
        base_hashtags = "#KAITO #CryptoAnalysis #SmartMoney #KAITOToken #Crypto"
        
        # Store all additional hashtags
        additional_hashtags = []
        
        # 2. CONDITIONAL HASHTAGS - Based on content analysis
        # Volume and accumulation related
        if 'volume' in analysis_lower or 'accumulation' in analysis_lower:
            additional_hashtags.append("#VolumeAnalysis")
        
        # L1 comparison related
        if 'layer 1' in analysis_lower or 'l1' in analysis_lower:
            additional_hashtags.append("#Layer1")
        
        # Price movement related
        if any(term in analysis_lower for term in ['surge', 'pump', 'jump', 'rocket', 'moon', 'soar']):
            additional_hashtags.append("#Momentum")
        elif any(term in analysis_lower for term in ['crash', 'dump', 'plunge', 'drop', 'fall', 'dip']):
            additional_hashtags.append("#CryptoAlert")
        
        # Technical analysis terminology
        if any(term in analysis_lower for term in ['divergence', 'resistance', 'support', 'pattern', 'indicator', 'signal']):
            additional_hashtags.append("#TechnicalAnalysis")
        
        # Market sentiment terminology
        if 'bullish' in analysis_lower:
            additional_hashtags.append("#Bullish")
        elif 'bearish' in analysis_lower:
            additional_hashtags.append("#Bearish")
        
        # Smart money and institutional terminology
        if any(term in analysis_lower for term in ['institution', 'smart money', 'whales', 'big players', 'accumulation']):
            additional_hashtags.append("#InstitutionalMoney")
        
        # Breakout and trend terminology
        if any(term in analysis_lower for term in ['breakout', 'trend', 'reversal', 'consolidation']):
            additional_hashtags.append("#TrendWatch")
            
        # Correlation terminology
        if any(term in analysis_lower for term in ['correlation', 'decoupling', 'coupled']):
            additional_hashtags.append("#MarketCorrelation")
            
        # 3. ROTATING HASHTAG SETS - Change with each post for variety
        rotating_hashtag_sets = [
            "#DeFi #Altcoins #CryptoGems",
            "#CryptoInvestor #AltSeason #UndervaluedGems",
            "#CryptoTrader #TradingSignals #MarketMoves",
            "#BlockchainTech #TokenEconomy #CryptoCommunity",
            "#Web3 #NewCrypto #EmergingAssets",
            "#TokenInvestor #CryptoAlpha #NextBigThing",
            "#DigitalAssets #CryptoBulls #MarketAlpha",
            "#DeepDive #CryptoResearch #TokenAnalysis"
        ]
        
        # Select a rotating set based on time and trigger
        # Use a hash of the date to select which set to use
        hashtag_set_index = hash(datetime.now().strftime("%Y-%m-%d-%H")) % len(rotating_hashtag_sets)
        rotating_hashtags = rotating_hashtag_sets[hashtag_set_index]
        
        # 4. MARKET CONDITION-BASED HASHTAGS - Based on actual data
        kaito_data = crypto_data.get('KAITO', {})
        
        if kaito_data:
            # Outperformance hashtags
            vs_layer1 = self._analyze_kaito_vs_layer1s(crypto_data)
            if vs_layer1.get('outperforming_layer1s', False):
                additional_hashtags.append("#Outperforming")
                if vs_layer1.get('vs_layer1_avg_change', 0) > 10:  # If outperforming by more than 10%
                    additional_hashtags.append("#MassiveOutperformance")
            
            # Volume-based hashtags
            smart_money = self._analyze_smart_money_indicators(kaito_data)
            if smart_money.get('abnormal_volume', False):
                additional_hashtags.append("#VolumeSpike")
            if smart_money.get('volume_z_score', 0) > 2.5:  # High Z-score
                additional_hashtags.append("#UnusualVolume")
            if smart_money.get('stealth_accumulation', False):
                additional_hashtags.append("#StealthMode")
            
            # Price action hashtags
            price_change = kaito_data.get('price_change_percentage_24h', 0)
            if price_change > 15:
                additional_hashtags.append("#PriceSurge")
            elif price_change > 5:
                additional_hashtags.append("#PriceAlert")
            elif price_change < -10:
                additional_hashtags.append("#PriceDrop")
                
            # Mood-based hashtags (determine from price change)
            if price_change > 8:
                additional_hashtags.append("#BullMarket")
            elif price_change < -8:
                additional_hashtags.append("#BearMarket")
            elif -3 <= price_change <= 3:
                additional_hashtags.append("#SidewaysMarket")
                
        # Combine all hashtags while respecting Twitter's constraints
        # Start with base hashtags, then add up to 5 additional hashtags
        # Finally add the rotating set if there's room
        
        # First prioritize and deduplicate additional hashtags
        additional_hashtags = list(set(additional_hashtags))  # Remove duplicates
        
        # Prioritize the most important ones (first 5)
        selected_additional = additional_hashtags[:min(5, len(additional_hashtags))]
        
        # Combine hashtags
        all_hashtags = f"{base_hashtags} {' '.join(selected_additional)}"
        
        # Add rotating hashtags if there's space
        if len(all_hashtags) + len(rotating_hashtags) + 1 <= 100:  # Stay under ~100 chars for hashtags
            all_hashtags = f"{all_hashtags} {rotating_hashtags}"
        
        # Construct the final tweet
        tweet = f"{analysis}\n\n{all_hashtags}"
        
        # Make sure to respect Twitter's character limit
        max_length = self.config.TWEET_CONSTRAINTS['HARD_STOP_LENGTH'] - 20
        if len(tweet) > max_length:
            # Trim the analysis part, not the hashtags
            chars_to_trim = len(tweet) - max_length
            trimmed_analysis = analysis[:len(analysis) - chars_to_trim - 3] + "..."
            tweet = f"{trimmed_analysis}\n\n{all_hashtags}"
        
        return tweet

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

    def _analyze_market_sentiment(self, crypto_data: Dict[str, Any], trigger_type: str) -> Optional[str]:
        """Generate KAITO-specific market analysis with focus on volume and smart money"""
        max_retries = 3
        retry_count = 0
        
        # Define rotating focus areas for more varied analyses
        focus_areas = [
            "Focus on volume patterns, smart money movements, and how KAITO is performing relative to Layer 1s.",
            "Emphasize technical indicators showing money flow from Layer 1s to KAITO. Pay special attention to volume-to-price divergence.",
            "Analyze accumulation patterns and Layer 1 capital rotation. Look for subtle signs of institutional interest in KAITO.",
            "Examine volume preceding price action in both KAITO and Layer 1s. Note any leading indicators.",
            "Highlight the relationship between KAITO's price action and significant Layer 1 volume changes.",
            "Investigate potential smart money positioning ahead of market moves. Note any anomalous volume signatures.",
            "Focus on recent volume clusters and their impact on price stability. Look for divergence patterns.",
            "Analyze how KAITO's volatility profile compares to Layer 1s and what this suggests about market sentiment."
        ]
        
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
                
                # NEW: Layer 1 volume flow technical analysis
                layer1_total_volume = sum([data['volume'] for sym, data in crypto_data.items() if sym in self.reference_tokens and sym in crypto_data])
                l1_volume_ratio = (kaito_data['volume'] / layer1_total_volume * 100) if layer1_total_volume > 0 else 0
                
                capital_rotation = "Yes" if vs_layer1.get('outperforming_layer1s', False) and smart_money.get('volume_vs_daily_avg', 0) > 0.2 else "No"
                
                l1_selling_pattern = "Detected" if vs_layer1.get('vs_layer1_volume_growth', 0) < 0 and volume_trend['change_pct'] > 5 else "Not detected"
                
                technical_context = f"""
Layer 1 Volume Flow Analysis:
- KAITO/Layer 1 volume ratio: {l1_volume_ratio:.2f}%
- Potential capital rotation: {capital_rotation}
- Layer 1 selling KAITO buying patterns: {l1_selling_pattern}
- Relative strength vs ETH: {correlations.get('price_correlation_ETH', 0):.2f}
- Relative strength vs SOL: {correlations.get('price_correlation_SOL', 0):.2f}
"""

                # Select a focus area using a deterministic but varied approach
                # Use a combination of date, hour and trigger type to ensure variety
                focus_seed = f"{datetime.now().date()}_{datetime.now().hour}_{trigger_type}"
                focus_index = hash(focus_seed) % len(focus_areas)
                selected_focus = focus_areas[focus_index]

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
                
                {technical_context}
                
                KAITO-specific context:
                - Meme: {meme_context}
                
                Trigger Type: {trigger_type}
                
                Past Context: {callback if callback else 'None'}
                
                Note: {selected_focus} Keep the analysis fresh and varied. Avoid repetitive phrases."""
                
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
                
                # For testing purposes, we'll skip the database similarity check 
                # and just check for exact duplicates in recent posts
                skip_similarity_check = True
                similarity_detected = False
                
                if not skip_similarity_check:
                    similarity_detected = self.config.db.check_content_similarity(formatted_tweet)
                    if similarity_detected:
                        logger.logger.info("Similar content detected, retrying analysis")
                        retry_count += 1
                        continue
                
                # Store the content if we proceed (always store for data collection)
                self.config.db.store_posted_content(
                    content=formatted_tweet,
                    sentiment={'KAITO': kaito_mood},
                    trigger_type=trigger_type,
                    price_data={'KAITO': {'price': kaito_data['current_price'], 
                                      'volume': kaito_data['volume']}},
                    meme_phrases={'KAITO': meme_context}
                )
                
                # For testing: Log that we're allowing a post that might be similar
                if similarity_detected:
                    logger.logger.info("Allowing potentially similar content for testing purposes")
                
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

    def _run_analysis_cycle(self) -> None:
        """Run analysis and posting cycle with focus on KAITO"""
        try:
            market_data = self._get_crypto_data()
            if not market_data:
                logger.logger.error("Failed to fetch market data")
                return
                
            # Make sure KAITO data is available
            if 'KAITO' not in market_data:
                logger.logger.error("KAITO data not available")
                return
                
            should_post, trigger_type = self._should_post_update(market_data)
            
            if should_post:
                logger.logger.info(f"Starting KAITO analysis cycle - Trigger: {trigger_type}")
                analysis = self._analyze_market_sentiment(market_data, trigger_type)
                if not analysis:
                    logger.logger.error("Failed to generate KAITO analysis")
                    return
                    
                last_posts = self._get_last_posts()
                if not self._is_duplicate_analysis(analysis, last_posts):
                    if self._post_analysis(analysis):
                        logger.logger.info(f"Successfully posted KAITO analysis - Trigger: {trigger_type}")
                        
                        # Store additional smart money metrics
                        if 'KAITO' in market_data:
                            smart_money = self._analyze_smart_money_indicators(market_data['KAITO'])
                            self.config.db.store_smart_money_indicators('KAITO', smart_money)
                            
                            # Log smart money indicators
                            logger.logger.debug(f"Smart money indicators stored for KAITO: {smart_money}")
                            
                            # Store Layer 1 comparison data
                            vs_layer1 = self._analyze_kaito_vs_layer1s(market_data)
                            if vs_layer1:
                                self.config.db.store_kaito_layer1_comparison(vs_layer1)
                                logger.logger.debug(f"KAITO vs Layer 1 comparison stored")
                    else:
                        logger.logger.error("Failed to post KAITO analysis")
                else:
                    logger.logger.info("Skipping duplicate KAITO analysis")
            else:
                logger.logger.debug("No significant KAITO changes detected, skipping post")
                
        except Exception as e:
            logger.log_error("KAITO Analysis Cycle", str(e))

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


if __name__ == "__main__":
    try:
        bot = KaitoAnalysisBot()
        bot.start()
    except Exception as e:
        logger.log_error("Bot Startup", str(e))
