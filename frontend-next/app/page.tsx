import { getApiBase } from "@/lib/api";

export default function HomePage() {
  return (
    <section className="grid">
      <article className="card">
        <h2>Home</h2>
        <p className="muted">
          This is a parallel migration shell for Next.js + TypeScript. The existing frontend service remains
          unchanged in production.
        </p>
      </article>
      <article className="card">
        <h2>Environment</h2>
        <p className="mono">NEXT_PUBLIC_API_URL: {getApiBase()}</p>
      </article>
    </section>
  );
}
