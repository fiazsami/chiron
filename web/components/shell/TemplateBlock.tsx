"use client";

import { Fragment } from "react";
import { useShell } from "./shell-context";

// phrase.template as a code block with {slots} highlighted. Slots are
// unparsed free text by design — highlighting is purely visual.

export default function TemplateBlock({ template }: { template: string }) {
  const { copied } = useShell();
  const parts = template.split(/(\{[^}]*\})/);
  return (
    <div className="template-wrap">
      <div className="copy-hint">{copied ? "copied" : "y copies"}</div>
      <pre className="template-block">
        <code>
          {parts.map((part, i) =>
            part.startsWith("{") && part.endsWith("}") ? (
              <span key={i} className="slot">
                {part}
              </span>
            ) : (
              <Fragment key={i}>{part}</Fragment>
            ),
          )}
        </code>
      </pre>
    </div>
  );
}
