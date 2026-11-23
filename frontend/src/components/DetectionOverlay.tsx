import { useDroneStore } from '@/stores/droneStore';
import type { Detection } from '@/types/drone';

const sameBox = (a: Detection, b: Detection | null) =>
  !!b && a.label === b.label && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;

/**
 * Detection boxes drawn over the video.
 *
 * The SVG's viewBox is the camera frame and `slice` crops it exactly like the
 * video's `object-cover`, so boxes stay glued to the picture at any window size.
 */
export default function DetectionOverlay() {
  const data = useDroneStore((s) => s.detections);
  if (!data || !data.frame_width || !data.frame_height) return null;

  const { frame_width: W, frame_height: H, detections, target, tracking, stale } = data;
  const fontSize = H * 0.028;

  return (
    <svg
      className="fixed inset-0 z-0 h-full w-full pointer-events-none"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label={`${detections.length} detected object${detections.length === 1 ? '' : 's'}`}
    >
      {detections.map((d, i) => {
        const followed = tracking && sameBox(d, target);
        const color = followed ? '#FBBF24' : '#38BDF8';
        const x = d.x * W;
        const y = d.y * H;
        const label = `${d.label} ${Math.round(d.confidence * 100)}%`;
        return (
          <g key={i} data-testid="detection" data-followed={followed || undefined}>
            <rect
              x={x}
              y={y}
              width={d.w * W}
              height={d.h * H}
              fill="none"
              stroke={color}
              strokeWidth={followed ? 3 : 1.5}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={x + fontSize * 0.25}
              // Put the label inside the box when it would run off the top of the frame.
              y={y > fontSize * 1.3 ? y - fontSize * 0.35 : y + fontSize * 1.1}
              fontSize={fontSize}
              fontFamily="ui-monospace, monospace"
              fill={color}
              stroke="rgba(0,0,0,0.75)"
              strokeWidth={fontSize * 0.14}
              paintOrder="stroke"
            >
              {label}
            </text>
          </g>
        );
      })}
      {stale && (
        <text
          x={W / 2}
          y={H * 0.12}
          textAnchor="middle"
          fontSize={fontSize}
          fontFamily="ui-monospace, monospace"
          fill="#F87171"
          stroke="rgba(0,0,0,0.75)"
          strokeWidth={fontSize * 0.14}
          paintOrder="stroke"
        >
          VIDEO STALLED — DETECTION PAUSED
        </text>
      )}
    </svg>
  );
}
