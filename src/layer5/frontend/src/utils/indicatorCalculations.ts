/**
 * Client-side indicator calculation functions
 * Pure functions with no external dependencies
 */

import type { OHLCData, IndicatorResult } from '@/types';

// ============================================================================
// Moving Averages
// ============================================================================

/**
 * Calculate Simple Moving Average (SMA)
 */
export function calculateSMA(
  data: OHLCData[],
  period: number,
  field: 'open' | 'high' | 'low' | 'close' = 'close'
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'sma', values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'sma', values: [], error: 'Invalid period' };
  }

  const values: (number | null)[] = [];
  let sum = 0;

  for (let i = 0; i < data.length; i++) {
    sum += data[i][field];
    
    if (i < period - 1) {
      values.push(null);
    } else {
      if (i >= period) {
        sum -= data[i - period][field];
      }
      values.push(sum / period);
    }
  }

  return {
    indicator: 'sma',
    name: `SMA(${period})`,
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

/**
 * Calculate Exponential Moving Average (EMA)
 */
export function calculateEMA(
  data: OHLCData[],
  period: number,
  field: 'open' | 'high' | 'low' | 'close' = 'close'
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'ema', values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'ema', values: [], error: 'Invalid period' };
  }

  const multiplier = 2 / (period + 1);
  const values: (number | null)[] = [];
  let ema: number | null = null;

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      values.push(null);
    } else if (i === period - 1) {
      // First EMA is SMA
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[j][field];
      }
      ema = sum / period;
      values.push(ema);
    } else {
      ema = (data[i][field] - ema!) * multiplier + ema!;
      values.push(ema);
    }
  }

  return {
    indicator: 'ema',
    name: `EMA(${period})`,
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

/**
 * Calculate Weighted Moving Average (WMA)
 */
export function calculateWMA(
  data: OHLCData[],
  period: number,
  field: 'open' | 'high' | 'low' | 'close' = 'close'
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'wma', values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'wma', values: [], error: 'Invalid period' };
  }

  const values: (number | null)[] = [];
  const denominator = (period * (period + 1)) / 2;

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      values.push(null);
    } else {
      let weightedSum = 0;
      for (let j = 0; j < period; j++) {
        weightedSum += data[i - j][field] * (period - j);
      }
      values.push(weightedSum / denominator);
    }
  }

  return {
    indicator: 'wma',
    name: `WMA(${period})`,
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

// ============================================================================
// Momentum Indicators
// ============================================================================

/**
 * Calculate Relative Strength Index (RSI)
 */
export function calculateRSI(
  data: OHLCData[],
  period: number = 14,
  overbought: number = 70,
  oversold: number = 30
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'rsi', values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'rsi', values: [], error: 'Invalid period' };
  }

  const values: (number | null)[] = [];
  let avgGain = 0;
  let avgLoss = 0;

  // Calculate price changes
  const changes: number[] = [];
  for (let i = 1; i < data.length; i++) {
    changes.push(data[i].close - data[i - 1].close);
  }

  // Initial averages
  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) avgGain += changes[i];
    else avgLoss += Math.abs(changes[i]);
  }
  avgGain /= period;
  avgLoss /= period;

  // First RSI value
  let rs = avgGain / avgLoss;
  let rsi = 100 - (100 / (1 + rs));

  // Pad with nulls for the first period
  for (let i = 0; i <= period; i++) {
    values.push(null);
  }
  values.push(rsi);

  // Calculate remaining RSI values using smoothing
  for (let i = period + 1; i < changes.length; i++) {
    const gain = changes[i] > 0 ? changes[i] : 0;
    const loss = changes[i] < 0 ? Math.abs(changes[i]) : 0;

    avgGain = ((avgGain * (period - 1)) + gain) / period;
    avgLoss = ((avgLoss * (period - 1)) + loss) / period;

    rs = avgGain / avgLoss;
    rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + rs));
    values.push(rsi);
  }

  return {
    indicator: 'rsi',
    name: `RSI(${period})`,
    timestamps: data.map(d => d.timestamp),
    values,
    overbought,
    oversold,
  };
}

/**
 * Calculate Stochastic Oscillator
 */
export function calculateStochastic(
  data: OHLCData[],
  kPeriod: number = 14,
  dPeriod: number = 3
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'stochastic', k: [], d: [], values: [], error: 'No data provided' };
  }
  if (kPeriod <= 0 || kPeriod > data.length) {
    return { indicator: 'stochastic', k: [], d: [], values: [], error: 'Invalid kPeriod' };
  }

  const kValues: (number | null)[] = [];
  const dValues: (number | null)[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i < kPeriod - 1) {
      kValues.push(null);
      dValues.push(null);
      continue;
    }

    let lowestLow = data[i].low;
    let highestHigh = data[i].high;

    for (let j = 1; j < kPeriod; j++) {
      lowestLow = Math.min(lowestLow, data[i - j].low);
      highestHigh = Math.max(highestHigh, data[i - j].high);
    }

    const range = highestHigh - lowestLow;
    const k = range === 0 ? 50 : ((data[i].close - lowestLow) / range) * 100;
    kValues.push(k);

    // Calculate %D (SMA of %K)
    if (i < kPeriod + dPeriod - 2) {
      dValues.push(null);
    } else {
      let dSum = 0;
      for (let j = 0; j < dPeriod; j++) {
        dSum += kValues[i - j]!;
      }
      dValues.push(dSum / dPeriod);
    }
  }

  return {
    indicator: 'stochastic',
    name: `Stochastic(${kPeriod},${dPeriod})`,
    timestamps: data.map(d => d.timestamp),
    values: kValues,
    k: kValues,
    d: dValues,
    overbought: 80,
    oversold: 20,
  };
}

// ============================================================================
// Trend Indicators
// ============================================================================

/**
 * Calculate MACD (Moving Average Convergence Divergence)
 */
export function calculateMACD(
  data: OHLCData[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'macd', values: [], signal: [], histogram: [], error: 'No data provided' };
  }
  if (slowPeriod <= fastPeriod) {
    return { indicator: 'macd', values: [], signal: [], histogram: [], error: 'slowPeriod must be > fastPeriod' };
  }

  // Calculate EMAs
  const fastEMA = calculateEMA(data, fastPeriod).values;
  const slowEMA = calculateEMA(data, slowPeriod).values;

  // Calculate MACD line
  const macdLine: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (fastEMA[i] === null || slowEMA[i] === null) {
      macdLine.push(null);
    } else {
      macdLine.push(fastEMA[i]! - slowEMA[i]!);
    }
  }

  // Calculate Signal line (EMA of MACD)
  const validStart = macdLine.findIndex(v => v !== null);
  const signalLine: (number | null)[] = new Array(data.length).fill(null);
  
  if (validStart >= 0) {
    const multiplier = 2 / (signalPeriod + 1);
    let signalEMA: number | null = null;
    let count = 0;

    for (let i = validStart; i < data.length; i++) {
      if (macdLine[i] !== null) {
        if (count < signalPeriod - 1) {
          count++;
        } else if (count === signalPeriod - 1) {
          // Calculate initial SMA
          let sum = 0;
          for (let j = 0; j < signalPeriod; j++) {
            sum += macdLine[i - j]!;
          }
          signalEMA = sum / signalPeriod;
          signalLine[i] = signalEMA;
          count++;
        } else {
          signalEMA = (macdLine[i]! - signalEMA!) * multiplier + signalEMA!;
          signalLine[i] = signalEMA;
        }
      }
    }
  }

  // Calculate Histogram
  const histogram: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (macdLine[i] === null || signalLine[i] === null) {
      histogram.push(null);
    } else {
      histogram.push(macdLine[i]! - signalLine[i]!);
    }
  }

  return {
    indicator: 'macd',
    name: `MACD(${fastPeriod},${slowPeriod},${signalPeriod})`,
    timestamps: data.map(d => d.timestamp),
    values: macdLine,
    signal: signalLine,
    histogram,
  };
}

/**
 * Calculate Average Directional Index (ADX)
 */
export function calculateADX(
  data: OHLCData[],
  period: number = 14
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'adx', values: [], plus_di: [], minus_di: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'adx', values: [], plus_di: [], minus_di: [], error: 'Invalid period' };
  }

  const trValues: number[] = [];
  const plusDM: number[] = [];
  const minusDM: number[] = [];

  // Calculate True Range and Directional Movement
  for (let i = 1; i < data.length; i++) {
    const high = data[i].high;
    const low = data[i].low;
    const prevHigh = data[i - 1].high;
    const prevLow = data[i - 1].low;
    const prevClose = data[i - 1].close;

    // True Range
    const tr1 = high - low;
    const tr2 = Math.abs(high - prevClose);
    const tr3 = Math.abs(low - prevClose);
    trValues.push(Math.max(tr1, tr2, tr3));

    // Directional Movement
    const upMove = high - prevHigh;
    const downMove = prevLow - low;

    plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }

  // Smooth the TR and DM values
  const smoothedTR: number[] = [];
  const smoothedPlusDM: number[] = [];
  const smoothedMinusDM: number[] = [];

  // Initial smoothed values
  let sumTR = 0;
  let sumPlusDM = 0;
  let sumMinusDM = 0;

  for (let i = 0; i < period; i++) {
    sumTR += trValues[i];
    sumPlusDM += plusDM[i];
    sumMinusDM += minusDM[i];
  }

  smoothedTR.push(sumTR);
  smoothedPlusDM.push(sumPlusDM);
  smoothedMinusDM.push(sumMinusDM);

  // Continue smoothing
  for (let i = period; i < trValues.length; i++) {
    smoothedTR.push(smoothedTR[smoothedTR.length - 1] - (smoothedTR[smoothedTR.length - 1] / period) + trValues[i]);
    smoothedPlusDM.push(smoothedPlusDM[smoothedPlusDM.length - 1] - (smoothedPlusDM[smoothedPlusDM.length - 1] / period) + plusDM[i]);
    smoothedMinusDM.push(smoothedMinusDM[smoothedMinusDM.length - 1] - (smoothedMinusDM[smoothedMinusDM.length - 1] / period) + minusDM[i]);
  }

  // Calculate +DI and -DI
  const plusDI: (number | null)[] = [null];
  const minusDI: (number | null)[] = [null];
  const dxValues: (number | null)[] = [null];

  for (let i = 0; i < smoothedTR.length; i++) {
    plusDI.push(smoothedTR[i] === 0 ? 0 : (smoothedPlusDM[i] / smoothedTR[i]) * 100);
    minusDI.push(smoothedTR[i] === 0 ? 0 : (smoothedMinusDM[i] / smoothedTR[i]) * 100);

    const diDiff = Math.abs(plusDI[plusDI.length - 1]! - minusDI[minusDI.length - 1]!);
    const diSum = plusDI[plusDI.length - 1]! + minusDI[minusDI.length - 1]!;
    dxValues.push(diSum === 0 ? 0 : (diDiff / diSum) * 100);
  }

  // Calculate ADX (smoothed DX)
  const adxValues: (number | null)[] = new Array(data.length).fill(null);

  // Initial ADX
  let adxSum = 0;
  for (let i = 1; i <= period; i++) {
    adxSum += dxValues[i] || 0;
  }
  adxValues[period * 2 - 1] = adxSum / period;

  // Continue ADX calculation
  for (let i = period * 2; i < data.length; i++) {
    const prevADX = adxValues[i - 1]!;
    adxValues[i] = ((prevADX * (period - 1)) + (dxValues[i - period] || 0)) / period;
  }

  return {
    indicator: 'adx',
    name: `ADX(${period})`,
    timestamps: data.map(d => d.timestamp),
    values: adxValues,
    plus_di: plusDI,
    minus_di: minusDI,
  };
}

// ============================================================================
// Volatility Indicators
// ============================================================================

/**
 * Calculate Bollinger Bands
 */
export function calculateBollingerBands(
  data: OHLCData[],
  period: number = 20,
  stdDev: number = 2
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'bollinger', upper: [], middle: [], lower: [], values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'bollinger', upper: [], middle: [], lower: [], values: [], error: 'Invalid period' };
  }

  const middle: (number | null)[] = [];
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      middle.push(null);
      upper.push(null);
      lower.push(null);
    } else {
      // Calculate SMA
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j].close;
      }
      const sma = sum / period;

      // Calculate Standard Deviation
      let sumSquaredDiff = 0;
      for (let j = 0; j < period; j++) {
        sumSquaredDiff += Math.pow(data[i - j].close - sma, 2);
      }
      const standardDeviation = Math.sqrt(sumSquaredDiff / period);

      middle.push(sma);
      upper.push(sma + (stdDev * standardDeviation));
      lower.push(sma - (stdDev * standardDeviation));
    }
  }

  return {
    indicator: 'bollinger',
    name: `Bollinger Bands(${period},${stdDev})`,
    timestamps: data.map(d => d.timestamp),
    values: middle,
    middle,
    upper,
    lower,
  };
}

/**
 * Calculate Average True Range (ATR)
 */
export function calculateATR(
  data: OHLCData[],
  period: number = 14
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'atr', values: [], error: 'No data provided' };
  }
  if (period <= 0 || period > data.length) {
    return { indicator: 'atr', values: [], error: 'Invalid period' };
  }

  const values: (number | null)[] = [];
  const trValues: number[] = [];

  // Calculate True Range
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      trValues.push(data[i].high - data[i].low);
    } else {
      const tr1 = data[i].high - data[i].low;
      const tr2 = Math.abs(data[i].high - data[i - 1].close);
      const tr3 = Math.abs(data[i].low - data[i - 1].close);
      trValues.push(Math.max(tr1, tr2, tr3));
    }
  }

  // Calculate ATR using Wilder's smoothing
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      values.push(null);
    } else if (i === period - 1) {
      // First ATR is simple average
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += trValues[j];
      }
      values.push(sum / period);
    } else {
      // Wilder's smoothing
      const prevATR = values[i - 1]!;
      values.push(((prevATR * (period - 1)) + trValues[i]) / period);
    }
  }

  return {
    indicator: 'atr',
    name: `ATR(${period})`,
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

// ============================================================================
// Volume Indicators
// ============================================================================

/**
 * Calculate Volume Weighted Average Price (VWAP)
 */
export function calculateVWAP(
  data: OHLCData[],
  anchor: 'session' | 'day' | 'week' | 'month' = 'day'
): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'vwap', values: [], error: 'No data provided' };
  }

  const values: (number | null)[] = [];
  let cumulativeTPV = 0; // Typical Price * Volume
  let cumulativeVolume = 0;
  let currentAnchor: string | null = null;

  for (let i = 0; i < data.length; i++) {
    const typicalPrice = (data[i].high + data[i].low + data[i].close) / 3;
    const volume = data[i].volume;

    // Determine anchor period
    let newAnchor: string;
    const date = new Date(data[i].timestamp);
    
    switch (anchor) {
      case 'session':
        newAnchor = data[i].timestamp.split('T')[0];
        break;
      case 'day':
        newAnchor = data[i].timestamp.split('T')[0];
        break;
      case 'week':
        const weekStart = new Date(date);
        weekStart.setDate(date.getDate() - date.getDay());
        newAnchor = weekStart.toISOString().split('T')[0];
        break;
      case 'month':
        newAnchor = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        break;
      default:
        newAnchor = data[i].timestamp.split('T')[0];
    }

    // Reset on new anchor period
    if (newAnchor !== currentAnchor) {
      currentAnchor = newAnchor;
      cumulativeTPV = 0;
      cumulativeVolume = 0;
    }

    cumulativeTPV += typicalPrice * volume;
    cumulativeVolume += volume;

    values.push(cumulativeVolume === 0 ? null : cumulativeTPV / cumulativeVolume);
  }

  return {
    indicator: 'vwap',
    name: `VWAP(${anchor})`,
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

/**
 * Calculate On-Balance Volume (OBV)
 */
export function calculateOBV(data: OHLCData[]): IndicatorResult {
  if (!data || data.length === 0) {
    return { indicator: 'obv', values: [], error: 'No data provided' };
  }

  const values: (number | null)[] = [];
  let obv = 0;

  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      values.push(0);
    } else {
      if (data[i].close > data[i - 1].close) {
        obv += data[i].volume;
      } else if (data[i].close < data[i - 1].close) {
        obv -= data[i].volume;
      }
      values.push(obv);
    }
  }

  return {
    indicator: 'obv',
    name: 'OBV',
    timestamps: data.map(d => d.timestamp),
    values,
  };
}

// ============================================================================
// Main Calculation Dispatcher
// ============================================================================

export interface CalculationRequest {
  indicator: string;
  data: OHLCData[];
  params: Record<string, number | string>;
}

export interface BatchCalculationRequest {
  id: string;
  calculations: CalculationRequest[];
}

/**
 * Calculate a single indicator based on type
 */
export function calculateIndicator(
  indicator: string,
  data: OHLCData[],
  params: Record<string, number | string> = {}
): IndicatorResult {
  switch (indicator.toLowerCase()) {
    case 'sma':
      return calculateSMA(data, (params.period as number) || 20);
    
    case 'ema':
      return calculateEMA(data, (params.period as number) || 20);
    
    case 'wma':
      return calculateWMA(data, (params.period as number) || 20);
    
    case 'rsi':
      return calculateRSI(
        data,
        (params.period as number) || 14,
        (params.overbought as number) || 70,
        (params.oversold as number) || 30
      );
    
    case 'macd':
      return calculateMACD(
        data,
        (params.fast as number) || 12,
        (params.slow as number) || 26,
        (params.signal as number) || 9
      );
    
    case 'bollinger':
    case 'bollingerbands':
      return calculateBollingerBands(
        data,
        (params.period as number) || 20,
        (params.stddev as number) || 2
      );
    
    case 'atr':
      return calculateATR(data, (params.period as number) || 14);
    
    case 'stochastic':
      return calculateStochastic(
        data,
        (params.kperiod as number) || 14,
        (params.dperiod as number) || 3
      );
    
    case 'adx':
      return calculateADX(data, (params.period as number) || 14);
    
    case 'vwap':
      return calculateVWAP(data, (params.anchor as 'session' | 'day' | 'week' | 'month') || 'day');
    
    case 'obv':
      return calculateOBV(data);
    
    default:
      return {
        indicator,
        values: [],
        error: `Unknown indicator: ${indicator}`,
      };
  }
}

/**
 * Calculate multiple indicators in batch
 */
export function calculateIndicatorsBatch(
  calculations: CalculationRequest[]
): IndicatorResult[] {
  return calculations.map(calc =>
    calculateIndicator(calc.indicator, calc.data, calc.params)
  );
}
