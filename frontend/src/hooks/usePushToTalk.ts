import { useEffect, useRef } from "react";

import type { KeyCombo } from "../settings";
import { comboIsEmpty } from "../settings";

/**
 * Sekme odaktayken combo tuşları basılı tutulduğu sürece onChange(true), bırakılınca
 * onChange(false) çağırır. Sekme arka plana geçerse (blur) basılı tuşlar bırakılmış sayılır -
 * tarayıcı odak dışı klavye olaylarını zaten iletmez, bu sadece mic'in "takılı açık" kalmasını önler.
 */
export function usePushToTalk(enabled: boolean, combo: KeyCombo, onChange: (active: boolean) => void): void {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!enabled || comboIsEmpty(combo)) {
      return;
    }

    const pressed = new Set<string>();
    let active = false;

    function evaluate() {
      const ctrlOk = !combo.ctrl || [...pressed].some((code) => code.startsWith("Control"));
      const shiftOk = !combo.shift || [...pressed].some((code) => code.startsWith("Shift"));
      const altOk = !combo.alt || [...pressed].some((code) => code.startsWith("Alt"));
      const codeOk = !combo.code || pressed.has(combo.code);
      const shouldBeActive = ctrlOk && shiftOk && altOk && codeOk;
      if (shouldBeActive !== active) {
        active = shouldBeActive;
        onChangeRef.current(active);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      pressed.add(event.code);
      evaluate();
    }
    function handleKeyUp(event: KeyboardEvent) {
      pressed.delete(event.code);
      evaluate();
    }
    function reset() {
      pressed.clear();
      if (active) {
        active = false;
        onChangeRef.current(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", reset);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", reset);
      if (active) onChangeRef.current(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, combo.ctrl, combo.shift, combo.alt, combo.code]);
}
