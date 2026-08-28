import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Renders artifact markdown — briefs, plans, reports.
 *
 * react-markdown builds React elements rather than setting innerHTML, so
 * agent-authored content cannot inject markup. Do not swap this for a
 * parse-to-HTML library without a sanitiser: this content is written by agents
 * reading arbitrary repositories.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Anything the agent links to is external and untrusted.
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow">
              {children}
            </a>
          ),
          // Wide tables scroll inside their own container rather than pushing
          // the whole page sideways.
          table: ({ children }) => (
            <div className="md-table-wrap">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
