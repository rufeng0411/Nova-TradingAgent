import { useState, useEffect } from 'react'

/**
 * 检测当前是否为移动设备环境
 * 基于屏幕宽度 (< 768px) 和 userAgent 进行双重判断
 */
export function useMobile() {
    const [isMobile, setIsMobile] = useState<boolean>(() => {
        // SSR / 未挂载时默认安全后备
        if (typeof window === 'undefined') return false
        
        // 1. 媒体查询检测
        const matchMedia = window.matchMedia('(max-width: 768px)').matches
        
        // 2. UA 检测（可选增强）
        const ua = navigator.userAgent || navigator.vendor || (window as any).opera
        const isMobileUA = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(ua.toLowerCase())

        return matchMedia || isMobileUA
    })

    useEffect(() => {
        if (typeof window === 'undefined') return

        const mediaQuery = window.matchMedia('(max-width: 768px)')
        const handleChange = (e: MediaQueryListEvent) => {
            // 当尺寸变化时，重新评估（这里不严格校验 UA 了，以防 PC 模拟手机调试）
            setIsMobile(e.matches)
        }

        // 兼容新老版 API
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleChange)
        } else {
            mediaQuery.addListener(handleChange)
        }

        return () => {
            if (mediaQuery.removeEventListener) {
                mediaQuery.removeEventListener('change', handleChange)
            } else {
                mediaQuery.removeListener(handleChange)
            }
        }
    }, [])

    return isMobile
}
