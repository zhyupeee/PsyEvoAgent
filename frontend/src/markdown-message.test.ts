import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkdownMessage } from './markdown-message'

const render = (text: string) =>
  renderToStaticMarkup(createElement(MarkdownMessage, { text }))

describe('AI Markdown rendering', () => {
  it('renders structured replies including GFM tables and code as semantic HTML', () => {
    const html = render(
      [
        '## A small step',
        '',
        '**Bold** and *emphasis*, ~~removed~~ and `inline`.',
        '',
        '1. First',
        '2. Second',
        '   - Nested',
        '',
        '> Take your time.',
        '',
        '- [x] Done',
        '',
        '| Action | Time |',
        '| --- | ---: |',
        '| Pause | 5 min |',
        '',
        '```js',
        'const example = "<script>"',
        '```',
      ].join('\n'),
    )
    expect(html).toContain('<h2>A small step</h2>')
    expect(html).toContain('<strong>Bold</strong>')
    expect(html).toContain('<em>emphasis</em>')
    expect(html).toContain('<del>removed</del>')
    expect(html).toContain('<ol>')
    expect(html).toContain('<li>Nested</li>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('type="checkbox" disabled="" checked=""')
    expect(html).toContain('<table>')
    expect(html).toContain('<td style="text-align:right">5 min</td>')
    expect(html).toContain('class="language-js"')
    expect(html).toContain('&lt;script&gt;')
  })

  it('does not execute model HTML, unsafe URLs or automatically load images', () => {
    const html = render(
      [
        '<script>alert(1)</script>',
        '',
        '<img src="https://example.com/track" onerror="alert(1)">',
        '',
        '[bad](javascript:alert%281%29)',
        '[data](data:text/html,test)',
        '![Image description](https://example.com/track.png)',
        '',
        '[Reference](https://example.com/info)',
      ].join('\n'),
    )
    expect(html).not.toMatch(/<script|<img|onerror|javascript:|data:text|track/)
    expect(html).toContain('Image description')
    expect(html).toContain('href="https://example.com/info"')
    expect(html).toContain('target="_blank" rel="noopener noreferrer"')
  })
})
