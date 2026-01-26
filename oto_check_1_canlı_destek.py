"""
Önce Terminal'de Chrome'u debug modda aç:

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome-remote"

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
VALUE1 = "canlı destek"   # adım 5
VALUE2 = "canlı destek"     # adım 8 (istersen değiştir)

# Sayıların okunduğu CSS seçici (senin sayfanda çalışan seçici)
CSS_SELECTOR = ".msgLength.translate"  # gerekirse ".msgLength.translate strong"

# KOORDİNATLAR (ekranına göre gerekirse güncelle)
POS_1_CLICK            = (1562, 262)    # 1-2: git ve tıkla
POS_2_FIELD            = (1583, 362)    # 3-5: sol tık + VALUE1 yaz
POS_3_CLICK            = (1602, 444)    # 6: sol tık
POS_4_FIELD            = (1544, 429)    # 7-8: sol tık + VALUE2 yaz
POS_5_CLICK            = (1613, 475)    # 9: sol tık
POS_DOUBLECLICK        = (1040, 754)    # 13-14: çift tıklanacak yer (ekran dışı olabilir!)
POS_SINGLE_AFTER_101   = (1518, 262)    # 14: tek tık (ekran dışı olabilir!)

# Hız / bekleme (güncel değerler)
MOVE_DURATION = 0.35            # fare hareket süresi (eski: 0.2)
DOUBLECLICK_INTERVAL = 0.12     # çift tık içi aralık (eski: 0.05)
READ_WAIT_AFTER_CLICK = 0.45    # tıklama sonrası DOM okuma beklemesi (eski: 0.2)
MAX_STAGNANT_READS = 40         # ilerleme yoksa deneme üst sınırı (eski: 20)

# PyAutoGUI genel pause (her aksiyon arası kısa bekleme)
pyautogui.PAUSE = 0.05

# Chrome debug port
DEBUGGER_ADDR = "127.0.0.1:9222"

# PyAutoGUI güvenlik
pyautogui.FAILSAFE = True      # imleci sol-üst köşeye taşırsan acil durdurur

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
    # Panoya yaz ve ⌘V ile yapıştır (Türkçe karakterler sorunsuz)
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
    # Duraklatıldıysa B’ye basılana kadar bekle; STOP geldiyse True döndür
    while True:
        with lock:
            if STOP:
                return True
            paused = PAUSED
        if not paused:
            return False
        time.sleep(0.1)

def apply_filter(v1, v2):
    # 1-2
    if wait_if_paused_or_stop(): return True
    click_at(*POS_1_CLICK, clicks=1)

    # 3-5
    if wait_if_paused_or_stop(): return True
    type_at(*POS_2_FIELD, v1, select_all=True)

    # 6
    if wait_if_paused_or_stop(): return True
    click_at(*POS_3_CLICK, clicks=1)

    # 7-8
    if wait_if_paused_or_stop(): return True
    type_at(*POS_4_FIELD, v2, select_all=True)

    # 9
    if wait_if_paused_or_stop(): return True
    click_at(*POS_5_CLICK, clicks=1)

    # 10
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

    # 1) Önce Selenium Manager ile dene (webdriver-manager gerekmez)
    try:
        driver = webdriver.Chrome(options=opts)
        return driver
    except Exception as e1:
        print(f"[Uyarı] Selenium Manager ile başlatılamadı: {e1}")

    # 2) Olmazsa webdriver-manager fallback
    try:
        path = ChromeDriverManager().install()
        driver = webdriver.Chrome(service=Service(path), options=opts)
        return driver
    except Exception as e2:
        # Net bir mesaj verip yukarıda yakalanması için yeniden fırlat
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
    # 1) Mevcut bağlamda dene
    txt = find_text_in_this_context(drv, selector)
    if txt:
        return txt, depth
    if depth >= max_depth:
        return None, depth

    # 2) Tüm iframeleri gez
    frames = drv.find_elements(By.CSS_SELECTOR, "iframe, frame")
    for fr in frames:
        try:
            drv.switch_to.frame(fr)
            found, d = find_text_across_iframes(drv, selector, max_depth, depth+1)
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
    # Her okumada top-level'e dön, doc ready bekle ve iframe'leri gez
    try:
        drv.switch_to.default_content()
    except WebDriverException:
        pass

    try:
        doc_ready(drv, timeout=10)
    except TimeoutError:
        pass  # bazı sayfalarda sürekli "interactive" kalabilir

    text, depth = find_text_across_iframes(drv, selector, max_depth=4)
    if not text:
        text, depth = find_text_across_iframes(drv, selector + " strong", max_depth=4)

    if not text:
        return None, None

    cur, tot = parse_first_two_numbers(text.strip())
    return cur, tot

def read_counts_with_retry(drv, selector=CSS_SELECTOR, timeout=15, interval=0.5):
    """
    Sayaç elementini (cur/tot) belirli bir süre boyunca tekrar tekrar okumayı dener.
    timeout süresi boyunca hem cur hem tot dolu gelirse döner.
    Aksi halde son görülen değeri (muhtemelen (None, None)) döner.
    """
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
def increment_until_v0(drv, target_first):
    """
    İlk sayı target_first olana kadar POS_DOUBLECLICK'te çift tık yapar.
    Hedefe ulaşıldığında (cur >= target_first) hiç tıklama yapmaz.
    B/P/ESC tuşlarına duyarlı; her adımda DOM'dan yeniden okur.
    """
    if target_first is None:
        print("[Uyarı] Hedef sayı None; işlem atlandı.")
        return

    stagnant = 0
    last_cur = None

    while True:
        if wait_if_paused_or_stop():
            return

        cur, tot = read_counts_via_dom(drv)
        if cur is not None:
            print(f"[İlerleme] {cur} / {tot} → hedef: {target_first}", end="\r")
            # Hedefe ulaşıldıysa tıklama YAPMA
            if cur >= target_first:
                print(f"\n[Bilgi] Hedefe ulaşıldı: {cur}/{tot}")
                return

        # Daima çift tık (100'de çift tık; 101'de tık yok)
        click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
        time.sleep(READ_WAIT_AFTER_CLICK)

        new_cur, _ = read_counts_via_dom(drv)
        if new_cur is None or new_cur == last_cur:
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı artmıyor gibi görünüyor; döngüden çıkılıyor.")
                return
        else:
            stagnant = 0
        last_cur = new_cur

def increment_until_v1(drv, target_first):
    """
    İlk sayı target_first olana kadar ilerler.
    Kural:
      - (tot > 101 ve target_first == 101) ise: cur >= 100 olduğunda TIKLAMA YOK → çık.
      - Diğer durumlarda: cur >= target_first ise TIKLAMA YOK → çık.
      - Aksi halde (cur < eşik) çift tık gönder.
    Yarış durumlarına karşı tıklamadan hemen önce bir JIT (just-in-time) kontrol daha yapılır.
    """
    if target_first is None:
        print("[Uyarı] Hedef sayı None; işlem atlandı.")
        return

    stagnant = 0
    last_seen = None

    while True:
        if wait_if_paused_or_stop():
            return

        # --- 1) İlk kontrol: sayıları oku ---
        cur, tot = read_counts_via_dom(drv)
        if cur is None:
            time.sleep(READ_WAIT_AFTER_CLICK)
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı okunamıyor; döngüden çıkılıyor.")
                return
            continue

        print(f"[İlerleme] {cur} / {tot} → hedef: {target_first}", end="\r")

        # --- 2) Eşik kontrolleri ---
        # (A) Toplam > 101 ve hedef 101 iken: 100'e ulaştıysan/üstündeysen tıklama yok
        if (tot is not None) and (tot > 101) and (target_first == 101) and (cur >= 100):
            print(f"\n[Bilgi] 100 eşiğine ulaşıldı: {cur}/{tot} (tıklama yok)")
            return

        # (B) Genel hedef kontrolü (tot <= 101 vb. senaryolar için)
        if cur >= target_first:
            print(f"\n[Bilgi] Hedefe ulaşıldı: {cur}/{tot} (tıklama yok)")
            return

        # --- 3) Tıklamadan hemen önce JIT kontrol ---
        cur2, tot2 = read_counts_via_dom(drv)
        if cur2 is not None:
            # Aynı eşik kurallarını JIT'te de uygula
            if (tot2 is not None) and (tot2 > 101) and (target_first == 101) and (cur2 >= 100):
                print(f"\n[Bilgi] 100 eşiğine ulaşıldı (JIT): {cur2}/{tot2} (tıklama yok)")
                return
            if cur2 >= target_first:
                print(f"\n[Bilgi] Hedefe ulaşıldı (JIT): {cur2}/{tot2} (tıklama yok)")
                return

        # --- 4) Hâlâ eşik altındayız → ÇİFT TIK ---
        click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
        time.sleep(READ_WAIT_AFTER_CLICK)

        # İlerleme/stagnation izle
        cur3, _ = read_counts_via_dom(drv)
        if cur3 is None or (last_seen is not None and cur3 <= last_seen):
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı artmıyor gibi; döngüden çıkılıyor.")
                return
        else:
            stagnant = 0
            last_seen = cur3

def increment_until(drv, target_first):
    """
    İlk sayı target_first olana kadar ilerler.
    Kural seti:
      - Eğer toplam > 101 ve target_first == 101:
          cur < 100  → çift tık
          cur == 100 → SON bir çift tık at ve çık
          cur >= 101 → tıklama YOK, çık
      - Diğer durumlarda:
          cur >= target_first → tıklama YOK, çık
          aksi → çift tık
    Tıklama öncesi/sonrası okuma yaparak overshoot'u önleyip akışı kontrol ediyoruz.
    """
    if target_first is None:
        print("[Uyarı] Hedef sayı None; işlem atlandı.")
        return

    stagnant = 0
    last_seen = None

    while True:
        if wait_if_paused_or_stop():
            return

        # 1) Oku
        cur, tot = read_counts_via_dom(drv)
        if cur is None:
            time.sleep(READ_WAIT_AFTER_CLICK)
            stagnant += 1
            if stagnant >= MAX_STAGNANT_READS:
                print("\n[Uyarı] Sayı okunamıyor; döngüden çıkılıyor.")
                return
            continue

        print(f"[İlerleme] {cur} / {tot} → hedef: {target_first}", end="\r")

        # 2) Özel durum: toplam > 101 ve hedef 101
        if (tot is not None) and (tot > 101) and (target_first == 101):
            if cur >= 101:
                print(f"\n[Bilgi] Hedefe ulaşıldı: {cur}/{tot} (tıklama yok)")
                return
            if cur == 100:
                # SON çift tık ve çık
                click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
                time.sleep(READ_WAIT_AFTER_CLICK)
                print("\n[Bilgi] 100'de son çift tık atıldı; sonraki aşamaya geçiliyor.")
                return
            # cur < 100 → çift tık
            click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
            time.sleep(READ_WAIT_AFTER_CLICK)
        else:
            # Genel durum
            if cur >= target_first:
                print(f"\n[Bilgi] Hedefe ulaşıldı: {cur}/{tot} (tıklama yok)")
                return
            click_at(*POS_DOUBLECLICK, clicks=2, interval=DOUBLECLICK_INTERVAL)
            time.sleep(READ_WAIT_AFTER_CLICK)

        # 3) İlerleme / stagnation kontrolü
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
        # Aktif sekme varsayılan olarak doğruysa doc_ready yeterli
        try:
            doc_ready(drv, timeout=15)
        except TimeoutError:
            print("[Uyarı] document.readyState zaman aşımı; yine de devam ediliyor.")

        while True:
            with lock:
                if STOP or not RUNNING:
                    break

            # 1-10: Filtre uygula
            if apply_filter(VALUE1, VALUE2):
                break  # STOP geldiyse

            # Filtre sonrası sonuçların gelmesi için küçük bir bekleme (opsiyonel)
            time.sleep(1.0)

            # 11: Sayıları oku (AJAX gecikmesine karşı retry'li)
            cur, tot = read_counts_with_retry(drv, timeout=15, interval=0.5)
            if cur is None or tot is None:
                print("[Hata] Sayılar 15 sn içinde okunamadı (CSS/iframe/shadow DOM?/gecikme?). Çalışma durduruldu.")
                break
            print(f"[Bilgi] Okunan: {cur} / {tot}")

            # 12-14: Karar
            if tot <= 101:
                print("[Senaryo] toplam ≤ 101 → sonuna kadar işle ve bitir.")
                increment_until(drv, tot)                # 13
                print("[Bitti] toplam ≤ 101 senaryosu tamamlandı.")
                break  # program açık kalır; B ile yeniden başlatabilirsin
            else:
                print("[Senaryo] toplam > 101 → 101'e kadar işle, sonra tek tık ve filtreyi yenile.")
                increment_until(drv, 101)                # 14
                if wait_if_paused_or_stop(): break
                click_at(*POS_SINGLE_AFTER_101, clicks=1)  # 14: tek tık
                time.sleep(0.3)
                # 15: while döngüsü başa döner → filtre tekrar uygulanır

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
            return False  # listener kapanır → program biter

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
