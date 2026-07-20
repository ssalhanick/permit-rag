/**
 * useLogoAnimation.js
 * Drives the permit_rag logo entrance sequence.
 *
 * Timing modes:
 *   "moderate" — 3.2 s full sequence (default on app load)
 *   "snappy"   — 1.32 s compressed sequence
 *
 * Usage:
 *   const { play, replay } = useLogoAnimation();
 *   useEffect(() => { play('moderate'); }, []);
 */

import { useCallback, useRef } from 'react';

/** @typedef {'moderate'|'snappy'} AnimMode */

const TIMINGS = {
  moderate: {
    rows:        [0, 0.35, 0.70],
    rowDur:      0.5,
    tools:       [1.3, 1.55, 1.8],
    toolDur:     0.5,
    checks:      [2.4, 2.6, 2.8],
    checkDur:    0.4,
    entranceEnd: 3.2,
  },
  snappy: {
    rows:        [0, 0.14, 0.28],
    rowDur:      0.2,
    tools:       [0.55, 0.65, 0.75],
    toolDur:     0.2,
    checks:      [1.0, 1.08, 1.16],
    checkDur:    0.16,
    entranceEnd: 1.32,
  },
};

/** Continuous bob durations per tool (seconds) */
const BOB_DUR = { brush: 2.4, hammer: 2.8, ruler: 2.2 };

/**
 * Force a CSS animation restart by clearing it, triggering reflow, then re-applying.
 * @param {HTMLElement} el
 */
function restartAnimation(el) {
  if (!el) return;
  el.style.animation = 'none';
  void el.offsetWidth; // force reflow
}

/**
 * Hook that provides logo animation controls.
 * The SVG must be rendered in the DOM with the expected element IDs
 * (row1, row2, row3, check1, check2, check3,
 *  tool-brush, tool-hammer, tool-ruler,
 *  tool-brush-bob, tool-hammer-bob, tool-ruler-bob).
 *
 * @returns {{ play: (mode?: AnimMode) => void, replay: () => void }}
 */
export function useLogoAnimation() {
  const currentModeRef = useRef(/** @type {AnimMode} */ ('moderate'));

  /**
   * Play the logo entrance animation.
   * @param {AnimMode} mode
   */
  const play = useCallback((mode = 'moderate') => {
    currentModeRef.current = mode;
    const t = TIMINGS[mode];

    const rowIds   = ['row1',      'row2',       'row3'];
    const toolIds  = ['tool-brush','tool-hammer', 'tool-ruler'];
    const checkIds = ['check1',    'check2',      'check3'];
    const toolKeys = ['brush',     'hammer',      'ruler'];

    rowIds.forEach((id, i) => {
      const el = document.getElementById(id);
      restartAnimation(el);
      if (el) {
        el.style.animation =
          `rowIn ${t.rowDur}s cubic-bezier(.22,.9,.32,1) ${t.rows[i]}s both`;
      }
    });

    toolIds.forEach((id, i) => {
      const el = document.getElementById(id);
      restartAnimation(el);
      if (el) {
        el.style.animation =
          `toolIn ${t.toolDur}s cubic-bezier(.22,.9,.32,1) ${t.tools[i]}s both`;
      }
    });

    checkIds.forEach((id, i) => {
      const el = document.getElementById(id);
      restartAnimation(el);
      if (el) {
        el.style.animation =
          `checkDraw ${t.checkDur}s ease ${t.checks[i]}s both`;
      }
    });

    toolKeys.forEach((key, i) => {
      const el = document.getElementById(`tool-${key}-bob`);
      restartAnimation(el);
      if (el) {
        const delay = t.tools[i] + t.toolDur;
        el.style.animation =
          `bob ${BOB_DUR[key]}s ease-in-out ${delay}s infinite`;
      }
    });
  }, []);

  /** Replay using the last-used mode. */
  const replay = useCallback(() => {
    play(currentModeRef.current);
  }, [play]);

  return { play, replay };
}
