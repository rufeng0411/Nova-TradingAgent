import { create } from 'zustand'
import type { AuthUser } from '@/types'
import { api } from '@/services/api'
import { useAnalysisStore } from '@/stores/analysisStore'

/** 会话恢复（/me、权益）在 API 不可达时不能无限挂起，否则 RequireAuth 会一直「加载中」。 */
const HYDRATE_HTTP_MS = 22_000
const PUBLIC_FEATURES_MS = 12_000

let hydrateInFlight: Promise<void> | null = null

function createTimeoutSignal(ms: number): { signal: AbortSignal; cancel: () => void } {
    const c = new AbortController()
    const t = setTimeout(() => c.abort(), ms)
    return {
        signal: c.signal,
        cancel: () => clearTimeout(t),
    }
}

async function mergeEntitlements(user: AuthUser, signal?: AbortSignal): Promise<AuthUser> {
    try {
        const ent = await api.getUserEntitlements({ signal })
        const merged = { ...user, entitlements: ent }
        try {
            localStorage.setItem('ta-user', JSON.stringify(merged))
        } catch {
            /* ignore */
        }
        return merged
    } catch {
        return { ...user, entitlements: null }
    }
}

/** 与账号绑定的本地缓存键：切换用户或登出时清理，避免串数据。 */
const PER_USER_LOCAL_KEYS = [
    'tradingagents-analysis',
    'tradingagents-settings',
    'ta-custom-prompt',
    'ta-tracking-board-view',
] as const

function clearPerUserLocalCaches() {
    let oldId: string | null = null
    try {
        const raw = localStorage.getItem('ta-user')
        if (raw) oldId = (JSON.parse(raw) as { id?: string }).id ?? null
    } catch {
        /* ignore */
    }
    try {
        for (const base of PER_USER_LOCAL_KEYS) {
            localStorage.removeItem(base)
            localStorage.removeItem(`${base}:signed-out`)
            if (oldId) localStorage.removeItem(`${base}:${oldId}`)
        }
    } catch {
        /* ignore */
    }
}

interface AuthState {
    user: AuthUser | null
    token: string | null
    loading: boolean
    hydrated: boolean
    publicFeatures: {
        allow_registration: boolean
        maintenance: boolean
        captcha_enabled: boolean
        ta_cost_analysis: number
        chat_task_submit_v2_enabled?: boolean
    } | null
    setAuth: (token: string, user: AuthUser) => void
    logout: () => void
    hydrate: () => Promise<void>
    refreshMe: () => Promise<AuthUser | null>
    fetchPublicFeatures: (signal?: AbortSignal) => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    token: null,
    loading: false,
    hydrated: false,
    publicFeatures: null,

    setAuth: (token, user) => {
        clearPerUserLocalCaches()
        localStorage.setItem('ta-access-token', token)
        localStorage.setItem('ta-user', JSON.stringify(user))
        useAnalysisStore.getState().clearSession()
        set({ token, user, hydrated: true })
        void mergeEntitlements(user)
            .then((u) => set({ user: u }))
            .catch(() => null)
        void get().fetchPublicFeatures().catch(() => null)
    },

    logout: () => {
        clearPerUserLocalCaches()
        localStorage.removeItem('ta-access-token')
        localStorage.removeItem('ta-user')
        useAnalysisStore.getState().clearSession()
        set({ token: null, user: null, hydrated: true, publicFeatures: null })
    },

    fetchPublicFeatures: async (signal?: AbortSignal) => {
        try {
            const f = await api.getPublicFeatures({ signal })
            set({ publicFeatures: f })
        } catch {
            set({ publicFeatures: null })
        }
    },

    refreshMe: async () => {
        const token = get().token || localStorage.getItem('ta-access-token')
        if (!token) {
            set({ user: null, token: null })
            return null
        }
        const { signal, cancel } = createTimeoutSignal(HYDRATE_HTTP_MS)
        try {
            const user = await api.getMe({ signal })
            const withEnt = await mergeEntitlements(user, signal)
            set({ token, user: withEnt })
            cancel()
            void get().fetchPublicFeatures().catch(() => null)
            return withEnt
        } catch {
            cancel()
            localStorage.removeItem('ta-access-token')
            localStorage.removeItem('ta-user')
            set({ token: null, user: null })
            return null
        }
    },

    hydrate: async () => {
        if (get().hydrated) return
        if (hydrateInFlight) return hydrateInFlight

        hydrateInFlight = (async () => {
            const loadFeaturesBestEffort = () => {
                const { signal, cancel } = createTimeoutSignal(PUBLIC_FEATURES_MS)
                return get()
                    .fetchPublicFeatures(signal)
                    .finally(() => cancel())
            }

            const token = localStorage.getItem('ta-access-token')
            const userRaw = localStorage.getItem('ta-user')
            if (!token || !userRaw) {
                set({ token: null, user: null, hydrated: true, loading: false })
                await loadFeaturesBestEffort()
                return
            }

            set({ loading: true })
            const { signal, cancel } = createTimeoutSignal(HYDRATE_HTTP_MS)
            try {
                // 先校验 token，避免 /v1/features 卡住时整站永远「加载中」
                const user = await api.getMe({ signal })
                const withEnt = await mergeEntitlements(user, signal)
                // 若在 await 期间已登出并清空 localStorage，勿把旧会话写回 store
                if (localStorage.getItem('ta-access-token') !== token) {
                    set({ hydrated: true, loading: false })
                    cancel()
                    void loadFeaturesBestEffort()
                    return
                }
                set({ token, user: withEnt, hydrated: true, loading: false })
                cancel()
                void loadFeaturesBestEffort()
            } catch {
                cancel()
                localStorage.removeItem('ta-access-token')
                localStorage.removeItem('ta-user')
                set({ token: null, user: null, hydrated: true, loading: false })
                void loadFeaturesBestEffort()
            }
        })()

        try {
            await hydrateInFlight
        } finally {
            hydrateInFlight = null
        }
    },
}))
