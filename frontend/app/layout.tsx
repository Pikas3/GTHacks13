import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Impiricus Ambient",
  description: "Hackathon prototype: voice-native, context-aware HCP engagement. Synthetic data only.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        {children}
        <footer className="px-4 pb-4 text-center text-[11px] text-muted-foreground sm:px-8">
          Hackathon prototype · synthetic HCPs and fictional products (Novara, Cardexa, Lumetrex) · not medical advice
        </footer>
      </body>
    </html>
  );
}
