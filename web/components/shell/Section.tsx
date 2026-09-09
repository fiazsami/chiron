"use client";

// An entry section: sans label + tabular count, 32px above / 12px below
// (spacing comes from .entry-body > section and .entry-section rules).

export default function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="entry-section">
        {title}
        {count !== undefined && <span className="count">{count}</span>}
      </h2>
      {children}
    </section>
  );
}
