import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Government Chatbot SaaS",
  description: "Multi-tenant AI chatbot dashboard for large government websites."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
