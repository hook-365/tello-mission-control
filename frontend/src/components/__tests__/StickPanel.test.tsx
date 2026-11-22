import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StickPanel from '@/components/StickPanel';
import { IDLE_STICKS, useDroneStore } from '@/stores/droneStore';

describe('StickPanel', () => {
  beforeEach(() => {
    useDroneStore.setState({
      keyboardMode: 'tap', gamepadName: null, isFlying: true, rcError: null,
      sequenceProgress: null, stickInput: IDLE_STICKS, stickSpeed: 50,
    });
  });

  it('prompts to plug in a controller and switches the keyboard to hold-to-fly', () => {
    render(<StickPanel />);
    expect(screen.getByTestId('stick-hint')).toHaveTextContent('Plug in a controller');
    fireEvent.click(screen.getByRole('button', { name: 'Hold to fly' }));
    expect(useDroneStore.getState().keyboardMode).toBe('hold');
    expect(screen.getByTestId('stick-hint')).toHaveTextContent('Hold W A S D');
    expect(screen.getByLabelText('Stick speed')).toHaveValue('50');
  });

  it('names the controller and explains the dead-man', () => {
    useDroneStore.setState({ gamepadName: 'Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e)' });
    render(<StickPanel />);
    expect(screen.getByText('Xbox Wireless Controller')).toBeInTheDocument();
    expect(screen.getByTestId('stick-hint')).toHaveTextContent('Hold LB or RB to fly');
    expect(screen.getByText(/Click both sticks in/)).toBeInTheDocument();
  });

  it('shows the backend refusal while the dead-man is held', () => {
    useDroneStore.setState({
      gamepadName: 'Pad',
      rcError: 'Busy with another command',
      stickInput: { sticks: { lr: 0, fb: 50, ud: 0, yaw: 0 }, armed: true, source: 'gamepad' },
    });
    render(<StickPanel />);
    expect(screen.getByTestId('stick-hint')).toHaveTextContent('Busy with another command');
  });

  it('says sticks are off during a sequence', () => {
    useDroneStore.setState({ sequenceProgress: { sequence_id: 'x', status: 'running', current_step: 1, total_steps: 2, step_description: '' } });
    render(<StickPanel />);
    expect(screen.getByTestId('stick-hint')).toHaveTextContent('off while a sequence runs');
  });
});
