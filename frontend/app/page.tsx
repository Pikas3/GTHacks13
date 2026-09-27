import { AudioLines, BarChart3 } from "lucide-react";
import Link from "next/link";

import { AppHeader } from "@/components/layout/AppHeader";

export default function Home() {
  return (
    <main>
      <AppHeader />
      <section className="mx-auto flex max-w-3xl flex-col items-center gap-6 px-4 py-16 text-center">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Ask. Remember. Ground every answer.</h1>
        <p className="max-w-xl text-muted-foreground">
          AskLepius is a voice-native assistant for HCPs over trusted resources. It remembers what each HCP
          reviewed, knows what changed since, cites approved evidence, and turns every interaction into structured
          engagement signals.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link href="/lepius" className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 font-medium text-primary-foreground">
            <AudioLines className="h-4 w-4" /> Open Lepius
          </Link>
          <Link href="/intelligence" className="inline-flex items-center gap-2 rounded-full border border-border px-5 py-2.5 font-medium">
            <BarChart3 className="h-4 w-4" /> Intelligence
          </Link>
        </div>
      </section>
    </main>
  );
}
