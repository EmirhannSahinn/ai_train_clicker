"""
Önce Terminal'de Chrome'u debug modda aç:

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome-remote"

Bu sürümde 101'e ulaşıldığında yeniden döngüye girme mantığı kaldırıldı.
İlk tespit edilen total değer neyse süreç tek seferde o hedefe kadar devam eder.

"""

import time, re, threading
import pyautogui
import pyperclip
from pynput import keyboard

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# ================== AYARLAR ==================
# Filtre metinleri
VALUE1 = "Kargo sorgulama"   # adım 5
VALUE2 = "kargom nerede"     # adım 8 (istersen değiştir)

# Sayıların okunduğu CSS seçici (senin sayfanda çalışan seçici)
CSS_SELECTOR = ".msgLength.translate"  # gerekirse ".msgLength.translate strong"

# KOORDİNATLAR (ekranına göre gerekirse güncelle)
POS_1_CLICK            = (1562, 262)    # 1-2: git ve tıkla
POS_2_FIELD            = (1583, 362)    # 3-5: sol tık + VALUE1 yaz
POS_3_CLICK            = (1602, 444)    # 6: sol tık
POS_4_FIELD            = (1544, 429)    # 7-8: sol tık + VALUE2 yaz
POS_5_CLICK            = (1613, 475)    # 9: sol tık
POS_DOUBLECLICK        = (1040, 754)    # ilerleme için çift tık alanı

# Hız / bekleme (güncel değerler)
MOVE_DURATION = 0.35
DOUBLECLICK_INTERVAL = 0.12
READ_WAIT_AFTER_CLICK = 0.45
MAX_STAGNANT_READS = 40

# PyAutoGUI genel pause (her aksiyon arası kısa bekleme)
pyautogui.PAUSE = 0.05

# Chrome debug port
DEBUGGER_ADDR = "127.0.0.1:9222"

# PyAutoGUI güvenlik
pyautogui.FAILSAFE = True

# ================== DURUM ==================
RUNNING = False
PAUSED  = False
STOP    = False
driver  = None
lock    = threading.Lock()

# ================== YARDIMCILAR ==================
def warn_if_offscreen(x, y):
    w, h = pyautogui.size()
    if not (0 <= x < w and 0 <= y < h):
        print(f"[Uyarı] Koordinat ekran dışında olabilir: ({x},{y}) | Ekran: {w}x{h}")

def move_to(x, y):
    warn_if_offscreen(x, y)
    pyautogui.moveTo(x, y, duration=MOVE_DURATION)

def click_at(x, y, clicks=1, interval=0.05):
    move_to(x, y)
    pyautogui.click(x=x, y=y, clicks=clicks, interval=interval)

def paste_text(text):
    prev_clip = None
    try:
        prev_clip = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    pyautogui.hotkey('command', 'v')
    if prev_clip is not None:
        try:
            pyperclip.copy(prev_clip)
        except Exception:
            pass

def type_at(x, y, text, select_all=True):
    move_to(x, y)
    pyautogui.click()
    if select_all:
        pyautogui.hotkey('command', 'a')
    paste_text(text)

def wait_if_paused_or_stop():
    while True:
        with lock:
            if STOP:
                return True
            paused = PAUSED
        if not paused:
            return False
        time.sleep(0.1)

def apply_filter(v1, v2):
    if wait_if_paused_or_stop(): return True
    click_at(*POS_1_CLICK, clicks=1)

    if wait_if_paused_or_stop(): return True
    type_at(*POS_2_FIELD, v1, select_all=True)

    if wait_if_paused_or_stop(): return True
    click_at(*POS_3_CLICK, clicks=1)

    if wait_if_paused_or_stop(): return True
    type_at(*POS_4_FIELD, v2, select_all=True)

    if wait_if_paused_or_stop(): return True
    click_at(*POS_5_CLICK, clicks=1)

    print("[Durum] Filtre uygulandı.")
    return False

# ================== SELENIUM: AÇIK CHROME'A BAĞLAN & OKU ==================
def attach_to_open_chrome():
    global driver
    if driver is not None:
        return driver

    opts = Options()
    opts.add_experimental_option("debuggerAddress", DEBUGGER_ADDR)
    opts.page_load_strategy = "none"

    try:
        driver = webdriver.Chrome(options=opts)
        return driver
    except Exception as e1:
        print(f"[Uyarı] Selenium Manager ile başlatılamadı: {e1}")

    try:
        path = ChromeDriverManager().install()
        driver = webdriver.Chrome(service=Service(path), options=opts)
        return driver
    except Exception:
        raise RuntimeError(
            "ChromeDriver başlatılamadı. Muhtemel neden: macOS karantinası veya uyumsuz sürüm.\n"
            "Aşağıdaki Terminal komutlarıyla düzeltip tekrar deneyin:\n"
            "  find ~/.wdm -name chromedriver -type f\n"
            "  xattr -dr com.apple.quarantine <bulduğunuz-yol>\n"
            "  chmod +x <bulduğunuz-yol>\n"
            "Ayrıca Chrome’u debug port ile açtığınızdan emin olun ve 9222 portunu kontrol edin:\n"
            "  http://127.0.0.1:9222/json/version"
        )

def doc_ready(drv, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = drv.execute_script("return document.readyState")
            if state in ("interactive", "complete"):
                return
        except WebDriverException:
            pass
        time.sleep(0.2)
    raise TimeoutError("document.readyState beklerken zaman aşımı")

def find_text_in_this_context(drv, selector):
    try:
        return drv.execute_script(
            "const el=document.querySelector(arguments[0]); return el? el.innerText : null;",
            selector
        )
    except WebDriverException:
        return None

def find_text_across_iframes(drv, selector, max_depth=4, depth=0):
    txt = find_text_in_this_context(drv, selector)
    if txt:
        return txt, depth
    if depth >= max_depth:
        return None, depth

    frames = drv.find_elements(By.CSS_SELECTOR, "iframe, frame")
    for fr in frames:
        try:
            drv.switch_to.frame(fr)
            found, d = find_text_across_iframes(drv, selector, max_depth, depth + 1)
            drv.switch_to.parent_frame()
            if found:
                return found, d
        except WebDriverException:
            drv.switch_to.parent_frame()
            continue
    return None, depth

def parse_first_two_numbers(text):
    m = re.search(r'(\d+)\s*/\s*(\d+)', text or "")
    if not m:
        m = re.search(r'(\d+)', text or "")
        if m:
            return int(m.group(1)), None
        return None, None
    return int(m.group(1)), int(m.group(2))

def read_counts_via_dom(drv, selector=CSS_SELECTOR):
    try:
        drv.switch_to.default_content()
    except WebDriverException:
        pass

    try:
        doc_ready(drv, timeout=10)
    except TimeoutError:
        pass

    text, depth = find_text_across_iframes(drv, selector, max_depth=4)
    if not text:
        text, depth = find_text_across_iframes(drv, selector + " strong", max_depth=4)

    if not text:
        return None, None

    cur, tot = parse_first_two_numbers(text.strip())
    return cur, tot

def read_counts_with_retry(drv, selector=CSS_SELECTOR, timeout=15, interval=0.5):
    end = time.time() + timeout
    last_cur, last_tot = None, None

    while time.time() < end:
        cur, tot = read_counts_via_dom(drv, selector)
        if cur is not None and tot is not None:
            return cur, tot
        last_cur, last_tot = cur, tot
        time.sleep(interval)

    return last_cur, last_tot

# ================== TIKLAMA HEDEFİNE KADAR İLERLE ==================
def increment_until(drv, target_first):
    """
    İlk tespit edilen hedefe kadar çift tıklayarak ilerler.
    Herhangi bir 101 özel kuralı yoktur; ilk okunan total kaç ise o hedeflenir.
    """
    if target_first is None:
        print("[Uyarı] Hedef sayı None; işlem atlandı.")
        return

    stagnant = 0
    last_seen = None

    while True:
        if wait_if_paused_or_stop():
            return

        cur, tot = read_counts_via_dom(drv)
        if cur is None:
            time.sleep(READ_WAIT_AFTER_CLICK)
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı okunamıyor; döngüden çıkılıyor.")
                return
            continue

        print(f"[İlerleme] {cur} / {tot} → hedef: {target_first}", end="\r")

        if cur >= target_first:
            print(f"\n[Bilgi] Hedefe ulaşıldı: {cur}/{tot} (tıklama yok)")
            return

        click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
        time.sleep(READ_WAIT_AFTER_CLICK)

        cur2, _ = read_counts_via_dom(drv)
        if cur2 is None or (last_seen is not None and cur2 <= last_seen):
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı artmıyor gibi; döngüden çıkılıyor.")
                return
        else:
            stagnant = 0
            last_seen = cur2

# ================== İŞ AKIŞI (THREAD) ==================
def workflow():
    global RUNNING
    try:
        drv = attach_to_open_chrome()
        print("[Bilgi] Chrome'a bağlanılıyor...")
        try:
            doc_ready(drv, timeout=15)
        except TimeoutError:
            print("[Uyarı] document.readyState zaman aşımı; yine de devam ediliyor.")

        with lock:
            if STOP or not RUNNING:
                return

        if apply_filter(VALUE1, VALUE2):
            return

        time.sleep(1.0)

        cur, tot = read_counts_with_retry(drv, timeout=15, interval=0.5)
        if cur is None or tot is None:
            print("[Hata] Sayılar 15 sn içinde okunamadı (CSS/iframe/shadow DOM?/gecikme?). Çalışma durduruldu.")
            return
        print(f"[Bilgi] Okunan: {cur} / {tot}")
        print(f"[Senaryo] İlk tespit edilen toplam {tot} → süreç bu hedefe kadar tek seferde ilerleyecek.")

        increment_until(drv, tot)
        print("[Bitti] İlk tespit edilen toplam hedefe kadar işlem tamamlandı.")

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
                        print("\n[B] Başlatılıyor / devam ediliyor...")
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
    print("""Hazır.
B  → Başlat / Devam
P  → Duraklat (program kapanmaz)
ESC→ Çıkış
(Failsafe: imleci ekranın sol-üstüne götürürsen PyAutoGUI acil durdurur.)
""")
    try:
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
    except KeyboardInterrupt:
        pass
