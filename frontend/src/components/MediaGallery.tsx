import { useEffect, useState } from 'react';
import { Download, Film, Image as ImageIcon, Trash2, X } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import type { MediaItem } from '@/types/drone';

function sizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function whenLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function Preview({ item, large }: { item: MediaItem; large?: boolean }) {
  const cls = large ? 'max-h-[60vh] w-full object-contain rounded-lg bg-black' : 'w-full h-full object-cover';
  if (!item.url) {
    return (
      <div className={`${large ? 'h-48' : 'h-full'} flex flex-col items-center justify-center gap-1 text-hud-dim bg-black/40`}>
        <Film size={large ? 32 : 20} />
        <span className="text-hud-xs">Preview not available here</span>
      </div>
    );
  }
  if (item.kind === 'photo') return <img src={item.url} alt={item.name} className={cls} loading="lazy" />;
  return large ? (
    <video src={item.url} className={cls} controls autoPlay playsInline />
  ) : (
    <video src={item.url} className={cls} muted playsInline preload="metadata" />
  );
}

export default function MediaGallery() {
  const open = useDroneStore((s) => s.galleryOpen);
  const setOpen = useDroneStore((s) => s.setGalleryOpen);
  const media = useDroneStore((s) => s.media);
  const refreshMedia = useDroneStore((s) => s.refreshMedia);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) refreshMedia();
  }, [open, refreshMedia]);

  if (!open) return null;
  const current = media.find((m) => m.name === selected) ?? null;
  const photos = media.filter((m) => m.kind === 'photo').length;

  const remove = async (item: MediaItem) => {
    if (!window.confirm(`Delete ${item.kind === 'photo' ? 'this photo' : 'this clip'}? It can't be undone.`)) return;
    try {
      await api.deleteMedia(item.name);
      setError(null);
      if (selected === item.name) setSelected(null);
      useDroneStore.getState().applyMediaEvent({ event: 'deleted', name: item.name });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  return (
    <aside
      className="fixed z-[4] left-3 top-3 sm:left-4 sm:top-4 w-[min(560px,calc(100vw-24px))] max-h-[calc(100vh-24px)] hud-panel flex flex-col gap-3 animate-fade-in-up"
      aria-label="Gallery"
    >
      <header className="flex items-center gap-2">
        <h2 className="text-hud-base font-semibold flex-1">
          Gallery
          <span className="ml-2 text-hud-xs text-hud-secondary font-normal">
            {photos} photo{photos === 1 ? '' : 's'}, {media.length - photos} clip{media.length - photos === 1 ? '' : 's'}
          </span>
        </h2>
        <button className="control-btn p-1.5" onClick={() => setOpen(false)} aria-label="Close gallery">
          <X size={16} />
        </button>
      </header>

      {current && (
        <figure className="flex flex-col gap-2" data-testid="gallery-viewer">
          <Preview item={current} large />
          <figcaption className="flex items-center gap-2 text-hud-xs text-hud-secondary">
            <span className="flex-1 truncate font-mono">{current.name}</span>
            {current.url && (
              <a className="control-btn px-2 py-1" href={current.url} download={current.name}>
                <Download size={12} /> Save
              </a>
            )}
            <button className="control-btn px-2 py-1 hover:text-danger" onClick={() => remove(current)}>
              <Trash2 size={12} /> Delete
            </button>
          </figcaption>
        </figure>
      )}

      {error && <p className="text-hud-xs text-danger">{error}</p>}

      {media.length === 0 ? (
        <p className="text-hud-sm text-hud-secondary py-6 text-center">
          Nothing yet. Use the camera or record buttons up top, or run a sequence with Photo or Record steps
          (try the built-in Orbit shot or Reveal).
        </p>
      ) : (
        <ul className="grid grid-cols-3 sm:grid-cols-4 gap-2 overflow-y-auto pr-1" data-testid="gallery-grid">
          {media.map((m) => (
            <li key={m.name}>
              <button
                className={`relative block w-full aspect-[4/3] overflow-hidden rounded-md border ${
                  selected === m.name ? 'border-info' : 'border-white/10 hover:border-white/30'
                }`}
                onClick={() => setSelected(selected === m.name ? null : m.name)}
                aria-label={`${m.kind === 'photo' ? 'Photo' : 'Clip'} ${whenLabel(m.created_at)}`}
                title={`${m.name} · ${sizeLabel(m.size_bytes)}`}
              >
                <Preview item={m} />
                <span className="absolute left-1 bottom-1 flex items-center gap-1 rounded bg-black/60 px-1 text-[10px] text-white">
                  {m.kind === 'photo' ? <ImageIcon size={10} /> : <Film size={10} />}
                  {m.kind === 'clip' && m.duration_s ? `${Math.round(m.duration_s)}s` : whenLabel(m.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
