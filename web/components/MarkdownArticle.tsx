import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

// External links leave the viewer, so they open a new window; relative links
// stay in-app. The override applies post-rehype-raw, so raw HTML anchors in
// generated pages get the same treatment as Markdown links.
const components: Components = {
  a({ node: _node, href, children, ...props }) {
    if (href && /^https?:\/\//i.test(href)) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
          {children}
        </a>
      );
    }
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
};

// GitHub-styled Markdown (github-markdown-css owns the typography under
// .markdown-body). Server-compatible; the one renderer for all surfaces.
export default function MarkdownArticle({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <article className={`markdown-body${className ? ` ${className}` : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </article>
  );
}
