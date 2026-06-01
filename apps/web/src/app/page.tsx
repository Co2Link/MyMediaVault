import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { VideoSearchForm } from "@/components/video-search-form";
import { VideoCard } from "@/components/video-card";
import { PaginationLinks } from "@/components/pagination-links";
import { firstQueryValue, paginate } from "@/lib/pagination";
import { searchVideos } from "@/lib/videos";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ page?: string | string[]; q?: string | string[] }>;
}) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/sign-in");
  }

  const query = await searchParams;
  const q = firstQueryValue(query.q) ?? "";
  const videos = await searchVideos(session.user.id, q);
  const page = paginate(videos, firstQueryValue(query.page), 12);

  return (
    <main className="workspace">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Collection</p>
          <h1>Your media vault</h1>
          <p className="lede">
            Search private notes and shared torrent metadata from one timeline-oriented collection view.
          </p>
        </div>
        <VideoSearchForm query={q} />
      </section>
      <section className="content-grid">
        {page.items.length === 0 ? (
          <div className="empty-panel">
            <h2>No videos match this search.</h2>
            <p className="muted-copy">Try a broader term or add a new title to seed the collection.</p>
          </div>
        ) : (
          page.items.map((video) => <VideoCard key={video.id} video={video} />)
        )}
      </section>
      <PaginationLinks page={page.page} pageCount={page.pageCount} pathname="/" query={q ? { q } : {}} />
    </main>
  );
}
