import { Link } from '@tanstack/react-router'

export function Brand() {
  return (
    <Link
      to="/"
      className="inline-flex items-center gap-2 font-brand text-xl font-semibold"
      aria-label="PsyEvoAgent 首页"
    >
      <img
        src="/brand/logo.png"
        width="32"
        height="32"
        alt=""
        className="h-8 w-8 object-contain"
      />
      <span>PsyEvoAgent</span>
    </Link>
  )
}
