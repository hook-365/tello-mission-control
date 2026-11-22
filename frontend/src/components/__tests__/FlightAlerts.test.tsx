import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FlightAlerts from '@/components/FlightAlerts';
import StatusBar from '@/components/StatusBar';
import { useDroneStore } from '@/stores/droneStore';
import { playAlarm } from '@/lib/alarm';
import type { TelemetryData } from '@/types/drone';

vi.mock('@/lib/alarm', () => ({ playAlarm: vi.fn(() => true) }));

const base: TelemetryData = {
  battery: 80, height: 50, flight_time: 10,
  temperature: { high: 60, low: 55 },
  attitude: { pitch: 0, roll: 0, yaw: 0 },
  speed: { x: 0, y: 0, z: 0 },
  barometer: 0, tof_distance: 50,
  wifi_snr: 90, battery_level: 'ok', signal_level: 'ok',
};

const setTelemetry = (t: Partial<TelemetryData>) =>
  useDroneStore.setState({ telemetry: { ...base, ...t } });

describe('FlightAlerts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDroneStore.setState({ connectionStatus: 'connected', previewMode: false, alertsMuted: false, telemetry: null });
  });

  it('shows nothing when all is well', () => {
    setTelemetry({});
    const { container } = render(<FlightAlerts />);
    expect(container).toBeEmptyDOMElement();
    expect(playAlarm).not.toHaveBeenCalled();
  });

  it('warns quietly on low battery and weak signal', () => {
    setTelemetry({ battery: 28, battery_level: 'low', wifi_snr: 35, signal_level: 'weak' });
    render(<FlightAlerts />);
    expect(screen.getByTestId('alert-battery')).toHaveTextContent('Battery 28%: land soon');
    expect(screen.getByTestId('alert-signal')).toHaveTextContent('Weak Wi-Fi (35)');
    expect(playAlarm).not.toHaveBeenCalled();
  });

  it('goes red and beeps when critical, and can be muted', () => {
    setTelemetry({ battery: 12, battery_level: 'critical' });
    render(<FlightAlerts />);
    const alert = screen.getByTestId('alert-battery');
    expect(alert).toHaveTextContent('Battery 12%: land now');
    expect(alert).toHaveAttribute('data-level', 'critical');
    expect(playAlarm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Mute alarm' }));
    expect(useDroneStore.getState().alertsMuted).toBe(true);
    expect(screen.getByRole('button', { name: 'Unmute alarm' })).toBeInTheDocument();
  });

  it('shows the signal reading in the status bar', () => {
    setTelemetry({ wifi_snr: 18, signal_level: 'critical' });
    render(<StatusBar />);
    const el = screen.getByTestId('wifi-signal');
    expect(el).toHaveTextContent('18');
    expect(el.className).toContain('text-danger');
  });
});
