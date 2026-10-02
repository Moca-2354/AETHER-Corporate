import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {title: "AETHER — AI Workspace", description: "社内の知識を、ひとつの会話へ。", robots: {index: false, follow: false}};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="ja"><body>{children}</body></html>;
}
