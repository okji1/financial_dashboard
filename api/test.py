from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def handler(request):
    return jsonify({
        "market_condition": "테스트 상승 전망",
        "recommended_strategy": "테스트 콜(Call) 옵션 매수",
        "supporting_data": {
            "average_change_rate": 1.5,
            "total_volume": 1000000,
            "analyzed_symbols": 3
        },
        "detailed_analysis": [
            {
                "symbol": "132030",
                "name": "KODEX 골드선물(H)",
                "current_price": 10500,
                "volume": 500000,
                "change_rate": 2.1,
                "price_trend": "상승"
            },
            {
                "symbol": "411060", 
                "name": "ACE KRX금현물",
                "current_price": 8900,
                "volume": 300000,
                "change_rate": 1.2,
                "price_trend": "상승"
            },
            {
                "symbol": "069500",
                "name": "KODEX 200",
                "current_price": 29800,
                "volume": 200000,
                "change_rate": 0.8,
                "price_trend": "상승"
            }
        ],
        "raw_data_summary": {
            "price_trend": "3개 종목 실시간 분석",
            "speculation_position": "평균 변동률: 1.37%",
            "open_interest": "총 거래량: 1,000,000주"
        },
        "analysis_time": "2025-01-28T12:00:00Z",
        "message": "테스트 데이터입니다 (Vercel)"
    })