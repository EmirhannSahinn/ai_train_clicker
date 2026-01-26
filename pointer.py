import time
import pyautogui
from mss import mss

pyautogui.FAILSAFE = True

def get_monitors():
    # mss.monitors[0] sanal tüm masaüstü; 1..N gerçek monitörler
    with mss() as sct:
        return sct.monitors[1:]

def find_monitor_for_point(x, y, monitors):
    for idx, m in enumerate(monitors, start=1):
        left, top, w, h = m["left"], m["top"], m["width"], m["height"]
        if left <= x < left + w and top <= y < top + h:
            return idx, m
    return None, None

def main():
    monitors = get_monitors()
    if not monitors:
        print("Monitör bulunamadı.")
        return

    print("CTRL+C ile durdurabilirsin.")
    try:
        while True:
            x, y = pyautogui.position()  # GLOBAL koordinat
            idx, mon = find_monitor_for_point(x, y, monitors)

            if mon:
                left, top, w, h = mon["left"], mon["top"], mon["width"], mon["height"]
                lx, ly = x - left, y - top                 # yerel (o monitöre göre)
                px, py = lx / w, ly / h                    # 0..1 arası yüzdesel
                print(
                    f"Global: ({x:4d}, {y:4d})  "
                    f"Monitör#{idx} @{left},{top} {w}x{h}  "
                    f"Local: ({lx:4d}, {ly:4d})  "
                    f"Percent: ({px:0.4f}, {py:0.4f})     ",
                    end="\r",
                    flush=True
                )
            else:
                # (Nadir) Monitör sınırları dışında bir değer
                print(f"Global: ({x}, {y})  Monitör bulunamadı.                         ", end="\r", flush=True)

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDurduruldu.")

if __name__ == "__main__":
    main()
