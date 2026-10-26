import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AICTE CaseSync — Complaint Operations",
  description: "Synthetic demonstration of cross-bureau complaint coordination"
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}

