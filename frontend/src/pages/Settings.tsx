import { useState, useEffect, useMemo } from 'react'
import { Save, Key, Database, Loader2, Trash2, Link2, Copy, Plus, CheckCircle2, Mail, Flame, Webhook } from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'
import type { RuntimeWarmupResult, TushareSettings, UserToken } from '@/types'

type ProviderPreset = {
    id: string
    label: string
    provider: string
    baseUrl: string
    protocol: string
    editableBaseUrl?: boolean
}

const PROVIDER_PRESETS: ProviderPreset[] = [
    { id: 'openai', label: 'OpenAI', provider: 'openai', baseUrl: 'https://api.openai.com/v1', protocol: 'OpenAI' },
    { id: 'anthropic', label: 'Anthropic', provider: 'anthropic', baseUrl: '', protocol: 'Anthropic' },
    { id: 'google', label: 'Google Gemini', provider: 'google', baseUrl: '', protocol: 'Google' },
    { id: 'dashscope', label: '阿里云百炼（DashScope）', provider: 'openai', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', protocol: 'OpenAI 兼容' },
    { id: 'deepseek', label: 'DeepSeek', provider: 'openai', baseUrl: 'https://api.deepseek.com/v1', protocol: 'OpenAI 兼容' },
    { id: 'moonshot', label: 'Moonshot AI（Kimi）', provider: 'openai', baseUrl: 'https://api.moonshot.cn/v1', protocol: 'OpenAI 兼容' },
    { id: 'zhipu', label: '智谱 AI', provider: 'openai', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', protocol: 'OpenAI 兼容' },
    { id: 'siliconflow', label: '硅基流动', provider: 'openai', baseUrl: 'https://api.siliconflow.cn/v1', protocol: 'OpenAI 兼容' },
    { id: 'custom-openai', label: '自定义 OpenAI 兼容', provider: 'openai', baseUrl: '', protocol: 'OpenAI 兼容', editableBaseUrl: true },
]

function inferPreset(llmProvider: string, backendUrl: string): string {
    const normalizedProvider = (llmProvider || '').toLowerCase()
    const normalizedUrl = (backendUrl || '').replace(/\/$/, '')
    const matched = PROVIDER_PRESETS.find((preset) => {
        if (preset.provider !== normalizedProvider) return false
        if (!preset.baseUrl && preset.id !== 'custom-openai') return true
        return preset.baseUrl.replace(/\/$/, '') === normalizedUrl
    })
    if (matched) return matched.id
    if (normalizedProvider === 'openai') return 'custom-openai'
    return normalizedProvider || 'openai'
}

export default function Settings() {
    const { user } = useAuthStore()
    const [defaultAnalysts, setDefaultAnalysts] = useState(['market', 'social', 'news', 'fundamentals', 'macro', 'smart_money', 'volume_price'])
    const [customPrompt, setCustomPrompt] = useState('')
    const [llmApiKey, setLlmApiKey] = useState('')
    const [hasStoredApiKey, setHasStoredApiKey] = useState(false)
    const [wecomWebhook, setWecomWebhook] = useState('')
    const [hasStoredWebhook, setHasStoredWebhook] = useState(false)
    const [storedWebhookDisplay, setStoredWebhookDisplay] = useState('')

    const [providerPreset, setProviderPreset] = useState('openai')
    const [customBaseUrl, setCustomBaseUrl] = useState('')
    const [deepThinkLlm, setDeepThinkLlm] = useState('')
    const [quickThinkLlm, setQuickThinkLlm] = useState('')
    const [maxDebateRounds, setMaxDebateRounds] = useState(1)
    const [maxRiskRounds, setMaxRiskRounds] = useState(1)
    const [searxngBaseUrl, setSearxngBaseUrl] = useState('')
    const [newsDataStrategy, setNewsDataStrategy] = useState<'fallback' | 'hybrid' | 'aggregate'>('hybrid')
    const [newsHybridMinItems, setNewsHybridMinItems] = useState(8)
    const [newsHybridMinConfidence, setNewsHybridMinConfidence] = useState(0.7)
    const [newsAggregateMaxItems, setNewsAggregateMaxItems] = useState(20)
    const [newsAggregateMaxChars, setNewsAggregateMaxChars] = useState(20000)
    const [newsDedupeEnabled, setNewsDedupeEnabled] = useState(true)
    const [serverFallbackEnabled, setServerFallbackEnabled] = useState(true)
    const [emailReportEnabled, setEmailReportEnabled] = useState(true)
    const [wecomReportEnabled, setWecomReportEnabled] = useState(true)
    const [configLoading, setConfigLoading] = useState(false)
    const [saving, setSaving] = useState(false)
    const [saveAllSaving, setSaveAllSaving] = useState(false)
    const [warmingUp, setWarmingUp] = useState(false)
    const [saved, setSaved] = useState(false)
    const [saveMessage, setSaveMessage] = useState('设置已保存')
    const [configError, setConfigError] = useState<string | null>(null)
    const [warmupResults, setWarmupResults] = useState<RuntimeWarmupResult[]>([])
    const [warmupError, setWarmupError] = useState<string | null>(null)
    const [wecomWarmingUp, setWecomWarmingUp] = useState(false)
    const [wecomWarmupMessage, setWecomWarmupMessage] = useState<string | null>(null)
    const [wecomWarmupError, setWecomWarmupError] = useState<string | null>(null)
    const [searxngTesting, setSearxngTesting] = useState(false)
    const [searxngTestMessage, setSearxngTestMessage] = useState<string | null>(null)
    const [searxngTestError, setSearxngTestError] = useState<string | null>(null)
    const [tushareSettings, setTushareSettings] = useState<TushareSettings | null>(null)
    const [tushareEnabled, setTushareEnabled] = useState(false)
    const [tushareToken, setTushareToken] = useState('')
    const [tushareTimeout, setTushareTimeout] = useState(10)
    const [tushareRateLimit, setTushareRateLimit] = useState(40)
    const [tushareCacheTtl, setTushareCacheTtl] = useState(86400)
    const [tushareSaving, setTushareSaving] = useState(false)
    const [tushareTesting, setTushareTesting] = useState(false)
    const [tushareProbing, setTushareProbing] = useState(false)
    const [tushareMessage, setTushareMessage] = useState<string | null>(null)
    const [tushareError, setTushareError] = useState<string | null>(null)

    // API Token states
    const [tokens, setTokens] = useState<UserToken[]>([])
    const [tokensLoading, setTokensLoading] = useState(false)
    const [newTokenName, setNewTokenName] = useState('')
    const [isCreatingToken, setIsCreatingToken] = useState(false)
    const [copiedTokenId, setCopiedTokenId] = useState<string | null>(null)
    const [newlyCreatedToken, setNewlyCreatedToken] = useState<string | null>(null)

    const selectedPreset = useMemo(
        () => PROVIDER_PRESETS.find((item) => item.id === providerPreset) || PROVIDER_PRESETS[0],
        [providerPreset],
    )

    const effectiveProvider = selectedPreset.provider
    const effectiveBaseUrl = selectedPreset.editableBaseUrl ? customBaseUrl.trim() : selectedPreset.baseUrl
    useEffect(() => {
        setWarmupResults([])
        setWarmupError(null)
    }, [providerPreset, customBaseUrl, deepThinkLlm, quickThinkLlm, llmApiKey])

    useEffect(() => {
        setWecomWarmupMessage(null)
        setWecomWarmupError(null)
    }, [wecomWebhook])

    useEffect(() => {
        setSearxngTestMessage(null)
        setSearxngTestError(null)
    }, [searxngBaseUrl])

    useEffect(() => {
        setTushareMessage(null)
        setTushareError(null)
    }, [tushareEnabled, tushareToken, tushareTimeout, tushareRateLimit, tushareCacheTtl])

    useEffect(() => {
        try {
            const stored = localStorage.getItem('tradingagents-settings')
            if (stored) {
                const s = JSON.parse(stored) as Record<string, unknown> & {
                    defaultAnalysts?: string[]
                }
                if ('apiUrl' in s) {
                    delete s.apiUrl
                    localStorage.setItem('tradingagents-settings', JSON.stringify(s))
                }
                if (s.defaultAnalysts) setDefaultAnalysts(s.defaultAnalysts)
                if (typeof s.customPrompt === 'string') setCustomPrompt(s.customPrompt)
            }
        } catch {}
    }, [])

    useEffect(() => {
        setConfigLoading(true)
        setConfigError(null)
        api.getConfig()
            .then(cfg => {
                setProviderPreset(inferPreset(cfg.llm_provider, cfg.backend_url))
                setCustomBaseUrl(cfg.backend_url || '')
                setDeepThinkLlm(cfg.deep_think_llm)
                setQuickThinkLlm(cfg.quick_think_llm)
                setMaxDebateRounds(cfg.max_debate_rounds)
                setMaxRiskRounds(cfg.max_risk_discuss_rounds)
                setSearxngBaseUrl(cfg.searxng_base_url || '')
                setNewsDataStrategy(cfg.news_data_strategy || 'hybrid')
                setNewsHybridMinItems(cfg.news_hybrid_min_items || 8)
                setNewsHybridMinConfidence(cfg.news_hybrid_min_confidence ?? 0.7)
                setNewsAggregateMaxItems(cfg.news_aggregate_max_items || 20)
                setNewsAggregateMaxChars(cfg.news_aggregate_max_chars || 20000)
                setNewsDedupeEnabled(cfg.news_dedupe_enabled !== false)
                setHasStoredApiKey(!!cfg.has_api_key)
                setHasStoredWebhook(!!cfg.has_wecom_webhook)
                setStoredWebhookDisplay(cfg.wecom_webhook_display || '')
                setServerFallbackEnabled(!!cfg.server_fallback_enabled)
                setEmailReportEnabled(cfg.email_report_enabled !== false)
                setWecomReportEnabled(cfg.wecom_report_enabled !== false)
                if (Array.isArray(cfg.default_analysts) && cfg.default_analysts.length > 0) {
                    setDefaultAnalysts(cfg.default_analysts)
                }
            })
            .catch(err => {
                setConfigError(err instanceof Error ? err.message : '无法连接到后端')
            })
            .finally(() => setConfigLoading(false))

        api.getTushareSettings()
            .then(settings => {
                setTushareSettings(settings)
                setTushareEnabled(!!settings.enabled)
                setTushareTimeout(settings.timeout || 10)
                setTushareRateLimit(settings.rate_limit_per_minute || 40)
                setTushareCacheTtl(settings.cache_ttl_seconds || 86400)
            })
            .catch(err => {
                setTushareError(err instanceof Error ? err.message : '无法加载 Tushare 设置')
            })

        // Fetch tokens
        fetchTokens()
    }, [])

    const fetchTokens = async () => {
        setTokensLoading(true)
        try {
            const data = await api.getTokens()
            setTokens(data)
        } catch (err) {
            console.error('Failed to fetch tokens:', err)
        } finally {
            setTokensLoading(false)
        }
    }

    const handleCreateToken = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!newTokenName.trim()) return
        setIsCreatingToken(true)
        try {
            const created = await api.createToken({ name: newTokenName.trim() })
            setNewTokenName('')
            setNewlyCreatedToken(created.token || null)
            await fetchTokens()
        } catch (err) {
            alert(err instanceof Error ? err.message : '创建 Token 失败')
        } finally {
            setIsCreatingToken(false)
        }
    }

    const handleDeleteToken = async (tokenId: string) => {
        if (!confirm('确定要吊销此 Token 吗？吊销后使用该 Token 的 API 请求将立即失效。')) return
        try {
            await api.deleteToken(tokenId)
            await fetchTokens()
        } catch (err) {
            alert(err instanceof Error ? err.message : '吊销 Token 失败')
        }
    }

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text)
        setCopiedTokenId(id)
        setTimeout(() => setCopiedTokenId(null), 2000)
    }

    const persistLocalSettings = () => {
        localStorage.setItem('tradingagents-settings', JSON.stringify({
            defaultAnalysts,
            customPrompt,
        }))
        localStorage.setItem('ta-custom-prompt', customPrompt)
    }

    const buildRuntimeConfigPayload = (options?: { includeEmail?: boolean; includeWecom?: boolean }) => ({
        llm_provider: effectiveProvider,
        backend_url: effectiveBaseUrl || undefined,
        deep_think_llm: deepThinkLlm,
        quick_think_llm: quickThinkLlm,
        max_debate_rounds: maxDebateRounds,
        max_risk_discuss_rounds: maxRiskRounds,
        searxng_base_url: searxngBaseUrl.trim(),
        news_data_strategy: newsDataStrategy,
        news_hybrid_min_items: newsHybridMinItems,
        news_hybrid_min_confidence: newsHybridMinConfidence,
        news_aggregate_max_items: newsAggregateMaxItems,
        news_aggregate_max_chars: newsAggregateMaxChars,
        news_dedupe_enabled: newsDedupeEnabled,
        api_key: llmApiKey || undefined,
        ...(options?.includeWecom ? {
            wecom_webhook_url: wecomWebhook.trim() || undefined,
            wecom_report_enabled: wecomReportEnabled,
        } : {}),
        ...(options?.includeEmail ? { email_report_enabled: emailReportEnabled } : {}),
        default_analysts: defaultAnalysts,
    })

    const showSavedMessage = (message: string) => {
        setSaveMessage(message)
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
    }

    const submitConfig = async (options?: { forceWarmup?: boolean; successMessage?: string; includeEmail?: boolean; includeWecom?: boolean }) => {
        persistLocalSettings()
        const { forceWarmup = false, successMessage = '设置已保存', includeEmail = true, includeWecom = false } = options || {}
        const response = await api.updateConfig({
            ...buildRuntimeConfigPayload({ includeEmail, includeWecom }),
            warmup: true,
            force_warmup: forceWarmup,
        })
        setHasStoredApiKey(!!response.has_api_key)
        setHasStoredWebhook(!!response.current.has_wecom_webhook)
        setStoredWebhookDisplay(response.current.wecom_webhook_display || '')
        setWecomReportEnabled(response.current.wecom_report_enabled !== false)
        setLlmApiKey('')
        setWecomWebhook('')
        showSavedMessage(response.warmup?.message || successMessage)
        return response
    }

    const handleSaveAll = async () => {
        setSaveAllSaving(true)
        try {
            await submitConfig({ includeEmail: true, includeWecom: true, successMessage: '全部设置已保存' })
            showSavedMessage('全部设置已保存')
        } catch (err) {
            alert(err instanceof Error ? err.message : '保存全部设置失败')
        } finally {
            setSaveAllSaving(false)
        }
    }

    const handleWarmup = async () => {
        setWarmingUp(true)
        setWarmupError(null)
        setWarmupResults([])
        try {
            const response = await api.warmupConfig({
                ...buildRuntimeConfigPayload(),
                prompt: '你好',
            })
            setWarmupResults(response.results || [])
        } catch (err) {
            setWarmupError(err instanceof Error ? err.message : 'Warmup 触发失败')
        } finally {
            setWarmingUp(false)
        }
    }

    const handleSearxngTest = async () => {
        setSearxngTesting(true)
        setSearxngTestMessage(null)
        setSearxngTestError(null)
        try {
            const response = await api.testSearxng(searxngBaseUrl.trim() || undefined)
            if (response.ok) {
                setSearxngTestMessage(`${response.message}，返回 ${response.result_count} 条结果，地址：${response.base_url}`)
            } else {
                setSearxngTestError(response.message)
            }
        } catch (err) {
            setSearxngTestError(err instanceof Error ? err.message : 'SearXNG 测试连接失败')
        } finally {
            setSearxngTesting(false)
        }
    }

    const applyTushareSettings = (settings: TushareSettings) => {
        setTushareSettings(settings)
        setTushareEnabled(!!settings.enabled)
        setTushareTimeout(settings.timeout || 10)
        setTushareRateLimit(settings.rate_limit_per_minute || 40)
        setTushareCacheTtl(settings.cache_ttl_seconds || 86400)
    }

    const handleSaveTushare = async () => {
        setTushareSaving(true)
        setTushareMessage(null)
        setTushareError(null)
        try {
            const settings = await api.updateTushareSettings({
                enabled: tushareEnabled,
                token: tushareToken.trim() || undefined,
                timeout: tushareTimeout,
                rate_limit_per_minute: tushareRateLimit,
                cache_ttl_seconds: tushareCacheTtl,
            })
            applyTushareSettings(settings)
            setTushareToken('')
            setTushareMessage('Tushare 设置已保存')
        } catch (err) {
            setTushareError(err instanceof Error ? err.message : '保存 Tushare 设置失败')
        } finally {
            setTushareSaving(false)
        }
    }

    const handleClearTushareToken = async () => {
        setTushareSaving(true)
        setTushareMessage(null)
        setTushareError(null)
        try {
            const settings = await api.updateTushareSettings({ clear_token: true })
            applyTushareSettings(settings)
            setTushareToken('')
            setTushareMessage('Tushare token 已清除')
        } catch (err) {
            setTushareError(err instanceof Error ? err.message : '清除 Tushare token 失败')
        } finally {
            setTushareSaving(false)
        }
    }

    const handleTestTushare = async () => {
        setTushareTesting(true)
        setTushareMessage(null)
        setTushareError(null)
        try {
            const response = await api.testTushare(tushareToken.trim() || undefined)
            const text = `${response.status}，样本行数 ${response.sample_row_count}。${response.message}`
            if (response.success) {
                setTushareMessage(text)
            } else {
                setTushareError(text)
            }
        } catch (err) {
            setTushareError(err instanceof Error ? err.message : 'Tushare 测试连接失败')
        } finally {
            setTushareTesting(false)
        }
    }

    const handleProbeTushare = async () => {
        setTushareProbing(true)
        setTushareMessage(null)
        setTushareError(null)
        try {
            const response = await api.probeTushareCapabilities()
            setTushareSettings(prev => ({
                ...(prev || {
                    enabled: tushareEnabled,
                    token_configured: false,
                    timeout: tushareTimeout,
                    rate_limit_per_minute: tushareRateLimit,
                    cache_ttl_seconds: tushareCacheTtl,
                    capability_cache_ttl_seconds: 86400,
                }),
                capabilities: response.capabilities,
                last_checked_at: response.last_checked_at,
            }))
            setTushareMessage('Tushare 权限检测已完成')
        } catch (err) {
            setTushareError(err instanceof Error ? err.message : 'Tushare 权限检测失败')
        } finally {
            setTushareProbing(false)
        }
    }

    const handleClearApiKey = async () => {
        if (!hasStoredApiKey) return
        setSaving(true)
        try {
            const response = await api.updateConfig({ clear_api_key: true })
            setHasStoredApiKey(!!response.has_api_key)
            setLlmApiKey('')
            setSaved(true)
            setTimeout(() => setSaved(false), 2000)
        } catch (err) {
            alert(err instanceof Error ? err.message : '清除密钥失败')
        } finally {
            setSaving(false)
        }
    }

    const handleClearWebhook = async () => {
        if (!hasStoredWebhook) return
        setSaving(true)
        try {
            const response = await api.updateConfig({ clear_wecom_webhook: true })
            setHasStoredWebhook(!!response.current.has_wecom_webhook)
            setStoredWebhookDisplay(response.current.wecom_webhook_display || '')
            setWecomWebhook('')
            setWecomWarmupMessage(null)
            setWecomWarmupError(null)
            showSavedMessage('企业微信机器人已清除')
        } catch (err) {
            alert(err instanceof Error ? err.message : '清除企业微信机器人失败')
        } finally {
            setSaving(false)
        }
    }

    const handleWecomWarmup = async () => {
        setWecomWarmingUp(true)
        setWecomWarmupMessage(null)
        setWecomWarmupError(null)
        try {
            const response = await api.warmupWecom({
                wecom_webhook_url: wecomWebhook.trim() || undefined,
            })
            setWecomWarmupMessage(
                response.webhook_display
                    ? `${response.message}，目标：${response.webhook_display}`
                    : response.message
            )
        } catch (err) {
            setWecomWarmupError(err instanceof Error ? err.message : 'Webhook 测试发送失败')
        } finally {
            setWecomWarmingUp(false)
        }
    }

    const toggleAnalyst = (analyst: string) => {
        setDefaultAnalysts(prev =>
            prev.includes(analyst) ? prev.filter(a => a !== analyst) : [...prev, analyst]
        )
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">系统设置</h1>
                <p className="text-slate-500 dark:text-slate-400 mt-1">配置当前账户的分析参数与模型</p>
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-purple-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">模型接入</h2>
                    {configLoading && <Loader2 className="ml-auto w-4 h-4 animate-spin text-slate-400" />}
                </div>

                {configError && (
                    <p className="text-sm text-amber-500">⚠ {configError}（显示本地默认值）</p>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            模型厂商
                        </label>
                        <select
                            value={providerPreset}
                            onChange={e => setProviderPreset(e.target.value)}
                            className="input w-full"
                            disabled={configLoading}
                        >
                            {PROVIDER_PRESETS.map((preset) => (
                                <option key={preset.id} value={preset.id}>{preset.label}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            接入协议
                        </label>
                        <div className="input w-full flex items-center gap-2 bg-slate-50 dark:bg-slate-900/70 text-slate-600 dark:text-slate-300">
                            <Link2 className="w-4 h-4 text-slate-400" />
                            <span>{selectedPreset.protocol}</span>
                        </div>
                    </div>

                    {(selectedPreset.baseUrl || selectedPreset.editableBaseUrl) && (
                        <div className="md:col-span-2">
                            <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                                Base URL
                            </label>
                            <input
                                type="text"
                                value={selectedPreset.editableBaseUrl ? customBaseUrl : selectedPreset.baseUrl}
                                onChange={e => setCustomBaseUrl(e.target.value)}
                                className="input w-full"
                                disabled={configLoading || !selectedPreset.editableBaseUrl}
                                placeholder="https://your-openai-compatible-endpoint/v1"
                            />
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                {selectedPreset.editableBaseUrl
                                    ? '自定义 OpenAI 兼容服务需要自行填写 Base URL。'
                                    : '该厂商默认通过预设的 OpenAI 兼容地址接入，通常只需填写模型名和 API Key。'}
                            </p>
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            常规模型
                            <span className="ml-1 text-xs text-slate-400 font-normal">用于意图识别、JSON 提取等轻量任务</span>
                        </label>
                        <input
                            type="text"
                            value={quickThinkLlm}
                            onChange={e => setQuickThinkLlm(e.target.value)}
                            className="input w-full"
                            placeholder="例如：gpt-4.1-mini / deepseek-chat / moonshot-v1-8k"
                            disabled={configLoading}
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            推理模型
                            <span className="ml-1 text-xs text-slate-400 font-normal">用于深度分析、辩论等复杂任务</span>
                        </label>
                        <input
                            type="text"
                            value={deepThinkLlm}
                            onChange={e => setDeepThinkLlm(e.target.value)}
                            className="input w-full"
                            placeholder="例如：gpt-4.1 / deepseek-reasoner / kimi-k2-0905-preview"
                            disabled={configLoading}
                        />
                    </div>

                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            用户模型 Key
                        </label>
                        <div className="relative">
                            <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <input
                                type="password"
                                value={llmApiKey}
                                onChange={e => setLlmApiKey(e.target.value)}
                                className="input w-full pl-10"
                                placeholder={hasStoredApiKey ? '已保存，留空则保持不变' : '输入你的模型 API Key'}
                                disabled={configLoading}
                            />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                            <div className="text-xs text-slate-500 dark:text-slate-400">
                                {serverFallbackEnabled
                                    ? '当前后端已开启公共模型回退：未填写个人 Key 时，可能仍会使用服务端默认模型配置。'
                                    : '当前后端已关闭公共模型回退：未填写个人 Key 时，将无法发起需要模型的分析任务。'}
                            </div>
                            {hasStoredApiKey && (
                                <button
                                    type="button"
                                    onClick={handleClearApiKey}
                                    disabled={saving || saveAllSaving}
                                    className="inline-flex items-center gap-1 text-xs text-rose-500 hover:text-rose-600 disabled:opacity-50"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                    清除密钥
                                </button>
                            )}
                        </div>
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                            保存模型配置后，系统会在后台自动测试连通性；也可以直接点击下方按钮，发送\u201c你好\u201d来验证模型是否正常响应。
                        </p>
                    </div>

                    <div className="md:col-span-2 rounded-2xl border border-slate-200/80 dark:border-slate-700/80 bg-slate-50/80 dark:bg-slate-900/40 p-4 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <div className="text-sm font-medium text-slate-900 dark:text-slate-100">连通性测试</div>
                                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                    使用当前表单配置向模型发送“你好”，不会自动保存设置。
                                </p>
                            </div>
                            <button onClick={handleWarmup} disabled={saving || saveAllSaving || warmingUp || configLoading} className="btn-secondary inline-flex items-center gap-2">
                                {warmingUp ? <Loader2 className="w-4 h-4 animate-spin" /> : <Flame className="w-4 h-4" />}
                                {warmingUp ? '测试中...' : '测试连接'}
                            </button>
                        </div>

                        {warmupError && (
                            <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                                {warmupError}
                            </div>
                        )}

                        {warmupResults.length > 0 && (
                            <div className="space-y-3">
                                {warmupResults.map((item, index) => (
                                    <div
                                        key={`${item.model}-${index}`}
                                        className="rounded-xl border border-slate-200/80 dark:border-slate-700/80 bg-white dark:bg-slate-950/40 px-4 py-3"
                                    >
                                        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                                            <span className="font-medium text-slate-700 dark:text-slate-200">{item.targets.join(' / ')}</span>
                                            <span>{item.model}</span>
                                        </div>
                                        {item.content && (
                                            <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm text-slate-700 dark:text-slate-200">
                                                {item.content}
                                            </pre>
                                        )}
                                        {item.error && (
                                            <p className="mt-2 text-sm text-rose-500 dark:text-rose-300">{item.error}</p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Link2 className="w-5 h-5 text-cyan-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">新闻源配置</h2>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                        SearXNG 接口地址
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                        <input
                            type="text"
                            value={searxngBaseUrl}
                            onChange={e => setSearxngBaseUrl(e.target.value)}
                            className="input flex-1"
                            placeholder="http://127.0.0.1:8888"
                            disabled={configLoading}
                        />
                        <button
                            type="button"
                            onClick={handleSearxngTest}
                            disabled={configLoading || searxngTesting}
                            className="btn-secondary inline-flex items-center justify-center gap-2 whitespace-nowrap"
                        >
                            {searxngTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Flame className="w-4 h-4" />}
                            {searxngTesting ? '测试中...' : '测试连接'}
                        </button>
                    </div>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        用于 SearXNG 新闻检索服务，系统会请求 {'{地址}'}/search?format=json。留空保存后使用环境变量或默认地址。
                    </p>
                    {searxngTestMessage && (
                        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
                            {searxngTestMessage}
                        </div>
                    )}
                    {searxngTestError && (
                        <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                            {searxngTestError}
                        </div>
                    )}
                </div>

                <div className="space-y-3">
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400">
                        新闻源模式
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {[
                            { key: 'fallback', title: 'Fallback 快速降级', desc: '最快：首个可用新闻源命中后停止。' },
                            { key: 'hybrid', title: 'Hybrid 智能补充', desc: '平衡速度和完整性：首选源不足时补查后续源。' },
                            { key: 'aggregate', title: 'Aggregate 全量聚合', desc: '最完整但更慢：查询所有新闻源并合并。' },
                        ].map((item) => {
                            const active = newsDataStrategy === item.key
                            return (
                                <button
                                    key={item.key}
                                    type="button"
                                    onClick={() => setNewsDataStrategy(item.key as 'fallback' | 'hybrid' | 'aggregate')}
                                    disabled={configLoading}
                                    className={`rounded-xl border px-3 py-3 text-left transition-colors ${
                                        active
                                            ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                                            : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-300'
                                    }`}
                                >
                                    <div className="text-sm font-medium">{item.title}</div>
                                    <div className="mt-1 text-xs opacity-80">{item.desc}</div>
                                </button>
                            )
                        })}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Fallback 最快；Hybrid 平衡速度和完整性；Aggregate 最完整但更慢。
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            Hybrid 最少条数
                        </label>
                        <input
                            type="number"
                            min={1}
                            max={100}
                            value={newsHybridMinItems}
                            onChange={e => setNewsHybridMinItems(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            Hybrid 最低可信分
                        </label>
                        <input
                            type="number"
                            min={0}
                            max={1}
                            step={0.05}
                            value={newsHybridMinConfidence}
                            onChange={e => setNewsHybridMinConfidence(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            聚合每源最多条数
                        </label>
                        <input
                            type="number"
                            min={1}
                            max={100}
                            value={newsAggregateMaxItems}
                            onChange={e => setNewsAggregateMaxItems(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            ???????
                        </label>
                        <input
                            type="number"
                            min={1000}
                            max={100000}
                            step={1000}
                            value={newsAggregateMaxChars}
                            onChange={e => setNewsAggregateMaxChars(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                    <div className="flex items-end">
                        <button
                            type="button"
                            onClick={() => setNewsDedupeEnabled(!newsDedupeEnabled)}
                            disabled={configLoading}
                            className={`w-full rounded-xl border px-3 py-2 text-sm transition-colors ${
                                newsDedupeEnabled
                                    ? 'border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
                                    : 'border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-300'
                            }`}
                            title="????? URL ?????????????????????"
                        >
                            ?????{newsDedupeEnabled ? '??' : '??'}
                        </button>
                    </div>
                </div>
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-emerald-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Tushare 数据源</h2>
                </div>

                <p className="text-sm text-slate-500 dark:text-slate-400">
                    Tushare token 用于结构化行情和财务数据。低积分账号可能只能访问部分接口，系统会自动检测权限并对不可用接口回退到其他数据源。
                    第一版行情使用 Tushare daily 未复权日线，技术指标也按未复权价格计算，不等同于前复权或后复权口径。
                </p>

                <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 dark:border-slate-700/80 dark:bg-slate-900/40">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">启用 Tushare</div>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                                {tushareSettings?.token_configured
                                    ? `已配置 token：${tushareSettings.token_masked || '********'}`
                                    : '未配置 token'}
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setTushareEnabled(!tushareEnabled)}
                            disabled={configLoading || tushareSaving}
                            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                                tushareEnabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
                            }`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${tushareEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                    </div>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                        Tushare Token
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                        <input
                            type="password"
                            value={tushareToken}
                            onChange={e => setTushareToken(e.target.value)}
                            className="input flex-1 font-mono"
                            placeholder={tushareSettings?.token_configured ? '已保存，留空则保持不变' : '输入 Tushare Pro token'}
                            disabled={configLoading || tushareSaving}
                            autoComplete="new-password"
                        />
                        {tushareSettings?.token_configured && (
                            <button
                                type="button"
                                onClick={handleClearTushareToken}
                                disabled={tushareSaving}
                                className="inline-flex items-center justify-center gap-1 text-xs text-slate-400 hover:text-rose-500 disabled:opacity-50 shrink-0"
                            >
                                <Trash2 className="w-3 h-3" />
                                清除
                            </button>
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">请求超时（秒）</label>
                        <input
                            type="number"
                            min={1}
                            max={120}
                            value={tushareTimeout}
                            onChange={e => setTushareTimeout(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading || tushareSaving}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">每分钟限流</label>
                        <input
                            type="number"
                            min={1}
                            max={500}
                            value={tushareRateLimit}
                            onChange={e => setTushareRateLimit(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading || tushareSaving}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">缓存 TTL（秒）</label>
                        <input
                            type="number"
                            min={0}
                            max={2592000}
                            value={tushareCacheTtl}
                            onChange={e => setTushareCacheTtl(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading || tushareSaving}
                        />
                    </div>
                </div>

                <div className="flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={handleSaveTushare}
                        disabled={configLoading || tushareSaving}
                        className="btn-primary inline-flex items-center gap-2"
                    >
                        {tushareSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        保存 Tushare
                    </button>
                    <button
                        type="button"
                        onClick={handleTestTushare}
                        disabled={configLoading || tushareTesting || (!tushareToken.trim() && !tushareSettings?.token_configured)}
                        className="btn-secondary inline-flex items-center gap-2"
                    >
                        {tushareTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Flame className="w-4 h-4" />}
                        测试连接
                    </button>
                    <button
                        type="button"
                        onClick={handleProbeTushare}
                        disabled={configLoading || tushareProbing || !tushareSettings?.token_configured}
                        className="btn-secondary inline-flex items-center gap-2"
                    >
                        {tushareProbing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
                        检测权限
                    </button>
                </div>

                {tushareMessage && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
                        {tushareMessage}
                    </div>
                )}
                {tushareError && (
                    <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                        {tushareError}
                    </div>
                )}

                {tushareSettings && Object.keys(tushareSettings.capabilities || {}).length > 0 && (
                    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-700">
                            <thead className="bg-slate-50 dark:bg-slate-900/70">
                                <tr>
                                    <th className="px-3 py-2 text-left font-medium text-slate-500 dark:text-slate-400">接口</th>
                                    <th className="px-3 py-2 text-left font-medium text-slate-500 dark:text-slate-400">状态</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {Object.entries(tushareSettings.capabilities).map(([name, status]) => (
                                    <tr key={name}>
                                        <td className="px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-200">{name}</td>
                                        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-300">{status}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {tushareSettings.last_checked_at && (
                            <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-400 dark:border-slate-800">
                                最近检测：{new Date(tushareSettings.last_checked_at).toLocaleString()}
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-green-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">默认分析配置</h2>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                        默认启用分析师
                    </label>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { key: 'market', label: '市场分析' },
                            { key: 'social', label: '舆情分析' },
                            { key: 'news', label: '新闻分析' },
                            { key: 'fundamentals', label: '基本面' },
                            { key: 'macro', label: '宏观板块' },
                            { key: 'smart_money', label: '主力资金' },
                            { key: 'volume_price', label: '量价分析' },
                        ].map((analyst) => {
                            const active = defaultAnalysts.includes(analyst.key)
                            return (
                                <button
                                    key={analyst.key}
                                    type="button"
                                    onClick={() => toggleAnalyst(analyst.key)}
                                    className={`rounded-xl border px-3 py-3 text-sm transition-colors ${
                                        active
                                            ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-500 text-blue-600 dark:text-blue-400'
                                            : 'bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400'
                                    }`}
                                >
                                    {analyst.label}
                                </button>
                            )
                        })}
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            辩论轮数上限
                        </label>
                        <input
                            type="number"
                            min={1}
                            max={5}
                            value={maxDebateRounds}
                            onChange={e => setMaxDebateRounds(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                            风险讨论轮数上限
                        </label>
                        <input
                            type="number"
                            min={1}
                            max={5}
                            value={maxRiskRounds}
                            onChange={e => setMaxRiskRounds(Number(e.target.value))}
                            className="input w-full"
                            disabled={configLoading}
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">
                        自定义分析提示
                    </label>
                    <textarea
                        value={customPrompt}
                        onChange={e => setCustomPrompt(e.target.value)}
                        className="input w-full min-h-[80px] resize-y"
                        placeholder="例如：更关注估值安全边际、政策催化与机构资金行为。"
                    />
                </div>
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Key className="w-5 h-5 text-amber-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">API 访问令牌</h2>
                    {tokensLoading && <Loader2 className="w-4 h-4 animate-spin text-slate-400 ml-auto" />}
                </div>

                <div className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                    使用 API Token 在三方应用（如 Open Claw）中调用投研分析接口。请妥善保管您的 Token。
                </div>

                {/* Newly created token — show once */}
                {newlyCreatedToken && (
                    <div className="p-3 rounded-2xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
                        <div className="text-sm font-medium text-emerald-800 dark:text-emerald-200 mb-1">Token 创建成功 — 请立即复制，关闭后无法再次查看</div>
                        <div className="flex items-center gap-2">
                            <code className="text-xs text-emerald-700 dark:text-emerald-300 bg-white dark:bg-slate-950 px-1.5 py-0.5 rounded border font-mono tracking-tight break-all">
                                {newlyCreatedToken}
                            </code>
                            <button
                                onClick={() => copyToClipboard(newlyCreatedToken, '__new__')}
                                className="p-1 hover:bg-emerald-100 dark:hover:bg-emerald-800 rounded transition-colors text-emerald-600"
                                title="复制 Token"
                            >
                                {copiedTokenId === '__new__' ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                            </button>
                        </div>
                        <button onClick={() => setNewlyCreatedToken(null)} className="mt-2 text-xs text-emerald-600 hover:underline">我已复制，关闭提示</button>
                    </div>
                )}

                {/* Token List */}
                <div className="space-y-3">
                    {tokens.map((token) => (
                        <div key={token.id} className="flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800 transition-all group">
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{token.name}</div>
                                <div className="flex items-center gap-2 mt-1">
                                    <code className="text-xs text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 px-1.5 py-0.5 rounded border border-slate-100 dark:border-slate-800 font-mono tracking-tight">
                                        ta-sk-{'•'.repeat(16)}{token.token_hint || '****'}
                                    </code>
                                </div>
                                <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                                    创建于：{new Date(token.created_at).toLocaleDateString()}
                                    {token.last_used_at && ` • 最后使用：${new Date(token.last_used_at).toLocaleString()}`}
                                </div>
                            </div>
                            <button
                                onClick={() => handleDeleteToken(token.id)}
                                className="self-end sm:self-center p-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-xl transition-colors"
                                title="吊销 Token"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}

                    {tokens.length === 0 && !tokensLoading && (
                        <div className="text-center py-6 border-2 border-dashed border-slate-100 dark:border-slate-800 rounded-3xl text-slate-400 text-sm font-medium">
                            暂无活跃的 API Token
                        </div>
                    )}
                </div>

                {/* Create Token Form */}
                    <form onSubmit={handleCreateToken} className="flex items-center gap-2 pt-2">
                        <input
                            type="text"
                            value={newTokenName}
                            onChange={e => setNewTokenName(e.target.value)}
                            placeholder="给新 Token 起个名字，如：Open Claw"
                            className="input flex-1 h-10 text-sm"
                            disabled={isCreatingToken || tokens.length >= 10}
                        />
                    <button
                        type="submit"
                        disabled={isCreatingToken || !newTokenName.trim() || tokens.length >= 10}
                        className="btn-primary h-10 px-4 flex items-center gap-2 whitespace-nowrap text-sm"
                    >
                        {isCreatingToken ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                        生成 Token
                    </button>
                </form>
                {tokens.length >= 10 && (
                    <p className="text-[10px] text-amber-500">已达到 Token 创建上限（10个）</p>
                )}
            </div>

            <div className="card space-y-4">
                <div className="flex items-center gap-2">
                    <Mail className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">报告推送</h2>
                </div>

                {/* 邮件推送 */}
                <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 dark:border-slate-700/80 dark:bg-slate-900/40">
                    <div className="flex items-center justify-between">
                        <div>
                            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">邮件推送</div>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">定时分析完成时发送至 {user?.email || '-'}</div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setEmailReportEnabled(!emailReportEnabled)}
                            disabled={configLoading}
                            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                                emailReportEnabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
                            }`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${emailReportEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                    </div>
                </div>

                {/* 企业微信 Webhook */}
                <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 space-y-3 dark:border-slate-700/80 dark:bg-slate-900/40">
                    <div className="flex items-center justify-between">
                        <div>
                            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">企业微信 Webhook</div>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                                定时分析完成时向机器人推送摘要
                                {storedWebhookDisplay && <span className="ml-2 font-mono">({storedWebhookDisplay})</span>}
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setWecomReportEnabled(!wecomReportEnabled)}
                            disabled={configLoading}
                            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                                wecomReportEnabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
                            }`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${wecomReportEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                    </div>

                    <div className="flex items-center gap-2">
                        <div className="relative flex-1">
                            <Webhook className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <input
                                type="text"
                                value={wecomWebhook}
                                onChange={e => setWecomWebhook(e.target.value)}
                                className="input w-full pl-10"
                                placeholder={hasStoredWebhook ? '已保存，留空则保持不变' : 'Webhook 地址'}
                                disabled={configLoading}
                            />
                        </div>
                        <button
                            type="button"
                            onClick={handleWecomWarmup}
                            disabled={configLoading || saving || saveAllSaving || wecomWarmingUp || (!wecomWebhook.trim() && !hasStoredWebhook)}
                            className="btn-secondary inline-flex items-center gap-1.5 text-xs shrink-0"
                        >
                            {wecomWarmingUp ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Flame className="w-3.5 h-3.5" />}
                            {wecomWarmingUp ? '发送中...' : '测试连接'}
                        </button>
                        {hasStoredWebhook && (
                            <button
                                type="button"
                                onClick={handleClearWebhook}
                                disabled={saving || saveAllSaving}
                                className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-rose-500 disabled:opacity-50 shrink-0"
                            >
                                <Trash2 className="w-3 h-3" />
                                清除
                            </button>
                        )}
                    </div>

                    {wecomWarmupMessage && (
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
                            {wecomWarmupMessage}
                        </div>
                    )}
                    {wecomWarmupError && (
                        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                            {wecomWarmupError}
                        </div>
                    )}
                </div>
            </div>

            <div className="flex items-center gap-4">
                <button onClick={handleSaveAll} disabled={saveAllSaving} className="btn-primary inline-flex items-center gap-2">
                    {saveAllSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    保存全部
                </button>
                {saved && <span className="text-sm text-green-600 dark:text-green-400">✓ {saveMessage}</span>}
            </div>
        </div>
    )
}
