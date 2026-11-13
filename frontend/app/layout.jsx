import "./globals.css";

export const metadata = {
  title: "צייד כרטיסים",
  description: "מעקב אחר מכירת כרטיסים להופעות",
  manifest: "/manifest.json",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#4f46e5",
};

export default function RootLayout({ children }) {
  return (
    <html lang="he" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
