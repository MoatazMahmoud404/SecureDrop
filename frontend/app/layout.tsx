import type { ReactNode } from 'react';
import './globals.css';
import AppShell from './components/AppShell';

export const metadata = {
  title: 'SecureDrop',
  description: 'Secure file transfer web application',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
