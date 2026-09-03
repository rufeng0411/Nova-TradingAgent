import { ReactNode } from 'react'
import MobileHeader from './MobileHeader'
import MobileBottomTab from './MobileBottomTab'
import { useAuthStore } from '@/stores/authStore'

interface MobileLayoutProps {
    children: ReactNode
    title?: string
    showBack?: boolean
    onBack?: () => void
    hideBottomTab?: boolean
}

export default function MobileLayout({ 
    children, 
    title, 
    showBack, 
    onBack, 
    hideBottomTab = false 
}: MobileLayoutProps) {
    const maintenance = useAuthStore((s) => s.publicFeatures?.maintenance)

    return (
        <div className="min-h-[100dvh] w-full flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
            {maintenance && (
                <div className="bg-amber-500 text-amber-950 text-center text-[10px] py-1.5 px-4 font-medium sticky top-0 z-50">
                    系统维护中，部分功能可能受限
                </div>
            )}
            
            <MobileHeader title={title} showBack={showBack} onBack={onBack} />
            
            <main className={`flex-1 w-full overflow-y-auto overflow-x-hidden ${hideBottomTab ? 'pb-[env(safe-area-inset-bottom)]' : 'pb-[calc(env(safe-area-inset-bottom)+3.5rem)]'}`}>
                {children}
            </main>
            
            {!hideBottomTab && <MobileBottomTab />}
        </div>
    )
}
