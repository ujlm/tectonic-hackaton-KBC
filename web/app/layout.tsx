export const metadata = { title: "Kate", description: "Kate, a proactive banking assistant (hackathon demo, synthetic data)" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
