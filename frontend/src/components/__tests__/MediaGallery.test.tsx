import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import MediaGallery from '@/components/MediaGallery';
import StatusBar from '@/components/StatusBar';
import { NOT_RECORDING, useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import type { MediaItem } from '@/types/drone';

vi.mock('@/lib/api', () => ({
  getMedia: vi.fn(),
  deleteMedia: vi.fn().mockResolvedValue({ ok: true }),
  takePhoto: vi.fn(),
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
  disconnectDrone: vi.fn(),
  stopVideoStream: vi.fn().mockResolvedValue({ ok: true }),
}));

const photo: MediaItem = {
  name: 'photo-20260101-120000-000.jpg',
  kind: 'photo',
  size_bytes: 52000,
  created_at: '2026-01-01T12:00:00Z',
  url: '/api/media/files/photo-20260101-120000-000.jpg',
};
const clip: MediaItem = { ...photo, name: 'clip-20260101-120100.mp4', kind: 'clip', duration_s: 42, url: null };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMedia).mockResolvedValue({ items: [clip, photo], recording: NOT_RECORDING });
  useDroneStore.setState({
    connectionStatus: 'connected',
    previewMode: false,
    telemetry: null,
    media: [],
    recording: NOT_RECORDING,
    galleryOpen: false,
    commandLog: [],
  });
});

describe('MediaGallery', () => {
  it('opens from the status bar and lists photos and clips', async () => {
    render(
      <>
        <StatusBar />
        <MediaGallery />
      </>,
    );
    expect(screen.queryByRole('complementary', { name: 'Gallery' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Gallery' }));
    await waitFor(() => expect(screen.getByText('1 photo, 1 clip')).toBeInTheDocument());
    expect(screen.getByAltText(photo.name)).toHaveAttribute('src', photo.url);
    expect(screen.getByText('42s')).toBeInTheDocument();
    expect(screen.getByText('Preview not available here')).toBeInTheDocument(); // clip with no url
  });

  it('shows a big preview and deletes after confirming', async () => {
    useDroneStore.setState({ galleryOpen: true, media: [photo] });
    vi.mocked(api.getMedia).mockResolvedValue({ items: [photo], recording: NOT_RECORDING });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<MediaGallery />);
    fireEvent.click(await screen.findByRole('button', { name: /^Photo/ }));
    expect(screen.getByTestId('gallery-viewer')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Save/ })).toHaveAttribute('download', photo.name);
    fireEvent.click(screen.getByRole('button', { name: /Delete/ }));
    await waitFor(() => expect(api.deleteMedia).toHaveBeenCalledWith(photo.name));
    await waitFor(() => expect(screen.getByText(/Nothing yet/)).toBeInTheDocument());
  });
});

describe('StatusBar camera buttons', () => {
  it('takes a photo and toggles recording', async () => {
    vi.mocked(api.takePhoto).mockResolvedValue(photo);
    vi.mocked(api.startRecording).mockResolvedValue({ recording: true, name: 'c.mp4', elapsed_s: 0, started_at: null });
    render(<StatusBar />);
    fireEvent.click(screen.getByRole('button', { name: 'Take photo' }));
    await waitFor(() => expect(api.takePhoto).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start recording' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Start recording' }));
    await waitFor(() => expect(api.startRecording).toHaveBeenCalled());
    // the server's media event flips the button
    act(() =>
      useDroneStore.getState().applyMediaEvent({
        event: 'recording_started', recording: true, name: 'c.mp4', elapsed_s: 0, started_at: new Date().toISOString(),
      }),
    );
    expect(await screen.findByTestId('rec-indicator')).toHaveTextContent('REC 0:0');
    fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }));
    await waitFor(() => expect(api.stopRecording).toHaveBeenCalled());
  });

  it('logs a camera error instead of failing silently', async () => {
    vi.mocked(api.takePhoto).mockRejectedValue(new Error("Camera didn't send a picture in time"));
    render(<StatusBar />);
    fireEvent.click(screen.getByRole('button', { name: 'Take photo' }));
    await waitFor(() => expect(useDroneStore.getState().commandLog.slice(-1)[0]?.error).toMatch(/in time/));
  });

  it('camera buttons are off in preview mode', () => {
    useDroneStore.setState({ previewMode: true });
    render(<StatusBar />);
    expect(screen.getByRole('button', { name: 'Take photo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeDisabled();
  });
});
