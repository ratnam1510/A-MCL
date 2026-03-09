import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "amcl — shared context for AI agents",
  description:
    "One persistent memory layer across Cursor, Claude, Amp. Every decision, conversation, and file change — always in sync.",
  openGraph: {
    title: "amcl",
    description: "Shared context for AI coding agents",
    siteName: "amcl",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
