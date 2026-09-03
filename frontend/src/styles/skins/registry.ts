/**
 * 皮肤注册表。新增皮肤：在此登记 id、显示名与 CSS 懒加载入口。
 */
export type ThemeSkinId = 'default' | 'linear' | 'graphite'

export interface SkinDefinition {
    id: ThemeSkinId
    /** 设置页 / 菜单展示名 */
    label: string
    /** 懒加载 CSS；默认皮肤无额外样式 */
    loadCss?: () => Promise<unknown>
}

export const SKINS: SkinDefinition[] = [
    { id: 'default', label: '默认' },
    {
        id: 'linear',
        label: 'Linear',
        loadCss: () => import('./linear.css'),
    },
    {
        id: 'graphite',
        label: '石墨',
        loadCss: () => import('./graphite.css'),
    },
]

export function isThemeSkinId(value: string | null | undefined): value is ThemeSkinId {
    return value === 'default' || value === 'linear' || value === 'graphite'
}
