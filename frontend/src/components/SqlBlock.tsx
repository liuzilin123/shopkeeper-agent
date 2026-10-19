/**
 * SQL 展示组件
 * 折叠展示本次问数执行的 SQL，并支持一键复制
 */
import { Check, ChevronDown, ChevronRight, Code2, Copy } from "lucide-react";
import { useState } from "react";

export function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="mt-4 overflow-hidden border border-ink/10 bg-white/70 shadow-line">
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="flex min-h-11 flex-1 items-center gap-2 px-4 py-2.5 text-left text-sm font-semibold text-ink transition hover:bg-ink/[0.03]"
        >
          <Code2 className="h-4 w-4 text-brass" aria-hidden="true" />
          执行 SQL
          {open ? (
            <ChevronDown className="h-4 w-4 text-ink/45" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-ink/45" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          onClick={copy}
          className="mr-2 grid h-8 w-8 place-items-center rounded-full text-ink/45 transition hover:bg-ink/5 hover:text-ink"
          title="复制 SQL"
          aria-label="复制 SQL"
        >
          {copied ? (
            <Check className="h-4 w-4 text-moss" aria-hidden="true" />
          ) : (
            <Copy className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
      {open && (
        <pre className="max-h-72 overflow-auto border-t border-ink/10 bg-[#efe6d8]/40 px-4 py-3 font-mono text-[13px] leading-6 text-ink/80 whitespace-pre-wrap">
          {sql}
        </pre>
      )}
    </section>
  );
}
