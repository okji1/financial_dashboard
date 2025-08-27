'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface StrategyData {
  market_condition: string;
  recommended_strategy: string;
  supporting_data: {
    price_trend: string;
    speculative_position: string;
    open_interest: string;
  };
  raw_data_summary: {
    last_price: number;
    volume: number;
    speculative_net_long: number;
    total_open_interest: number;
  };
  message?: string;
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
  }, []);

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
          <div>
            <p className="text-center text-lg font-semibold">시장 상황: <span className="text-yellow-500">{data.market_condition}</span></p>
            <p className="text-center text-2xl font-bold text-green-600 dark:text-green-400">{data.recommended_strategy}</p>
          </div>
          <div className="p-4 bg-gray-100 dark:bg-gray-700 rounded-md">
            <h3 className="font-semibold mb-2">분석 근거 데이터</h3>
            <ul className="space-y-1">
              <li className="flex justify-between"><span>가격 추세:</span> <span>{data.supporting_data.price_trend}</span></li>
              <li className="flex justify-between"><span>투기적 포지션:</span> <span>{data.supporting_data.speculative_position}</span></li>
              <li className="flex justify-between"><span>미결제 약정:</span> <span>{data.supporting_data.open_interest}</span></li>
            </ul>
          </div>
          {data.message && <p className="text-sm text-center text-gray-500 dark:text-gray-400">*{data.message}*</p>}
        </div>
      );
    }
    return null;
  };

  return (
    <Card title="금 선물 투자 전략">
      {renderContent()}
    </Card>
  );
};

export default InvestmentStrategy;
