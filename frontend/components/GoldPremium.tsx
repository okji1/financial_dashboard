'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface GoldPremiumData {
  london_gold_usd: number;
  london_gold_krw: number;
  domestic_gold_price: number;
  premium_percentage: number;
  premium_grade: string;
  exchange_rate: number;
  active_contract: string;
  cached: boolean;
}

const GoldPremium = () => {
  const [data, setData] = useState<GoldPremiumData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
        const res = await fetch(`${apiUrl}/api/gold-premium`);
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

  const getPremiumColor = (grade: string) => {
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
      return <p className="text-gray-500 dark:text-gray-400">Loading data...</p>;
    }
    if (error) {
      return <p className="text-red-500">Error: {error}</p>;
    }
    if (data) {
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <h3 className="font-semibold text-gray-700 dark:text-gray-300">런던 금 현물</h3>
              <ul className="space-y-1 text-sm">
                <li className="flex justify-between">
                  <span>USD/oz</span> 
                  <strong>${data.london_gold_usd?.toFixed(2) || 'N/A'}</strong>
                </li>
                <li className="flex justify-between">
                  <span>KRW/g</span> 
                  <strong>₩{data.london_gold_krw ? Math.round(data.london_gold_krw / 31.1035).toLocaleString() : 'N/A'}</strong>
                </li>
              </ul>
            </div>
            
            <div className="space-y-2">
              <h3 className="font-semibold text-gray-700 dark:text-gray-300">국내 금 현물</h3>
              <ul className="space-y-1 text-sm">
                <li className="flex justify-between">
                  <span>타입</span> 
                  <strong>{data.active_contract || '현물금'}</strong>
                </li>
                <li className="flex justify-between">
                  <span>가격</span> 
                  <strong>₩{data.domestic_gold_price?.toLocaleString() || 'N/A'}/g</strong>
                </li>
              </ul>
            </div>
          </div>

          <div className="border-t pt-4">
            <div className="flex justify-between items-center">
              <span className="text-lg font-semibold">프리미엄</span>
              <div className="text-right">
                <div className={`text-xl font-bold ${getPremiumColor(data.premium_grade)}`}>
                  {data.premium_percentage?.toFixed(2) || 'N/A'}%
                </div>
                <div className={`text-sm ${getPremiumColor(data.premium_grade)}`}>
                  ({data.premium_grade})
                </div>
              </div>
            </div>
          </div>

          <div className="text-xs text-gray-500 dark:text-gray-400 flex justify-between">
            <span>환율: ₩{data.exchange_rate?.toFixed(2) || 'N/A'}</span>
            <span>{data.cached ? '캐시됨' : '실시간'}</span>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <Card title="금 프리미엄 분석">
      {renderContent()}
    </Card>
  );
};

export default GoldPremium;
