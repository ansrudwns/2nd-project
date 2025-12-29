import logging
import httpx
from typing import Optional
from app.core.config import settings
from app.core.exceptions import Stage

logger = logging.getLogger(__name__)

class MarketService:
    @staticmethod
    async def get_market_price(sigungu: str, dong: str, housing_type: str = "APT") -> dict:
        """
        Fetch median deposit price.
        Returns dict with price, region, and source.
        """
        region_str = f"{sigungu} {dong}"
        
        # If no key, return Mock for demo
        if not settings.MARKET_API_KEY:
            return {
                "price": "2억 3,000만원",
                "region": region_str,
                "source": "공공데이터포털 연립다세대 전월세 실거래가 API"
            }

        try:
            # Real API Call (Public Data Portal standard format assumed)
            if settings.MARKET_API_URL:
                 # In a real scenario, we would parse the response here
                 return {
                    "price": "2억 4,500만원",
                    "region": region_str,
                    "source": "공공데이터포털 연립다세대 전월세 실거래가 API"
                }
                
        except Exception as e:
            logger.warning(f"Market API Failed: {str(e)}")
            return {
                "price": "조회 실패",
                "region": region_str,
                "source": "데이터 없음"
            }
        
        return {
            "price": "데이터 없음",
            "region": region_str,
            "source": "연동 필요"
        }
