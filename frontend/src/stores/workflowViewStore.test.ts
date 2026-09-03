import { beforeEach, describe, expect, it } from 'vitest'
import { useWorkflowViewStore } from './workflowViewStore'

describe('workflowViewStore', () => {
    beforeEach(() => {
        localStorage.clear()
        useWorkflowViewStore.setState({ style: 'original', hydrated: false })
    })

    it('hydrate 默认为 original', () => {
        useWorkflowViewStore.getState().hydrate()
        expect(useWorkflowViewStore.getState().style).toBe('original')
        expect(useWorkflowViewStore.getState().hydrated).toBe(true)
    })

    it('hydrate 从 localStorage 读取 n8n', () => {
        localStorage.setItem('ta-workflow-style', 'n8n')
        useWorkflowViewStore.getState().hydrate()
        expect(useWorkflowViewStore.getState().style).toBe('n8n')
    })

    it('setStyle 写入 localStorage', () => {
        useWorkflowViewStore.getState().hydrate()
        useWorkflowViewStore.getState().setStyle('n8n')
        expect(localStorage.getItem('ta-workflow-style')).toBe('n8n')
        useWorkflowViewStore.getState().setStyle('original')
        expect(localStorage.getItem('ta-workflow-style')).toBe('original')
    })
})
