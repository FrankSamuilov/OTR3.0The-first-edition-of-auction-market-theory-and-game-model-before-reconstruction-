"""
SMC (Smart Money Concepts) 模块
包含FVG、订单块、流动性等概念的实现
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import logging
from datetime import datetime

from logger_utils import Colors, print_colored


class SMCAnalyzer:
    """SMC分析器基类"""

    def __init__(self):
        self.logger = logging.getLogger('SMC')


def detect_fvg(df: pd.DataFrame, min_gap_pct: float = 0.001) -> List[Dict[str, Any]]:
    """
    检测FVG（Fair Value Gap/公允价值缺口）

    参数:
        df: 包含OHLC数据的DataFrame
        min_gap_pct: 最小缺口百分比（默认0.1%）

    返回:
        FVG列表，每个包含方向、价格范围等信息
    """
    fvg_list = []

    if df is None or len(df) < 3:
        return fvg_list

    try:
        for i in range(1, len(df) - 1):
            # 获取三根K线
            prev_candle = df.iloc[i - 1]
            curr_candle = df.iloc[i]
            next_candle = df.iloc[i + 1]

            # 检测看涨FVG（Bullish FVG）
            # 条件：第三根K线的低点 > 第一根K线的高点
            if next_candle['low'] > prev_candle['high']:
                gap_size = next_candle['low'] - prev_candle['high']
                gap_pct = gap_size / curr_candle['close']

                if gap_pct >= min_gap_pct:
                    fvg = {
                        'type': 'FVG',
                        'direction': 'UP',
                        'index': i,
                        'timestamp': curr_candle.name if hasattr(curr_candle, 'name') else i,
                        'upper_boundary': next_candle['low'],
                        'lower_boundary': prev_candle['high'],
                        'gap_size': gap_size,
                        'gap_percentage': gap_pct * 100,
                        'is_filled': False,
                        'fill_percentage': 0,
                        'strength': calculate_fvg_strength(df, i, 'UP', gap_pct)
                    }
                    fvg_list.append(fvg)

            # 检测看跌FVG（Bearish FVG）
            # 条件：第三根K线的高点 < 第一根K线的低点
            elif next_candle['high'] < prev_candle['low']:
                gap_size = prev_candle['low'] - next_candle['high']
                gap_pct = gap_size / curr_candle['close']

                if gap_pct >= min_gap_pct:
                    fvg = {
                        'type': 'FVG',
                        'direction': 'DOWN',
                        'index': i,
                        'timestamp': curr_candle.name if hasattr(curr_candle, 'name') else i,
                        'upper_boundary': prev_candle['low'],
                        'lower_boundary': next_candle['high'],
                        'gap_size': gap_size,
                        'gap_percentage': gap_pct * 100,
                        'is_filled': False,
                        'fill_percentage': 0,
                        'strength': calculate_fvg_strength(df, i, 'DOWN', gap_pct)
                    }
                    fvg_list.append(fvg)

        # 检查FVG是否被填补
        for fvg in fvg_list:
            check_fvg_fill_status(df, fvg)

        # 按强度排序
        fvg_list.sort(key=lambda x: x['strength'], reverse=True)

    except Exception as e:
        logging.error(f"FVG检测错误: {e}")

    return fvg_list


def calculate_fvg_strength(df: pd.DataFrame, index: int, direction: str, gap_pct: float) -> float:
    """
    计算FVG的强度

    考虑因素：
    1. 缺口大小
    2. 成交量
    3. 趋势方向
    4. 市场动量
    """
    strength = 0.0

    try:
        # 1. 缺口大小得分（0-3分）
        if gap_pct > 0.005:  # 0.5%以上
            strength += 3
        elif gap_pct > 0.003:  # 0.3%以上
            strength += 2
        else:
            strength += 1

        # 2. 成交量得分（0-2分）
        if index > 20:
            recent_volume = df['volume'].iloc[index - 5:index].mean()
            avg_volume = df['volume'].iloc[index - 20:index - 5].mean()

            if recent_volume > avg_volume * 1.5:
                strength += 2
            elif recent_volume > avg_volume * 1.2:
                strength += 1

        # 3. 趋势一致性得分（0-3分）
        if index > 50:
            # 使用EMA判断趋势
            ema20 = df['close'].iloc[index - 20:index].ewm(span=20).mean().iloc[-1]
            ema50 = df['close'].iloc[index - 50:index].ewm(span=50).mean().iloc[-1]
            current_price = df['close'].iloc[index]

            if direction == 'UP':
                if current_price > ema20 > ema50:
                    strength += 3  # 强上升趋势
                elif current_price > ema20:
                    strength += 2  # 中等上升趋势
                elif current_price > ema50:
                    strength += 1  # 弱上升趋势
            else:  # DOWN
                if current_price < ema20 < ema50:
                    strength += 3  # 强下降趋势
                elif current_price < ema20:
                    strength += 2  # 中等下降趋势
                elif current_price < ema50:
                    strength += 1  # 弱下降趋势

        # 4. 动量得分（0-2分）
        if 'RSI' in df.columns and not pd.isna(df['RSI'].iloc[index]):
            rsi = df['RSI'].iloc[index]
            if direction == 'UP' and 40 < rsi < 70:
                strength += 2  # 健康的上涨动量
            elif direction == 'DOWN' and 30 < rsi < 60:
                strength += 2  # 健康的下跌动量
            elif (direction == 'UP' and rsi > 70) or (direction == 'DOWN' and rsi < 30):
                strength += 0.5  # 过度延伸，降低得分

    except Exception as e:
        logging.error(f"计算FVG强度错误: {e}")

    # 归一化到0-1范围
    return min(strength / 10.0, 1.0)


def check_fvg_fill_status(df: pd.DataFrame, fvg: Dict[str, Any]) -> None:
    """
    检查FVG是否被填补
    """
    try:
        fvg_index = fvg['index']

        # 检查FVG之后的K线
        for i in range(fvg_index + 1, len(df)):
            candle = df.iloc[i]

            if fvg['direction'] == 'UP':
                # 看涨FVG，检查是否有K线回到缺口区域
                if candle['low'] <= fvg['upper_boundary']:
                    # 计算填补百分比
                    if candle['low'] <= fvg['lower_boundary']:
                        fvg['fill_percentage'] = 100
                        fvg['is_filled'] = True
                    else:
                        fill_depth = fvg['upper_boundary'] - candle['low']
                        fvg['fill_percentage'] = (fill_depth / fvg['gap_size']) * 100
                        fvg['is_filled'] = fvg['fill_percentage'] >= 50  # 填补50%以上认为已填补
                    break

            else:  # DOWN
                # 看跌FVG，检查是否有K线回到缺口区域
                if candle['high'] >= fvg['lower_boundary']:
                    # 计算填补百分比
                    if candle['high'] >= fvg['upper_boundary']:
                        fvg['fill_percentage'] = 100
                        fvg['is_filled'] = True
                    else:
                        fill_depth = candle['high'] - fvg['lower_boundary']
                        fvg['fill_percentage'] = (fill_depth / fvg['gap_size']) * 100
                        fvg['is_filled'] = fvg['fill_percentage'] >= 50
                    break

    except Exception as e:
        logging.error(f"检查FVG填补状态错误: {e}")


def detect_order_blocks(df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, Any]]:
    """
    检测订单块（Order Blocks）

    订单块是机构进行大量买卖的区域，通常在趋势反转前形成
    """
    order_blocks = []

    if df is None or len(df) < lookback:
        return order_blocks

    try:
        # 计算必要的指标
        if 'ATR' not in df.columns:
            df['ATR'] = calculate_atr(df)

        for i in range(lookback, len(df) - 1):
            # 获取当前和之前的K线
            curr_candle = df.iloc[i]
            prev_candle = df.iloc[i - 1]
            next_candle = df.iloc[i + 1]

            # 检测看涨订单块（Bullish Order Block）
            # 条件：下跌后的最后一根阴线，随后出现强劲上涨
            if (prev_candle['close'] < prev_candle['open'] and  # 前一根是阴线
                    curr_candle['close'] < curr_candle['open'] and  # 当前是阴线
                    next_candle['close'] > next_candle['open'] and  # 下一根是阳线
                    next_candle['close'] > curr_candle['high']):  # 下一根突破当前高点

                # 检查成交量
                volume_spike = curr_candle['volume'] > df['volume'].iloc[i - 10:i].mean() * 1.5

                if volume_spike:
                    order_block = {
                        'type': 'ORDER_BLOCK',
                        'direction': 'BULLISH',
                        'index': i,
                        'timestamp': curr_candle.name if hasattr(curr_candle, 'name') else i,
                        'upper_boundary': curr_candle['high'],
                        'lower_boundary': curr_candle['low'],
                        'price': curr_candle['close'],
                        'volume': curr_candle['volume'],
                        'strength': calculate_order_block_strength(df, i, 'BULLISH')
                    }
                    order_blocks.append(order_block)

            # 检测看跌订单块（Bearish Order Block）
            # 条件：上涨后的最后一根阳线，随后出现强劲下跌
            elif (prev_candle['close'] > prev_candle['open'] and  # 前一根是阳线
                  curr_candle['close'] > curr_candle['open'] and  # 当前是阳线
                  next_candle['close'] < next_candle['open'] and  # 下一根是阴线
                  next_candle['close'] < curr_candle['low']):  # 下一根跌破当前低点

                # 检查成交量
                volume_spike = curr_candle['volume'] > df['volume'].iloc[i - 10:i].mean() * 1.5

                if volume_spike:
                    order_block = {
                        'type': 'ORDER_BLOCK',
                        'direction': 'BEARISH',
                        'index': i,
                        'timestamp': curr_candle.name if hasattr(curr_candle, 'name') else i,
                        'upper_boundary': curr_candle['high'],
                        'lower_boundary': curr_candle['low'],
                        'price': curr_candle['close'],
                        'volume': curr_candle['volume'],
                        'strength': calculate_order_block_strength(df, i, 'BEARISH')
                    }
                    order_blocks.append(order_block)

        # 过滤出最强的订单块
        order_blocks.sort(key=lambda x: x['strength'], reverse=True)

        # 只保留最近和最强的订单块
        filtered_blocks = []
        for block in order_blocks[:10]:  # 最多保留10个
            # 检查是否仍然有效（未被突破）
            if is_order_block_valid(df, block):
                filtered_blocks.append(block)

        return filtered_blocks

    except Exception as e:
        logging.error(f"订单块检测错误: {e}")
        return []


def calculate_order_block_strength(df: pd.DataFrame, index: int, direction: str) -> float:
    """计算订单块的强度"""
    strength = 0.0

    try:
        # 1. 成交量强度（0-3分）
        if index > 20:
            volume = df['volume'].iloc[index]
            avg_volume = df['volume'].iloc[index - 20:index].mean()

            volume_ratio = volume / avg_volume if avg_volume > 0 else 1

            if volume_ratio > 3:
                strength += 3
            elif volume_ratio > 2:
                strength += 2
            elif volume_ratio > 1.5:
                strength += 1

        # 2. 价格反转强度（0-3分）
        if index < len(df) - 3:
            # 检查订单块后的价格变动
            price_before = df['close'].iloc[index]
            price_after = df['close'].iloc[index + 3]

            price_change = abs(price_after - price_before) / price_before

            if price_change > 0.02:  # 2%以上的变动
                strength += 3
            elif price_change > 0.01:  # 1%以上的变动
                strength += 2
            elif price_change > 0.005:  # 0.5%以上的变动
                strength += 1

        # 3. K线实体大小（0-2分）
        candle_body = abs(df['close'].iloc[index] - df['open'].iloc[index])
        candle_range = df['high'].iloc[index] - df['low'].iloc[index]

        if candle_range > 0:
            body_ratio = candle_body / candle_range
            if body_ratio > 0.7:  # 实体占比70%以上
                strength += 2
            elif body_ratio > 0.5:  # 实体占比50%以上
                strength += 1

        # 4. 趋势确认（0-2分）
        if index > 50:
            # 使用移动平均线确认趋势
            ma20 = df['close'].iloc[index - 20:index].mean()
            ma50 = df['close'].iloc[index - 50:index].mean()
            current_price = df['close'].iloc[index]

            if direction == 'BULLISH' and current_price < ma20 < ma50:
                strength += 2  # 在下降趋势中的看涨订单块更有价值
            elif direction == 'BEARISH' and current_price > ma20 > ma50:
                strength += 2  # 在上升趋势中的看跌订单块更有价值

    except Exception as e:
        logging.error(f"计算订单块强度错误: {e}")

    # 归一化到0-1范围
    return min(strength / 10.0, 1.0)


def is_order_block_valid(df: pd.DataFrame, order_block: Dict[str, Any]) -> bool:
    """检查订单块是否仍然有效"""
    try:
        block_index = order_block['index']

        # 检查价格是否已经突破订单块
        for i in range(block_index + 1, len(df)):
            if order_block['direction'] == 'BULLISH':
                # 看涨订单块，如果价格跌破下边界则失效
                if df['close'].iloc[i] < order_block['lower_boundary']:
                    return False
            else:  # BEARISH
                # 看跌订单块，如果价格突破上边界则失效
                if df['close'].iloc[i] > order_block['upper_boundary']:
                    return False

        return True

    except Exception as e:
        logging.error(f"检查订单块有效性错误: {e}")
        return False


def detect_liquidity_pools(df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
    """
    检测流动性池（Liquidity Pools）

    流动性池通常在以下位置：
    1. 前期高点/低点
    2. 整数关口
    3. 均线聚集区
    """
    liquidity_pools = []

    if df is None or len(df) < lookback:
        return liquidity_pools

    try:
        current_price = df['close'].iloc[-1]

        # 1. 检测摆动高低点
        swing_highs, swing_lows = detect_swing_points(df, lookback)

        # 2. 添加摆动高点作为卖方流动性
        for high in swing_highs:
            if high['price'] > current_price:  # 只考虑当前价格上方的
                pool = {
                    'type': 'LIQUIDITY_POOL',
                    'side': 'SELL',
                    'price': high['price'],
                    'strength': high['strength'],
                    'source': 'SWING_HIGH',
                    'index': high['index']
                }
                liquidity_pools.append(pool)

        # 3. 添加摆动低点作为买方流动性
        for low in swing_lows:
            if low['price'] < current_price:  # 只考虑当前价格下方的
                pool = {
                    'type': 'LIQUIDITY_POOL',
                    'side': 'BUY',
                    'price': low['price'],
                    'strength': low['strength'],
                    'source': 'SWING_LOW',
                    'index': low['index']
                }
                liquidity_pools.append(pool)

        # 4. 检测整数关口
        round_numbers = detect_round_numbers(current_price)
        for price in round_numbers:
            pool = {
                'type': 'LIQUIDITY_POOL',
                'side': 'BOTH',  # 整数关口双向都有流动性
                'price': price,
                'strength': 0.7,  # 整数关口通常有中等强度
                'source': 'ROUND_NUMBER'
            }
            liquidity_pools.append(pool)

        # 5. 检测均线聚集区
        if 'EMA20' in df.columns and 'EMA50' in df.columns:
            ema20 = df['EMA20'].iloc[-1]
            ema50 = df['EMA50'].iloc[-1]

            # 如果两条均线接近
            if abs(ema20 - ema50) / current_price < 0.01:  # 相差不到1%
                avg_price = (ema20 + ema50) / 2
                pool = {
                    'type': 'LIQUIDITY_POOL',
                    'side': 'BOTH',
                    'price': avg_price,
                    'strength': 0.8,
                    'source': 'EMA_CLUSTER'
                }
                liquidity_pools.append(pool)

        # 按距离当前价格排序
        liquidity_pools.sort(key=lambda x: abs(x['price'] - current_price))

        return liquidity_pools[:20]  # 返回最近的20个流动性池

    except Exception as e:
        logging.error(f"流动性池检测错误: {e}")
        return []


def detect_swing_points(df: pd.DataFrame, lookback: int) -> Tuple[List[Dict], List[Dict]]:
    """检测摆动高低点"""
    swing_highs = []
    swing_lows = []

    try:
        for i in range(lookback, len(df) - lookback):
            # 检测摆动高点
            is_swing_high = True
            for j in range(1, lookback + 1):
                if df['high'].iloc[i] <= df['high'].iloc[i - j] or df['high'].iloc[i] <= df['high'].iloc[i + j]:
                    is_swing_high = False
                    break

            if is_swing_high:
                swing_highs.append({
                    'index': i,
                    'price': df['high'].iloc[i],
                    'strength': calculate_swing_strength(df, i, 'HIGH')
                })

            # 检测摆动低点
            is_swing_low = True
            for j in range(1, lookback + 1):
                if df['low'].iloc[i] >= df['low'].iloc[i - j] or df['low'].iloc[i] >= df['low'].iloc[i + j]:
                    is_swing_low = False
                    break

            if is_swing_low:
                swing_lows.append({
                    'index': i,
                    'price': df['low'].iloc[i],
                    'strength': calculate_swing_strength(df, i, 'LOW')
                })

    except Exception as e:
        logging.error(f"检测摆动点错误: {e}")

    return swing_highs, swing_lows


def calculate_swing_strength(df: pd.DataFrame, index: int, swing_type: str) -> float:
    """计算摆动点的强度"""
    try:
        # 基于触及次数和成交量计算强度
        price = df['high'].iloc[index] if swing_type == 'HIGH' else df['low'].iloc[index]

        # 计算该价位被触及的次数
        touches = 0
        for i in range(max(0, index - 50), min(len(df), index + 50)):
            if swing_type == 'HIGH':
                if abs(df['high'].iloc[i] - price) / price < 0.001:  # 0.1%范围内
                    touches += 1
            else:
                if abs(df['low'].iloc[i] - price) / price < 0.001:
                    touches += 1

        # 成交量权重
        volume_weight = df['volume'].iloc[index] / df['volume'].iloc[index - 20:index].mean()

        # 综合强度
        strength = min(1.0, (touches / 10.0) * 0.5 + min(volume_weight / 2.0, 0.5))

        return strength

    except Exception as e:
        logging.error(f"计算摆动点强度错误: {e}")
        return 0.5


def detect_round_numbers(price: float, levels: int = 5) -> List[float]:
    """检测整数关口"""
    round_numbers = []

    # 根据价格大小确定整数间隔
    if price >= 10000:
        interval = 1000
    elif price >= 1000:
        interval = 100
    elif price >= 100:
        interval = 10
    elif price >= 10:
        interval = 1
    else:
        interval = 0.1

    # 找到最近的整数
    base = round(price / interval) * interval

    # 生成上下各levels个整数关口
    for i in range(-levels, levels + 1):
        level = base + i * interval
        if 0.9 * price <= level <= 1.1 * price:  # 只保留±10%范围内的
            round_numbers.append(level)

    return round_numbers


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算ATR（平均真实范围）"""
    high = df['high']
    low = df['low']
    close = df['close']

    # 计算真实范围
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # 计算ATR
    atr = tr.rolling(period).mean()

    return atr


def detect_imbalance_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    检测不平衡模式（SIBI/BISI）

    SIBI: Sell-side Imbalance, Buy-side Inefficiency
    BISI: Buy-side Imbalance, Sell-side Inefficiency
    """
    result = {
        'detected': False,
        'sibi': False,
        'bisi': False,
        'patterns': []
    }

    if df is None or len(df) < 3:
        return result

    try:
        for i in range(1, len(df) - 1):
            prev_candle = df.iloc[i - 1]
            curr_candle = df.iloc[i]
            next_candle = df.iloc[i + 1]

            # SIBI检测（卖方不平衡）
            if (curr_candle['close'] < curr_candle['open'] and  # 当前是阴线
                    prev_candle['low'] > next_candle['high']):  # 存在缺口

                pattern = {
                    'type': 'SIBI',
                    'index': i,
                    'upper': prev_candle['low'],
                    'lower': next_candle['high'],
                    'strength': abs(prev_candle['low'] - next_candle['high']) / curr_candle['close']
                }
                result['patterns'].append(pattern)
                result['sibi'] = True
                result['detected'] = True

            # BISI检测（买方不平衡）
            elif (curr_candle['close'] > curr_candle['open'] and  # 当前是阳线
                  prev_candle['high'] < next_candle['low']):  # 存在缺口

                pattern = {
                    'type': 'BISI',
                    'index': i,
                    'lower': prev_candle['high'],
                    'upper': next_candle['low'],
                    'strength': abs(next_candle['low'] - prev_candle['high']) / curr_candle['close']
                }
                result['patterns'].append(pattern)
                result['bisi'] = True
                result['detected'] = True

    except Exception as e:
        logging.error(f"检测不平衡模式错误: {e}")

    return result


# 为了兼容性，保留这些函数名
def detect_fvg_zones(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """别名函数，调用detect_fvg"""
    return detect_fvg(df)


def detect_order_blocks_enhanced(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """别名函数，调用detect_order_blocks"""
    return detect_order_blocks(df)