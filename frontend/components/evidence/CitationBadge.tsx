/** Inline [E1]-style citation that jumps to its evidence card. */
export function CitationBadge({ id, onClick }: { id: string; onClick?: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onClick?.(id)}
      className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded-md bg-primary/15 px-1.5 text-[11px] font-semibold text-primary hover:bg-primary/25"
      aria-label={`Show evidence ${id}`}
    >
      {id}
    </button>
  );
}
