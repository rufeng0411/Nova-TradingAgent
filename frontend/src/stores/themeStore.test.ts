import { beforeEach, describe, expect, it } from 'vitest'
import { useThemeStore } from './themeStore'

describe('themeStore', () => {
    beforeEach(() => {
        localStorage.clear()
        document.documentElement.removeAttribute('data-skin')
        document.documentElement.classList.remove('dark')
        useThemeStore.setState({ skin: 'default', hydrated: false })
    })

    it('hydrate sets default skin and data-skin on html', () => {
        useThemeStore.getState().hydrate()
        expect(document.documentElement.dataset.skin).toBe('default')
        expect(useThemeStore.getState().skin).toBe('default')
        expect(useThemeStore.getState().hydrated).toBe(true)
    })

    it('hydrate reads linear from localStorage', () => {
        localStorage.setItem('ta-skin', 'linear')
        useThemeStore.getState().hydrate()
        expect(document.documentElement.dataset.skin).toBe('linear')
        expect(useThemeStore.getState().skin).toBe('linear')
    })

    it('hydrate reads graphite from localStorage', () => {
        localStorage.setItem('ta-skin', 'graphite')
        useThemeStore.getState().hydrate()
        expect(document.documentElement.dataset.skin).toBe('graphite')
        expect(useThemeStore.getState().skin).toBe('graphite')
    })

    it('setSkin updates dom and storage', () => {
        useThemeStore.getState().hydrate()
        useThemeStore.getState().setSkin('graphite')
        expect(localStorage.getItem('ta-skin')).toBe('graphite')
        expect(document.documentElement.dataset.skin).toBe('graphite')
        useThemeStore.getState().setSkin('linear')
        expect(localStorage.getItem('ta-skin')).toBe('linear')
        expect(document.documentElement.dataset.skin).toBe('linear')
        useThemeStore.getState().setSkin('default')
        expect(localStorage.getItem('ta-skin')).toBe('default')
        expect(document.documentElement.dataset.skin).toBe('default')
    })
})
