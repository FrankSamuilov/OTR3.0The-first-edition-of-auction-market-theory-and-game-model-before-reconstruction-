"""
博弈论分析模块 - 包含所有博弈相关的分析
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import logging
from datetime import datetime
import time
import asyncio

from logger_utils import Colors, print_colored
from indicators_module import calculate_optimized_indicators
from smc_module import detect_fvg, detect_order_blocks


class MarketDataCollector:
    """市场数据收集器 - 收集所有博弈分析需要的数据"""

    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.logger = logging.getLogger('GameTheory')

    async def collect_comprehensive_data(self, symbol):
        """收集综合市场数据"""

        data = {
            'timestamp': time.time(),
            'symbol': symbol,
            'kline_data': None,
            'order_book': None,
            'long_short_ratio': None,
            'funding_rate': None,
            'open_interest': None,
            'recent_trades': None,
            'liquidations': None
        }

        try:
            # 1. K线数据和技术指标
            print_colored(f"📊 获取{symbol}K线数据...", Colors.INFO)
            df = self.get_historical_data_safe(symbol)
            if df is not None and not df.empty:
                df = calculate_optimized_indicators(df)
                data['kline_data'] = df

            # 2. 订单簿深度
            print_colored(f"📖 获取{symbol}订单簿...", Colors.INFO)
            order_book = await self.get_order_book_async(symbol)
            data['order_book'] = order_book

            # 3. 多空持仓比率
            print_colored(f"⚖️ 获取{symbol}多空比...", Colors.INFO)
            long_short = await self.get_long_short_ratio(symbol)
            data['long_short_ratio'] = long_short

            # 4. 资金费率
            funding = await self.get_funding_rate_async(symbol)
            data['funding_rate'] = funding

            # 5. 持仓量
            open_interest = await self.get_open_interest_async(symbol)
            data['open_interest'] = open_interest

            # 6. 最近成交
            trades = await self.get_recent_trades_async(symbol)
            data['recent_trades'] = self.analyze_trade_flow(trades)

            # 7. 爆仓数据（可选）
            liquidations = await self.get_liquidation_data(symbol)
            data['liquidations'] = liquidations

            print_colored(f"✅ {symbol}数据收集完成", Colors.GREEN)

        except Exception as e:
            self.logger.error(f"数据收集错误 {symbol}: {e}")
            print_colored(f"❌ {symbol}数据收集失败: {e}", Colors.ERROR)

        return data

    def get_historical_data_safe(self, symbol):
        """安全获取历史数据"""
        try:
            from data_module import get_historical_data
            return get_historical_data(self.client, symbol)
        except Exception as e:
            self.logger.error(f"获取历史数据失败: {e}")
            return None

    async def get_order_book_async(self, symbol):
        """异步获取订单簿"""
        try:
            order_book = self.client.futures_order_book(symbol=symbol, limit=20)
            return self.parse_order_book(order_book)
        except Exception as e:
            self.logger.error(f"获取订单簿失败: {e}")
            return None

    def parse_order_book(self, order_book):
        """解析订单簿数据"""
        if not order_book:
            return None

        return {
            'bid_prices': [float(bid[0]) for bid in order_book.get('bids', [])],
            'bid_sizes': [float(bid[1]) for bid in order_book.get('bids', [])],
            'ask_prices': [float(ask[0]) for ask in order_book.get('asks', [])],
            'ask_sizes': [float(ask[1]) for ask in order_book.get('asks', [])],
            'timestamp': time.time()
        }

    async def get_long_short_ratio(self, symbol):
        """获取多空比数据"""
        try:
            # 顶级交易员持仓比
            top_trader_ratio = self.client.futures_top_longshort_position_ratio(
                symbol=symbol,
                period='5m',
                limit=1
            )

            # 普通用户持仓比
            global_ratio = self.client.futures_global_longshort_ratio(
                symbol=symbol,
                period='5m',
                limit=1
            )

            # 大户持仓比
            taker_ratio = self.client.futures_takerlongshort_ratio(
                symbol=symbol,
                period='5m',
                limit=1
            )

            return {
                'top_traders': {
                    'long_ratio': float(top_trader_ratio[0]['longAccount']) if top_trader_ratio else 0.5,
                    'short_ratio': float(top_trader_ratio[0]['shortAccount']) if top_trader_ratio else 0.5,
                    'ratio': float(top_trader_ratio[0]['longShortRatio']) if top_trader_ratio else 1.0
                },
                'global': {
                    'long_ratio': float(global_ratio[0]['longAccount']) if global_ratio else 0.5,
                    'short_ratio': float(global_ratio[0]['shortAccount']) if global_ratio else 0.5,
                    'ratio': float(global_ratio[0]['longShortRatio']) if global_ratio else 1.0
                },
                'takers': {
                    'buy_vol_ratio': float(taker_ratio[0]['buySellRatio']) if taker_ratio else 1.0,
                    'sell_vol_ratio': 1.0,  # 计算得出
                    'ratio': float(taker_ratio[0]['buySellRatio']) if taker_ratio else 1.0
                }
            }
        except Exception as e:
            self.logger.error(f"获取多空比失败: {e}")
            # 返回默认值
            return {
                'top_traders': {'long_ratio': 0.5, 'short_ratio': 0.5, 'ratio': 1.0},
                'global': {'long_ratio': 0.5, 'short_ratio': 0.5, 'ratio': 1.0},
                'takers': {'buy_vol_ratio': 1.0, 'sell_vol_ratio': 1.0, 'ratio': 1.0}
            }

    async def get_funding_rate_async(self, symbol):
        """异步获取资金费率"""
        try:
            funding = self.client.futures_funding_rate(symbol=symbol, limit=1)
            return float(funding[0]['fundingRate']) if funding else 0
        except Exception as e:
            self.logger.error(f"获取资金费率失败: {e}")
            return 0

    async def get_open_interest_async(self, symbol):
        """异步获取持仓量"""
        try:
            open_interest = self.client.futures_open_interest(symbol=symbol)
            return float(open_interest['openInterest'])
        except Exception as e:
            self.logger.error(f"获取持仓量失败: {e}")
            return 0

    async def get_recent_trades_async(self, symbol):
        """异步获取最近成交"""
        try:
            trades = self.client.futures_recent_trades(symbol=symbol, limit=100)
            return trades
        except Exception as e:
            self.logger.error(f"获取最近成交失败: {e}")
            return []

    def analyze_trade_flow(self, trades):
        """分析成交流"""
        if not trades:
            return {
                'buy_volume': 0,
                'sell_volume': 0,
                'buy_count': 0,
                'sell_count': 0,
                'large_trades': []
            }

        buy_volume = 0
        sell_volume = 0
        buy_count = 0
        sell_count = 0
        large_trades = []

        # 计算平均交易量
        volumes = [float(t['qty']) for t in trades]
        avg_volume = np.mean(volumes) if volumes else 0
        large_threshold = avg_volume * 3  # 3倍平均值为大单

        for trade in trades:
            qty = float(trade['qty'])
            price = float(trade['price'])

            # 判断买卖方向
            if trade['isBuyerMaker']:
                sell_volume += qty
                sell_count += 1
            else:
                buy_volume += qty
                buy_count += 1

            # 记录大单
            if qty > large_threshold:
                large_trades.append({
                    'price': price,
                    'qty': qty,
                    'side': 'SELL' if trade['isBuyerMaker'] else 'BUY',
                    'time': trade['time']
                })

        return {
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'large_trades': large_trades[:10]  # 只保留最近10笔大单
        }

    async def get_liquidation_data(self, symbol):
        """获取爆仓数据（如果可用）"""
        # 这个需要特殊API或第三方数据源
        # 暂时返回模拟数据
        return {
            'long_liquidations': 0,
            'short_liquidations': 0,
            'total_liquidations': 0
        }


class SMCGameTheoryAnalyzer:
    """结合SMC概念的博弈分析器"""

    def __init__(self):
        self.logger = logging.getLogger('SMCGameTheory')

    def analyze_market_structure(self, data):
        """分析市场结构 - 结合SMC和博弈论"""

        analysis = {
            'smc_signals': {},
            'game_theory_signals': {},
            'long_short_dynamics': {},
            'manipulation_evidence': {},
            'trading_recommendation': {}
        }

        if not data or not data.get('kline_data') is not None:
            return analysis

        df = data['kline_data']

        # 1. SMC分析
        # 检测FVG（公允价值缺口）
        fvg_analysis = self.analyze_fvg_with_game_theory(df, data)
        analysis['smc_signals']['fvg'] = fvg_analysis

        # 检测订单块
        order_blocks = self.detect_order_blocks_with_volume(df, data['order_book'])
        analysis['smc_signals']['order_blocks'] = order_blocks

        # 检测流动性区域
        liquidity_zones = self.identify_liquidity_zones(df, data)
        analysis['smc_signals']['liquidity'] = liquidity_zones

        # 2. 多空比博弈分析
        ls_game = self.analyze_long_short_game(data['long_short_ratio'], data)
        analysis['long_short_dynamics'] = ls_game

        # 3. 操纵检测
        manipulation = self.detect_market_manipulation(data)
        analysis['manipulation_evidence'] = manipulation

        # 4. 综合判断
        final_signal = self.synthesize_signals(analysis, data)
        analysis['trading_recommendation'] = final_signal

        return analysis

    def analyze_fvg_with_game_theory(self, df, market_data):
        """FVG分析结合博弈论"""

        # 使用现有的FVG检测
        try:
            fvg_data = detect_fvg(df)
        except:
            fvg_data = []

        if not market_data.get('long_short_ratio'):
            return fvg_data

        # 增强：结合多空比分析FVG的可靠性
        enhanced_fvgs = []

        for fvg in fvg_data:
            # 检查FVG形成时的多空比
            fvg_reliability = self.assess_fvg_reliability(
                fvg,
                market_data['long_short_ratio'],
                market_data['order_book']
            )

            fvg['game_theory_assessment'] = fvg_reliability

            # 如果是看涨FVG
            if fvg['direction'] == 'UP':
                # 检查是否与多头趋势一致
                if market_data['long_short_ratio']['top_traders']['ratio'] > 1.5:
                    fvg['reliability'] = 'HIGH'
                    fvg['reason'] = '顶级交易员支持看涨FVG'
                elif market_data['long_short_ratio']['global']['ratio'] < 0.8:
                    fvg['reliability'] = 'LOW'
                    fvg['reason'] = '散户过度看空，可能是诱多陷阱'
                else:
                    fvg['reliability'] = 'MEDIUM'
                    fvg['reason'] = '市场情绪中性'

            # 如果是看跌FVG
            elif fvg['direction'] == 'DOWN':
                if market_data['long_short_ratio']['top_traders']['ratio'] < 0.7:
                    fvg['reliability'] = 'HIGH'
                    fvg['reason'] = '顶级交易员支持看跌FVG'
                elif market_data['long_short_ratio']['global']['ratio'] > 1.2:
                    fvg['reliability'] = 'LOW'
                    fvg['reason'] = '散户过度看多，可能是诱空陷阱'
                else:
                    fvg['reliability'] = 'MEDIUM'
                    fvg['reason'] = '市场情绪中性'

            enhanced_fvgs.append(fvg)

        return enhanced_fvgs

    def assess_fvg_reliability(self, fvg, ls_ratio, order_book):
        """评估FVG的可靠性"""
        reliability_score = 0.5  # 基础分数

        # 1. 检查订单簿支持
        if order_book:
            bid_pressure = sum(order_book.get('bid_sizes', [])[:5])
            ask_pressure = sum(order_book.get('ask_sizes', [])[:5])

            if fvg['direction'] == 'UP' and bid_pressure > ask_pressure * 1.5:
                reliability_score += 0.2
            elif fvg['direction'] == 'DOWN' and ask_pressure > bid_pressure * 1.5:
                reliability_score += 0.2

        # 2. 检查多空比一致性
        if ls_ratio:
            top_ratio = ls_ratio['top_traders']['ratio']
            if (fvg['direction'] == 'UP' and top_ratio > 1.3) or \
                    (fvg['direction'] == 'DOWN' and top_ratio < 0.7):
                reliability_score += 0.3

        return {
            'score': reliability_score,
            'grade': 'HIGH' if reliability_score > 0.7 else 'MEDIUM' if reliability_score > 0.4 else 'LOW'
        }

    def analyze_long_short_game(self, ls_ratio, market_data):
        """多空比博弈分析"""

        if not ls_ratio:
            return {'status': 'NO_DATA'}

        game_analysis = {
            'market_sentiment': '',
            'smart_vs_retail': '',
            'manipulation_probability': 0.0,
            'game_state': '',
            'strategic_recommendation': ''
        }

        # 1. 分析顶级交易员vs散户的博弈
        top_ratio = ls_ratio['top_traders']['ratio']
        global_ratio = ls_ratio['global']['ratio']

        # 计算聪明钱与散户的分歧度
        divergence = abs(top_ratio - global_ratio) / max(top_ratio, global_ratio)

        if divergence > 0.3:  # 30%以上的分歧
            if top_ratio > global_ratio * 1.3:
                game_analysis['smart_vs_retail'] = 'SMART_BULLISH_RETAIL_BEARISH'
                game_analysis['game_state'] = '聪明钱在吸筹，散户在恐慌'
                game_analysis['manipulation_probability'] = 0.7
                game_analysis['strategic_recommendation'] = '跟随聪明钱做多'
            elif top_ratio < global_ratio * 0.7:
                game_analysis['smart_vs_retail'] = 'SMART_BEARISH_RETAIL_BULLISH'
                game_analysis['game_state'] = '聪明钱在派发，散户在接盘'
                game_analysis['manipulation_probability'] = 0.8
                game_analysis['strategic_recommendation'] = '跟随聪明钱做空'
        else:
            game_analysis['smart_vs_retail'] = 'ALIGNED'
            game_analysis['game_state'] = '市场共识'
            game_analysis['manipulation_probability'] = 0.2
            game_analysis['strategic_recommendation'] = '顺势而为'

        # 2. 极端多空比分析
        if global_ratio > 2.0:
            game_analysis['market_sentiment'] = 'EXTREME_BULLISH'
            if game_analysis['strategic_recommendation'] == '顺势而为':
                game_analysis['strategic_recommendation'] = '极度看多，注意反转风险'
        elif global_ratio < 0.5:
            game_analysis['market_sentiment'] = 'EXTREME_BEARISH'
            if game_analysis['strategic_recommendation'] == '顺势而为':
                game_analysis['strategic_recommendation'] = '极度看空，可能接近底部'
        else:
            game_analysis['market_sentiment'] = 'NEUTRAL'

        # 3. 结合资金费率的博弈
        funding = market_data.get('funding_rate', 0)
        if funding > 0.001 and global_ratio > 1.5:
            game_analysis['funding_pressure'] = '多头支付高额资金费率，可能被迫平仓'
        elif funding < -0.001 and global_ratio < 0.7:
            game_analysis['funding_pressure'] = '空头支付高额资金费率，可能反弹'

        return game_analysis

    def detect_order_blocks_with_volume(self, df, order_book):
        """结合成交量检测订单块"""
        try:
            # 使用现有的订单块检测
            order_blocks = detect_order_blocks(df)

            # 增强：结合订单簿信息
            if order_book and order_blocks:
                current_price = df['close'].iloc[-1]

                for block in order_blocks:
                    # 检查订单块附近的订单簿深度
                    block_price = block['price']

                    # 计算订单块附近的支撑/阻力强度
                    support_strength = 0
                    resistance_strength = 0

                    if order_book.get('bid_prices'):
                        for i, bid_price in enumerate(order_book['bid_prices'][:10]):
                            if abs(bid_price - block_price) / block_price < 0.01:  # 1%范围内
                                support_strength += order_book['bid_sizes'][i]

                    if order_book.get('ask_prices'):
                        for i, ask_price in enumerate(order_book['ask_prices'][:10]):
                            if abs(ask_price - block_price) / block_price < 0.01:
                                resistance_strength += order_book['ask_sizes'][i]

                    block['order_book_support'] = support_strength
                    block['order_book_resistance'] = resistance_strength

            return order_blocks

        except Exception as e:
            self.logger.error(f"订单块检测失败: {e}")
            return []

    def identify_liquidity_zones(self, df, market_data):
        """识别流动性区域"""
        zones = []

        if df is None or df.empty:
            return zones

        try:
            # 1. 识别前高前低
            recent_high = df['high'].tail(50).max()
            recent_low = df['low'].tail(50).min()
            current_price = df['close'].iloc[-1]

            # 2. 计算关键心理价位
            psychological_levels = self.calculate_psychological_levels(current_price)

            # 3. 结合多空比识别止损区域
            if market_data.get('long_short_ratio'):
                ls_ratio = market_data['long_short_ratio']['global']['ratio']

                if ls_ratio > 1.5:  # 多头过多
                    # 多头止损区可能在下方
                    long_stop_zone = current_price * 0.97  # 3%下方
                    zones.append({
                        'type': 'LONG_STOP_ZONE',
                        'price': long_stop_zone,
                        'strength': ls_ratio,
                        'description': '多头止损密集区'
                    })

                elif ls_ratio < 0.7:  # 空头过多
                    # 空头止损区可能在上方
                    short_stop_zone = current_price * 1.03  # 3%上方
                    zones.append({
                        'type': 'SHORT_STOP_ZONE',
                        'price': short_stop_zone,
                        'strength': 1 / ls_ratio,
                        'description': '空头止损密集区'
                    })

            # 4. 添加前高前低作为流动性区域
            zones.append({
                'type': 'RESISTANCE',
                'price': recent_high,
                'strength': 1.0,
                'description': '近期高点阻力'
            })

            zones.append({
                'type': 'SUPPORT',
                'price': recent_low,
                'strength': 1.0,
                'description': '近期低点支撑'
            })

            return zones

        except Exception as e:
            self.logger.error(f"流动性区域识别失败: {e}")
            return zones

    def calculate_psychological_levels(self, price):
        """计算心理价位"""
        levels = []

        # 整千价位
        thousand_level = round(price / 1000) * 1000
        levels.append(thousand_level)

        # 整百价位
        hundred_level = round(price / 100) * 100
        levels.append(hundred_level)

        # 整十价位（对于小价格）
        if price < 100:
            ten_level = round(price / 10) * 10
            levels.append(ten_level)

        return [l for l in levels if 0.95 * price <= l <= 1.05 * price]  # 只保留±5%范围内的

    def detect_market_manipulation(self, data):
        """检测市场操纵行为"""
        manipulation = {
            'detected': False,
            'type': None,
            'confidence': 0.0,
            'evidence': []
        }

        if not data:
            return manipulation

        # 1. 检测诱多陷阱
        bull_trap = self.detect_bull_trap(data)
        if bull_trap['detected']:
            manipulation['detected'] = True
            manipulation['type'] = 'BULL_TRAP'
            manipulation['confidence'] = bull_trap['confidence']
            manipulation['evidence'].extend(bull_trap['evidence'])

        # 2. 检测诱空陷阱
        bear_trap = self.detect_bear_trap(data)
        if bear_trap['detected']:
            manipulation['detected'] = True
            manipulation['type'] = 'BEAR_TRAP'
            manipulation['confidence'] = max(manipulation['confidence'], bear_trap['confidence'])
            manipulation['evidence'].extend(bear_trap['evidence'])

        # 3. 检测止损猎杀
        stop_hunt = self.detect_stop_hunting(data)
        if stop_hunt['detected']:
            manipulation['detected'] = True
            manipulation['type'] = 'STOP_HUNTING'
            manipulation['confidence'] = max(manipulation['confidence'], stop_hunt['confidence'])
            manipulation['evidence'].extend(stop_hunt['evidence'])

        return manipulation

    def detect_bull_trap(self, data):
        """检测诱多陷阱"""
        result = {
            'detected': False,
            'confidence': 0.0,
            'evidence': []
        }

        if not data.get('kline_data') is not None:
            return result

        df = data['kline_data']
        ls_ratio = data.get('long_short_ratio', {})

        # 条件1：价格在高位，但聪明钱在卖
        if len(df) >= 20:
            price_position = (df['close'].iloc[-1] - df['low'].tail(20).min()) / \
                             (df['high'].tail(20).max() - df['low'].tail(20).min())

            if price_position > 0.8:  # 价格在近期高位
                if ls_ratio and ls_ratio['top_traders']['ratio'] < 0.8:  # 但顶级交易员看空
                    result['detected'] = True
                    result['confidence'] += 0.4
                    result['evidence'].append('价格高位但聪明钱看空')

        # 条件2：成交量递减的上涨
        if len(df) >= 5:
            price_change = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
            volume_change = (df['volume'].iloc[-1] - df['volume'].iloc[-5]) / df['volume'].iloc[-5]

            if price_change > 0.02 and volume_change < -0.2:  # 价涨量缩
                result['detected'] = True
                result['confidence'] += 0.3
                result['evidence'].append('价格上涨但成交量萎缩')

        return result

    def detect_bear_trap(self, data):
        """检测诱空陷阱"""
        result = {
            'detected': False,
            'confidence': 0.0,
            'evidence': []
        }

        if not data.get('kline_data') is not None:
            return result

        df = data['kline_data']
        ls_ratio = data.get('long_short_ratio', {})

        # 条件1：价格在低位，但聪明钱在买
        if len(df) >= 20:
            price_position = (df['close'].iloc[-1] - df['low'].tail(20).min()) / \
                             (df['high'].tail(20).max() - df['low'].tail(20).min())

            if price_position < 0.2:  # 价格在近期低位
                if ls_ratio and ls_ratio['top_traders']['ratio'] > 1.2:  # 但顶级交易员看多
                    result['detected'] = True
                    result['confidence'] += 0.4
                    result['evidence'].append('价格低位但聪明钱看多')

        # 条件2：恐慌性下跌后的快速反弹
        if len(df) >= 3:
            if df['close'].iloc[-3] > df['close'].iloc[-2] * 1.02 and \
                    df['close'].iloc[-1] > df['close'].iloc[-2] * 1.01:
                # V型反转
                result['detected'] = True
                result['confidence'] += 0.3
                result['evidence'].append('V型反转形态')

        return result

    def detect_stop_hunting(self, data):
        """检测止损猎杀"""
        result = {
            'detected': False,
            'confidence': 0.0,
            'evidence': []
        }

        if not data.get('kline_data') is not None:
            return result

        df = data['kline_data']

        # 检测插针行为
        if len(df) >= 1:
            last_candle = df.iloc[-1]
            body = abs(last_candle['close'] - last_candle['open'])
            upper_wick = last_candle['high'] - max(last_candle['close'], last_candle['open'])
            lower_wick = min(last_candle['close'], last_candle['open']) - last_candle['low']

            # 上影线过长
            if upper_wick > body * 2:
                result['detected'] = True
                result['confidence'] += 0.5
                result['evidence'].append('长上影线，可能扫空头止损')

            # 下影线过长
            if lower_wick > body * 2:
                result['detected'] = True
                result['confidence'] += 0.5
                result['evidence'].append('长下影线，可能扫多头止损')

        return result

    def synthesize_signals(self, analysis, data):
        """综合所有信号生成最终建议"""
        recommendation = {
            'action': 'HOLD',
            'confidence': 0.0,
            'entry_price': 0,
            'stop_loss': 0,
            'take_profit': 0,
            'position_size': 0,
            'reasoning': []
        }

        if not data.get('kline_data') is not None:
            return recommendation

        current_price = data['kline_data']['close'].iloc[-1]

        # 1. 检查是否有操纵行为
        if analysis['manipulation_evidence']['detected']:
            manipulation_type = analysis['manipulation_evidence']['type']

            if manipulation_type == 'BULL_TRAP':
                recommendation['action'] = 'SELL'
                recommendation['confidence'] = analysis['manipulation_evidence']['confidence']
                recommendation['reasoning'].append('检测到诱多陷阱，建议做空')
            elif manipulation_type == 'BEAR_TRAP':
                recommendation['action'] = 'BUY'
                recommendation['confidence'] = analysis['manipulation_evidence']['confidence']
                recommendation['reasoning'].append('检测到诱空陷阱，建议做多')
            elif manipulation_type == 'STOP_HUNTING':
                recommendation['action'] = 'WAIT'
                recommendation['reasoning'].append('检测到止损猎杀，等待明朗')
                return recommendation

        # 2. 分析多空博弈
        ls_dynamics = analysis['long_short_dynamics']
        if ls_dynamics.get('manipulation_probability', 0) > 0.6:
            if 'SMART_BULLISH' in ls_dynamics.get('smart_vs_retail', ''):
                recommendation['action'] = 'BUY'
                recommendation['confidence'] = max(recommendation['confidence'], 0.7)
                recommendation['reasoning'].append(ls_dynamics['strategic_recommendation'])
            elif 'SMART_BEARISH' in ls_dynamics.get('smart_vs_retail', ''):
                recommendation['action'] = 'SELL'
                recommendation['confidence'] = max(recommendation['confidence'], 0.7)
                recommendation['reasoning'].append(ls_dynamics['strategic_recommendation'])

        # 3. 检查SMC信号
        # FVG信号
        fvg_signals = analysis['smc_signals'].get('fvg', [])
        for fvg in fvg_signals:
            if fvg.get('reliability') == 'HIGH' and not fvg.get('is_filled', True):
                if fvg['direction'] == 'UP' and recommendation['action'] != 'SELL':
                    recommendation['action'] = 'BUY'
                    recommendation['confidence'] = max(recommendation['confidence'], 0.8)
                    recommendation['reasoning'].append(f"高可靠性看涨FVG: {fvg.get('reason', '')}")
                elif fvg['direction'] == 'DOWN' and recommendation['action'] != 'BUY':
                    recommendation['action'] = 'SELL'
                    recommendation['confidence'] = max(recommendation['confidence'], 0.8)
                    recommendation['reasoning'].append(f"高可靠性看跌FVG: {fvg.get('reason', '')}")

        # 4. 计算具体交易参数
        if recommendation['action'] in ['BUY', 'SELL']:
            recommendation['entry_price'] = current_price

            if recommendation['action'] == 'BUY':
                recommendation['stop_loss'] = current_price * 0.98  # 2%止损
                recommendation['take_profit'] = current_price * 1.05  # 5%止盈
            else:
                recommendation['stop_loss'] = current_price * 1.02
                recommendation['take_profit'] = current_price * 0.95

            # 根据置信度计算仓位
            recommendation['position_size'] = min(recommendation['confidence'], 0.3)  # 最大30%仓位

        return recommendation


class IntegratedDecisionEngine:
    """综合所有分析的决策引擎"""

    def __init__(self):
        self.smc_analyzer = SMCGameTheoryAnalyzer()
        self.logger = logging.getLogger('DecisionEngine')

    def make_trading_decision(self, market_data):
        """基于完整分析做出交易决策"""

        decision = {
            'action': 'HOLD',
            'confidence': 0.0,
            'position_size': 0.0,
            'entry_strategy': {},
            'risk_management': {},
            'reasoning': []
        }

        try:
            # 1. 运行SMC + 博弈论分析
            analysis = self.smc_analyzer.analyze_market_structure(market_data)

            # 2. 获取综合建议
            recommendation = analysis.get('trading_recommendation', {})

            # 3. 转换为决策格式
            if recommendation.get('action') in ['BUY', 'SELL']:
                decision['action'] = recommendation['action']
                decision['confidence'] = recommendation.get('confidence', 0.5)
                decision['position_size'] = recommendation.get('position_size', 0.1)
                decision['reasoning'] = recommendation.get('reasoning', [])

                # 设置入场策略
                decision['entry_strategy'] = {
                    'type': 'MARKET',
                    'entry_price': recommendation.get('entry_price', 0),
                    'method': '市价入场'
                }

                # 设置风险管理
                decision['risk_management'] = {
                    'stop_loss': recommendation.get('stop_loss', 0),
                    'take_profit': recommendation.get('take_profit', 0),
                    'risk_level': 'HIGH' if decision['confidence'] < 0.6 else 'MEDIUM'
                }

            elif recommendation.get('action') == 'WAIT':
                decision['action'] = 'HOLD'
                decision['reasoning'] = recommendation.get('reasoning', ['等待更好的入场时机'])

        except Exception as e:
            self.logger.error(f"决策引擎错误: {e}")
            decision['reasoning'].append(f'分析错误: {str(e)}')

        return decision