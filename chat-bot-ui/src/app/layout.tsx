import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RAG pgvector chat",
  description: "Chat UI for rag-pgvector question-api POST /ask",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
      style={
        {
          ["--font-sans" as string]: "var(--font-geist-sans)",
          ["--font-mono" as string]: "var(--font-geist-mono)",
        } as CSSProperties
      }
    >
      <body className="antialiased">{children}</body>
    </html>
  );
}
