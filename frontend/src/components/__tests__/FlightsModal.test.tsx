import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FlightsModal from '@/components/FlightsModal';
import * as api from '@/lib/api';
import type { FlightDetail, FlightSummary, TelemetryData } from '@/types/drone';

vi.mock('@/lib/api', () => ({
  getFlights: vi.fn(),
  getFlight: vi.fn(),
  deleteFlight: vi.fn(),
}));

const T0 = '2026-11-23T18:00:00.000Z';
const at = (s: number) => new Date(new Date(T0).getTime() + s * 1000).toISOString();

function telemetry(height: number): TelemetryData {
  return {
    battery: 80,
    height,
    flight_time: 0,
    temperature: { high: 60, low: 55 },
    attitude: { pitch: 0, roll: 0, yaw: 0 },
    speed: { x: 0, y: 0, z: 0 },
    barometer: 0,
    tof_distance: height,
  };
}

const done: FlightSummary = {
  id: 7, started_at: T0, ended_at: at(95), telemetry_frames: 3, commands: 3, active: false,
};
const recording: FlightSummary = {
  id: 8, started_at: at(200), ended_at: null, telemetry_frames: 1, commands: 1, active: true,
};
const detail: FlightDetail = {
  ...done,
  telemetry: [
    { timestamp: at(0), data: telemetry(0) },
    { timestamp: at(10), data: telemetry(50) },
    { timestamp: at(20), data: telemetry(120) },
  ],
  command_log: [
    { command: 'connect', params: {}, result: 'ok', timestamp: at(0) },
    { command: 'takeoff', params: {}, result: 'ok', timestamp: at(5) },
    { command: 'move', params: { direction: 'up', distance_cm: 70 }, result: 'ok', timestamp: at(15) },
  ],
};

describe('FlightsModal', () => {
  beforeEach(() => {
    vi.mocked(api.getFlights).mockReset().mockResolvedValue([recording, done]);
    vi.mocked(api.getFlight).mockReset().mockResolvedValue(detail);
    vi.mocked(api.deleteFlight).mockReset().mockResolvedValue({ ok: true });
  });

  it('renders nothing and fetches nothing while closed', () => {
    const { container } = render(<FlightsModal isOpen={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.getFlights).not.toHaveBeenCalled();
  });

  it('lists flights with duration and counts', async () => {
    render(<FlightsModal isOpen onClose={() => {}} />);
    expect(await screen.findByText(/1:35 · 3 commands · 3 frames/)).toBeInTheDocument();
    expect(screen.getByText('recording')).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    vi.mocked(api.getFlights).mockResolvedValue([]);
    render(<FlightsModal isOpen onClose={() => {}} />);
    expect(await screen.findByText('No flights recorded yet')).toBeInTheDocument();
  });

  it('reports when the flight log is unavailable', async () => {
    vi.mocked(api.getFlights).mockRejectedValue(new Error('HTTP 503'));
    render(<FlightsModal isOpen onClose={() => {}} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Flight log unavailable');
  });

  it('cannot delete a flight that is still recording', async () => {
    render(<FlightsModal isOpen onClose={() => {}} />);
    expect(await screen.findByLabelText('Delete flight 8')).toBeDisabled();
    expect(screen.getByLabelText('Delete flight 7')).not.toBeDisabled();
  });

  it('deletes a flight and refreshes the list', async () => {
    const user = userEvent.setup();
    render(<FlightsModal isOpen onClose={() => {}} />);
    await user.click(await screen.findByLabelText('Delete flight 7'));
    expect(api.deleteFlight).toHaveBeenCalledWith(7);
    await waitFor(() => expect(api.getFlights).toHaveBeenCalledTimes(2));
  });

  it('scrubs through recorded telemetry and marks commands issued so far', async () => {
    const user = userEvent.setup();
    render(<FlightsModal isOpen onClose={() => {}} />);
    await user.click(await screen.findByText(/1:35 · 3 commands/));

    expect(await screen.findByText('0 cm')).toBeInTheDocument();
    expect(screen.getByText('0:00 / 0:20')).toBeInTheDocument();
    expect(screen.getByText('connect').closest('li')).toHaveClass('text-white');
    expect(screen.getByText('takeoff').closest('li')).toHaveClass('text-hud-dim');

    fireEvent.change(screen.getByLabelText('Replay position'), { target: { value: '2' } });
    expect(screen.getByText('120 cm')).toBeInTheDocument();
    expect(screen.getByText('0:20 / 0:20')).toBeInTheDocument();
    expect(screen.getByText('move up 70').closest('li')).toHaveClass('text-white');
  });

  it('returns to the list from a flight', async () => {
    const user = userEvent.setup();
    render(<FlightsModal isOpen onClose={() => {}} />);
    await user.click(await screen.findByText(/1:35 · 3 commands/));
    await user.click(await screen.findByLabelText('Back to flight list'));
    expect(screen.getByText('FLIGHT LOG')).toBeInTheDocument();
  });

  it('closes from the close button', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<FlightsModal isOpen onClose={onClose} />);
    await user.click(await screen.findByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });
});
