import type { Annotation } from '@/lib/api';

// Hard cap on how many annotations a single chart will render. Anything
// past this gets dropped (oldest first) so the chart stays readable.
// The Annotations panel under the chart still shows the full list.
export const MAX_VISIBLE_ANNOTATIONS = 8;

interface LayoutInfo {
  lane: number;   // 0 = top row, 1 = next row down, etc.
}

/**
 * Pre-compute label layout for a chart's annotations.
 *
 * To guarantee labels never overlap horizontally (regardless of chart
 * width or label length), we put every annotation on its own vertical
 * lane. The chart's top margin grows to fit all lanes.
 *
 * If there are more than MAX_VISIBLE_ANNOTATIONS, the oldest ones are
 * dropped — the chart can't visually accommodate more than ~8 stacked
 * labels at 200px height, and the full list is always available in the
 * Annotations panel below the chart.
 */
export function layoutAnnotations(annotations: Annotation[]): {
  visible: Annotation[];
  layout:  Map<string, LayoutInfo>;
} {
  // Sort by date, take the most-recent N, then re-sort for stable lane
  // assignment (oldest visible → lane 0, newest → lane N-1).
  const recent = [...annotations]
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-MAX_VISIBLE_ANNOTATIONS);

  const layout = new Map<string, LayoutInfo>();
  recent.forEach((ann, i) => layout.set(ann.id, { lane: i }));

  return { visible: recent, layout };
}

interface RenderProps {
  label:  string;
  color:  string;
  layout: LayoutInfo;
}

/**
 * Build a recharts ReferenceLine `label` renderer for one annotation.
 * Renders SVG <text> centred above the reference line, offset upward
 * by the annotation's lane.
 */
export function makeAnnotationLabel({ label, color, layout }: RenderProps) {
  // recharts passes { viewBox: { x, y, width, height } } where x/y are
  // the top of the reference line and y is also the top of the plot area.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (props: any) => {
    const vb = props.viewBox ?? { x: 0, y: 0 };
    // Stack from the top of the chart downward; lane 0 sits closest to
    // the plot, higher lanes sit further above.
    const yOffset = -6 - (layout.lane * 13);
    return (
      <text
        x={vb.x}
        y={vb.y + yOffset}
        fill={color}
        fontSize={10}
        textAnchor="middle"
      >
        {label}
      </text>
    );
  };
}
