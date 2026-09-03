/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_URL: string
    /** 开发环境下设为 1 时，不再走 Vite 代理，改用 VITE_API_URL 直连后端 */
    readonly VITE_DEV_API_DIRECT: string
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}

declare const __APP_BUILD_COMMIT__: string
declare const __APP_BUILD_DATE__: string
declare const __APP_BUILD_VERSION__: string
