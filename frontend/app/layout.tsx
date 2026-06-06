import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'w.LiGHTER | Web Novel Localization Studio',
  description: 'AI powered web novel localization workflow',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
