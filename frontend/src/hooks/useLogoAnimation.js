/**
 * useLogoAnimation.js
 * Drives the permit_rag logo animation sequence.
 *
 * Sequence:
 *   1. Tools float/bob continuously from time 0.
 *   2. Rows animate in (row1, row2, row3).
 *   3. Checks draw in sequence.
 */

import { useCallback, useRef } from 'react';

/** @typedef {'moderate'|'snappy'} AnimMode */

const TIMINGS = {
  moderate: {
    rows:        [0.1, 0.45, 0.80],
    rowDur:      0.5,
    checks:      [1.3, 1.55, 1.8],
    checkDur:    0.4,
  },
  snappy: {
    rows:        [0.05, 0.20, 0.35],
    rowDur:      0.25,
    checks:      [0.6, 0.72, 0.84],
    checkDur:    0.2,
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

    const rowIds   = ['row1',   'row2',   'row3'];
    const checkIds = ['check1', 'check2', 'check3'];
    const toolKeys = ['brush',  'hammer', 'ruler'];

    // 1. Tools float/bob continuously right away (0s delay)
    toolKeys.forEach((key) => {
      const el = document.getElementById(`tool-${key}-bob`) || document.getElementById(`tool-${key}`);
      restartAnimation(el);
      if (el) {
        el.style.animation = `bob ${BOB_DUR[key]}s ease-in-out 0s infinite`;
      }
    });

    // 2. Rows animate in
    rowIds.forEach((id, i) => {
      const el = document.getElementById(id);
      restartAnimation(el);
      if (el) {
        el.style.animation = `rowIn ${t.rowDur}s cubic-bezier(.22,.9,.32,1) ${t.rows[i]}s both`;
      }
    });

    // 3. Checks draw after rows
    checkIds.forEach((id, i) => {
      const el = document.getElementById(id);
      restartAnimation(el);
      if (el) {
        el.style.animation = `checkDraw ${t.checkDur}s ease ${t.checks[i]}s both`;
      }
    });
  }, []);

  /** Replay using the last-used mode. */
  const replay = useCallback(() => {
    play(currentModeRef.current);
  }, [play]);

  return { play, replay };
}
