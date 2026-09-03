import { create } from 'zustand'

const STORAGE_KEY = 'ta-workflow-style'

export type WorkflowStyle = 'original' | 'n8n'

function isWorkflowStyle(raw: string | null): raw is WorkflowStyle {
    return raw === 'original' || raw === 'n8n'
}

interface WorkflowViewState {
    style: WorkflowStyle
    hydrated: boolean
    hydrate: () => void
    setStyle: (style: WorkflowStyle) => void
}

export const useWorkflowViewStore = create<WorkflowViewState>((set) => ({
    style: 'original',
    hydrated: false,

    hydrate: () => {
        let raw: string | null = null
        try {
            raw = localStorage.getItem(STORAGE_KEY)
        } catch {
            raw = null
        }
        const style: WorkflowStyle = isWorkflowStyle(raw) ? raw : 'original'
        set({ style, hydrated: true })
    },

    setStyle: (style) => {
        try {
            localStorage.setItem(STORAGE_KEY, style)
        } catch {
            /* 同上：无 localStorage 时仅内存生效 */
        }
        set({ style })
    },
}))
