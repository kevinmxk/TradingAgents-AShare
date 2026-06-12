import { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Menu, TrendingUp } from 'lucide-react'

import { navItems } from '@/components/sidebarNav'

interface MobileLayoutProps {
    children: ReactNode
}

const primaryPaths = new Set(['/', '/analysis', '/reports', '/portfolio', '/settings'])

export default function MobileLayout({ children }: MobileLayoutProps) {
    const location = useLocation()
    const bottomItems = navItems.filter(item => primaryPaths.has(item.path))
    const secondaryItems = navItems.filter(item => !primaryPaths.has(item.path))

    return (
        <div className="mobile-layout min-h-screen overflow-x-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
            <header className="fixed inset-x-0 top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/90">
                <div className="flex h-14 items-center justify-between px-4">
                    <NavLink to="/" className="flex min-w-0 items-center gap-2">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-cyan-400 text-white shadow-sm">
                            <TrendingUp className="h-5 w-5" />
                        </span>
                        <span className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
                            TradingAgents
                        </span>
                    </NavLink>

                    <nav className="flex items-center gap-1">
                        {secondaryItems.slice(0, 2).map(item => (
                            <NavLink
                                key={item.path}
                                to={item.path}
                                className={({ isActive }) =>
                                    `flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
                                        isActive
                                            ? 'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300'
                                            : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900'
                                    }`
                                }
                                title={item.label}
                            >
                                <item.icon className="h-5 w-5" />
                            </NavLink>
                        ))}
                        <NavLink
                            to="/feedback"
                            className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900"
                            title="更多"
                        >
                            <Menu className="h-5 w-5" />
                        </NavLink>
                    </nav>
                </div>
            </header>

            <main className="min-h-screen overflow-x-hidden px-3 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-16">
                {children}
            </main>

            <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200/80 bg-white/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-12px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/92">
                <div className="grid h-16 grid-cols-5">
                    {bottomItems.map(item => {
                        const isRoot = item.path === '/'
                        const active = isRoot ? location.pathname === '/' : location.pathname.startsWith(item.path)

                        return (
                            <NavLink
                                key={item.path}
                                to={item.path}
                                className={`flex min-h-[44px] flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${
                                    active
                                        ? 'text-blue-600 dark:text-blue-300'
                                        : 'text-slate-500 dark:text-slate-400'
                                }`}
                            >
                                <item.icon className="h-5 w-5" />
                                <span className="max-w-full truncate px-1">{item.label}</span>
                            </NavLink>
                        )
                    })}
                </div>
            </nav>
        </div>
    )
}
