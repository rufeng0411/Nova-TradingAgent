/** 左侧分组导航：路径、权限 scope、建设状态（与升级计划信息架构对齐） */

export type AdminScope = 'superadmin' | 'finance' | 'ops' | 'content' | 'support'

export type AdminNavItem = {
    to: string
    label: string
    scope?: AdminScope
    status?: 'ready' | 'building'
}

export type AdminNavGroup = {
    id: string
    label: string
    items: AdminNavItem[]
}

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
    {
        id: 'reports',
        label: '分析报表',
        items: [
            { to: '/admin/reports/overview', label: '概览', status: 'ready' },
            { to: '/admin/reports/users-trend', label: '用户趋势', status: 'ready' },
            { to: '/admin/reports/projects-trend', label: '项目趋势', status: 'ready' },
            { to: '/admin/reports/revenue-trend', label: '收入趋势', scope: 'finance', status: 'ready' },
            { to: '/admin/reports/usage-trend', label: '用量趋势', status: 'ready' },
            { to: '/admin/reports/ops-stats', label: '运营统计', status: 'ready' },
            { to: '/admin/reports/feature-token', label: '功能与 Token', status: 'ready' },
        ],
    },
    {
        id: 'commerce',
        label: '商业化与结算',
        items: [
            { to: '/admin/commerce/orders', label: '订单管理', scope: 'finance', status: 'ready' },
            { to: '/admin/plans', label: '套餐配置', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/pricing', label: '计费表格', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/credit-packages', label: '礼包管理', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/payment-settings', label: '支付配置', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/credit-ledger', label: '点数账本', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/reconciliation', label: '对账中心', scope: 'finance', status: 'ready' },
            { to: '/admin/commerce/api-costs', label: 'API 成本管理', scope: 'finance', status: 'ready' },
        ],
    },
    {
        id: 'ops',
        label: '运行与观测',
        items: [
            { to: '/admin/ops/tasks', label: '任务管理', scope: 'ops', status: 'ready' },
            { to: '/admin/ops/usage', label: '用量记录', scope: 'ops', status: 'ready' },
            { to: '/admin/ops/ai-calls', label: 'AI 调用日志', scope: 'ops', status: 'ready' },
            { to: '/admin/signals', label: '事件信号', scope: 'ops', status: 'ready' },
        ],
    },
    {
        id: 'security',
        label: '安全与审计',
        items: [
            { to: '/admin/audit-logs', label: '后台操作日志', status: 'ready' },
            { to: '/admin/access-logs', label: '用户访问日志', scope: 'ops', status: 'ready' },
        ],
    },
    {
        id: 'content',
        label: '内容与品牌',
        items: [
            { to: '/admin/content/home', label: '首页管理', scope: 'content', status: 'ready' },
            { to: '/admin/content/assets', label: '素材库', scope: 'content', status: 'ready' },
            { to: '/admin/content/messages', label: '站内信', scope: 'content', status: 'ready' },
            { to: '/admin/content/appearance', label: '外观设置', scope: 'content', status: 'ready' },
        ],
    },
    {
        id: 'tools',
        label: '通用',
        items: [
            { to: '/admin/users', label: '用户管理', scope: 'support', status: 'ready' },
            { to: '/admin/exports', label: '导出中心', status: 'ready' },
        ],
    },
]

export function adminHasScope(
    permissions: string[] | null | undefined,
    scope: AdminScope | undefined,
): boolean {
    if (!scope) return true
    if (permissions == null || permissions.length === 0) return true
    if (permissions.includes('superadmin')) return true
    return permissions.includes(scope)
}

export function filterAdminNavGroups(
    groups: AdminNavGroup[],
    permissions: string[] | null | undefined,
): AdminNavGroup[] {
    return groups
        .map((g) => ({
            ...g,
            items: g.items.filter((it) => adminHasScope(permissions, it.scope)),
        }))
        .filter((g) => g.items.length > 0)
}
