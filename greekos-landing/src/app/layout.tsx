import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GreekOS — Chapter Intelligence",
  description:
    "The AI-native operating system for Greek-letter organizations. Manage dues, events, tasks, officers, accountability, and chapter memory.",
  openGraph: {
    title: "GreekOS — Chapter Intelligence",
    description:
      "AI-native operations for modern Greek life.",
    type: "website",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
