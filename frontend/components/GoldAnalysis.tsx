'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface MarketOverview {
  london_gold_usd: number;
  london_gold_krw: number;
  domestic_gold_price: number;
  premium_percentage: number;
}

interface RiskAssessment {
  premium_grade: {
    grade: string;
    description: string;
  };
  market_volatility: string;
  liquidity_score: number;
}

interface TradingSignal {
  type: string;
  strength: string;
  reason: string;
}

interface ComprehensiveAnalysis {
  timestamp: string;
  market_overview: MarketOverview;
  risk_assessment: RiskAssessment;
  trading_signals: TradingSignal[];
  recommendations: string[];
}

const GoldAnalysis = () => {
  const [data, setData] = useState<ComprehensiveAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
        const res = await fetch(`${apiUrl}/api/gold-analysis`);
        const result = await res.json();

        if (!res.ok) {
          throw new Error(result.error || `HTTP error! status: ${res.status}`);
        }

        setData(result);
      } catch (e) {
        if (e instanceof Error) {
          setError(e.message);
        } else {
          setError(String(e));
        }
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    
    // 10분마다 자동 새로고침
    const interval = setInterval(fetchData, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const getSignalBadgeStyle = (signal: TradingSignal) => {
    const baseStyle = "px-3 py-1 rounded-full text-sm font-medium";
    if (signal.type === 'BUY') {
      return `${baseStyle} bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200`;
    } else if (signal.type === 'SELL') {
      return `${baseStyle} bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200`;
    }
    return `${baseStyle} bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200`;
  };

  const getRiskColor = (grade: string) => {
    switch (grade) {
      case '매우좋음': return 'text-green-600 dark:text-green-400';
      case '좋음': return 'text-blue-600 dark:text-blue-400';
      case '보통': return 'text-yellow-600 dark:text-yellow-400';
      case '높음': return 'text-orange-600 dark:text-orange-400';
      case '매우높음': return 'text-red-600 dark:text-red-400';
      default: return 'text-gray-600 dark:text-gray-400';
    }
  };

  const renderContent = () => {
    if (loading) {
      return <p className="text-gray-500 dark:text-gray-400">종합 분석 중...</p>;
    }
    if (error) {
      return <p className="text-red-500">Error: {error}</p>;
    }
    if (data) {
      return (
        <div className="space-y-6">
          {/* 시장 개요 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="text-xs text-gray-500 dark:text-gray-400">런던 금 (USD)</div>
              <div className="text-lg font-bold">${data.market_overview.london_gold_usd?.toFixed(0) || 'N/A'}</div>
            </div>
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="text-xs text-gray-500 dark:text-gray-400">국내 금 (KRW)</div>
              <div className="text-lg font-bold">₩{data.market_overview.domestic_gold_price?.toLocaleString() || 'N/A'}</div>
            </div>
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="text-xs text-gray-500 dark:text-gray-400">프리미엄</div>
              <div className="text-lg font-bold">{data.market_overview.premium_percentage?.toFixed(2) || 'N/A'}%</div>
            </div>
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="text-xs text-gray-500 dark:text-gray-400">유동성</div>
              <div className="text-lg font-bold">{data.risk_assessment.liquidity_score?.toFixed(1) || 'N/A'}</div>
            </div>
          </div>

          {/* 리스크 평가 */}
          <div className="p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
            <h3 className="font-semibold mb-3 text-blue-800 dark:text-blue-200">리스크 평가</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <span className="text-sm text-blue-700 dark:text-blue-300">프리미엄 등급:</span>
                <div className={`font-bold ${getRiskColor(data.risk_assessment.premium_grade.grade)}`}>
                  {data.risk_assessment.premium_grade.grade}
                </div>
                <div className="text-xs text-blue-600 dark:text-blue-400">
                  {data.risk_assessment.premium_grade.description}
                </div>
              </div>
              <div>
                <span className="text-sm text-blue-700 dark:text-blue-300">시장 변동성:</span>
                <div className="font-bold">{data.risk_assessment.market_volatility}</div>
              </div>
            </div>
          </div>

          {/* 매매 신호 */}
          {data.trading_signals && data.trading_signals.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-gray-700 dark:text-gray-300">매매 신호</h3>
              <div className="space-y-2">
                {data.trading_signals.map((signal, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <span className={getSignalBadgeStyle(signal)}>
                        {signal.type === 'BUY' ? '매수' : signal.type === 'SELL' ? '매도' : signal.type}
                      </span>
                      <span className="text-sm">{signal.reason}</span>
                    </div>
                    <span className="text-xs px-2 py-1 bg-white dark:bg-gray-700 rounded">
                      {signal.strength === 'Strong' ? '강함' : signal.strength === 'Medium' ? '중간' : '약함'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 추천사항 */}
          {data.recommendations && data.recommendations.length > 0 && (
            <div className="p-4 bg-yellow-50 dark:bg-yellow-900 rounded-lg">
              <h3 className="font-semibold mb-3 text-yellow-800 dark:text-yellow-200">투자 추천사항</h3>
              <ul className="space-y-2">
                {data.recommendations.map((rec, index) => (
                  <li key={index} className="text-sm text-yellow-700 dark:text-yellow-300 flex items-start">
                    <span className="mr-2">•</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 분석 시간 */}
          <div className="text-xs text-gray-500 dark:text-gray-400 text-center">
            분석 시간: {new Date(data.timestamp).toLocaleString('ko-KR')}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <Card title="종합 금 시장 분석">
      {renderContent()}
    </Card>
  );
};

export default GoldAnalysis;
