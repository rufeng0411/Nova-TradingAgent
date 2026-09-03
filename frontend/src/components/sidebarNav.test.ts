import { describe, expect, it } from 'vitest'

import { navItems } from '@/components/sidebarNav'

describe('sidebarNav', () => {
    it('includes chart route after analysis', () => {
        const analysisIndex = navItems.findIndex((item) => item.path === '/analysis')
        const chartIndex = navItems.findIndex((item) => item.path === '/chart')
        const tasksIndex = navItems.findIndex((item) => item.path === '/tasks')
        expect(analysisIndex).toBeGreaterThanOrEqual(0)
        expect(chartIndex).toBe(analysisIndex + 1)
        expect(tasksIndex).toBe(chartIndex + 1)
        expect(navItems[chartIndex]).toMatchObject({
            path: '/chart',
            label: 'K线分析',
        })
        expect(navItems[tasksIndex]).toMatchObject({
            path: '/tasks',
            label: '任务中心',
        })
    })

    it('includes a dedicated tracking board entry in the sidebar', () => {
        const dashboardIndex = navItems.findIndex(item => item.path === '/')
        const trackingBoardIndex = navItems.findIndex(item => item.path === '/tracking-board')

        expect(trackingBoardIndex).toBeGreaterThan(0)
        expect(dashboardIndex).toBe(0)
        expect(navItems[trackingBoardIndex]).toMatchObject({
            path: '/tracking-board',
            label: '跟踪看板',
        })
        expect(trackingBoardIndex).toBeGreaterThan(dashboardIndex)
    })
})
