"""
Geographic Utilities
====================
IP geolocation and geographic spread tracking for deepfake origin detection.

Uses free IP-API service for hackathon demo (100 req/min limit).
Can be upgraded to MaxMind GeoLite2 for production.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import urllib.request
import urllib.error


@dataclass
class GeoLocation:
    """Geographic location data."""
    ip_hash: str = ""  # SHA256 hash of IP for privacy
    country: str = "Unknown"
    country_code: str = "XX"
    region: str = ""
    city: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = ""
    isp: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'ip_hash': self.ip_hash,
            'country': self.country,
            'country_code': self.country_code,
            'region': self.region,
            'city': self.city,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'timezone': self.timezone,
            'isp': self.isp,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeoLocation':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class GeoIPService:
    """
    Service for looking up geographic location from IP addresses.
    
    Uses ip-api.com free tier (100 requests/minute).
    Caches results to minimize API calls.
    """
    
    API_URL = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp"
    
    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize GeoIP service.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default 1 hour)
        """
        self.cache: Dict[str, Tuple[GeoLocation, float]] = {}
        self.cache_ttl = cache_ttl
        self._last_request_time = 0
        self._min_request_interval = 0.6  # 100 req/min = 1 req/0.6s
    
    def _hash_ip(self, ip: str) -> str:
        """Hash IP address for privacy."""
        return hashlib.sha256(ip.encode()).hexdigest()[:16]
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    def lookup(self, ip: str) -> GeoLocation:
        """
        Look up geographic location for an IP address.
        
        Args:
            ip: IP address to look up
            
        Returns:
            GeoLocation with geographic data
        """
        # Handle localhost/private IPs
        if self._is_private_ip(ip):
            return self._get_demo_location(ip)
        
        ip_hash = self._hash_ip(ip)
        
        # Check cache
        if ip_hash in self.cache:
            cached, timestamp = self.cache[ip_hash]
            if time.time() - timestamp < self.cache_ttl:
                return cached
        
        # Make API request
        try:
            self._rate_limit()
            url = self.API_URL.format(ip=ip)
            
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            if data.get('status') == 'success':
                location = GeoLocation(
                    ip_hash=ip_hash,
                    country=data.get('country', 'Unknown'),
                    country_code=data.get('countryCode', 'XX'),
                    region=data.get('regionName', ''),
                    city=data.get('city', ''),
                    latitude=data.get('lat', 0.0),
                    longitude=data.get('lon', 0.0),
                    timezone=data.get('timezone', ''),
                    isp=data.get('isp', '')
                )
                self.cache[ip_hash] = (location, time.time())
                return location
            else:
                print(f"GeoIP lookup failed: {data.get('message', 'Unknown error')}")
                return self._get_demo_location(ip)
                
        except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
            print(f"GeoIP API error: {e}")
            return self._get_demo_location(ip)
    
    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/localhost."""
        private_prefixes = [
            '127.', '10.', '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.',
            '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.',
            '192.168.', '0.0.', 'localhost', '::1'
        ]
        return any(ip.startswith(prefix) for prefix in private_prefixes)
    
    def _get_demo_location(self, ip: str) -> GeoLocation:
        """
        Return demo location for localhost/private IPs.
        Uses Vellore, India as the fixed demo location.
        """
        ip_hash = self._hash_ip(ip)
        
        # Fixed location: Vellore, Tamil Nadu, India (VIT University area)
        return GeoLocation(
            ip_hash=ip_hash,
            country="India",
            country_code="IN",
            region="Tamil Nadu",
            city="Vellore",
            latitude=12.9692,
            longitude=79.1559,
            timezone="Asia/Kolkata",
            isp="Local Network"
        )
        
        # Old random demo locations (kept for reference)
        _demo_locations = [
            {"country": "India", "country_code": "IN", "city": "Mumbai", "lat": 19.0760, "lon": 72.8777},
            {"country": "United States", "country_code": "US", "city": "New York", "lat": 40.7128, "lon": -74.0060},
            {"country": "United Kingdom", "country_code": "GB", "city": "London", "lat": 51.5074, "lon": -0.1278},
            {"country": "Germany", "country_code": "DE", "city": "Berlin", "lat": 52.5200, "lon": 13.4050},
            {"country": "Japan", "country_code": "JP", "city": "Tokyo", "lat": 35.6762, "lon": 139.6503},
            {"country": "Australia", "country_code": "AU", "city": "Sydney", "lat": -33.8688, "lon": 151.2093},
            {"country": "Brazil", "country_code": "BR", "city": "São Paulo", "lat": -23.5505, "lon": -46.6333},
            {"country": "Singapore", "country_code": "SG", "city": "Singapore", "lat": 1.3521, "lon": 103.8198},
        ]
        
        # Use hash to pick location deterministically
        idx = int(ip_hash[:4], 16) % len(demo_locations)
        loc = demo_locations[idx]
        
        return GeoLocation(
            ip_hash=ip_hash,
            country=loc['country'],
            country_code=loc['country_code'],
            city=loc['city'],
            latitude=loc['lat'],
            longitude=loc['lon'],
            timezone="UTC",
            isp="Demo ISP"
        )


# Singleton instance
_geo_service: Optional[GeoIPService] = None


def get_geo_service() -> GeoIPService:
    """Get or create GeoIP service singleton."""
    global _geo_service
    if _geo_service is None:
        _geo_service = GeoIPService()
    return _geo_service


def lookup_ip(ip: str) -> GeoLocation:
    """Convenience function to look up IP location."""
    return get_geo_service().lookup(ip)


def get_client_ip(request) -> str:
    """
    Extract client IP from Flask request.
    Handles proxies via X-Forwarded-For header.
    """
    # Check for proxy headers
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For can contain multiple IPs; first is the client
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or '127.0.0.1'


# Country flag emoji mapping
COUNTRY_FLAGS = {
    'AD': '🇦🇩', 'AE': '🇦🇪', 'AF': '🇦🇫', 'AG': '🇦🇬', 'AI': '🇦🇮', 'AL': '🇦🇱', 'AM': '🇦🇲', 'AO': '🇦🇴',
    'AQ': '🇦🇶', 'AR': '🇦🇷', 'AS': '🇦🇸', 'AT': '🇦🇹', 'AU': '🇦🇺', 'AW': '🇦🇼', 'AX': '🇦🇽', 'AZ': '🇦🇿',
    'BA': '🇧🇦', 'BB': '🇧🇧', 'BD': '🇧🇩', 'BE': '🇧🇪', 'BF': '🇧🇫', 'BG': '🇧🇬', 'BH': '🇧🇭', 'BI': '🇧🇮',
    'BJ': '🇧🇯', 'BL': '🇧🇱', 'BM': '🇧🇲', 'BN': '🇧🇳', 'BO': '🇧🇴', 'BQ': '🇧🇶', 'BR': '🇧🇷', 'BS': '🇧🇸',
    'BT': '🇧🇹', 'BV': '🇧🇻', 'BW': '🇧🇼', 'BY': '🇧🇾', 'BZ': '🇧🇿', 'CA': '🇨🇦', 'CC': '🇨🇨', 'CD': '🇨🇩',
    'CF': '🇨🇫', 'CG': '🇨🇬', 'CH': '🇨🇭', 'CI': '🇨🇮', 'CK': '🇨🇰', 'CL': '🇨🇱', 'CM': '🇨🇲', 'CN': '🇨🇳',
    'CO': '🇨🇴', 'CR': '🇨🇷', 'CU': '🇨🇺', 'CV': '🇨🇻', 'CW': '🇨🇼', 'CX': '🇨🇽', 'CY': '🇨🇾', 'CZ': '🇨🇿',
    'DE': '🇩🇪', 'DJ': '🇩🇯', 'DK': '🇩🇰', 'DM': '🇩🇲', 'DO': '🇩🇴', 'DZ': '🇩🇿', 'EC': '🇪🇨', 'EE': '🇪🇪',
    'EG': '🇪🇬', 'EH': '🇪🇭', 'ER': '🇪🇷', 'ES': '🇪🇸', 'ET': '🇪🇹', 'FI': '🇫🇮', 'FJ': '🇫🇯', 'FK': '🇫🇰',
    'FM': '🇫🇲', 'FO': '🇫🇴', 'FR': '🇫🇷', 'GA': '🇬🇦', 'GB': '🇬🇧', 'GD': '🇬🇩', 'GE': '🇬🇪', 'GF': '🇬🇫',
    'GG': '🇬🇬', 'GH': '🇬🇭', 'GI': '🇬🇮', 'GL': '🇬🇱', 'GM': '🇬🇲', 'GN': '🇬🇳', 'GP': '🇬🇵', 'GQ': '🇬🇶',
    'GR': '🇬🇷', 'GS': '🇬🇸', 'GT': '🇬🇹', 'GU': '🇬🇺', 'GW': '🇬🇼', 'GY': '🇬🇾', 'HK': '🇭🇰', 'HM': '🇭🇲',
    'HN': '🇭🇳', 'HR': '🇭🇷', 'HT': '🇭🇹', 'HU': '🇭🇺', 'ID': '🇮🇩', 'IE': '🇮🇪', 'IL': '🇮🇱', 'IM': '🇮🇲',
    'IN': '🇮🇳', 'IO': '🇮🇴', 'IQ': '🇮🇶', 'IR': '🇮🇷', 'IS': '🇮🇸', 'IT': '🇮🇹', 'JE': '🇯🇪', 'JM': '🇯🇲',
    'JO': '🇯🇴', 'JP': '🇯🇵', 'KE': '🇰🇪', 'KG': '🇰🇬', 'KH': '🇰🇭', 'KI': '🇰🇮', 'KM': '🇰🇲', 'KN': '🇰🇳',
    'KP': '🇰🇵', 'KR': '🇰🇷', 'KW': '🇰🇼', 'KY': '🇰🇾', 'KZ': '🇰🇿', 'LA': '🇱🇦', 'LB': '🇱🇧', 'LC': '🇱🇨',
    'LI': '🇱🇮', 'LK': '🇱🇰', 'LR': '🇱🇷', 'LS': '🇱🇸', 'LT': '🇱🇹', 'LU': '🇱🇺', 'LV': '🇱🇻', 'LY': '🇱🇾',
    'MA': '🇲🇦', 'MC': '🇲🇨', 'MD': '🇲🇩', 'ME': '🇲🇪', 'MF': '🇲🇫', 'MG': '🇲🇬', 'MH': '🇲🇭', 'MK': '🇲🇰',
    'ML': '🇲🇱', 'MM': '🇲🇲', 'MN': '🇲🇳', 'MO': '🇲🇴', 'MP': '🇲🇵', 'MQ': '🇲🇶', 'MR': '🇲🇷', 'MS': '🇲🇸',
    'MT': '🇲🇹', 'MU': '🇲🇺', 'MV': '🇲🇻', 'MW': '🇲🇼', 'MX': '🇲🇽', 'MY': '🇲🇾', 'MZ': '🇲🇿', 'NA': '🇳🇦',
    'NC': '🇳🇨', 'NE': '🇳🇪', 'NF': '🇳🇫', 'NG': '🇳🇬', 'NI': '🇳🇮', 'NL': '🇳🇱', 'NO': '🇳🇴', 'NP': '🇳🇵',
    'NR': '🇳🇷', 'NU': '🇳🇺', 'NZ': '🇳🇿', 'OM': '🇴🇲', 'PA': '🇵🇦', 'PE': '🇵🇪', 'PF': '🇵🇫', 'PG': '🇵🇬',
    'PH': '🇵🇭', 'PK': '🇵🇰', 'PL': '🇵🇱', 'PM': '🇵🇲', 'PN': '🇵🇳', 'PR': '🇵🇷', 'PS': '🇵🇸', 'PT': '🇵🇹',
    'PW': '🇵🇼', 'PY': '🇵🇾', 'QA': '🇶🇦', 'RE': '🇷🇪', 'RO': '🇷🇴', 'RS': '🇷🇸', 'RU': '🇷🇺', 'RW': '🇷🇼',
    'SA': '🇸🇦', 'SB': '🇸🇧', 'SC': '🇸🇨', 'SD': '🇸🇩', 'SE': '🇸🇪', 'SG': '🇸🇬', 'SH': '🇸🇭', 'SI': '🇸🇮',
    'SJ': '🇸🇯', 'SK': '🇸🇰', 'SL': '🇸🇱', 'SM': '🇸🇲', 'SN': '🇸🇳', 'SO': '🇸🇴', 'SR': '🇸🇷', 'SS': '🇸🇸',
    'ST': '🇸🇹', 'SV': '🇸🇻', 'SX': '🇸🇽', 'SY': '🇸🇾', 'SZ': '🇸🇿', 'TC': '🇹🇨', 'TD': '🇹🇩', 'TF': '🇹🇫',
    'TG': '🇹🇬', 'TH': '🇹🇭', 'TJ': '🇹🇯', 'TK': '🇹🇰', 'TL': '🇹🇱', 'TM': '🇹🇲', 'TN': '🇹🇳', 'TO': '🇹🇴',
    'TR': '🇹🇷', 'TT': '🇹🇹', 'TV': '🇹🇻', 'TW': '🇹🇼', 'TZ': '🇹🇿', 'UA': '🇺🇦', 'UG': '🇺🇬', 'UM': '🇺🇲',
    'US': '🇺🇸', 'UY': '🇺🇾', 'UZ': '🇺🇿', 'VA': '🇻🇦', 'VC': '🇻🇨', 'VE': '🇻🇪', 'VG': '🇻🇬', 'VI': '🇻🇮',
    'VN': '🇻🇳', 'VU': '🇻🇺', 'WF': '🇼🇫', 'WS': '🇼🇸', 'XK': '🇽🇰', 'YE': '🇾🇪', 'YT': '🇾🇹', 'ZA': '🇿🇦',
    'ZM': '🇿🇲', 'ZW': '🇿🇼', 'XX': '🏳️'
}


def get_country_flag(country_code: str) -> str:
    """Get flag emoji for country code."""
    return COUNTRY_FLAGS.get(country_code.upper(), '🏳️')


def hash_ip(ip: str) -> str:
    """
    Hash IP address for privacy-preserving storage.
    
    Args:
        ip: IP address to hash
        
    Returns:
        First 16 characters of SHA256 hash
    """
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def lookup_ip(ip: str) -> GeoLocation:
    """
    Convenience function to lookup IP location.
    Creates a new GeoIPService instance for one-off lookups.
    
    Args:
        ip: IP address to lookup
        
    Returns:
        GeoLocation with geographic data
    """
    service = GeoIPService()
    return service.lookup(ip)
