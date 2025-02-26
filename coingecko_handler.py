#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import requests
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import json
from utils.logger import logger

class CoinGeckoHandler:
    """
    Enhanced CoinGecko API handler with caching, rate limiting, and fallback strategies
    """
    def __init__(self, base_url: str, cache_duration: int = 60) -> None:
        """
        Initialize the CoinGecko handler
        
        Args:
            base_url: The base URL for the CoinGecko API
            cache_duration: Cache duration in seconds
        """
        self.base_url = base_url
        self.cache_duration = cache_duration
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 1.5  # Minimum 1.5 seconds between requests
        self.daily_requests = 0
        self.daily_requests_reset = datetime.now()
        self.failed_requests = 0
        self.active_retries = 0
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
        
        logger.logger.info("CoinGecko handler initialized")
    
    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        """Generate a unique cache key for the request"""
        param_str = json.dumps(params, sort_keys=True)
        return f"{endpoint}:{param_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self.cache:
            return False
        
        cache_entry = self.cache[cache_key]
        cache_time = cache_entry['timestamp']
        current_time = time.time()
        
        return (current_time - cache_time) < self.cache_duration
    
    def _get_from_cache(self, cache_key: str) -> Any:
        """Get data from cache if available and valid"""
        if self._is_cache_valid(cache_key):
            logger.logger.debug(f"Cache hit for {cache_key}")
            return self.cache[cache_key]['data']
        return None
    
    def _add_to_cache(self, cache_key: str, data: Any) -> None:
        """Add data to cache"""
        self.cache[cache_key] = {
            'timestamp': time.time(),
            'data': data
        }
        logger.logger.debug(f"Added to cache: {cache_key}")
    
    def _clean_cache(self) -> None:
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if (current_time - entry['timestamp']) >= self.cache_duration
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")
    
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting to avoid API restrictions"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            logger.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        # Reset daily request count if a day has passed
        if (datetime.now() - self.daily_requests_reset).total_seconds() >= 86400:
            self.daily_requests = 0
            self.daily_requests_reset = datetime.now()
            logger.logger.info("Daily request counter reset")
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """Make a request to the CoinGecko API with retries and error handling"""
        if params is None:
            params = {}
        
        url = f"{self.base_url}/{endpoint}"
        self._enforce_rate_limit()
        
        self.last_request_time = time.time()
        self.daily_requests += 1
        
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'application/json'
            }
            
            logger.logger.debug(f"Making API request to {endpoint} with params {params}")
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logger.logger.debug(f"API request successful: {endpoint}")
                return response.json()
            elif response.status_code == 429:
                self.failed_requests += 1
                logger.logger.warning(f"API rate limit exceeded: {response.status_code}")
                time.sleep(self.retry_delay * 2)  # Longer delay for rate limits
                return None
            else:
                self.failed_requests += 1
                logger.logger.error(f"API request failed: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.failed_requests += 1
            logger.logger.error(f"Request exception: {str(e)}")
            return None
        except Exception as e:
            self.failed_requests += 1
            logger.logger.error(f"Unexpected error in API request: {str(e)}")
            return None
    
    def get_with_cache(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """Get data from API with caching"""
        if params is None:
            params = {}
        
        cache_key = self._get_cache_key(endpoint, params)
        
        # Try to get from cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Not in cache, make API request
        retry_count = 0
        while retry_count < self.max_retries:
            data = self._make_request(endpoint, params)
            if data is not None:
                self._add_to_cache(cache_key, data)
                return data
            
            retry_count += 1
            if retry_count < self.max_retries:
                logger.logger.warning(f"Retrying API request ({retry_count}/{self.max_retries})")
                time.sleep(self.retry_delay * retry_count)
        
        logger.logger.error(f"Failed to get data after {self.max_retries} retries")
        return None
    
    def get_market_data(self, params: Dict = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get cryptocurrency market data from CoinGecko
        
        Args:
            params: Query parameters for the API
            
        Returns:
            List of market data entries
        """
        endpoint = "coins/markets"
        
        # Set default params for KAITO and major Layer 1s
        if params is None:
            params = {
                "vs_currency": "usd",
                "ids": "kaito,solana,ethereum,avalanche-2,polkadot",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": True,
                "price_change_percentage": "1h,24h,7d"
            }
        
        # Add low market cap option to ensure we get KAITO
        if "kaito" in params.get("ids", "").lower():
            params["per_page"] = max(params.get("per_page", 50), 250)
        
        return self.get_with_cache(endpoint, params)
    
    def get_coin_detail(self, coin_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed data for a specific coin
        
        Args:
            coin_id: CoinGecko coin ID (e.g., 'kaito', 'bitcoin')
            
        Returns:
            Detailed coin data
        """
        endpoint = f"coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "true"
        }
        
        return self.get_with_cache(endpoint, params)

    def get_coin_ohlc(self, coin_id: str, days: int = 1) -> Optional[List[List[float]]]:
        """
        Get OHLC data for a specific coin
        
        Args:
            coin_id: CoinGecko coin ID
            days: Number of days (1, 7, 14, 30, 90, 180, 365)
            
        Returns:
            OHLC data as list of [timestamp, open, high, low, close]
        """
        # Valid days values: 1, 7, 14, 30, 90, 180, 365
        if days not in [1, 7, 14, 30, 90, 180, 365]:
            days = 1
            
        endpoint = f"coins/{coin_id}/ohlc"
        params = {
            "vs_currency": "usd",
            "days": days
        }
        
        return self.get_with_cache(endpoint, params)
    
    def find_kaito_id(self) -> Optional[str]:
        """
        Find the exact CoinGecko ID for KAITO token
        (In case 'kaito' isn't the actual ID)
        
        Returns:
            CoinGecko ID for KAITO or None if not found
        """
        endpoint = "coins/list"
        coins_list = self.get_with_cache(endpoint)
        
        if not coins_list:
            return None
        
        # First try exact match on 'kaito'
        for coin in coins_list:
            if coin.get('id', '').lower() == 'kaito':
                logger.logger.info(f"Found KAITO with ID: {coin['id']}")
                return coin['id']
        
        # If not found, try symbol match on 'kaito'
        for coin in coins_list:
            if coin.get('symbol', '').lower() == 'kaito':
                logger.logger.info(f"Found KAITO with ID: {coin['id']} (matched by symbol)")
                return coin['id']
        
        # If still not found, try partial name match
        for coin in coins_list:
            if 'kaito' in coin.get('name', '').lower():
                logger.logger.info(f"Found possible KAITO match with ID: {coin['id']} (name: {coin['name']})")
                return coin['id']
        
        logger.logger.error("Could not find KAITO in CoinGecko coin list")
        return None
    
    def get_request_stats(self) -> Dict[str, int]:
        """
        Get API request statistics
        
        Returns:
            Dictionary with request stats
        """
        self._clean_cache()
        return {
            'daily_requests': self.daily_requests,
            'failed_requests': self.failed_requests,
            'cache_size': len(self.cache)
        }
