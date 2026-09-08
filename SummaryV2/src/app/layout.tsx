import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Delhi OD Passenger / Goods Survey Dashboard (Next.js)",
  description: "High-performance TrafficLenz OD survey data explorer with Neon PostgreSQL sync.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="h-full antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}

