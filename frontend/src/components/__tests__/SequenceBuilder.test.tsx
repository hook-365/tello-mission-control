import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SequenceBuilder from '@/components/SequenceBuilder';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import type { Sequence } from '@/types/drone';

const victoryLap: Sequence = {
  id: 'builtin-victory-lap',
  name: 'Victory lap',
  description: 'Fly out and back',
  auto_takeoff_land: true,
  builtin: true,
  steps: [
    { type: 'move', direction: 'up', distance_cm: 50 },
    { type: 'rotate', direction: 'cw', angle_deg: 180 },
    { type: 'flip', direction: 'back' },
  ],
};

vi.mock('@/lib/api', () => ({
  getSequences: vi.fn(),
  createSequence: vi.fn(),
  updateSequence: vi.fn(),
  deleteSequence: vi.fn(),
  runSequence: vi.fn(),
  runDraft: vi.fn(),
  abortSequence: vi.fn().mockResolvedValue({ ok: true }),
}));

describe('SequenceBuilder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getSequences).mockResolvedValue([victoryLap]);
    useDroneStore.setState({
      connectionStatus: 'connected',
      previewMode: false,
      sequences: [victoryLap],
      sequenceProgress: null,
      telemetry: null,
    });
  });

  it('builds a sequence from the palette and plays it as a draft', async () => {
    vi.mocked(api.runDraft).mockResolvedValue({
      sequence_id: null, status: 'running', current_step: 1, total_steps: 4, step_index: null, step_description: 'Take off (auto)',
    });
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Sequence name'), { target: { value: 'Hop' } });
    fireEvent.click(screen.getByRole('button', { name: /Move/ }));
    fireEvent.click(screen.getByRole('button', { name: /Spin/ }));
    expect(screen.getByTestId('step-1')).toHaveAttribute('title', 'Spin clockwise 360°');

    fireEvent.click(screen.getByRole('button', { name: /Play/ }));
    await waitFor(() => expect(api.runDraft).toHaveBeenCalled());
    const sent = vi.mocked(api.runDraft).mock.calls[0][0];
    expect(sent.name).toBe('Hop');
    expect(sent.steps.map((s) => s.type)).toEqual(['move', 'rotate']);
  });

  it('reorders and deletes steps', () => {
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Move/ }));
    fireEvent.click(screen.getByRole('button', { name: /Flip/ }));
    fireEvent.click(screen.getByLabelText('Move step 2 up'));
    expect(screen.getByTestId('step-0')).toHaveAttribute('title', 'Flip back');
    fireEvent.click(screen.getByLabelText('Delete step 1'));
    expect(screen.getByTestId('step-0')).toHaveAttribute('title', 'Forward 100 cm');
    expect(screen.queryByTestId('step-1')).not.toBeInTheDocument();
  });

  it('disables Play while a step is out of range', () => {
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Sequence name'), { target: { value: 'Bad' } });
    fireEvent.click(screen.getByRole('button', { name: /Move/ }));
    fireEvent.change(screen.getByLabelText('Distance in cm'), { target: { value: '900' } });
    expect(screen.getByText(/distance must be 20-500 cm/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Play/ })).toBeDisabled();
  });

  it('loads a built-in, runs it by id and highlights the live step', async () => {
    vi.mocked(api.runSequence).mockResolvedValue({
      sequence_id: victoryLap.id, status: 'running', current_step: 1, total_steps: 5, step_index: null, step_description: 'Take off (auto)',
    });
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Load a sequence'), { target: { value: victoryLap.id } });
    expect(screen.getByLabelText('Sequence name')).toHaveValue('Victory lap');
    fireEvent.click(screen.getByRole('button', { name: /Play/ }));
    await waitFor(() => expect(api.runSequence).toHaveBeenCalledWith(victoryLap.id));

    useDroneStore.setState({
      sequenceProgress: {
        sequence_id: victoryLap.id, status: 'running', current_step: 3, total_steps: 5, step_index: 1, step_description: 'Spin',
      },
    });
    expect(await screen.findByRole('button', { name: /Abort and land/ })).toBeInTheDocument();
    expect(screen.getByTestId('step-1')).toHaveAttribute('data-active', 'true');
    expect(screen.getByTestId('step-0')).not.toHaveAttribute('data-active');

    fireEvent.click(screen.getByRole('button', { name: /Abort and land/ }));
    expect(api.abortSequence).toHaveBeenCalled();
  });

  it('saves a new sequence', async () => {
    const saved: Sequence = { ...victoryLap, id: 'hop-abc123', name: 'Hop', builtin: false };
    vi.mocked(api.createSequence).mockResolvedValue(saved);
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Sequence name'), { target: { value: 'Hop' } });
    fireEvent.click(screen.getByRole('button', { name: /Move/ }));
    fireEvent.click(screen.getByRole('button', { name: /Save new/ }));
    expect(await screen.findByText('Saved "Hop"')).toBeInTheDocument();
    expect(api.getSequences).toHaveBeenCalled();
  });

  it('shows pre-flight problems from the backend', async () => {
    vi.mocked(api.runDraft).mockRejectedValue(new Error('Battery is 20%, needs at least 30% to run a sequence'));
    render(<SequenceBuilder isOpen onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Sequence name'), { target: { value: 'Hop' } });
    fireEvent.click(screen.getByRole('button', { name: /Move/ }));
    fireEvent.click(screen.getByRole('button', { name: /Play/ }));
    expect(await screen.findByText(/needs at least 30%/)).toBeInTheDocument();
  });
});
