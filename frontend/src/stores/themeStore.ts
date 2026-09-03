import { create } from 'zustand'
import type { ThemeSkinId } from '@/styles/skins/registry'
import { isThemeSkinId, SKINS } from '@/styles/skins/registry'

const STORAGE_KEY = 'ta-skin'

interface ThemeState {
    skin: ThemeSkinId
    hydrated: boolean
    /** 同步 localStorage + DOM + 按需加载皮肤 CSS */
    hydrate: () => void
    setSkin: (skin: ThemeSkinId) => void
}

function applySkinToDom(skin: ThemeSkinId) {
    document.documentElement.dataset.skin = skin
}

async function ensureSkinCssLoaded(skin: ThemeSkinId) {
    const def = SKINS.find((s) => s.id === skin)
    if (def?.loadCss) await def.loadCss()
}

export const useThemeStore = create<ThemeState>((set) => ({
    skin: 'default',
    hydrated: false,

    hydrate: () => {
        let raw: string | null = null
        try {
            raw = localStorage.getItem(STORAGE_KEY)
        } catch {
            raw = null
        }
        const skin: ThemeSkinId = isThemeSkinId(raw) ? raw : 'default'
        applySkinToDom(skin)
        if (skin !== 'default') {
            void ensureSkinCssLoaded(skin)
        }
        set({ skin, hydrated: true })
    },

    setSkin: (skin) => {
        try {
            localStorage.setItem(STORAGE_KEY, skin)
        } catch {
            /* Edge / InPrivate / 策略禁用存储时仍可切换当前会话皮肤 */
        }
        applySkinToDom(skin)
        if (skin !== 'default') {
            void ensureSkinCssLoaded(skin)
        }
        set({ skin })
    },
}))
