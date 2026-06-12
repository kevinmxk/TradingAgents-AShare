import { useEffect, useMemo, useRef, useState } from 'react'
import {
    BusinessDay,
    CandlestickData,
    CandlestickSeries,
    ColorType,
    IChartApi,
    ISeriesApi,
    MouseEventParams,
    createChart,
} from 'lightweight-charts'
import { Activity, CandlestickChart } from 'lucide-react'
import { api } from '@/services/api'
import type { KlineCandle } from '@/types'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useResponsive } from '@/hooks/useResponsive'

interface KlinePanelProps {
    symbol: string
    onSymbolChange?: (symbol: string) => void
}

const SYMBOL_NAME_MAP: Record<string, string> = {
    '000001.SH': '上证指数',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000688.SH': '科创50',
    '899050.BJ': '北证50',
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
    '300750.SZ': '宁德时代',
    '600406.SH': '国电南瑞',
    '510300.SH': '沪深300ETF',
}

const INDEX_PRESETS = [
    { symbol: '000001.SH', label: '上证指数' },
    { symbol: '399001.SZ', label: '深证成指' },
    { symbol: '399006.SZ', label: '创业板指' },
    { symbol: '000688.SH', label: '科创50' },
    { symbol: '899050.BJ', label: '北证50' },
] as const

function toDateText(date: Date): string {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
}

function toBusinessDay(value: string): BusinessDay | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (!m) return null
    const year = Number(m[1])
    const month = Number(m[2])
    const day = Number(m[3])
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null
    return { year, month, day }
}

function getSymbolName(symbol: string): string {
    const s = symbol.toUpperCase()
    return SYMBOL_NAME_MAP[s] || s
}

function getDisplayName(symbol: string): string {
    const s = symbol.toUpperCase()
    return SYMBOL_NAME_MAP[s] ? `${SYMBOL_NAME_MAP[s]} (${s})` : s
}

function formatNumber(value?: number | null, digits = 2): string {
    if (value == null || !Number.isFinite(value)) return '--'
    return new Intl.NumberFormat('zh-CN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    }).format(value)
}

function formatVolume(value?: number | null): string {
    if (value == null || !Number.isFinite(value)) return '--'
    if (Math.abs(value) >= 1e8) return `${formatNumber(value / 1e8, 2)}亿`
    if (Math.abs(value) >= 1e4) return `${formatNumber(value / 1e4, 2)}万`
    return formatNumber(value, 0)
}

function toChartData(candles: KlineCandle[]): CandlestickData[] {
    return candles.flatMap((c) => {
        const time = toBusinessDay((c.date || '').slice(0, 10))
        const open = Number(c.open)
        const high = Number(c.high)
        const low = Number(c.low)
        const close = Number(c.close)
        if (!time) return []
        if (![open, high, low, close].every(Number.isFinite)) return []
        return [{ time, open, high, low, close }]
    })
}

export default function KlinePanel({ symbol, onSymbolChange }: KlinePanelProps) {
    const { isMobile } = useResponsive()
    const currentAnalysisSymbol = useAnalysisStore((state) => state.currentSymbol)
    const containerRef = useRef<HTMLDivElement | null>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [isDark, setIsDark] = useState(document.documentElement.classList.contains('dark'))
    const [candles, setCandles] = useState<KlineCandle[]>([])
    const [activeCandle, setActiveCandle] = useState<KlineCandle | null>(null)
    const candlesRef = useRef<KlineCandle[]>([])

    const range = useMemo(() => {
        const end = new Date()
        const start = new Date(end.getTime() - 180 * 24 * 60 * 60 * 1000)
        return {
            start: toDateText(start),
            end: toDateText(end),
        }
    }, [])

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'))
        })
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        const container = containerRef.current
        if (!container) return undefined

        const textColor = isDark ? '#94a3b8' : '#475569'
        const gridColor = isDark ? 'rgba(51, 65, 85, 0.6)' : 'rgba(203, 213, 225, 0.6)'

        const chart = createChart(container, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor,
                attributionLogo: false,
            },
            localization: {
                locale: 'zh-CN',
                dateFormat: 'yyyy-MM-dd',
            },
            width: container.clientWidth,
            height: container.clientHeight,
            grid: {
                vertLines: { color: gridColor },
                horzLines: { color: gridColor },
            },
            rightPriceScale: {
                borderColor: isDark ? '#334155' : '#cbd5e1',
                scaleMargins: isMobile ? { top: 0.12, bottom: 0.18 } : undefined,
            },
            timeScale: {
                borderColor: isDark ? '#334155' : '#cbd5e1',
                timeVisible: true,
                rightOffset: isMobile ? 2 : 6,
                tickMarkFormatter: (time: BusinessDay | string) => {
                    if (typeof time !== 'object') return String(time)
                    const y = String(time.year)
                    const m = String(time.month).padStart(2, '0')
                    const d = String(time.day).padStart(2, '0')
                    return isMobile ? `${m}/${d}` : `${y}/${m}/${d}`
                },
            },
            crosshair: {
                vertLine: { color: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)' },
                horzLine: { color: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)' },
            },
        })

        const series = chart.addSeries(CandlestickSeries, {
            upColor: '#ef4444',
            downColor: '#22c55e',
            wickUpColor: '#ef4444',
            wickDownColor: '#22c55e',
            borderVisible: false,
        })

        chartRef.current = chart
        seriesRef.current = series
        if (candlesRef.current.length) {
            series.setData(toChartData(candlesRef.current))
            chart.timeScale().fitContent()
        }

        const handleCrosshairMove = (param: MouseEventParams) => {
            if (!param.time || !seriesRef.current) {
                setActiveCandle(candlesRef.current.length ? candlesRef.current[candlesRef.current.length - 1] : null)
                return
            }
            const pointData = param.seriesData.get(seriesRef.current) as CandlestickData | undefined
            if (!pointData) return
            const time = typeof pointData.time === 'object'
                ? `${pointData.time.year}-${String(pointData.time.month).padStart(2, '0')}-${String(pointData.time.day).padStart(2, '0')}`
                : String(pointData.time)
            const matched = candlesRef.current.find(c => c.date === time)
            if (matched) setActiveCandle(matched)
        }
        chart.subscribeCrosshairMove(handleCrosshairMove)

        const handleDblClick = () => {
            chartRef.current?.timeScale().fitContent()
        }
        container.addEventListener('dblclick', handleDblClick)

        const onResize = () => {
            if (!containerRef.current || !chartRef.current) return
            chartRef.current.applyOptions({
                width: containerRef.current.clientWidth,
                height: containerRef.current.clientHeight,
            })
        }

        window.addEventListener('resize', onResize)
        return () => {
            window.removeEventListener('resize', onResize)
            container.removeEventListener('dblclick', handleDblClick)
            chart.unsubscribeCrosshairMove(handleCrosshairMove)
            chartRef.current?.remove()
            chartRef.current = null
            seriesRef.current = null
        }
    }, [isDark, isMobile])

    useEffect(() => {
        let cancelled = false

        const load = async () => {
            if (!seriesRef.current) return
            setLoading(true)
            setError(null)
            try {
                const resp = await api.getKline(symbol, range.start, range.end)
                const data = toChartData(resp.candles)

                if (cancelled) return
                setCandles(resp.candles)
                candlesRef.current = resp.candles
                setActiveCandle(resp.candles.length ? resp.candles[resp.candles.length - 1] : null)
                seriesRef.current?.setData(data)
                chartRef.current?.timeScale().fitContent()
                if (!data.length) {
                    setError('暂无可用 K 线数据')
                }
            } catch (e) {
                if (cancelled) return
                setError(e instanceof Error ? e.message : '加载 K 线失败')
                setCandles([])
                candlesRef.current = []
                setActiveCandle(null)
                seriesRef.current?.setData([])
            } finally {
                if (!cancelled) setLoading(false)
            }
        }

        void load()
        return () => {
            cancelled = true
        }
    }, [range.end, range.start, symbol])

    const panelCandle = activeCandle ?? (candles.length ? candles[candles.length - 1] : null)
    const panelChange = panelCandle?.change ?? (panelCandle ? panelCandle.close - panelCandle.open : null)
    const panelChangePercent = panelCandle?.change_percent ?? (
        panelCandle && panelCandle.open !== 0 ? (panelChange! / panelCandle.open) * 100 : null
    )
    const isUp = (panelChange ?? 0) >= 0
    const compactChangePercent = panelChangePercent == null ? '--' : `${panelChangePercent >= 0 ? '+' : ''}${formatNumber(panelChangePercent)}%`
    const showCurrentSymbolButton = !!currentAnalysisSymbol && currentAnalysisSymbol !== symbol
    const currentSymbolLabel = currentAnalysisSymbol ? getSymbolName(currentAnalysisSymbol) : '当前标的'
    const changeTone = panelChange == null
        ? 'text-slate-500 dark:text-slate-400'
        : isUp
            ? 'text-red-500'
            : 'text-emerald-500'
    const changeBgTone = panelChange == null
        ? 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
        : isUp
            ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300'
            : 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300'

    if (isMobile) {
        return (
            <section className="card flex h-full min-w-0 flex-col overflow-hidden p-4">
                <div className="shrink-0">
                    <div className="flex items-start gap-2">
                        <CandlestickChart className="mt-0.5 h-5 w-5 shrink-0 text-cyan-500" />
                        <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium text-slate-400 dark:text-slate-500">市场指数</p>
                            <h2 className="mt-0.5 whitespace-normal break-words text-lg font-semibold leading-6 text-slate-900 dark:text-slate-100">
                                {getSymbolName(symbol)}
                            </h2>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{panelCandle?.date || '--'}</p>
                        </div>
                    </div>

                    <div className="-mx-1 mt-4 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                        <div className="flex min-w-max gap-2">
                            {showCurrentSymbolButton && (
                                <button
                                    type="button"
                                    onClick={() => onSymbolChange?.(currentAnalysisSymbol)}
                                    className="min-h-10 flex-none whitespace-nowrap rounded-full border border-emerald-500 bg-emerald-50 px-3 text-sm font-medium text-emerald-600 transition-colors dark:bg-emerald-500/10 dark:text-emerald-300"
                                >
                                    {currentSymbolLabel}
                                </button>
                            )}
                            {INDEX_PRESETS.map((item) => (
                                <button
                                    key={item.symbol}
                                    type="button"
                                    onClick={() => onSymbolChange?.(item.symbol)}
                                    className={`min-h-10 flex-none whitespace-nowrap rounded-full border px-3 text-sm font-medium transition-colors ${
                                        item.symbol === symbol
                                            ? 'border-blue-500 bg-blue-50 text-blue-600 shadow-sm dark:bg-blue-500/10 dark:text-blue-300'
                                            : 'border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300'
                                    }`}
                                >
                                    {item.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-3 dark:border-slate-700 dark:bg-slate-900/45">
                        <div className="flex items-end justify-between gap-3">
                            <div>
                                <p className="text-xs text-slate-400 dark:text-slate-500">收盘</p>
                                <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                                    {formatNumber(panelCandle?.close)}
                                </p>
                            </div>
                            <div className="text-right">
                                <p className="text-xs text-slate-400 dark:text-slate-500">涨跌幅</p>
                                <p className={`mt-1 rounded-full px-2.5 py-1 text-base font-semibold tabular-nums ${changeBgTone}`}>
                                    {compactChangePercent}
                                </p>
                            </div>
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                            <MobileMetric label="开盘" value={formatNumber(panelCandle?.open)} />
                            <MobileMetric label="成交量" value={formatVolume(panelCandle?.volume)} />
                            <MobileMetric label="高 / 低" value={`${formatNumber(panelCandle?.high)} / ${formatNumber(panelCandle?.low)}`} wide />
                            <MobileMetric label="换手" value={panelCandle?.turnover_rate == null ? '--' : `${formatNumber(panelCandle.turnover_rate)}%`} />
                            <MobileMetric label="涨跌额" value={panelChange == null ? '--' : `${panelChange >= 0 ? '+' : ''}${formatNumber(panelChange)}`} valueClassName={changeTone} />
                        </div>
                    </div>
                </div>

                <div className="relative mt-4 min-h-[150px] flex-1 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
                    <div ref={containerRef} className="absolute inset-0" />
                    {loading && (
                        <div className="absolute right-3 top-3 flex items-center gap-1 rounded bg-white/90 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800/90 dark:text-slate-400">
                            <Activity className="h-3 w-3 animate-pulse" />
                            加载中
                        </div>
                    )}
                    {error && (
                        <div className="absolute left-3 top-3 rounded bg-white/90 px-2 py-1 text-xs text-orange-500 dark:bg-slate-800/90">
                            {error}
                        </div>
                    )}
                </div>
            </section>
        )
    }

    return (
        <section className="card h-full flex flex-col overflow-hidden">
            <div className="flex items-center justify-between mb-3 shrink-0">
                <div className="min-w-0 flex items-center gap-3">
                    <CandlestickChart className="w-5 h-5 text-cyan-500" />
                    <div className="min-w-0 flex flex-wrap items-center gap-x-4 gap-y-1">
                        <h2 className="truncate text-lg font-semibold text-slate-900 dark:text-slate-100">{getDisplayName(symbol)} K 线</h2>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                            <span className="text-slate-500 dark:text-slate-400">{panelCandle?.date || '--'}</span>
                            <span className={`font-medium ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>收盘 {formatNumber(panelCandle?.close)}</span>
                            <span className="text-slate-500 dark:text-slate-400">开盘 {formatNumber(panelCandle?.open)}</span>
                            <span className={`font-medium ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>{compactChangePercent}</span>
                            <span className="text-slate-500 dark:text-slate-400">高/低 {formatNumber(panelCandle?.high)} / {formatNumber(panelCandle?.low)}</span>
                            <span className="text-slate-500 dark:text-slate-400">量 {formatVolume(panelCandle?.volume)}</span>
                            <span className="text-slate-500 dark:text-slate-400">换手 {panelCandle?.turnover_rate == null ? '--' : `${formatNumber(panelCandle.turnover_rate)}%`}</span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-1.5">
                    {showCurrentSymbolButton && (
                        <button
                            onClick={() => onSymbolChange?.(currentAnalysisSymbol)}
                            className="text-xs px-2.5 py-1 rounded border border-emerald-500 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 transition-colors"
                        >
                            {currentSymbolLabel}
                        </button>
                    )}
                    {INDEX_PRESETS.map((item) => (
                        <button
                            key={item.symbol}
                            onClick={() => onSymbolChange?.(item.symbol)}
                            className={`text-xs px-2 py-1 rounded border transition-colors ${item.symbol === symbol
                                ? 'border-blue-500 text-blue-500 bg-blue-50 dark:bg-blue-500/10'
                                : 'border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:border-slate-400 dark:hover:border-slate-500'
                            }`}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>
            </div>
            <div className="relative flex-1 min-h-0 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 overflow-hidden">
                <div ref={containerRef} className="absolute inset-0" />
                {loading && (
                    <div className="absolute right-3 top-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-slate-600 dark:text-slate-400 flex items-center gap-1">
                        <Activity className="w-3 h-3 animate-pulse" />
                        加载中
                    </div>
                )}
                {error && (
                    <div className="absolute left-3 top-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-orange-500">
                        {error}
                    </div>
                )}
            </div>
        </section>
    )
}

function MobileMetric({
    label,
    value,
    valueClassName = 'text-slate-800 dark:text-slate-100',
    wide = false,
}: {
    label: string
    value: string
    valueClassName?: string
    wide?: boolean
}) {
    return (
        <div className={`min-w-0 rounded-xl bg-white px-3 py-2 dark:bg-slate-800/70 ${wide ? 'col-span-2' : ''}`}>
            <p className="text-xs text-slate-400 dark:text-slate-500">{label}</p>
            <p className={`mt-1 break-words text-sm font-medium tabular-nums ${valueClassName}`}>{value}</p>
        </div>
    )
}
