import time
import threading
import pyautogui
from pynput import keyboard

# ================== AYARLAR ==================
CLICK_DELAY = 0.5       # bekleme süresi (saniye)
DELAY_MODE  = "cycle"   # "each"  → her tıklama sonrası bekle
                        # "cycle" → üçlü tıklama bittikten sonra bekle
MOVE_DURATION = 0.35    # fare hareket süresi

CLICK_POINTS = [
    (1016, 625),
    (845,  627),
    (871,  712),
]

pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True

# ================== DURUM ==================
RUNNING = False
PAUSED  = False
STOP    = False
lock    = threading.Lock()

# ================== YARDIMCILAR ==================
def warn_if_offscreen(x, y):
    w, h = pyautogui.size()
    if not (0 <= x < w and 0 <= y < h):
        print(f"[Uyarı] Koordinat ekran dışında olabilir: ({x},{y}) | Ekran: {w}x{h}")

def click_at(x, y):
    warn_if_offscreen(x, y)
    pyautogui.moveTo(x, y, duration=MOVE_DURATION)
    pyautogui.click(x=x, y=y)

def wait_if_paused_or_stop():
    while True:
        with lock:
            if STOP:
                return True
            paused = PAUSED
        if not paused:
            return False
        time.sleep(0.1)

# ================== İŞ AKIŞI (THREAD) ==================
def workflow():
    global RUNNING
    try:
        step = 0
        while True:
            with lock:
                if STOP or not RUNNING:
                    break

            if wait_if_paused_or_stop():
                break

            x, y = CLICK_POINTS[step]
            print(f"[Tıklama] Nokta {step + 1}: ({x}, {y})")
            click_at(x, y)

            is_last = (step == len(CLICK_POINTS) - 1)
            step = (step + 1) % len(CLICK_POINTS)

            if wait_if_paused_or_stop():
                break

            if DELAY_MODE == "each" or (DELAY_MODE == "cycle" and is_last):
                time.sleep(CLICK_DELAY)

    except pyautogui.FailSafeException:
        print("\n[FailSafe] İmleç sol-üst köşeye gitti, durduruldu.")
    except KeyboardInterrupt:
        print("\n[Çıkış] Kullanıcı tarafından durduruldu.")
    finally:
        with lock:
            RUNNING = False
        print("[Durum] Çalışma durdu. 'B' ile yeniden başlatabilir, 'ESC' ile çıkabilirsin.")

# ================== KLAVYE KONTROL ==================
def on_press(key):
    global RUNNING, PAUSED, STOP
    try:
        if key == keyboard.Key.esc:
            with lock:
                STOP = True
                RUNNING = False
            print("\n[ESC] Çıkış isteniyor...")
            return False

        if isinstance(key, keyboard.KeyCode) and key.char:
            ch = key.char.lower()

            if ch == 'b':
                with lock:
                    if STOP:
                        return
                    if not RUNNING:
                        PAUSED = False
                        RUNNING = True
                        print("\n[B] Başlatılıyor...")
                        threading.Thread(target=workflow, daemon=True).start()
                    else:
                        if PAUSED:
                            PAUSED = False
                            print("\n[B] Devam edildi.")
                        else:
                            print("\n[B] Zaten çalışıyor.")

            elif ch == 'p':
                with lock:
                    if RUNNING and not PAUSED:
                        PAUSED = True
                        print("\n[P] Duraklatıldı. Devam için 'B'.")
                    elif RUNNING and PAUSED:
                        print("\n[P] Zaten duraklatılmış. Devam için 'B'.")
                    else:
                        print("\n[P] Çalışma yok. 'B' ile başlatabilirsin.")

    except Exception as e:
        print(f"\n[Klavye Hatası] {e}")

# ================== MAIN ==================
if __name__ == "__main__":
    mode_label = "her tıklama sonrası" if DELAY_MODE == "each" else "üçlü tıklama sonrası"
    print(f"""Hazır. Tıklanacak noktalar ({CLICK_DELAY}sn — {mode_label}, sürekli döngü):
  1. {CLICK_POINTS[0]}
  2. {CLICK_POINTS[1]}
  3. {CLICK_POINTS[2]}

B   → Başlat / Devam
P   → Duraklat
ESC → Çıkış
(Failsafe: imleci ekranın sol-üstüne götürürsen PyAutoGUI acil durdurur.)
""")
    try:
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
    except KeyboardInterrupt:
        pass
