import sqlite3
from datetime import datetime
import json
from typing import Dict, List, Optional, Union, Any
from dataclasses import asdict
import os
from utils.logger import logger

class CryptoDatabase:
    def __init__(self, db_path: str = "data/crypto_history.db"):
        """Initialize database connection and create tables if they don't exist"""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._initialize_database()

    def _get_connection(self):
        """Get database connection, creating it if necessary"""
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
        return self.conn, self.cursor

    def _initialize_database(self):
        """Create necessary tables if they don't exist"""
        conn, cursor = self._get_connection()
        
        try:
            # Market Data Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    chain TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    price_change_24h REAL,
                    market_cap REAL,
                    ath REAL,
                    ath_change_percentage REAL
                )
            """)

            # Correlation Analysis Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS correlation_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    price_correlation REAL NOT NULL,
                    volume_correlation REAL NOT NULL,
                    market_cap_ratio REAL NOT NULL
                )
            """)

            # Posted Content Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    content TEXT NOT NULL,
                    sentiment JSON NOT NULL,
                    trigger_type TEXT NOT NULL,
                    price_data JSON NOT NULL,
                    meme_phrases JSON NOT NULL
                )
            """)

            # Chain Mood History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mood_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    chain TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    indicators JSON NOT NULL
                )
            """)
            
            # Smart Money Indicators Table (New)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS smart_money_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    chain TEXT NOT NULL,
                    volume_z_score REAL,
                    price_volume_divergence BOOLEAN,
                    stealth_accumulation BOOLEAN,
                    abnormal_volume BOOLEAN,
                    volume_vs_hourly_avg REAL,
                    volume_vs_daily_avg REAL,
                    volume_cluster_detected BOOLEAN,
                    unusual_trading_hours JSON,
                    raw_data JSON
                )
            """)

            # KAITO Layer1 Comparison Table (New)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kaito_layer1_comparison (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    vs_layer1_avg_change REAL,
                    vs_layer1_volume_growth REAL,
                    outperforming_layer1s BOOLEAN,
                    correlations JSON
                )
            """)
            
            # Generic JSON Data Table for flexible storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS generic_json_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    data_type TEXT NOT NULL,
                    data JSON NOT NULL
                )
            """)
            
            # Create indices for better query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_data_timestamp ON market_data(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_data_chain ON market_data(chain)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_correlation_timestamp ON correlation_analysis(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posted_content_timestamp ON posted_content(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mood_history_timestamp ON mood_history(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_smart_money_timestamp ON smart_money_indicators(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_smart_money_chain ON smart_money_indicators(chain)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kaito_l1_timestamp ON kaito_layer1_comparison(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_generic_json_timestamp ON generic_json_data(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_generic_json_type ON generic_json_data(data_type)")

            conn.commit()
            logger.logger.info("Database initialized successfully")

        except Exception as e:
            logger.log_error("Database Initialization", str(e))
            raise

    def store_market_data(self, chain: str, data: Dict[str, Any]) -> None:
        """Store market data for a specific chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                INSERT INTO market_data (
                    timestamp, chain, price, volume, price_change_24h, 
                    market_cap, ath, ath_change_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                chain,
                data['current_price'],
                data['volume'],
                data['price_change_percentage_24h'],
                data['market_cap'],
                data['ath'],
                data['ath_change_percentage']
            ))
            conn.commit()
        except Exception as e:
            logger.log_error(f"Store Market Data - {chain}", str(e))
            conn.rollback()

    def store_correlation_analysis(self, analysis: Dict[str, float]) -> None:
        """Store correlation analysis results"""
        conn, cursor = self._get_connection()
        try:
            # Handle both old and new correlation format
            if 'price_correlation' in analysis and 'volume_correlation' in analysis and 'market_cap_ratio' in analysis:
                # Original format
                cursor.execute("""
                    INSERT INTO correlation_analysis (
                        timestamp, price_correlation, volume_correlation, market_cap_ratio
                    ) VALUES (?, ?, ?, ?)
                """, (
                    datetime.now(),
                    analysis['price_correlation'],
                    analysis['volume_correlation'],
                    analysis['market_cap_ratio']
                ))
            else:
                # New format - store as JSON in the same table for compatibility
                avg_price_corr = analysis.get('avg_price_correlation', 0)
                avg_volume_corr = analysis.get('avg_volume_correlation', 0)
                # Use 1.0 as default market_cap_ratio since we're focusing on KAITO now
                market_cap_ratio = 1.0
                
                cursor.execute("""
                    INSERT INTO correlation_analysis (
                        timestamp, price_correlation, volume_correlation, market_cap_ratio
                    ) VALUES (?, ?, ?, ?)
                """, (
                    datetime.now(),
                    avg_price_corr,
                    avg_volume_corr,
                    market_cap_ratio
                ))
                
                # Also store the full correlation data as JSON for more detailed analysis
                self._store_json_data('correlations', analysis)
                
            conn.commit()
        except Exception as e:
            logger.log_error("Store Correlation Analysis", str(e))
            conn.rollback()

    def store_posted_content(self, content: str, sentiment: Dict, 
                           trigger_type: str, price_data: Dict, 
                           meme_phrases: Dict) -> None:
        """Store posted content with metadata"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                INSERT INTO posted_content (
                    timestamp, content, sentiment, trigger_type, 
                    price_data, meme_phrases
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                content,
                json.dumps(sentiment),
                trigger_type,
                json.dumps(price_data),
                json.dumps(meme_phrases)
            ))
            conn.commit()
        except Exception as e:
            logger.log_error("Store Posted Content", str(e))
            conn.rollback()

    def store_mood(self, chain: str, mood: str, indicators: Dict) -> None:
        """Store mood data for a specific chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                INSERT INTO mood_history (
                    timestamp, chain, mood, indicators
                ) VALUES (?, ?, ?, ?)
            """, (
                datetime.now(),
                chain,
                mood,
                json.dumps(asdict(indicators))
            ))
            conn.commit()
        except Exception as e:
            logger.log_error(f"Store Mood - {chain}", str(e))
            conn.rollback()
            
    def store_smart_money_indicators(self, chain: str, indicators: Dict[str, Any]) -> None:
        """Store smart money indicators for a chain"""
        conn, cursor = self._get_connection()
        try:
            # Extract values with defaults for potential missing keys
            volume_z_score = indicators.get('volume_z_score', 0.0)
            price_volume_divergence = 1 if indicators.get('price_volume_divergence', False) else 0
            stealth_accumulation = 1 if indicators.get('stealth_accumulation', False) else 0
            abnormal_volume = 1 if indicators.get('abnormal_volume', False) else 0
            volume_vs_hourly_avg = indicators.get('volume_vs_hourly_avg', 0.0)
            volume_vs_daily_avg = indicators.get('volume_vs_daily_avg', 0.0)
            volume_cluster_detected = 1 if indicators.get('volume_cluster_detected', False) else 0
            
            # Convert unusual_trading_hours to JSON if present
            unusual_hours = json.dumps(indicators.get('unusual_trading_hours', []))
            
            # Store all raw data for future reference
            raw_data = json.dumps(indicators)
            
            cursor.execute("""
                INSERT INTO smart_money_indicators (
                    timestamp, chain, volume_z_score, price_volume_divergence,
                    stealth_accumulation, abnormal_volume, volume_vs_hourly_avg,
                    volume_vs_daily_avg, volume_cluster_detected, unusual_trading_hours,
                    raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                chain,
                volume_z_score,
                price_volume_divergence,
                stealth_accumulation,
                abnormal_volume,
                volume_vs_hourly_avg,
                volume_vs_daily_avg,
                volume_cluster_detected,
                unusual_hours,
                raw_data
            ))
            conn.commit()
        except Exception as e:
            logger.log_error(f"Store Smart Money Indicators - {chain}", str(e))
            conn.rollback()
            
    def store_kaito_layer1_comparison(self, comparison_data: Dict[str, Any]) -> None:
        """Store KAITO vs Layer 1 comparison data"""
        conn, cursor = self._get_connection()
        try:
            # Extract values with defaults
            vs_layer1_avg_change = comparison_data.get('vs_layer1_avg_change', 0.0)
            vs_layer1_volume_growth = comparison_data.get('vs_layer1_volume_growth', 0.0)
            outperforming_layer1s = 1 if comparison_data.get('outperforming_layer1s', False) else 0
            correlations = json.dumps(comparison_data.get('correlations', {}))
            
            cursor.execute("""
                INSERT INTO kaito_layer1_comparison (
                    timestamp, vs_layer1_avg_change, vs_layer1_volume_growth,
                    outperforming_layer1s, correlations
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                vs_layer1_avg_change,
                vs_layer1_volume_growth,
                outperforming_layer1s,
                correlations
            ))
            conn.commit()
        except Exception as e:
            logger.log_error("Store KAITO Layer1 Comparison", str(e))
            conn.rollback()

    def get_recent_market_data(self, chain: str, hours: int = 24) -> List[Dict]:
        """Get recent market data for a specific chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT * FROM market_data 
                WHERE chain = ? 
                AND timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (chain, hours))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.log_error(f"Get Recent Market Data - {chain}", str(e))
            return []

    def get_recent_correlations(self, hours: int = 24) -> List[Dict]:
        """Get recent correlation analysis"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT * FROM correlation_analysis 
                WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (hours,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.log_error("Get Recent Correlations", str(e))
            return []

    def get_recent_posts(self, hours: int = 24) -> List[Dict]:
        """Get recent posted content"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT * FROM posted_content 
                WHERE timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (hours,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.log_error("Get Recent Posts", str(e))
            return []

    def check_content_similarity(self, content: str) -> bool:
        """Check if similar content was recently posted"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT content FROM posted_content 
                WHERE timestamp >= datetime('now', '-1 hour')
            """)
            recent_posts = [row['content'] for row in cursor.fetchall()]
            
            # Simple similarity check - can be enhanced later
            return any(content.strip() == post.strip() for post in recent_posts)
        except Exception as e:
            logger.log_error("Check Content Similarity", str(e))
            return False

    def get_chain_stats(self, chain: str, hours: int = 24) -> Dict[str, Any]:
        """Get statistical summary for a chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT 
                    AVG(price) as avg_price,
                    MAX(price) as max_price,
                    MIN(price) as min_price,
                    AVG(volume) as avg_volume,
                    MAX(volume) as max_volume,
                    AVG(price_change_24h) as avg_price_change
                FROM market_data 
                WHERE chain = ? 
                AND timestamp >= datetime('now', '-' || ? || ' hours')
            """, (chain, hours))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return {}
        except Exception as e:
            logger.log_error(f"Get Chain Stats - {chain}", str(e))
            return {}
            
    def get_smart_money_indicators(self, chain: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent smart money indicators for a chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT * FROM smart_money_indicators
                WHERE chain = ? 
                AND timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (chain, hours))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.log_error(f"Get Smart Money Indicators - {chain}", str(e))
            return []
            
    def get_kaito_vs_layer1_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get statistical summary of KAITO vs Layer 1 performance"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT 
                    AVG(vs_layer1_avg_change) as avg_performance_diff,
                    AVG(vs_layer1_volume_growth) as avg_volume_growth_diff,
                    SUM(CASE WHEN outperforming_layer1s = 1 THEN 1 ELSE 0 END) as outperforming_count,
                    COUNT(*) as total_records
                FROM kaito_layer1_comparison
                WHERE timestamp >= datetime('now', '-' || ? || ' hours')
            """, (hours,))
            result = cursor.fetchone()
            if result:
                result_dict = dict(result)
                
                # Calculate percentage of time outperforming
                if result_dict['total_records'] > 0:
                    result_dict['outperforming_percentage'] = (result_dict['outperforming_count'] / result_dict['total_records']) * 100
                else:
                    result_dict['outperforming_percentage'] = 0
                    
                return result_dict
            return {}
        except Exception as e:
            logger.log_error("Get KAITO vs Layer1 Stats", str(e))
            return {}

    def _store_json_data(self, data_type: str, data: Dict[str, Any]) -> None:
        """Generic method to store JSON data in a generic_json_data table"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                INSERT INTO generic_json_data (
                    timestamp, data_type, data
                ) VALUES (?, ?, ?)
            """, (
                datetime.now(),
                data_type,
                json.dumps(data)
            ))
            conn.commit()
        except Exception as e:
            logger.log_error(f"Store JSON Data - {data_type}", str(e))
            conn.rollback()
    
    def get_latest_smart_money_alert(self, chain: str) -> Optional[Dict[str, Any]]:
        """Get the most recent smart money alert for a chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT * FROM smart_money_indicators
                WHERE chain = ? 
                AND (abnormal_volume = 1 OR stealth_accumulation = 1 OR volume_cluster_detected = 1)
                ORDER BY timestamp DESC
                LIMIT 1
            """, (chain,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.log_error(f"Get Latest Smart Money Alert - {chain}", str(e))
            return None
    
    def get_volume_trend(self, chain: str, hours: int = 24) -> Dict[str, Any]:
        """Get volume trend analysis for a chain"""
        conn, cursor = self._get_connection()
        try:
            cursor.execute("""
                SELECT 
                    timestamp,
                    volume
                FROM market_data
                WHERE chain = ? 
                AND timestamp >= datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp ASC
            """, (chain, hours))
            
            results = cursor.fetchall()
            if not results:
                return {'trend': 'insufficient_data', 'change': 0}
                
            # Calculate trend
            volumes = [row['volume'] for row in results]
            earliest_volume = volumes[0] if volumes else 0
            latest_volume = volumes[-1] if volumes else 0
            
            if earliest_volume > 0:
                change_pct = ((latest_volume - earliest_volume) / earliest_volume) * 100
            else:
                change_pct = 0
                
            # Determine trend description
            if change_pct >= 15:
                trend = "significant_increase"
            elif change_pct <= -15:
                trend = "significant_decrease"
            elif change_pct >= 5:
                trend = "moderate_increase"
            elif change_pct <= -5:
                trend = "moderate_decrease"
            else:
                trend = "stable"
                
            return {
                'trend': trend,
                'change': change_pct,
                'earliest_volume': earliest_volume,
                'latest_volume': latest_volume,
                'data_points': len(volumes)
            }
            
        except Exception as e:
            logger.log_error(f"Get Volume Trend - {chain}", str(e))
            return {'trend': 'error', 'change': 0}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
