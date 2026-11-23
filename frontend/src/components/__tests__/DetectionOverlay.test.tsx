import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import DetectionOverlay from '@/components/DetectionOverlay';
import { useDroneStore } from '@/stores/droneStore';
import type { Detection, DetectionsData } from '@/types/drone';

const person: Detection = { label: 'person', confidence: 0.87, x: 0.25, y: 0.5, w: 0.5, h: 0.25 };
const dog: Detection = { label: 'dog', confidence: 0.6, x: 0.7, y: 0.01, w: 0.1, h: 0.1 };

function frame(over: Partial<DetectionsData> = {}): DetectionsData {
  return {
    detections: [person, dog],
    target: null,
    detecting: true,
    tracking: false,
    stale: false,
    frame_width: 960,
    frame_height: 720,
    ...over,
  };
}

describe('DetectionOverlay', () => {
  beforeEach(() => {
    useDroneStore.setState({
      detections: null,
      vision: { available: true, detecting: false, tracking: false },
    });
  });

  it('renders nothing without detection data', () => {
    const { container } = render(<DetectionOverlay />);
    expect(container).toBeEmptyDOMElement();
  });

  it('crops the overlay the same way as the video', () => {
    useDroneStore.setState({ detections: frame() });
    render(<DetectionOverlay />);
    const svg = screen.getByRole('img');
    expect(svg).toHaveAttribute('viewBox', '0 0 960 720');
    expect(svg).toHaveAttribute('preserveAspectRatio', 'xMidYMid slice');
    expect(svg).toHaveAccessibleName('2 detected objects');
  });

  it('scales normalised boxes to frame pixels and labels them', () => {
    useDroneStore.setState({ detections: frame() });
    render(<DetectionOverlay />);
    const rect = screen.getByText('person 87%').parentElement!.querySelector('rect')!;
    expect(rect).toHaveAttribute('x', '240');
    expect(rect).toHaveAttribute('y', '360');
    expect(rect).toHaveAttribute('width', '480');
    expect(rect).toHaveAttribute('height', '180');
    expect(screen.getByText('dog 60%')).toBeInTheDocument();
  });

  it('highlights only the followed target while tracking', () => {
    useDroneStore.setState({ detections: frame({ tracking: true, target: person }) });
    render(<DetectionOverlay />);
    const groups = screen.getAllByTestId('detection');
    expect(groups[0]).toHaveAttribute('data-followed', 'true');
    expect(groups[1]).not.toHaveAttribute('data-followed');
  });

  it('warns when the video has stalled', () => {
    useDroneStore.setState({ detections: frame({ detections: [], stale: true }) });
    render(<DetectionOverlay />);
    expect(screen.getByText(/VIDEO STALLED/)).toBeInTheDocument();
  });

  it('the store drops boxes and syncs flags when detection switches off', () => {
    useDroneStore.getState().setDetections(frame({ tracking: true }));
    expect(useDroneStore.getState().vision).toMatchObject({ detecting: true, tracking: true });

    useDroneStore.getState().setDetections(frame({ detecting: false, tracking: false }));
    expect(useDroneStore.getState().detections).toBeNull();
    expect(useDroneStore.getState().vision).toMatchObject({ detecting: false, tracking: false });
  });
});
