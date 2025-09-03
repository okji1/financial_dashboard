'use client'

import { useEffect, useState } from 'react';
import Card from './Card';

interface ContractCandidate {
  symbol: string;
  year: number;
  month: number;
  description: string;
}

interface ActiveContract {
  symbol: string;
  description: string;
  current_price: number;
  volume: number;
  open_interest: number;
  expiry_year: number;
  expiry_month: number;
  updated_at: string;
  buy_pressure?: number;
  sell_pressure?: number;
  pressure_signal?: string;
  best_bid?: number;
  best_ask?: number;
  spread?: number;
}

interface PressureAnalysis {
  symbol: string;
  pressure_signal: string;
  buy_pressure: number;
  sell_pressure: number;
  recommendation: string;
  timestamp: string;
}

const ActiveContractManager = () => {
  const [activeContract, setActiveContract] = useState<ActiveContract | null>(null);
  const [candidates, setCandidates] = useState<ContractCandidate[]>([]);
  const [pressureAnalysis, setPressureAnalysis] = useState<PressureAnalysis | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [updating, setUpdating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPressureAnalysis = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
      console.log('🔗 Pressure API 호출:', `${apiUrl}/api/pressure-signal`);
      
      const res = await fetch(`${apiUrl}/api/pressure-signal`);
      console.log('📡 Pressure API 응답 상태:', res.status);
      
      if (res.ok) {
        const result = await res.json();
        console.log('✅ Pressure 데이터 수신:', result);
        setPressureAnalysis(result);
      } else {
        const errorText = await res.text();
        console.error('❌ Pressure API 오류:', res.status, errorText);
      }
    } catch (e) {
      console.error('❌ Pressure analysis fetch error:', e);
    }
  };

  const fetchActiveContract = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
      const res = await fetch(`${apiUrl}/api/active-contract`);
      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.error || `HTTP error! status: ${res.status}`);
      }

      setActiveContract(result);
    } catch (e) {
      console.error('Active contract fetch error:', e);
    }
  };

  const fetchCandidates = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
      const res = await fetch(`${apiUrl}/api/futures-candidates`);
      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.error || `HTTP error! status: ${res.status}`);
      }

      setCandidates(result.candidates || []);
    } catch (e) {
      console.error('Candidates fetch error:', e);
    }
  };

  const updateActiveContract = async () => {
    setUpdating(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
      const res = await fetch(`${apiUrl}/api/update-active-contract`, {
        method: 'POST',
      });
      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.error || `HTTP error! status: ${res.status}`);
      }

      setActiveContract(result.contract);
      setError(null);
    } catch (e) {
      if (e instanceof Error) {
        setError(e.message);
      } else {
        setError(String(e));
      }
    } finally {
      setUpdating(false);
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      await Promise.all([
        fetchActiveContract(), 
        fetchCandidates(),
        fetchPressureAnalysis()
      ]);
      setLoading(false);
    };

    fetchData();
    
    // 1시간마다 자동 새로고침
    const interval = setInterval(() => {
      fetchActiveContract();
      fetchPressureAnalysis();
    }, 60 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('ko-KR');
  };

  const isContractExpiringSoon = (year: number, month: number) => {
    const now = new Date();
    const expiryDate = new Date(year, month - 1, 1);
    const daysUntilExpiry = Math.ceil((expiryDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    return daysUntilExpiry <= 30; // 30일 이내 만료
  };

  const renderContent = () => {
    if (loading) {
      return <p className="text-gray-500 dark:text-gray-400">계약 정보 로딩 중...</p>;
    }

    return (
      <div className="space-y-4">
        {/* 활성 계약 정보 */}
        {activeContract && (
          <div className="p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
            <div className="flex justify-between items-start mb-3">
              <h3 className="font-semibold text-blue-800 dark:text-blue-200">현재 활성 계약</h3>
              <div className="flex items-center space-x-2">
                {isContractExpiringSoon(activeContract.expiry_year, activeContract.expiry_month) && (
                  <span className="px-2 py-1 text-xs bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded">
                    만료임박
                  </span>
                )}
                <button
                  onClick={updateActiveContract}
                  disabled={updating}
                  className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  {updating ? '업데이트 중...' : '업데이트'}
                </button>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">계약 코드:</span>
                  <strong className="text-blue-800 dark:text-blue-200">{activeContract.symbol}</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">만료일:</span>
                  <strong className="text-blue-800 dark:text-blue-200">
                    {activeContract.expiry_year}년 {activeContract.expiry_month}월
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">현재가:</span>
                  <strong className="text-blue-800 dark:text-blue-200">
                    ₩{activeContract.current_price?.toLocaleString()}
                  </strong>
                </div>
              </div>
              
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">거래량:</span>
                  <strong className="text-blue-800 dark:text-blue-200">
                    {activeContract.volume?.toLocaleString()}
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">미결제약정:</span>
                  <strong className="text-blue-800 dark:text-blue-200">
                    {activeContract.open_interest?.toLocaleString()}
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-blue-700 dark:text-blue-300">업데이트:</span>
                  <span className="text-xs text-blue-600 dark:text-blue-400">
                    {formatDate(activeContract.updated_at)}
                  </span>
                </div>
              </div>
            </div>

            {/* 매수/매도 압력 분석 - 실제 API 데이터 사용 */}
            <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900 rounded-lg">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-semibold text-yellow-800 dark:text-yellow-200">실시간 매수/매도 압력 분석</h4>
                <button
                  onClick={fetchPressureAnalysis}
                  className="px-2 py-1 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700"
                >
                  새로고침
                </button>
              </div>
              
              {pressureAnalysis ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="text-center">
                    <div className="text-xs text-yellow-700 dark:text-yellow-300">매수 압력</div>
                    <div className="text-lg font-bold text-green-600 dark:text-green-400">
                      {pressureAnalysis.buy_pressure?.toFixed(1) || '0'}%
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-yellow-700 dark:text-yellow-300">매도 압력</div>
                    <div className="text-lg font-bold text-red-600 dark:text-red-400">
                      {pressureAnalysis.sell_pressure?.toFixed(1) || '0'}%
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-yellow-700 dark:text-yellow-300">시장 신호</div>
                    <div className={`text-sm font-bold ${
                      pressureAnalysis.pressure_signal?.includes('매수') ? 'text-green-600 dark:text-green-400' :
                      pressureAnalysis.pressure_signal?.includes('매도') ? 'text-red-600 dark:text-red-400' :
                      'text-gray-600 dark:text-gray-400'
                    }`}>
                      {pressureAnalysis.pressure_signal}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-4">
                  <div className="text-sm text-yellow-700 dark:text-yellow-300">
                    매수/매도 압력 데이터를 불러오는 중...
                  </div>
                  <div className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                    브라우저 개발자 도구(F12) → Console에서 오류 확인 가능
                  </div>
                </div>
              )}
              
              {pressureAnalysis && (
                <div className="mt-3 pt-3 border-t border-yellow-200 dark:border-yellow-700">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-yellow-700 dark:text-yellow-300">
                      종목: {pressureAnalysis.symbol}
                    </span>
                    <span className="text-yellow-700 dark:text-yellow-300">
                      {pressureAnalysis.recommendation}
                    </span>
                    <span className="text-yellow-700 dark:text-yellow-300">
                      업데이트: {pressureAnalysis.timestamp}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 에러 메시지 */}
        {error && (
          <div className="p-3 bg-red-50 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* 후보 계약들 */}
        {candidates.length > 0 && (
          <div className="space-y-3">
            <h3 className="font-semibold text-gray-700 dark:text-gray-300">선물 계약 후보</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {candidates.map((candidate, index) => (
                <div
                  key={index}
                  className={`p-3 rounded-lg border ${
                    candidate.symbol === activeContract?.symbol
                      ? 'bg-green-50 border-green-200 dark:bg-green-900 dark:border-green-700'
                      : 'bg-gray-50 border-gray-200 dark:bg-gray-800 dark:border-gray-700'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <div className="font-medium">{candidate.symbol}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">
                        {candidate.description}
                      </div>
                    </div>
                    {candidate.symbol === activeContract?.symbol && (
                      <span className="px-2 py-1 text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded">
                        활성
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="text-xs text-gray-500 dark:text-gray-400 text-center">
          활성 계약은 거래량을 기준으로 자동 선택됩니다
        </div>
      </div>
    );
  };

  return (
    <Card title="선물 계약 관리">
      {renderContent()}
    </Card>
  );
};

export default ActiveContractManager;
