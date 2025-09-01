import GoldPremium from "@/components/GoldPremium";
import InvestmentStrategy from "@/components/InvestmentStrategy";
import GoldAnalysis from "@/components/GoldAnalysis";
import ActiveContractManager from "@/components/ActiveContractManager";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold">Financial Dashboard</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              실시간 금 시장 분석 및 투자 전략 플랫폼
            </p>
          </div>
          <ThemeSwitcher />
        </header>
        
        <main className="space-y-6">
          {/* 상단: 실시간 데이터 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <GoldPremium />
            <InvestmentStrategy />
          </div>
          
          {/* 중단: 계약 관리 */}
          <ActiveContractManager />
          
          {/* 하단: 종합 분석 */}
          <GoldAnalysis />
        </main>

        <footer className="text-center mt-12 text-sm text-gray-500 dark:text-gray-400">
          <div className="space-y-1">
            <p>📊 데이터 제공: Naver Finance, 한국수출입은행, 한국투자증권</p>
            <p>⚡ 실시간 업데이트: 10분 간격 자동 갱신</p>
            <p>⚠️ 투자 결정은 신중히 하시기 바랍니다. 본 정보는 참고용입니다.</p>
          </div>
        </footer>
      </div>
    </div>
  );
}