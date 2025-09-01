'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface Signal {
  type: string;
  message: string;
  strength: string;
}

interface StrategyData {
  premium_grade: string;
  signals: Signal[];
  recommendation: string;
}

const InvestmentStrategy = () => {
  const [data, setData] = useState<StrategyData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
        const res = await fetch(`${apiUrl}/api/investment-strategy`);
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
    
    // 5분마다 자동 새로고침
    const interval = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const getSignalColor = (type: string) => {
    if (type.includes('매수')) return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900';
    if (type.includes('매도')) return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900';
    return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900';
  };

  const getStrengthIcon = (strength: string) => {
    switch (strength) {
      case '강함': return '🔴';
      case '중간': return '🟡';
      case '약함': return '🟢';
      default: return '⚪';
    }
  };

  const renderContent = () => {
    if (loading) {
      return <p className="text-gray-500 dark:text-gray-400">Loading strategy data...</p>;
    }
    if (error) {
      return <p className="text-red-500">Error: {error}</p>;
    }
    if (data) {
      return (
        <div className="space-y-4">
          <div className="text-center p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <h3 className="text-lg font-semibold mb-2">프리미엄 등급</h3>
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {data.premium_grade}
            </div>
          </div>

          {data.signals && data.signals.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-gray-700 dark:text-gray-300">매매 신호</h3>
              {data.signals.map((signal, index) => (
                <div key={index} className={`p-3 rounded-lg border ${getSignalColor(signal.type)}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span>{getStrengthIcon(signal.strength)}</span>
                      <span className="font-semibold">{signal.type}</span>
                      <span className="text-xs px-2 py-1 rounded bg-white dark:bg-gray-700">
                        {signal.strength}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm mt-2">{signal.message}</p>
                </div>
              ))}
            </div>
          )}

          <div className="p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
            <h3 className="font-semibold mb-2 text-blue-800 dark:text-blue-200">투자 권고사항</h3>
            <p className="text-sm text-blue-700 dark:text-blue-300">{data.recommendation}</p>
          </div>

          <div className="text-xs text-gray-500 dark:text-gray-400 text-center">
            * 투자 결정은 신중하게 하시고, 본 정보는 참고용입니다.
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <Card title="투자 전략 분석">
      {renderContent()}
    </Card>
  );
};

export default InvestmentStrategy;
