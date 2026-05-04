export default function DashboardHome() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(239,117,80,0.22),_transparent_34%),linear-gradient(135deg,_#f8f1e4_0%,_#ecf6f7_100%)] px-6 py-10">
      <section className="mx-auto flex max-w-5xl flex-col gap-8 rounded-[2rem] border bg-card/85 p-8 shadow-2xl shadow-slate-900/10 backdrop-blur">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-primary">
            Step 1 Scaffold
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold tracking-tight text-foreground md:text-6xl">
            Multi-tenant AI chatbot control room
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-muted-foreground">
            The dashboard UI shell is ready. Step 4 will add URL ingestion, job polling,
            demo links, embed code, and the tenant chat experience.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {["Tenant isolation", "Async ingestion", "Hybrid RAG"].map((item) => (
            <div key={item} className="rounded-2xl border bg-background/70 p-5">
              <h2 className="font-semibold">{item}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Scaffolded for the production path without committing to placeholder data.
              </p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
