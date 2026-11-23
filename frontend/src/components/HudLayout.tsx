import { useState } from 'react';
import TelemetryPanel from '@/components/TelemetryPanel';
import StatusBar from '@/components/StatusBar';
import CommandLog from '@/components/CommandLog';
import FlightControls from '@/components/FlightControls';
import ActionButtons from '@/components/ActionButtons';
import SequenceBuilder from '@/components/SequenceBuilder';
import FlightAlerts from '@/components/FlightAlerts';
import MediaGallery from '@/components/MediaGallery';
import FlightsModal from '@/components/FlightsModal';

export default function HudLayout() {
  const [sequencerOpen, setSequencerOpen] = useState(false);
  const [flightsModalOpen, setFlightsModalOpen] = useState(false);

  return (
    <>
      <div
        className="fixed inset-0 z-[2] grid pointer-events-none"
        style={{
          padding: 'clamp(8px, 1vw, 16px)',
          gap: 'clamp(4px, 0.5vw, 8px)',
          gridTemplateColumns: 'minmax(180px, 220px) 1fr minmax(200px, 260px)',
          gridTemplateRows: 'auto 1fr',
          gridTemplateAreas: `
            "telemetry  .  status"
            "controls   .  ."
          `,
        }}
      >
        <div className="pointer-events-auto self-start" style={{ gridArea: 'telemetry' }}>
          <TelemetryPanel />
        </div>

        {/* StatusBar + CommandLog stacked together in top-right */}
        <div className="pointer-events-auto self-start justify-self-end flex flex-col gap-2" style={{ gridArea: 'status' }}>
          <StatusBar onOpenFlights={() => setFlightsModalOpen(true)} />
          <CommandLog />
        </div>

        <div className="pointer-events-auto self-end" style={{ gridArea: 'controls' }}>
          <FlightControls />
        </div>
      </div>

      {/* Action buttons — fixed bottom-center, outside grid */}
      <div className="fixed bottom-3 left-1/2 -translate-x-1/2 z-[2] pointer-events-auto sm:bottom-5">
        <ActionButtons onOpenSequences={() => setSequencerOpen((o) => !o)} />
      </div>

      <FlightAlerts />

      <MediaGallery />

      <SequenceBuilder isOpen={sequencerOpen} onClose={() => setSequencerOpen(false)} />

      <FlightsModal isOpen={flightsModalOpen} onClose={() => setFlightsModalOpen(false)} />
    </>
  );
}
