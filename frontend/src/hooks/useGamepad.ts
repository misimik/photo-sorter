import { useEffect, useRef } from "react";

interface GamepadAction {
  button: number;
  keys: string[];
}

const ACTIONS: GamepadAction[] = [
  { button: 0,  keys: ["Enter"] },
  { button: 1,  keys: ["Escape"] },
  { button: 2,  keys: ["x"] },
  { button: 3,  keys: ["f"] },
  { button: 14, keys: ["ArrowLeft"] },
  { button: 15, keys: ["ArrowRight"] },
];

export function useGamepad(onKey: (key: string) => void, enabled: boolean = true) {
  const prevButtons = useRef<number[]>([]);
  const activePad = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const poll = () => {
      const pads = navigator.getGamepads();
      for (const pad of pads) {
        if (!pad) continue;
        const pressed = pad.buttons.map((b) => b.value);

        for (const action of ACTIONS) {
          if (pressed[action.button] > 0.5 && !(prevButtons.current[action.button] > 0.5)) {
            for (const key of action.keys) onKey(key);
          }
        }

        const stick = Math.abs(pad.axes[0]) > 0.3 || Math.abs(pad.axes[1]) > 0.3;
        if (stick && activePad.current === null) activePad.current = pad.index;

        if (activePad.current === pad.index) {
          if (pad.axes[0] < -0.3) onKey("ArrowLeft");
          if (pad.axes[0] > 0.3) onKey("ArrowRight");
          if (pad.axes[1] < -0.3) onKey("ArrowUp");
          if (pad.axes[1] > 0.3) onKey("ArrowDown");
        }

        prevButtons.current = pressed;
      }
    };

    const interval = setInterval(poll, 100);
    return () => clearInterval(interval);
  }, [onKey, enabled]);

  return activePad;
}
