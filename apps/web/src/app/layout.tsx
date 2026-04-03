import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GradeAgent",
  description: "Gemini-routed browser grading console for short Swedish text submissions."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
