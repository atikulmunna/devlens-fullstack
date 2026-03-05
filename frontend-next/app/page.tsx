import { getApiBase } from "@/lib/api";

export default function HomePage() {
  return (
    <section className="grid">
      <article className="card">
        <h2>Route</h2>
        <p className="mono">Rendered path: /</p>
      </article>
      <article className="card">
        <h2>Home</h2>
        <p className="muted">
          DevLens v1.1 home shell route is live in Next.js migration scaffold.
        </p>
      </article>
      <article className="card">
        <h2>Environment</h2>
        <p className="mono">NEXT_PUBLIC_API_URL: {getApiBase()}</p>
      </article>
      <article className="card">
        <h2>Global States</h2>
        <div className="notice">Loading state placeholder (used during route transitions and data fetch).</div>
        <div className="error">Error state placeholder (used for recoverable render/API failures).</div>
      </article>
    </section>
  );
}
