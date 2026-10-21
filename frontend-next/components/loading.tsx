// Gray stand-ins shaped like the content on its way, so the page does not jump when it arrives.
// Screen readers hear the label once instead of the shapes.

// Each number is one card and how many lines of text it gets.
export function LoadingCards({ label, cards }: { label: string; cards: number[] }) {
  return (
    <div className="loading-cards" role="status">
      <span className="visually-hidden">{label}</span>
      {cards.map((lines, index) => (
        <div key={index} className="card" aria-hidden="true">
          <span className="skeleton skeleton-heading" />
          {Array.from({ length: lines }, (_, line) => (
            <span key={line} className="skeleton skeleton-line" />
          ))}
        </div>
      ))}
    </div>
  );
}

// One block inside a card, for a graph or list that loads after the card itself.
export function LoadingBlock({ label }: { label: string }) {
  return (
    <div role="status">
      <span className="visually-hidden">{label}</span>
      <span className="skeleton skeleton-block" aria-hidden="true" />
    </div>
  );
}

// The repository header while the repository is looked up: the name is known from the URL.
export function RepoLoading({ name }: { name: string }) {
  return (
    <>
      <header className="repo-header" aria-hidden="true">
        <h1 className="repo-title">{name}</h1>
        <span className="skeleton skeleton-line" />
        <span className="skeleton skeleton-tabs" />
      </header>
      <LoadingCards label={`Loading ${name}`} cards={[3, 2]} />
    </>
  );
}

export function LoadingPill({ label }: { label: string }) {
  return (
    <span className="skeleton skeleton-pill" role="status">
      <span className="visually-hidden">{label}</span>
    </span>
  );
}
