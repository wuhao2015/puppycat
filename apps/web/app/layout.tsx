import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "../lib/auth";
import { TripsProvider } from "../lib/trips";
import "./globals.css";

export const metadata: Metadata = {
  title: "Puppycat Travel",
  description: "Simple, friendly travel planning.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <TripsProvider>{children}</TripsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
