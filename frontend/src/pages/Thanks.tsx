import { useEffect, useState } from 'react'
import { ArrowLeft, Github, Heart, Cpu, Code2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { getBaseUrl } from '@/services/api'

interface SponsorItem {
    id: string
    sponsor_type: string
    name: string
    github?: string | null
    avatar?: string | null
    email?: string | null
    provider?: string | null
    date: string
}

interface SponsorsData {
    money: SponsorItem[]
    token: SponsorItem[]
}

/** 与 `public/contributors.json` 中条目一致；头像请使用站内路径或你方 CDN，勿依赖第三方域名。 */
interface ContributorEntry {
    login: string
    avatar_url: string
    html_url?: string
    contributions: number
}

interface ContributorsFile {
    contributors?: ContributorEntry[]
    upstream?: {
        name: string
        subtitle?: string
        avatar_url?: string
    } | null
}

function Avatar({ name, avatar, size = 'md' }: { name: string; avatar?: string | null; size?: 'sm' | 'md' }) {
    const dim = size === 'sm' ? 'w-10 h-10' : 'w-12 h-12'
    const textSize = size === 'sm' ? 'text-sm' : 'text-base'

    if (avatar) {
        return (
            <img
                src={avatar}
                alt={name}
                className={`${dim} rounded-full object-cover ring-2 ring-white dark:ring-slate-800`}
            />
        )
    }

    const initials = name.slice(0, 1).toUpperCase()
    return (
        <div className={`${dim} rounded-full bg-gradient-to-br from-slate-200 to-slate-300 dark:from-slate-700 dark:to-slate-600 flex items-center justify-center ring-2 ring-white dark:ring-slate-800`}>
            <span className={`${textSize} font-bold text-slate-500 dark:text-slate-300`}>{initials}</span>
        </div>
    )
}

function formatDate(dateStr: string): string {
    const d = new Date(dateStr)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

function SponsorCard({ name, avatar, email, date, badge, badgeColor, extra }: {
    name: string
    avatar?: string
    email?: string
    date: string
    badge: string
    badgeColor: string
    extra?: string
}) {
    return (
        <div className="group relative flex items-center gap-3 px-4 py-3 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-colors">
            <Avatar name={name} avatar={avatar} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">{name}</span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded-full ${badgeColor}`}>{badge}</span>
                    {extra && <span className="text-[11px] text-slate-400 dark:text-slate-500">{extra}</span>}
                    <span className="text-[11px] text-slate-400 dark:text-slate-500">{formatDate(date)}</span>
                </div>
            </div>
            {email && (
                <div className="absolute left-1/2 -translate-x-1/2 -top-9 px-2.5 py-1 rounded-lg bg-slate-800 dark:bg-slate-700 text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-lg">
                    {email}
                </div>
            )}
        </div>
    )
}

export default function Thanks() {
    const navigate = useNavigate()
    const [sponsors, setSponsors] = useState<SponsorsData | null>(null)
    const [contributors, setContributors] = useState<ContributorEntry[]>([])
    const [upstream, setUpstream] = useState<ContributorsFile['upstream']>(null)
    const [loadingContributors, setLoadingContributors] = useState(true)
    const [excludeContributors, setExcludeContributors] = useState<string[]>([])

    useEffect(() => {
        fetch(`${getBaseUrl()}/v1/sponsors`)
            .then(res => res.json())
            .then(setSponsors)
            .catch(() => setSponsors({ money: [], token: [] }))

        fetch('/sponsors.json')
            .then(res => res.json())
            .then(data => setExcludeContributors(data.excludeContributors ?? []))
            .catch(() => {})
    }, [])

    useEffect(() => {
        const excludeSet = new Set(excludeContributors)

        fetch('/contributors.json')
            .then((res) => (res.ok ? res.json() : Promise.resolve({})))
            .then((data: ContributorsFile) => {
                const list = Array.isArray(data.contributors) ? data.contributors : []
                setContributors(list.filter((c) => c.login && !excludeSet.has(c.login)))
                setUpstream(data.upstream ?? null)
            })
            .catch(() => {
                setContributors([])
                setUpstream(null)
            })
            .finally(() => setLoadingContributors(false))
    }, [excludeContributors])

    const hasMoney = sponsors && sponsors.money.length > 0
    const hasToken = sponsors && sponsors.token.length > 0
    const showUpstream = upstream && upstream.name

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-amber-50/20 to-slate-100 dark:from-slate-950 dark:via-amber-950/5 dark:to-slate-950 flex items-center justify-center p-6">
            <div className="w-full max-w-3xl">
                <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm rounded-3xl border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
                    {/* Header */}
                    <div className="bg-gradient-to-r from-amber-500 to-orange-500 px-6 py-5 text-center">
                        <Heart className="w-8 h-8 text-white mx-auto mb-2" fill="white" />
                        <h1 className="text-xl font-bold text-white">致谢</h1>
                        <p className="text-amber-100 text-sm mt-1">感谢每一位支持者，让项目走得更远</p>
                    </div>

                    <div className="px-6 py-6 space-y-8">
                        {/* Money Sponsors */}
                        {hasMoney && (
                            <section>
                                <div className="flex items-center gap-2 mb-4">
                                    <Heart className="w-4 h-4 text-pink-500" />
                                    <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide">资金赞助</h2>
                                    <span className="text-xs text-slate-400 dark:text-slate-500">· {sponsors!.money.length} 位</span>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {sponsors!.money.map((s, i) => (
                                        <SponsorCard
                                            key={`money-${i}`}
                                            name={s.name}
                                            avatar={s.avatar || undefined}
                                            email={s.email || undefined}
                                            date={s.date}
                                            badge="资金赞助"
                                            badgeColor="bg-pink-50 text-pink-600 dark:bg-pink-500/15 dark:text-pink-300"
                                        />
                                    ))}
                                </div>
                            </section>
                        )}

                        {/* Token Sponsors */}
                        {hasToken && (
                            <section>
                                <div className="flex items-center gap-2 mb-4">
                                    <Cpu className="w-4 h-4 text-violet-500" />
                                    <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide">Token 赞助</h2>
                                    <span className="text-xs text-slate-400 dark:text-slate-500">· {sponsors!.token.length} 位</span>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {sponsors!.token.map((s, i) => (
                                        <SponsorCard
                                            key={`token-${i}`}
                                            name={s.name}
                                            avatar={s.avatar || undefined}
                                            date={s.date}
                                            badge={s.provider ?? ""}
                                            badgeColor="bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300"
                                            extra="Token 赞助"
                                        />
                                    ))}
                                </div>
                            </section>
                        )}

                        {/* Code Contributors */}
                        <section>
                            <div className="flex items-center gap-2 mb-4">
                                <Code2 className="w-4 h-4 text-emerald-500" />
                                <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide">代码贡献</h2>
                                {contributors.length > 0 && (
                                    <span className="text-xs text-slate-400 dark:text-slate-500">· {contributors.length} 位</span>
                                )}
                            </div>
                            {loadingContributors ? (
                                <div className="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">加载中...</div>
                            ) : contributors.length > 0 ? (
                                <div className="flex flex-wrap gap-3">
                                    {contributors.map((c) => (
                                        <div
                                            key={c.login}
                                            className="group relative"
                                            title={`@${c.login} · ${c.contributions} commits`}
                                        >
                                            <img
                                                src={c.avatar_url}
                                                alt={c.login}
                                                className="w-12 h-12 rounded-full ring-2 ring-white dark:ring-slate-800 group-hover:ring-emerald-400 dark:group-hover:ring-emerald-500 transition-all group-hover:scale-110"
                                            />
                                            <span className="absolute -bottom-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-emerald-500 text-white text-[10px] font-bold flex items-center justify-center shadow-sm">
                                                {c.contributions}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">
                                    暂无贡献者数据。可在 <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 rounded">public/contributors.json</code> 中配置（私有化部署无外链）。
                                </div>
                            )}
                        </section>

                        {/* Upstream — 仅当 contributors.json 提供 upstream 时展示 */}
                        {showUpstream && (
                            <section>
                                <div className="flex items-center gap-2 mb-3">
                                    <Github className="w-4 h-4 text-slate-500" />
                                    <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide">上游项目</h2>
                                </div>
                                <div className="flex items-center gap-4 px-4 py-3 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                                    {upstream.avatar_url ? (
                                        <img
                                            src={upstream.avatar_url}
                                            alt=""
                                            className="w-10 h-10 rounded-full ring-2 ring-white dark:ring-slate-700 object-cover"
                                        />
                                    ) : (
                                        <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-slate-600 ring-2 ring-white dark:ring-slate-700" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{upstream.name}</div>
                                        {upstream.subtitle && (
                                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{upstream.subtitle}</div>
                                        )}
                                    </div>
                                </div>
                            </section>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="px-6 pb-6 flex items-center justify-center">
                        <button
                            onClick={() => navigate(-1)}
                            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            返回
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
