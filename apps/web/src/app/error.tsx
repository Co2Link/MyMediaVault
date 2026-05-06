"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="workspace">
      <section className="editor-card">
        <h1>Something went wrong.</h1>
        <p className="muted-copy">{error.message}</p>
        <button className="primary-button" type="button" onClick={() => reset()}>
          Try again
        </button>
      </section>
    </main>
  );
}
