"""
拍卖市场理论模块
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import logging
from datetime import datetime

from logger_utils import Colors, print_colored


class AuctionTheoryFramework:
    """拍卖理论框架 - 理解价格发现的本质"""

    def __init__(self):
        self.auction_types = {
            'CONTINUOUS_DOUBLE_AUCTION': '连续双向拍卖',
            'CALL_AUCTION': '集合竞价',
            'DUTCH_AUCTION': '荷兰式拍卖',
            'VICKREY_AUCTION': '维克里拍卖'
        }
        self.logger = logging.getLogger('AuctionTheory')

    def analyze_price_discovery_mechanism(self, order_book_sequence, trades):
        """分析价格发现机制的效率"""

        discovery_analysis = {
            'price_efficiency': 0.0,
            'information_incorporation_speed': 0.0,
            'market_quality': {},
            'auction_failures': [],
            'manipulation_evidence': []
        }

        if not order_book_sequence or not trades:
            return discovery_analysis

        try:
            # 1. 分析价格发现效率 (Hasbrouck信息份额)
            if len(trades) >= 100:
                # 计算价格变化的信息含量
                price_changes = np.diff([float(t.get('price', 0)) for t in trades])
                volume_weighted_changes = np.diff([float(t.get('price', 0)) * float(t.get('qty', 0)) for t in trades])

                # Hasbrouck信息份额：衡量价格发现的效率
                if np.var(volume_weighted_changes) > 0:
                    info_share = np.var(price_changes) / np.var(volume_weighted_changes)
                    discovery_analysis['price_efficiency'] = min(1.0, info_share)

            # 2. 分析拍卖过程中的信息不对称
            auction_asymmetry = self.measure_information_asymmetry(order_book_sequence)
            discovery_analysis['information_asymmetry'] = auction_asymmetry

            # 3. 检测拍卖失败（市场操纵的标志）
            failures = self.detect_auction_failures(order_book_sequence, trades)
            discovery_analysis['auction_failures'] = failures

            # 4. 计算市场质量指标
            market_quality = self.calculate_market_quality(order_book_sequence)
            discovery_analysis['market_quality'] = market_quality

        except Exception as e:
            self.logger.error(f"价格发现分析错误: {e}")

        return discovery_analysis

    def measure_information_asymmetry(self, order_book_sequence):
        """测量拍卖过程中的信息不对称程度"""

        asymmetry_metrics = {
            'glosten_milgrom_spread': 0.0,  # GM模型的信息不对称价差
            'probability_informed_trading': 0.0,  # PIN概率
            'adverse_selection_cost': 0.0,  # 逆向选择成本
            'kyle_lambda': 0.0  # Kyle模型的价格影响系数
        }

        if not order_book_sequence or len(order_book_sequence) < 10:
            return asymmetry_metrics

        try:
            # 1. 计算Glosten-Milgrom价差组成
            spreads = []
            for book in order_book_sequence:
                if book and book.get('bid_prices') and book.get('ask_prices'):
                    if len(book['bid_prices']) > 0 and len(book['ask_prices']) > 0:
                        spread = book['ask_prices'][0] - book['bid_prices'][0]
                        mid_price = (book['ask_prices'][0] + book['bid_prices'][0]) / 2
                        if mid_price > 0:
                            spreads.append(spread / mid_price)

            if spreads:
                # 逆向选择组成部分（信息不对称导致的价差）
                asymmetry_metrics['glosten_milgrom_spread'] = np.percentile(spreads, 75)

            # 2. 估算知情交易概率 (PIN)
            order_imbalances = []
            for book in order_book_sequence:
                if book and book.get('bid_sizes') and book.get('ask_sizes'):
                    buy_volume = sum(book['bid_sizes'][:5]) if len(book['bid_sizes']) >= 5 else sum(book['bid_sizes'])
                    sell_volume = sum(book['ask_sizes'][:5]) if len(book['ask_sizes']) >= 5 else sum(book['ask_sizes'])
                    total_volume = buy_volume + sell_volume
                    if total_volume > 0:
                        imbalance = abs(buy_volume - sell_volume) / total_volume
                        order_imbalances.append(imbalance)

            if order_imbalances:
                # 高不平衡度暗示知情交易
                asymmetry_metrics['probability_informed_trading'] = np.mean(order_imbalances)

            # 3. Kyle's Lambda - 价格影响系数
            if len(order_book_sequence) >= 20:
                price_impacts = []
                for i in range(1, len(order_book_sequence)):
                    curr_book = order_book_sequence[i]
                    prev_book = order_book_sequence[i - 1]

                    if (curr_book and prev_book and
                            curr_book.get('bid_prices') and prev_book.get('bid_prices') and
                            len(curr_book['bid_prices']) > 0 and len(prev_book['bid_prices']) > 0):

                        price_change = curr_book['bid_prices'][0] - prev_book['bid_prices'][0]
                        volume_change = sum(curr_book.get('bid_sizes', [])) - sum(prev_book.get('bid_sizes', []))

                        if volume_change != 0:
                            impact = abs(price_change) / abs(volume_change)
                            price_impacts.append(impact)

                if price_impacts:
                    asymmetry_metrics['kyle_lambda'] = np.median(price_impacts)

        except Exception as e:
            self.logger.error(f"信息不对称测量错误: {e}")

        return asymmetry_metrics

    def detect_auction_failures(self, order_book_sequence, trades):
        """检测拍卖失败和操纵行为"""

        failures = []

        try:
            # 1. 检测"幌骗"(Spoofing) - 虚假订单操纵
            spoofing = self.detect_spoofing(order_book_sequence)
            if spoofing['detected']:
                failures.append({
                    'type': 'SPOOFING',
                    'severity': spoofing['severity'],
                    'evidence': spoofing['evidence'],
                    'timestamp': spoofing.get('timestamp', datetime.now())
                })

            # 2. 检测"分层"(Layering) - 多层虚假订单
            layering = self.detect_layering(order_book_sequence)
            if layering['detected']:
                failures.append({
                    'type': 'LAYERING',
                    'severity': layering['severity'],
                    'evidence': layering['evidence']
                })

            # 3. 检测"钓鱼单"(Fishing) - 探测性订单
            fishing = self.detect_fishing_orders(order_book_sequence, trades)
            if fishing['detected']:
                failures.append({
                    'type': 'FISHING',
                    'severity': fishing['severity'],
                    'evidence': fishing['evidence']
                })

            # 4. 检测"冰山订单"(Iceberg) - 隐藏大单
            iceberg = self.detect_iceberg_orders(order_book_sequence, trades)
            if iceberg['detected']:
                failures.append({
                    'type': 'ICEBERG',
                    'severity': iceberg['severity'],
                    'evidence': iceberg['evidence']
                })

        except Exception as e:
            self.logger.error(f"拍卖失败检测错误: {e}")

        return failures

    def detect_spoofing(self, order_book_sequence):
        """检测幌骗行为 - 快速下单又撤单"""

        spoofing_evidence = {
            'detected': False,
            'severity': 0.0,
            'evidence': [],
            'timestamp': None
        }

        if not order_book_sequence or len(order_book_sequence) < 5:
            return spoofing_evidence

        try:
            # 分析订单簿的快速变化
            for i in range(len(order_book_sequence) - 5):
                window = order_book_sequence[i:i + 5]

                # 检测买卖盘的异常变化
                bid_changes = []
                ask_changes = []

                for j in range(1, len(window)):
                    curr = window[j]
                    prev = window[j - 1]

                    if (curr and prev and
                            curr.get('bid_sizes') and prev.get('bid_sizes')):

                        # 计算各档位的变化
                        for level in range(min(3, len(curr['bid_sizes']), len(prev['bid_sizes']))):
                            change = curr['bid_sizes'][level] - prev['bid_sizes'][level]
                            bid_changes.append(change)

                # 如果出现大量增加后快速减少，可能是幌骗
                if bid_changes:
                    max_increase = max(bid_changes) if any(c > 0 for c in bid_changes) else 0
                    max_decrease = min(bid_changes) if any(c < 0 for c in bid_changes) else 0

                    if max_increase > 0 and abs(max_decrease) > max_increase * 0.8:
                        # 快速增加又快速撤单
                        spoofing_evidence['detected'] = True
                        spoofing_evidence['severity'] = min(1.0, abs(max_decrease) / max_increase)
                        spoofing_evidence['evidence'].append({
                            'type': '快速下撤单',
                            'increase': max_increase,
                            'decrease': max_decrease,
                            'window_index': i
                        })

        except Exception as e:
            self.logger.error(f"幌骗检测错误: {e}")

        return spoofing_evidence

    def detect_layering(self, order_book_sequence):
        """检测分层操纵"""

        layering_evidence = {
            'detected': False,
            'severity': 0.0,
            'evidence': []
        }

        if not order_book_sequence:
            return layering_evidence

        try:
            # 检查是否有多个价位同时出现大单
            for book in order_book_sequence[-5:]:  # 检查最近5个快照
                if not book or not book.get('bid_sizes') or not book.get('ask_sizes'):
                    continue

                # 计算各档位的平均大小
                avg_bid_size = np.mean(book['bid_sizes'][:10]) if len(book['bid_sizes']) >= 10 else np.mean(
                    book['bid_sizes'])
                avg_ask_size = np.mean(book['ask_sizes'][:10]) if len(book['ask_sizes']) >= 10 else np.mean(
                    book['ask_sizes'])

                # 检查是否有多个档位同时出现异常大单
                large_bid_levels = sum(1 for size in book['bid_sizes'][:5] if size > avg_bid_size * 3)
                large_ask_levels = sum(1 for size in book['ask_sizes'][:5] if size > avg_ask_size * 3)

                if large_bid_levels >= 3 or large_ask_levels >= 3:
                    layering_evidence['detected'] = True
                    layering_evidence['severity'] = max(large_bid_levels, large_ask_levels) / 5
                    layering_evidence['evidence'].append({
                        'large_bid_levels': large_bid_levels,
                        'large_ask_levels': large_ask_levels
                    })

        except Exception as e:
            self.logger.error(f"分层检测错误: {e}")

        return layering_evidence

    def detect_fishing_orders(self, order_book_sequence, trades):
        """检测钓鱼单"""

        fishing_evidence = {
            'detected': False,
            'severity': 0.0,
            'evidence': []
        }

        # 钓鱼单特征：小单试探后跟随大单
        # 这里简化实现
        if trades and len(trades) >= 10:
            recent_trades = trades[-10:]
            sizes = [float(t.get('qty', 0)) for t in recent_trades]
            avg_size = np.mean(sizes)

            # 检查是否有小单后跟大单的模式
            for i in range(len(sizes) - 2):
                if sizes[i] < avg_size * 0.2 and sizes[i + 1] > avg_size * 3:
                    fishing_evidence['detected'] = True
                    fishing_evidence['severity'] = 0.6
                    fishing_evidence['evidence'].append('检测到试探性小单后跟大单')

        return fishing_evidence

    def detect_iceberg_orders(self, order_book_sequence, trades):
        """检测冰山订单"""

        iceberg_evidence = {
            'detected': False,
            'severity': 0.0,
            'evidence': []
        }

        # 冰山订单特征：在同一价位持续成交但订单簿显示量不大
        if trades and len(trades) >= 20:
            # 统计各价位的成交量
            price_volumes = {}
            for trade in trades[-50:]:
                price = float(trade.get('price', 0))
                qty = float(trade.get('qty', 0))
                if price > 0:
                    price_volumes[price] = price_volumes.get(price, 0) + qty

            # 找出成交量最大的价位
            if price_volumes:
                max_price = max(price_volumes.keys(), key=lambda x: price_volumes[x])
                max_volume = price_volumes[max_price]
                avg_volume = np.mean(list(price_volumes.values()))

                if max_volume > avg_volume * 5:
                    iceberg_evidence['detected'] = True
                    iceberg_evidence['severity'] = min(1.0, max_volume / (avg_volume * 10))
                    iceberg_evidence['evidence'].append({
                        'price': max_price,
                        'volume': max_volume,
                        'ratio': max_volume / avg_volume
                    })

        return iceberg_evidence

    def calculate_market_quality(self, order_book_sequence):
        """计算市场质量指标"""

        quality = {
            'bid_ask_spread': 0,
            'market_depth': 0,
            'price_volatility': 0,
            'liquidity_score': 0
        }

        if not order_book_sequence:
            return quality

        try:
            spreads = []
            depths = []

            for book in order_book_sequence[-20:]:  # 最近20个快照
                if (book and book.get('bid_prices') and book.get('ask_prices') and
                        len(book['bid_prices']) > 0 and len(book['ask_prices']) > 0):

                    # 计算价差
                    spread = book['ask_prices'][0] - book['bid_prices'][0]
                    mid_price = (book['ask_prices'][0] + book['bid_prices'][0]) / 2
                    if mid_price > 0:
                        spreads.append(spread / mid_price)

                    # 计算深度
                    bid_depth = sum(book.get('bid_sizes', [])[:5])
                    ask_depth = sum(book.get('ask_sizes', [])[:5])
                    depths.append(bid_depth + ask_depth)

            if spreads:
                quality['bid_ask_spread'] = np.mean(spreads)
            if depths:
                quality['market_depth'] = np.mean(depths)

            # 计算流动性得分
            if quality['bid_ask_spread'] > 0 and quality['market_depth'] > 0:
                quality['liquidity_score'] = quality['market_depth'] / (quality['bid_ask_spread'] * 1000)

        except Exception as e:
            self.logger.error(f"市场质量计算错误: {e}")

        return quality


class AuctionManipulationDetector:
    """拍卖操纵检测器 - 识别对拍卖过程的干预"""

    def __init__(self):
        self.logger = logging.getLogger('AuctionManipulation')

    def detect_manipulation_patterns(self, order_book_history, trade_history):
        """检测操纵模式"""

        patterns = {
            'wash_trading': self.detect_wash_trading(trade_history),
            'pump_and_dump': self.detect_pump_and_dump(order_book_history, trade_history),
            'bear_raid': self.detect_bear_raid(order_book_history, trade_history),
            'momentum_ignition': self.detect_momentum_ignition(trade_history)
        }

        # 综合评分
        total_score = sum(p.get('score', 0) for p in patterns.values())

        return {
            'patterns': patterns,
            'total_manipulation_score': min(1.0, total_score),
            'most_likely': max(patterns.keys(), key=lambda x: patterns[x].get('score', 0))
        }

    def detect_wash_trading(self, trade_history):
        """检测对倒交易"""

        result = {
            'detected': False,
            'score': 0.0,
            'evidence': []
        }

        if not trade_history or len(trade_history) < 20:
            return result

        # 检查是否有相同大小的买卖交替
        sizes = [float(t.get('qty', 0)) for t in trade_history[-20:]]

        # 查找重复的交易大小
        size_counts = {}
        for size in sizes:
            size_counts[size] = size_counts.get(size, 0) + 1

        # 如果某个特定大小出现过多，可能是对倒
        max_count = max(size_counts.values()) if size_counts else 0
        if max_count >= 5:
            result['detected'] = True
            result['score'] = min(1.0, max_count / 10)
            result['evidence'].append(f'发现重复交易大小，出现{max_count}次')

        return result

    def detect_pump_and_dump(self, order_book_history, trade_history):
        """检测拉高出货"""

        result = {
            'detected': False,
            'score': 0.0,
            'evidence': []
        }

        # 这里需要更长的历史数据来检测
        # 简化实现：检查快速拉升后的抛压

        return result

    def detect_bear_raid(self, order_book_history, trade_history):
        """检测空头突袭"""

        result = {
            'detected': False,
            'score': 0.0,
            'evidence': []
        }

        # 检查是否有大量卖单突然出现
        if order_book_history and len(order_book_history) >= 5:
            recent_books = order_book_history[-5:]

            # 检查卖压是否突然增加
            initial_ask_pressure = sum(recent_books[0].get('ask_sizes', [])[:5])
            final_ask_pressure = sum(recent_books[-1].get('ask_sizes', [])[:5])

            if initial_ask_pressure > 0 and final_ask_pressure / initial_ask_pressure > 3:
                result['detected'] = True
                result['score'] = min(1.0, (final_ask_pressure / initial_ask_pressure - 1) / 5)
                result['evidence'].append('卖压突然增加3倍以上')

        return result

    def detect_momentum_ignition(self, trade_history):
        """检测动量点火"""

        result = {
            'detected': False,
            'score': 0.0,
            'evidence': []
        }

        # 检查是否有连续的同方向大单
        if trade_history and len(trade_history) >= 10:
            recent_trades = trade_history[-10:]

            # 计算平均交易大小
            avg_size = np.mean([float(t.get('qty', 0)) for t in recent_trades])

            # 检查连续大单
            large_trades = 0
            for trade in recent_trades:
                if float(trade.get('qty', 0)) > avg_size * 2:
                    large_trades += 1

            if large_trades >= 5:
                result['detected'] = True
                result['score'] = min(1.0, large_trades / 7)
                result['evidence'].append(f'发现{large_trades}笔连续大单交易')

        return result


class AuctionOrderFlowAnalyzer:
    """拍卖订单流分析器"""

    def __init__(self):
        self.logger = logging.getLogger('OrderFlow')

    def analyze_order_flow_with_ls_ratio(self, order_book, ls_ratio, recent_trades):
        """结合多空比的订单流分析"""

        flow_analysis = {
            'auction_pressure': {},
            'hidden_liquidity': {},
            'stop_hunt_zones': {},
            'liquidity_grab_probability': 0.0,
            'smart_money_direction': 'NEUTRAL'
        }

        if not order_book:
            return flow_analysis

        try:
            # 1. 分析买卖压力与多空比的关系
            bid_pressure = sum(order_book.get('bid_sizes', [])[:10])
            ask_pressure = sum(order_book.get('ask_sizes', [])[:10])

            if bid_pressure + ask_pressure > 0:
                book_ratio = bid_pressure / (bid_pressure + ask_pressure)
            else:
                book_ratio = 0.5

            flow_analysis['auction_pressure'] = {
                'bid_pressure': bid_pressure,
                'ask_pressure': ask_pressure,
                'book_ratio': book_ratio
            }

            # 如果订单簿与多空比背离，可能有隐藏意图
            if ls_ratio:
                global_ratio = ls_ratio.get('global', {}).get('ratio', 1.0)

                if global_ratio > 1.2 and book_ratio < 0.4:
                    flow_analysis['hidden_liquidity']['type'] = 'HIDDEN_SELLING'
                    flow_analysis['hidden_liquidity']['description'] = '多头占优但卖盘压力大，可能有隐藏卖单'
                    flow_analysis['liquidity_grab_probability'] = 0.7
                    flow_analysis['smart_money_direction'] = 'SELLING'

                elif global_ratio < 0.8 and book_ratio > 0.6:
                    flow_analysis['hidden_liquidity']['type'] = 'HIDDEN_BUYING'
                    flow_analysis['hidden_liquidity']['description'] = '空头占优但买盘支撑强，可能有隐藏买单'
                    flow_analysis['liquidity_grab_probability'] = 0.7
                    flow_analysis['smart_money_direction'] = 'BUYING'

            # 2. 识别止损猎杀区域
            stop_hunt_zones = self.identify_stop_hunting_zones(
                order_book,
                ls_ratio,
                recent_trades
            )
            flow_analysis['stop_hunt_zones'] = stop_hunt_zones

            # 3. 分析订单流毒性
            toxicity = self.analyze_order_flow_toxicity(order_book, recent_trades)
            flow_analysis['order_flow_toxicity'] = toxicity

        except Exception as e:
            self.logger.error(f"订单流分析错误: {e}")

        return flow_analysis

    def identify_stop_hunting_zones(self, order_book, ls_ratio, recent_trades):
        """识别止损猎杀区域"""

        zones = []

        if not order_book or not order_book.get('bid_prices') or not order_book.get('ask_prices'):
            return zones

        try:
            current_price = (order_book['bid_prices'][0] + order_book['ask_prices'][0]) / 2

            # 基于多空比推测止损位置
            if ls_ratio:
                global_ratio = ls_ratio.get('global', {}).get('ratio', 1.0)

                if global_ratio > 1.5:  # 多头过多
                    # 多头止损可能在下方2-3%
                    long_stop_zone = {
                        'type': 'LONG_STOPS',
                        'price_level': current_price * 0.97,
                        'strength': global_ratio,
                        'hunt_probability': min(0.9, global_ratio / 2)
                    }
                    zones.append(long_stop_zone)

                elif global_ratio < 0.7:  # 空头过多
                    # 空头止损可能在上方2-3%
                    short_stop_zone = {
                        'type': 'SHORT_STOPS',
                        'price_level': current_price * 1.03,
                        'strength': 1 / global_ratio,
                        'hunt_probability': min(0.9, 1 / global_ratio / 2)
                    }
                    zones.append(short_stop_zone)

            # 基于订单簿识别流动性空洞
            self.identify_liquidity_voids(order_book, zones, current_price)

        except Exception as e:
            self.logger.error(f"止损区域识别错误: {e}")

        return zones

    def identify_liquidity_voids(self, order_book, zones, current_price):
        """识别流动性空洞"""

        # 检查买卖盘的断层
        if order_book.get('bid_prices') and len(order_book['bid_prices']) >= 10:
            for i in range(1, 10):
                price_gap = order_book['bid_prices'][i - 1] - order_book['bid_prices'][i]
                normal_gap = current_price * 0.0001  # 0.01%的正常价差

                if price_gap > normal_gap * 5:  # 5倍正常价差
                    zones.append({
                        'type': 'LIQUIDITY_VOID',
                        'price_level': (order_book['bid_prices'][i - 1] + order_book['bid_prices'][i]) / 2,
                        'gap_size': price_gap,
                        'side': 'BID'
                    })

    def analyze_order_flow_toxicity(self, order_book, recent_trades):
        """分析订单流毒性"""

        toxicity = {
            'level': 'LOW',
            'score': 0.0,
            'indicators': []
        }

        try:
            # 1. 计算订单簿不平衡
            if order_book and order_book.get('bid_sizes') and order_book.get('ask_sizes'):
                bid_total = sum(order_book['bid_sizes'][:10])
                ask_total = sum(order_book['ask_sizes'][:10])

                if bid_total + ask_total > 0:
                    imbalance = abs(bid_total - ask_total) / (bid_total + ask_total)
                    if imbalance > 0.7:
                        toxicity['score'] += 0.3
                        toxicity['indicators'].append('订单簿严重不平衡')

            # 2. 分析大单比例
            if recent_trades:
                sizes = [float(t.get('qty', 0)) for t in recent_trades]
                if sizes:
                    avg_size = np.mean(sizes)
                    large_trades = sum(1 for s in sizes if s > avg_size * 3)
                    large_ratio = large_trades / len(sizes)

                    if large_ratio > 0.3:
                        toxicity['score'] += 0.3
                        toxicity['indicators'].append('大单交易频繁')

            # 3. 计算价格影响
            if recent_trades and len(recent_trades) >= 10:
                prices = [float(t.get('price', 0)) for t in recent_trades[-10:]]
                if prices:
                    price_volatility = np.std(prices) / np.mean(prices)
                    if price_volatility > 0.001:
                        toxicity['score'] += 0.2
                        toxicity['indicators'].append('价格波动剧烈')

            # 设置毒性级别
            if toxicity['score'] >= 0.7:
                toxicity['level'] = 'HIGH'
            elif toxicity['score'] >= 0.4:
                toxicity['level'] = 'MEDIUM'
            else:
                toxicity['level'] = 'LOW'

        except Exception as e:
            self.logger.error(f"订单流毒性分析错误: {e}")

        return toxicity