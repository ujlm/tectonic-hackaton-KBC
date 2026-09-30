import "./globals.css";

export const metadata = { title: "Kaat", description: "Kaat, a proactive banking assistant (hackathon demo, synthetic data)" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,600;6..12,700;6..12,800&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
