import { useEffect, useState } from 'react'

export interface ResponsiveBreakpoints {
    mobile: number
    desktop: number
}

const DEFAULT_BREAKPOINTS: ResponsiveBreakpoints = {
    mobile: 768,
    desktop: 1024,
}

function getViewportWidth(): number {
    if (typeof window === 'undefined') return DEFAULT_BREAKPOINTS.desktop
    return window.innerWidth
}

export function useResponsive(breakpoints: ResponsiveBreakpoints = DEFAULT_BREAKPOINTS) {
    const [width, setWidth] = useState(getViewportWidth)

    useEffect(() => {
        if (typeof window === 'undefined') return undefined

        const handleResize = () => setWidth(window.innerWidth)
        handleResize()
        window.addEventListener('resize', handleResize)

        return () => window.removeEventListener('resize', handleResize)
    }, [])

    return {
        width,
        isMobile: width < breakpoints.mobile,
        isTablet: width >= breakpoints.mobile && width < breakpoints.desktop,
        isDesktop: width >= breakpoints.desktop,
    }
}
