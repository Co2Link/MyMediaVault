import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono } from "next/font/google";
import { auth } from "@/auth";
import { Header } from "@/components/header";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "MyMediaVault",
  description: "Authenticated video collection management with Entra ID.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await auth();

  return (
    <html lang="en" className={`${fraunces.variable} ${plexMono.variable}`}>
      <body>
        <div className="page-bg" />
        <div className="page-shell">
          <Header session={session as Parameters<typeof Header>[0]["session"]} />
          {children}
        </div>
      </body>
    </html>
  );
}
