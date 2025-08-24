import GoldPremium from "@/components/GoldPremium";
import InvestmentStrategy from "@/components/InvestmentStrategy";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-4 sm:p-6 lg:p-8">
      <div className="max-w-4xl mx-auto">
        <header className="flex justify-between items-center mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold">Financial Dashboard</h1>
          <ThemeSwitcher />
        </header>
        
        <main className="space-y-6">
          <GoldPremium />
          <InvestmentStrategy />
        </main>

        <footer className="text-center mt-12 text-sm text-gray-500 dark:text-gray-400">
          <p>Data provided by Naver Finance, KoreaExim, and Korea Investment & Securities.</p>
          <p>This is a web application created based on the provided documents.</p>
        </footer>
      </div>
    </div>
  );
}