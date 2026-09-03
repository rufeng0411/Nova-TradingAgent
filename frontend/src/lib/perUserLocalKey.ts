/**
 * 与当前登录用户绑定的 localStorage 键（读取 `ta-user` JSON 中的 id）。
 * 未登录时使用 `signed-out`，避免多账号在同一浏览器串草稿数据。
 */
export function perUserLocalStorageKey(base: string): string {
    try {
        const raw = localStorage.getItem('ta-user')
        if (!raw) return `${base}:signed-out`
        const j = JSON.parse(raw) as { id?: string }
        if (j?.id && typeof j.id === 'string') return `${base}:${j.id}`
    } catch {
        /* ignore */
    }
    return `${base}:signed-out`
}
