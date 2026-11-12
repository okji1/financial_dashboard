"""Framework-independent response contracts backed exclusively by snapshots."""
import datetime
import re
from analysis import generate_comprehensive_analysis
from gold_data import analyze_premium_signals
from shared_store import StoreUnavailable, fresh_timestamp


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def premium_response(quote):
    return {
        'london_gold_usd': quote['international_price_usd_oz'],
        'london_gold_krw': quote['converted_intl_price_krw_g'] * 31.1035,
        'domestic_gold_price': quote['domestic_price_krw_g'],
        'premium_percentage': quote['premium_percentage'], 'premium_grade': quote['premium_grade'],
        'exchange_rate': quote['usd_krw_rate'], 'active_contract': '현물금', 'cached': True,
        'international_gold_source': 'NAVER_COMEX_GCcv1_FUTURES',
        'price_alignment_warning': '국제 선물과 국내 현물의 참고 비교입니다',
        'timestamp': quote['timestamp'],
    }


def strategy_response(quote):
    return {'premium_grade': quote['premium_grade'], 'premium_percentage': quote['premium_percentage'],
        'signals': analyze_premium_signals(quote['premium_percentage']),
        'recommendation': '국제 선물과 국내 현물의 참고 비교이며 실제 매매 가능 가격차를 뜻하지 않습니다'}


def trading_recommendation(signal):
    return {'강한 매수': '🟢 매수 고려 - 매수 압력이 강합니다',
        '약한 매수': '🟡 관망 - 매수 압력이 약간 우세합니다',
        '균형': '⚪ 중립 - 매수/매도 압력이 균형입니다',
        '약한 매도': '🟡 관망 - 매도 압력이 약간 우세합니다',
        '강한 매도': '🔴 매도 고려 - 매도 압력이 강합니다'}.get(signal, '⚪ 데이터 부족')


class DashboardService:
    def __init__(self, store):
        self.store = store
        self._row = None

    def bundle(self):
        if self._row is None:
            try:
                self._row = self.store.read()
            except StoreUnavailable:
                raise ServiceError(503, '시세 데이터를 일시적으로 사용할 수 없습니다') from None
        return self._row['payload']

    def require(self, value, *, empty_message='현재 조회 가능한 데이터가 없습니다'):
        if not isinstance(value, dict) or not fresh_timestamp(value.get('collected_at')):
            raise ServiceError(503, '시세 데이터를 일시적으로 사용할 수 없습니다')
        if value.get('state') == 'empty':
            raise ServiceError(404, empty_message)
        if value.get('state') != 'ok' or not isinstance(value.get('data'), dict):
            raise ServiceError(503, '시세 데이터를 일시적으로 사용할 수 없습니다')
        return value['data']

    def quote(self):
        from quote_store import valid_quote
        quote = self.require(self.bundle().get('gold'))
        if not valid_quote(quote) or not fresh_timestamp(quote.get('timestamp')):
            raise ServiceError(503, '시세 데이터를 일시적으로 사용할 수 없습니다')
        return quote

    def premium(self):
        return premium_response(self.quote())

    def strategy(self):
        return strategy_response(self.quote())

    def analysis(self):
        result = generate_comprehensive_analysis(self.quote())
        if result.get('error'):
            raise ServiceError(502, '분석 응답을 생성하지 못했습니다')
        return result

    def candidates(self):
        return self.require(self.bundle().get('candidates'))

    def active(self):
        return self.require(self.bundle().get('active_contract'), empty_message='활성 계약을 찾을 수 없습니다')

    def book(self, symbol=None):
        if not symbol:
            symbol = self.active()['symbol']
        allowed = {item['symbol'] for item in self.candidates()['candidates']}
        if symbol not in allowed:
            raise ServiceError(404, '검증된 금선물 후보에 없는 계약입니다')
        return self.require(self.bundle().get('orderbooks', {}).get(symbol), empty_message='호가 데이터 없음')

    def pressure(self, symbol=None):
        book = self.book(symbol)
        source_time = book.get('last_update_time', '')
        timestamp = f'{source_time[:2]}:{source_time[2:4]}:{source_time[4:]}' if re.fullmatch(r'\d{6}', source_time) else self._row['collected_at']
        return {'symbol': book['symbol'], 'pressure_signal': book['pressure_signal'],
            'buy_pressure': book['buy_pressure_pct'], 'sell_pressure': book['sell_pressure_pct'],
            'recommendation': trading_recommendation(book['pressure_signal']),
            'timestamp': timestamp}

    def orderbook(self, symbol=None):
        book = self.book(symbol)
        return {'symbol': book['symbol'], 'contract_name': book['contract_name'],
            'current_price': book['current_price'], 'volume': book['volume'],
            'pressure_analysis': {'buy_pressure_pct': book['buy_pressure_pct'],
                'sell_pressure_pct': book['sell_pressure_pct'], 'pressure_ratio': book['pressure_ratio'],
                'pressure_signal': book['pressure_signal'], 'total_bid_quantity': book['total_bid_quantity'],
                'total_ask_quantity': book['total_ask_quantity']},
            'orderbook': book['orderbook'],
            'price_info': {'prev_day_price': book['prev_day_price'], 'price_change': book['price_change'],
                'change_rate': book['change_rate']},
            'last_update_time': book['last_update_time'], 'analysis_time': self._row['collected_at']}

    def update(self):
        # Acknowledge a worker refresh, never synchronously call a provider.
        contract = self.active()
        self.store.request_refresh()
        return {'message': '수집기에 활성 계약 갱신을 요청했습니다', 'contract': contract, 'refresh_requested': True}
