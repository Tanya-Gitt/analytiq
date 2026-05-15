import type { Annotation } from '@/lib/api';

// Days within which two adjacent annotations are considered "colliding" and
// pushed to alternating vertical lanes.
const MIN_GAP_DAYS = 21;

interface LayoutInfo {
  lane:   number;                       // 0 = top row, 1 = pushed down a row, etc.
  anchor: 'start' | 'middle' | 'end';   // text-anchor — keeps labels inside the chart
}

/**
 * Pre-compute label layout for a set of annotations: vertical lane (so close
 * annotations don't draw on top of each other) and horizontal anchor (so the
 * first/last annotation's text stays inside the chart bounds).
 */
export function layoutAnnotations(annotations: Annotation[]): Map<string, LayoutInfo> {
  const sorted = [...annotations].sort((a, b) => a.date.localeCompare(b.date));
  const out    = new Map<string, LayoutInfo>();

  // Greedy lane assignment: for each annotation, find the lowest lane whose
  // most-recent annotation is at least MIN_GAP_DAYS earlier.
  const laneLastDate: string[] = [];

  sorted.forEach((ann, i) => {
    let lane = -1;
    for (let l = 0; l < laneLastDate.length; l++) {
      const gap = (new Date(ann.date).getTime() - new Date(laneLastDate[l]).getTime())
                  / (24 * 3600 * 1000);
      if (gap >= MIN_GAP_DAYS) { lane = l; break; }
    }
    if (lane === -1) { lane = laneLastDate.length; laneLastDate.push(ann.date); }
    else             { laneLastDate[lane] = ann.date; }

    // Anchor: clamp the first and last labels inwards so long text doesn't
    // get clipped at the chart edges.
    const anchor: LayoutInfo['anchor'] =
      i === 0                       ? 'start' :
      i === sorted.length - 1       ? 'end'   :
                                      'middle';

    out.set(ann.id, { lane, anchor });
  });

  return out;
}

interface RenderProps {
  label:  string;
  color:  string;
  layout: LayoutInfo;
}

/**
 * Build a recharts ReferenceLine `label` renderer for a single annotation.
 * The renderer draws an SVG <text> at the line's x position, offset
 * vertically by lane and anchored according to layout.anchor.
 */
export function makeAnnotationLabel({ label, color, layout }: RenderProps) {
  // recharts passes { viewBox: { x, y, width, height } } where x/y are the
  // top-of-line anchor; y is the top of the plot area.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (props: any) => {
    const vb = props.viewBox ?? { x: 0, y: 0 };
    const yOffset = -8 - layout.lane * 13;       // above plot area, stacked by lane
    // Nudge horizontally based on anchor so 'end' sits just left of the line
    // (otherwise text hangs off the right edge of the chart).
    const xOffset = layout.anchor === 'end'   ? -4
                  : layout.anchor === 'start' ?  4
                  :                              0;
    return (
      <text
        x={vb.x + xOffset}
        y={vb.y + yOffset}
        fill={color}
        fontSize={10}
        textAnchor={layout.anchor}
      >
        {label}
      </text>
    );
  };
}
