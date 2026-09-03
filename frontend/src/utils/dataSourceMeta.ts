import type { DataSourceItem } from '@/types'

export const DEFAULT_VENDOR_ICON = '/vendor-icons/internal.svg'

type VendorMeta = {
    display: string
    site: string
    icon: string
}

export const VENDOR_META: Record<string, VendorMeta> = {
    cn_akshare: {
        display: 'AkShare（聚合东财/新浪/腾讯/雪球）',
        site: 'https://akshare.akfamily.xyz/',
        icon: '/vendor-icons/cn_akshare.svg',
    },
    cn_baostock: {
        display: 'BaoStock',
        site: 'http://baostock.com/',
        icon: '/vendor-icons/cn_baostock.svg',
    },
    cn_tushare: {
        display: 'Tushare Pro',
        site: 'https://tushare.pro/',
        icon: '/vendor-icons/cn_tushare.svg',
    },
    yfinance: {
        display: 'Yahoo Finance',
        site: 'https://finance.yahoo.com/',
        icon: '/vendor-icons/yfinance.svg',
    },
    alpha_vantage: {
        display: 'Alpha Vantage',
        site: 'https://www.alphavantage.co/',
        icon: '/vendor-icons/alpha_vantage.svg',
    },
    juchao: {
        display: '巨潮资讯（CNINFO）',
        site: 'http://www.cninfo.com.cn/',
        icon: '/vendor-icons/internal.svg',
    },
    stats_cn: {
        display: '国家统计局',
        site: 'http://data.stats.gov.cn/',
        icon: '/vendor-icons/internal.svg',
    },
    fred: {
        display: 'FRED（圣路易斯联储）',
        site: 'https://fred.stlouisfed.org/',
        icon: '/vendor-icons/internal.svg',
    },
    internal: {
        display: '本地计算（指标/VPA）',
        site: '',
        icon: '/vendor-icons/internal.svg',
    },
}

export function getVendorMeta(vendor?: string | null): VendorMeta {
    if (!vendor) {
        return {
            display: '未知来源',
            site: '',
            icon: DEFAULT_VENDOR_ICON,
        }
    }
    return VENDOR_META[vendor] ?? {
        display: vendor,
        site: '',
        icon: DEFAULT_VENDOR_ICON,
    }
}

export function getItemVendorDisplay(item: DataSourceItem): string {
    return item.vendor_display || getVendorMeta(item.vendor).display
}

export function getItemVendorSite(item: DataSourceItem): string {
    return item.vendor_site || getVendorMeta(item.vendor).site
}

export function getItemVendorIcon(item: DataSourceItem): string {
    const icon = getVendorMeta(item.vendor).icon
    return icon || DEFAULT_VENDOR_ICON
}
