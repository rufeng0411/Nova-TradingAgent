/** 将后端 `detail`（字符串或 FastAPI 校验数组）转为用户可读中文。 */

const CODE_ZH: Record<string, string> = {
    /** 旧接口/网关可能仍返回该码；与登录失败同等对待，避免卡在「验证码」上。 */
    captcha_invalid: '用户名或密码不正确，或该账号尚未设置密码（可尝试「忘记密码」）。',
    invalid_credentials: '用户名或密码不正确，或该账号尚未设置密码（可尝试「忘记密码」）。',
    too_many_requests: '请求过于频繁，请稍后再试。',
    invalid_or_expired_token: '重置链接无效或已过期，请重新申请找回密码。',
    invalid_password: '管理员密码不正确。',
    ADMIN_CONFIRM_REQUIRED: '请先完成敏感操作确认：在弹窗中输入您的管理员登录密码以获取确认令牌；若已确认过，请重新输入密码再试。',
    ADMIN_SCOPE_DENIED: '当前管理员账号没有执行此操作的权限（需要对应职能权限）。',
    ADMIN_UNKNOWN_FEATURE_KEY: '未知的功能开关键。',
    ADMIN_DOWNLOAD_CONSUMED: '该下载链接已使用或已失效，请重新导出。',
    not_found: '未找到请求的资源。',
    not_ready: '任务尚未完成，请稍后再试。',
    registration_disabled: '本站已关闭新用户注册。',
    invalid_username: '用户名格式不正确（3–50 位小写字母、数字、下划线）。',
    invalid_email: '邮箱格式不正确。',
    username_taken: '该用户名已被注册。',
    email_taken: '该邮箱已被注册。',
    no_password_set: '该账号尚未设置密码，请先使用「忘记密码」设置密码。',
}

export function formatApiErrorDetail(detail: unknown): string {
    if (detail == null || detail === '') return '请求失败，请稍后重试。'
    if (typeof detail === 'string') {
        const mapped = CODE_ZH[detail]
        if (mapped) return mapped
        if (detail.startsWith('too_many_requests:')) {
            return '请求过于频繁：' + detail.replace(/^too_many_requests:\s*/, '')
        }
        return detail
    }
    if (Array.isArray(detail)) {
        const parts = detail.map((item) => {
            if (item && typeof item === 'object' && 'msg' in item) {
                const o = item as { loc?: (string | number)[]; msg?: string; type?: string }
                const loc = Array.isArray(o.loc) ? o.loc.filter((x) => x !== 'body').join('.') : ''
                const m = o.msg || o.type || '校验失败'
                return loc ? `${loc}：${m}` : m
            }
            return String(item)
        })
        return parts.join('；')
    }
    if (typeof detail === 'object' && detail !== null && 'message' in (detail as object)) {
        return String((detail as { message: unknown }).message)
    }
    return String(detail)
}
