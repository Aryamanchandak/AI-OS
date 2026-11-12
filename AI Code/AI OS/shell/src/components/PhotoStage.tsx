import { motion, useMotionValue } from "framer-motion";
import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

export type PhotoBox = {
  key: string;
  bbox: [number, number, number, number];
  title?: string;
};

const MIN_SCALE = 1;
const MAX_SCALE = 4;

/**
 * A zoomable, pannable photo with normalized-bbox overlays. Extracted out of
 * ImageReview.tsx so a second screen (KnowledgeProposalReview, seeing the
 * source page while reviewing what was extracted from it) can show the same
 * viewer without duplicating the pan/zoom/keyboard wiring.
 */
export function PhotoStage({
  imageUrl,
  imageError,
  boxes,
  alt,
  label = alt,
  loadingLabel = "Loading current evidence…",
}: {
  imageUrl: string | null;
  imageError: string | null;
  boxes: PhotoBox[];
  /** The `<img>`'s own alt text. */
  alt: string;
  /** The stage's aria-label prefix, read as `"{label}. Arrow keys pan..."`.
   * Defaults to `alt` when the two should read the same. */
  label?: string;
  loadingLabel?: string;
}) {
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 });

  // The transform lives on .image-wrap itself, the container that holds both
  // the <img> and the box overlays. Their positions are already percentages
  // of that wrapper's own size, so scaling/translating it as one unit keeps
  // every box registered for free -- nothing here touches the box math below.
  const stageRef = useRef<HTMLDivElement>(null);
  const scale = useMotionValue(1);
  const panX = useMotionValue(0);
  const panY = useMotionValue(0);

  const zoomBy = useCallback((delta: number) => {
    scale.set(Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.get() + delta)));
  }, [scale]);

  const resetView = useCallback(() => {
    scale.set(1);
    panX.set(0);
    panY.set(0);
  }, [panX, panY, scale]);

  // A fixed pixel step, scaled down as the image is zoomed in so a key press
  // always moves the same amount of visible content regardless of zoom level.
  const panBy = useCallback((dx: number, dy: number) => {
    const step = 40 / scale.get();
    panX.set(panX.get() + dx * step);
    panY.set(panY.get() + dy * step);
  }, [panX, panY, scale]);

  // Wheel zoom needs preventDefault, which React's onWheel cannot reliably do
  // (modern browsers treat it as passive by default) -- a native listener
  // with { passive: false } is the only way to stop the page from scrolling
  // under the cursor while zooming.
  useEffect(() => {
    const node = stageRef.current;
    if (!node) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoomBy(event.deltaY > 0 ? -0.2 : 0.2);
    };
    node.addEventListener("wheel", handleWheel, { passive: false });
    return () => node.removeEventListener("wheel", handleWheel);
  }, [zoomBy]);

  const handleStageKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowLeft": event.preventDefault(); panBy(1, 0); break;
      case "ArrowRight": event.preventDefault(); panBy(-1, 0); break;
      case "ArrowUp": event.preventDefault(); panBy(0, 1); break;
      case "ArrowDown": event.preventDefault(); panBy(0, -1); break;
      case "+": case "=": event.preventDefault(); zoomBy(0.2); break;
      case "-": case "_": event.preventDefault(); zoomBy(-0.2); break;
      case "0": event.preventDefault(); resetView(); break;
      default: break;
    }
  };

  return (
    <div
      className="image-stage"
      ref={stageRef}
      tabIndex={imageUrl ? 0 : undefined}
      role={imageUrl ? "group" : undefined}
      aria-label={imageUrl ? `${label}. Arrow keys pan, plus and minus zoom, 0 resets.` : undefined}
      onKeyDown={imageUrl ? handleStageKeyDown : undefined}
    >
      {imageError ? (
        <div className="inline-error">{imageError}</div>
      ) : imageUrl ? (
        <>
          <motion.div
            className="image-wrap"
            style={{ x: panX, y: panY, scale }}
            drag
            dragConstraints={stageRef}
            dragElastic={0.08}
            dragMomentum={false}
          >
            <img
              src={imageUrl}
              alt={alt}
              onLoad={(event) => setDimensions({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })}
            />
            {boxes.map((box) => (
              <span
                key={box.key}
                className="passage-box"
                title={box.title}
                style={{
                  left: `${box.bbox[0] / dimensions.width * 100}%`,
                  top: `${box.bbox[1] / dimensions.height * 100}%`,
                  width: `${box.bbox[2] / dimensions.width * 100}%`,
                  height: `${box.bbox[3] / dimensions.height * 100}%`,
                }}
              />
            ))}
          </motion.div>
          <div className="zoom-controls">
            <button type="button" className="button quiet" aria-label="Zoom in" onClick={() => zoomBy(0.2)}>
              <ZoomIn size={16} />
            </button>
            <button type="button" className="button quiet" aria-label="Zoom out" onClick={() => zoomBy(-0.2)}>
              <ZoomOut size={16} />
            </button>
            <button type="button" className="button quiet" aria-label="Reset zoom and pan" onClick={resetView}>
              <Maximize2 size={16} />
            </button>
          </div>
        </>
      ) : (
        <div className="image-loading">{loadingLabel}</div>
      )}
    </div>
  );
}
