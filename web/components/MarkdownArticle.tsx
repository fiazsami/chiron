import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

// prettier-ignore
const HTML_TAGS = new Set([
  "a", "abbr", "address", "area", "article", "aside", "audio", "b", "bdi",
  "bdo", "blockquote", "br", "button", "canvas", "caption", "cite", "code",
  "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn",
  "dialog", "div", "dl", "dt", "em", "embed", "fieldset", "figcaption",
  "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
  "hgroup", "hr", "i", "iframe", "img", "input", "ins", "kbd", "label",
  "legend", "li", "main", "mark", "menu", "meter", "nav", "ol", "optgroup",
  "option", "output", "p", "picture", "pre", "progress", "q", "rp", "rt",
  "ruby", "s", "samp", "section", "select", "small", "source", "span",
  "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th",
  "thead", "time", "tr", "track", "u", "ul", "var", "video", "wbr",
  // svg essentials
  "svg", "path", "circle", "rect", "g", "line", "polygon", "polyline",
  "text", "defs", "use",
]);

interface HastNode {
  type: string;
  tagName?: string;
  children?: HastNode[];
  value?: string;
}

// Corpus prose can contain angle-bracket tokens like "<type>" that the
// raw-HTML pass parses into elements no browser knows (React then warns,
// and sanitizing would silently delete the token from prose that is about
// it). Turn unknown elements back into the literal text they were.
function rehypeLiteralUnknowns() {
  return (tree: HastNode) => {
    const walk = (node: HastNode) => {
      if (!node.children) return;
      node.children = node.children.flatMap((child) => {
        walk(child);
        if (
          child.type === "element" &&
          child.tagName &&
          !HTML_TAGS.has(child.tagName)
        ) {
          return [
            { type: "text", value: `<${child.tagName}>` },
            ...(child.children ?? []),
            { type: "text", value: `</${child.tagName}>` },
          ];
        }
        return [child];
      });
    };
    walk(tree);
    return tree;
  };
}

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
        rehypePlugins={[rehypeRaw, rehypeLiteralUnknowns]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </article>
  );
}
