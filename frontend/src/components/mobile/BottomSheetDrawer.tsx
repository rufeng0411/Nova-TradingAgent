import { ReactNode, useEffect, useState } from 'react'

interface BottomSheetDrawerProps {
    isOpen: boolean
    onClose: () => void
    children: ReactNode
    title?: string
    heightClass?: string // 例如 'h-[80vh]' 默认半屏
}

export default function BottomSheetDrawer({ 
    isOpen, 
    onClose, 
    children, 
    title,
    heightClass = 'h-[75vh]' 
}: BottomSheetDrawerProps) {
    const [render, setRender] = useState(isOpen)
    const [visible, setVisible] = useState(false)

    useEffect(() => {
        if (isOpen) {
            setRender(true)
            // 延迟一帧触发动画
            requestAnimationFrame(() => setVisible(true))
            // 锁定 body 滚动
            document.body.style.overflow = 'hidden'
        } else {
            setVisible(false)
            // 动画完成后卸载
            const timer = setTimeout(() => {
                setRender(false)
                document.body.style.overflow = ''
            }, 300)
            return () => clearTimeout(timer)
        }
        return () => {
            document.body.style.overflow = ''
        }
    }, [isOpen])

    if (!render) return null

    return (
        <div className="fixed inset-0 z-[100] flex flex-col justify-end">
            <div 
                className={`absolute inset-0 bg-slate-900/40 dark:bg-black/60 backdrop-blur-sm transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
                onClick={onClose}
            />
            <div 
                className={`relative w-full ${heightClass} bg-white dark:bg-slate-900 rounded-t-3xl shadow-xl flex flex-col transform transition-transform duration-300 ease-out ${visible ? 'translate-y-0' : 'translate-y-full'}`}
            >
                <div className="flex justify-center py-3" onClick={onClose}>
                    <div className="w-12 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full" />
                </div>
                {title && (
                    <div className="px-5 pb-3 font-bold text-lg text-slate-900 dark:text-slate-100 border-b border-slate-100 dark:border-slate-800">
                        {title}
                    </div>
                )}
                <div className="flex-1 overflow-y-auto p-5">
                    {children}
                </div>
            </div>
        </div>
    )
}
