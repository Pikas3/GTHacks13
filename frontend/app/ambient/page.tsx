"use client";

import { Volume2, VolumeX } from "lucide-react";
import { useState } from "react";

import { AmbientResponse } from "@/components/ambient/AmbientResponse";
import { ConversationContext } from "@/components/ambient/ConversationContext";
import { TextQueryInput } from "@/components/ambient/TextQueryInput";
import { TranscriptPanel } from "@/components/ambient/TranscriptPanel";
import { VoiceOrb } from "@/components/ambient/VoiceOrb";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { HCPSelector } from "@/components/hcp/HCPSelector";
import { InteractionTimeline } from "@/components/hcp/InteractionTimeline";
import { AppHeader } from "@/components/layout/AppHeader";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useConversation } from "@/hooks/useConversation";
import { useHCP } from "@/hooks/useHCP";
import { isBusy } from "@/lib/orbMachine";
import type { EvidenceReference } from "@/lib/types";

export default function AmbientPage() {
  const hcp = useHCP();
  const convo = useConversation(hcp.selectedId, { onInteraction: hcp.refresh });
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [openSource, setOpenSource] = useState<EvidenceReference | null>(null);

  const evidence = convo.response?.evidence ?? [];
  const busy = isBusy(convo.state);

  const cite = (id: string) => {
    setHighlighted(id);
    document.getElementById(`evidence-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  };
  const viewSource = (e: EvidenceReference) => {
    setOpenSource(e);
    void convo.openSource(e);
  };

  return (
    <main className="flex min-h-dvh flex-col">
      <AppHeader>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => convo.setSpeechEnabled(!convo.speechEnabled)}
            aria-label={convo.speechEnabled ? "Mute spoken answers" : "Enable spoken answers"}
          >
            {convo.speechEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <HCPSelector hcps={hcp.hcps} selectedId={hcp.selectedId} onSelect={hcp.select} />
        </div>
      </AppHeader>

      <div className="grid flex-1 gap-6 px-4 pb-6 sm:px-8 lg:grid-cols-[1fr_340px]">
        <section className="flex flex-col items-center gap-6 pt-4">
          <ErrorBanner error={hcp.error ?? convo.error} className="w-full max-w-2xl" />
          <VoiceOrb
            state={convo.state}
            disabled={!hcp.selectedId}
            level={convo.level}
            onPressStart={() => void convo.pressStart()}
            onPressEnd={() => void convo.pressEnd()}
            onStopSpeaking={convo.stopSpeaking}
          />
          <TranscriptPanel transcript={convo.transcript} response={convo.response} />
          <AmbientResponse response={convo.response} onCite={cite} onFollowUp={(q) => void convo.submitText(q)} disabled={busy} />
          <TextQueryInput onSubmit={(q) => void convo.submitText(q)} disabled={busy || !hcp.selectedId} />
        </section>

        <aside className="flex flex-col gap-3">
          <ConversationContext context={convo.response?.context ?? null} timeline={hcp.timeline} />
          <InteractionTimeline entries={hcp.timeline} limit={6} />
        </aside>
      </div>

      <div className="border-t border-border/60 px-4 pt-4 sm:px-8">
        <EvidenceDrawer
          evidence={evidence}
          highlightedId={highlighted}
          openSource={openSource}
          onViewSource={viewSource}
          onCloseSource={() => setOpenSource(null)}
        />
      </div>
    </main>
  );
}
