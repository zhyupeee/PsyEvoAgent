import { memo } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

const remarkPlugins = [remarkGfm]
const components: Components = {
  a: ({ href, children, title }) =>
    href ? (
      <a
        href={href}
        title={title}
        target="_blank"
        rel="noopener noreferrer"
        className="link-inline"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  // Model-provided images must not trigger automatic requests to third parties.
  img: ({ alt }) => <span className="text-muted">{alt || '图片'}</span>,
  pre: ({ children }) => (
    <pre tabIndex={0} aria-label="代码块，可横向滚动">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div
      className="my-4 max-w-full overflow-x-auto rounded-xl border border-line"
      role="region"
      aria-label="表格，可横向滚动"
      tabIndex={0}
    >
      <table>{children}</table>
    </div>
  ),
}

export const MarkdownMessage = memo(function MarkdownMessage({
  text,
}: {
  text: string
}) {
  return (
    <div className="markdown-content min-w-0 max-w-full leading-7 wrap-anywhere">
      <Markdown remarkPlugins={remarkPlugins} components={components} skipHtml>
        {text}
      </Markdown>
    </div>
  )
})
