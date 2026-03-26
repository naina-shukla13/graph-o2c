import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { Analytics } from '@vercel/analytics/next';
import './globals.css';

const geist = Geist({ 
  subsets: ["latin"], 
  variable: '--font-sans' 
});

const geistMono = Geist_Mono({ 
  subsets: ["latin"], 
  variable: '--font-mono' 
});

export const metadata: Metadata = {
  title: 'Supply Chain Explorer',
  description: 'Supply Chain Explorer',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${geist.variable} ${geistMono.variable} antialiased`}>
        {children}
        <Analytics />
      </body>
    </html>
  );
}