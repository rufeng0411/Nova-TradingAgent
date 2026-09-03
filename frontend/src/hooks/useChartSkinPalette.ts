import { useMemo } from 'react'
import { useThemeStore } from '@/stores/themeStore'

export interface ChartSkinPalette {
    textColor: string
    gridColor: string
    borderColor: string
    crosshairVert: string
    crosshairHorz: string
}

/** K 线 / ProChart 非 Tailwind 通道：默认皮肤与现有一致，Linear 为低饱和网格与坐标 */
export function useChartSkinPalette(isDark: boolean): ChartSkinPalette {
    const skin = useThemeStore((s) => s.skin)

    return useMemo(() => {
        if (skin === 'linear') {
            return {
                textColor: isDark ? '#a3a3a3' : '#525252',
                gridColor: isDark ? 'rgba(64, 64, 64, 0.45)' : 'rgba(0, 0, 0, 0.06)',
                borderColor: isDark ? '#404040' : '#e5e5e5',
                crosshairVert: isDark ? 'rgba(113, 112, 255, 0.45)' : 'rgba(94, 106, 210, 0.35)',
                crosshairHorz: isDark ? 'rgba(113, 112, 255, 0.45)' : 'rgba(94, 106, 210, 0.35)',
            }
        }
        if (skin === 'graphite') {
            return {
                textColor: isDark ? '#a1a1aa' : '#4b5563',
                gridColor: isDark ? 'rgba(38, 38, 38, 0.5)' : 'rgba(209, 213, 219, 0.85)',
                borderColor: isDark ? '#262626' : '#d1d5db',
                crosshairVert: isDark ? 'rgba(129, 140, 248, 0.42)' : 'rgba(79, 70, 229, 0.32)',
                crosshairHorz: isDark ? 'rgba(129, 140, 248, 0.42)' : 'rgba(79, 70, 229, 0.32)',
            }
        }
        return {
            textColor: isDark ? '#94a3b8' : '#475569',
            gridColor: isDark ? 'rgba(51, 65, 85, 0.6)' : 'rgba(203, 213, 225, 0.6)',
            borderColor: isDark ? '#334155' : '#cbd5e1',
            crosshairVert: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)',
            crosshairHorz: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)',
        }
    }, [isDark, skin])
}
