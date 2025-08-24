'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface GoldPremiumData {
  international_price_usd_oz: number;
  domestic_price_krw_g: number;
  usd_krw_rate: number;
  converted_intl_price_krw_g: number;
  premium_percentage: number;
}

const GoldPremium = () => {
  const [data, setData] = useState<GoldPremiumData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch('http://127.0.0.1:5000/api/gold-premium');
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        const result = await res.json();
        setData(result);
      } catch (e: any) {
        setError(e.message);
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
        <ul className="space-y-2">
          <li className="flex justify-between"><span>국제 시세 (USD/oz)</span> <strong>${data.international_price_usd_oz.toFixed(2)}</strong></li>
          <li className="flex justify-between"><span>국내 시세 (KRW/g)</span> <strong>₩{data.domestic_price_krw_g.toLocaleString()}</strong></li>
          <li className="flex justify-between"><span>적용 환율 (KRW/USD)</span> <strong>{data.usd_krw_rate.toFixed(2)}</strong></li>
          <li className="flex justify-between"><span>국제 시세 환산 (KRW/g)</span> <strong>₩{Math.round(data.converted_intl_price_krw_g).toLocaleString()}</strong></li>
          <li className="flex justify-between text-lg font-semibold text-blue-600 dark:text-blue-400">
            <span>프리미엄</span>
            <strong>{data.premium_percentage.toFixed(2)}%</strong>
          </li>
        </ul>
      );
    }
    return null;
  };

  return (
    <Card title="금 프리미엄 (국내/외 시세 차이)">
      {renderContent()}
    </Card>
  );
};

export default GoldPremium;
