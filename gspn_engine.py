from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select, WebDriverWait
import re
import time
import os
import socket
import subprocess
from pathlib import Path

DEBUG_ADDRESS = "127.0.0.1:9222"
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

def log(msg):
    print(msg)

def _debug_port_open(host="127.0.0.1", port=9222, timeout=0.35):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_chrome_exe():
    candidates = []

    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if base:
            candidates.extend([
                Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(base) / "Google" / "Chrome Beta" / "Application" / "chrome.exe",
            ])

    # Common Windows locations as fallback.
    candidates.extend([
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ])

    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass

    return None


def _launch_debug_chrome():
    chrome = _find_chrome_exe()
    if not chrome:
        raise RuntimeError(
            "Google Chrome bulunamadı. Chrome'un kurulu olduğundan emin olun."
        )

    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    profile_dir = os.path.join(
        local_appdata,
        "GSPN_Automasyon",
        "ChromeProfile",
    )
    os.makedirs(profile_dir, exist_ok=True)

    args = [
        chrome,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gspn1.samsungcsportal.com/main.jsp",
    ]

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    end = time.time() + 20
    while time.time() < end:
        if _debug_port_open():
            return
        time.sleep(0.4)

    raise RuntimeError(
        "Chrome açıldı fakat 9222 debug portu hazır hale gelmedi."
    )


def connect():
    """
    Önce mevcut 127.0.0.1:9222 Chrome oturumuna bağlanır.
    Port kapalıysa Chrome'u otomatik olarak özel GSPN profiliyle açar.
    """
    if not _debug_port_open():
        log("Chrome debug oturumu bulunamadı; Chrome otomatik açılıyor...")
        _launch_debug_chrome()
        log("Chrome debug oturumu hazır.")

    options = Options()
    options.debugger_address = DEBUG_ADDRESS

    try:
        return webdriver.Chrome(options=options)
    except Exception as first_error:
        # Port görünse bile eski/bozuk Chrome oturumu olabilir.
        # Bir kez yeniden başlatmayı deniyoruz.
        if not _debug_port_open():
            _launch_debug_chrome()
            options = Options()
            options.debugger_address = DEBUG_ADDRESS
            return webdriver.Chrome(options=options)

        raise RuntimeError(
            "Chrome'a bağlanılamadı. "
            f"Detay: {first_error}"
        )


def wait_for_gspn_main(driver, timeout=180):
    """
    Kullanıcı ilk açılışta giriş yapmak zorundaysa, GSPN main.jsp
    görünene kadar bekler. Kullanıcı bu sırada açılan Chrome'da giriş yapabilir.
    """
    end = time.time() + timeout

    while time.time() < end:
        try:
            for h in driver.window_handles:
                try:
                    driver.switch_to.window(h)
                    url = (driver.current_url or "").lower()
                    if "gspn1.samsungcsportal.com/main.jsp" in url:
                        driver.switch_to.default_content()
                        return h
                except Exception:
                    pass
        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError(
        "GSPN ana sayfası 3 dakika içinde bulunamadı. "
        "Açılan Chrome penceresinde GSPN'ye giriş yapıp ana sayfayı açın."
    )

def norm(s):
    return " ".join((s or "").replace("\xa0", " ").split()).strip()

def safe_attr(el, name):
    try:
        return el.get_attribute(name) or ""
    except Exception:
        return ""

def find_main_window(driver):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "gspn1.samsungcsportal.com/main.jsp" in (driver.current_url or ""):
                return h
        except Exception:
            pass
    return None

def find_operate_window(driver):
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "biz1.samsungcsportal.com/gspn/operate.do" in (driver.current_url or ""):
                return h
        except Exception:
            pass
    return None

def step2_management(driver):
    log("\n[ADIM 2] Yönetim açılıyor...")

    existing = find_operate_window(driver)
    if existing:
        driver.switch_to.window(existing)
        log("operate.do sekmesi zaten açık; mevcut sekme kullanılacak.")
        return existing

    main = find_main_window(driver)
    if not main:
        raise RuntimeError("GSPN ana sekmesi bulunamadı.")

    driver.switch_to.window(main)
    driver.switch_to.default_content()
    driver.switch_to.frame(driver.find_element(By.NAME, "menu"))

    management = driver.find_element(By.XPATH, "//span[normalize-space()='Yönetim']")
    try:
        management.click()
    except Exception:
        driver.execute_script("arguments[0].click();", management)

    driver.switch_to.default_content()
    log("Yönetim'e tıklandı. operate.do bekleniyor...")

    end = time.time() + 20
    while time.time() < end:
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                if "biz1.samsungcsportal.com/gspn/operate.do" in (driver.current_url or ""):
                    log("Yönetim iş ekranı açıldı.")
                    return h
            except Exception:
                pass
        time.sleep(0.4)

    raise RuntimeError("Yönetim sonrası operate.do bulunamadı.")

def recursive_find_text(driver, text, depth=0, max_depth=7):
    for xp in [
        f"//*[normalize-space()='{text}']",
        f"//*[contains(normalize-space(.),'{text}')]"
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    pass
        except Exception:
            pass

    if depth >= max_depth:
        return None

    frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
    for i in range(len(frames)):
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
            driver.switch_to.frame(frames[i])
            found = recursive_find_text(driver, text, depth + 1, max_depth)
            if found is not None:
                return found
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                driver.switch_to.default_content()
    return None

def smart_click_menu_item(driver, element):
    candidates = []
    if safe_attr(element, "onclick") or safe_attr(element, "href"):
        candidates.append(element)

    for xp in [
        ".//*[@onclick]",
        ".//a[@href]",
        ".//*[contains(@style,'cursor') and contains(@style,'pointer')]",
        ".//span", ".//td", ".//a"
    ]:
        try:
            for child in element.find_elements(By.XPATH, xp):
                if child not in candidates and child.is_displayed():
                    candidates.append(child)
        except Exception:
            pass

    if not candidates:
        candidates = [element]

    def score(el):
        return (
            (5 if safe_attr(el, "onclick") else 0)
            + (4 if safe_attr(el, "href") else 0)
            + (3 if el.tag_name.lower() == "a" else 0)
            + (2 if "pointer" in safe_attr(el, "style") else 0)
        )

    candidates.sort(key=score, reverse=True)
    target = candidates[0]

    try:
        target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", target)

def switch_to_frame_recursive(driver, frame_name, depth=0, max_depth=7):
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
    except Exception:
        frames = []

    for i in range(len(frames)):
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, "frame, iframe")
            fr = frames[i]
            name = safe_attr(fr, "name")
            fid = safe_attr(fr, "id")

            if name == frame_name or fid == frame_name:
                driver.switch_to.frame(fr)
                return True

            if depth < max_depth:
                driver.switch_to.frame(fr)
                if switch_to_frame_recursive(driver, frame_name, depth + 1, max_depth):
                    return True
                driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                driver.switch_to.default_content()
    return False

def wait_for_search_form(driver, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            driver.switch_to.default_content()
            if switch_to_frame_recursive(driver, "rightContents"):
                if driver.find_elements(By.ID, "status1"):
                    return True
            driver.switch_to.default_content()
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
        time.sleep(0.5)
    return False

def step3_work_order_lite(driver):
    log("\n[ADIM 3] İş Emirlerini Listele Lite açılıyor...")

    driver.switch_to.default_content()
    if wait_for_search_form(driver, timeout=2):
        driver.switch_to.default_content()
        log("İş Emirlerini Listele formu zaten açık.")
        return

    driver.switch_to.default_content()
    target = None
    end = time.time() + 15

    while time.time() < end:
        driver.switch_to.default_content()
        target = recursive_find_text(driver, "İş Emirlerini Listele Lite")
        if target is not None:
            break
        time.sleep(0.5)

    if target is None:
        raise RuntimeError("'İş Emirlerini Listele Lite' bulunamadı.")

    smart_click_menu_item(driver, target)
    driver.switch_to.default_content()

    if not wait_for_search_form(driver, timeout=20):
        raise RuntimeError("İş Emirlerini Listele formu yüklenmedi.")

    driver.switch_to.default_content()
    log("Arama formu yüklendi.")

def switch_right(driver):
    driver.switch_to.default_content()
    if not switch_to_frame_recursive(driver, "rightContents"):
        raise RuntimeError("rightContents frame bulunamadı.")

def step4_status(driver):
    log("\n[ADIM 4] Durum = ST025 Teknisyen Atandı...")
    switch_right(driver)

    status = WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "status1")
    )

    Select(status).select_by_value("ST025")
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
        status
    )

    log("Durum seçildi: " + norm(Select(status).first_selected_option.text))

def find_warranty_select(driver):
    for xp in [
        "//*[contains(normalize-space(.),'G.Dahili/Harici')]/following::select[1]",
        "//*[contains(normalize-space(.),'Dahili/Harici')]/following::select[1]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    return el
        except Exception:
            pass

    for el in driver.find_elements(By.TAG_NAME, "select"):
        try:
            if any("garanti harici" in norm(o.text).casefold() for o in Select(el).options):
                return el
        except Exception:
            pass
    return None

def step5_warranty(driver):
    log("\n[ADIM 5] G.Dahili/Harici = Garanti Harici...")
    switch_right(driver)

    el = find_warranty_select(driver)
    if el is None:
        raise RuntimeError("G.Dahili/Harici alanı bulunamadı.")

    sel = Select(el)
    target = None

    for opt in sel.options:
        if norm(opt.text).casefold() == "garanti harici":
            target = opt
            break

    if target is None:
        for opt in sel.options:
            if "garanti harici" in norm(opt.text).casefold():
                target = opt
                break

    if target is None:
        raise RuntimeError("Garanti Harici seçeneği bulunamadı.")

    value = safe_attr(target, "value")
    if value:
        sel.select_by_value(value)
    else:
        sel.select_by_visible_text(target.text)

    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el
    )

    log("Garanti seçildi: " + norm(Select(el).first_selected_option.text))

def find_search_button(driver):
    candidates = []
    for xp in [
        "//input[@value='Ara']",
        "//button[normalize-space()='Ara']",
        "//*[self::a or self::span][normalize-space()='Ara']",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    candidates.append(el)
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda e: e.rect.get("x", 0), reverse=True)
    return candidates[0]

def step6_search_edit(driver):
    log("\n[ADIM 6] Ara > Edit...")
    switch_right(driver)

    search = find_search_button(driver)
    if search is None:
        raise RuntimeError("Ara butonu bulunamadı.")

    try:
        search.click()
    except Exception:
        driver.execute_script("arguments[0].click();", search)

    def get_edit(d):
        for xp in [
            "//a[normalize-space()='Edit']",
            "//*[normalize-space()='Edit' and (self::a or self::span or self::td)]",
        ]:
            try:
                for el in d.find_elements(By.XPATH, xp):
                    if el.is_displayed():
                        return el
            except Exception:
                pass
        return False

    edit = WebDriverWait(driver, 20).until(get_edit)

    click_target = edit
    try:
        a = edit.find_element(By.XPATH, "./ancestor::a[1]")
        if a.is_displayed():
            click_target = a
    except Exception:
        pass

    try:
        click_target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", click_target)

    log("Edit'e basıldı.")
    time.sleep(2)

def find_label(driver, text):
    # En küçük görünür öğeyi seçmeye çalış.
    candidates = []
    for xp in [
        f"//*[normalize-space()='{text}']",
        f"//*[contains(normalize-space(.),'{text}')]"
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        candidates.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda e: len(norm(e.text)) if norm(e.text) else 99999)
    return candidates[0]

def get_nonzero_date_inputs(driver):
    result = []
    for inp in driver.find_elements(By.XPATH, "//input"):
        try:
            # Disabled/readonly olsa da JS value okunur.
            value = norm(driver.execute_script("return arguments[0].value || '';", inp))
            if not DATE_RE.match(value):
                continue
            if value == "00.00.0000":
                continue

            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
            """, inp)

            result.append((inp, value, rect))
        except Exception:
            pass
    return result

def choose_nearest_date_input(driver, label):
    lrect = driver.execute_script("""
        const r = arguments[0].getBoundingClientRect();
        return {x:r.x, y:r.y, width:r.width, height:r.height};
    """, label)

    lx = float(lrect.get("x", 0))
    ly = float(lrect.get("y", 0))
    lright = lx + float(lrect.get("width", 0))
    lcenter_y = ly + float(lrect.get("height", 0)) / 2

    candidates = get_nonzero_date_inputs(driver)
    if not candidates:
        return None, None

    scored = []
    for inp, value, rect in candidates:
        ix = float(rect.get("x", 0))
        iy = float(rect.get("y", 0))
        icenter_y = iy + float(rect.get("height", 0)) / 2

        dy = abs(icenter_y - lcenter_y)
        dx = max(0, ix - lright)

        # Aynı satıra yakın olanları çok güçlü tercih et.
        score = dy * 10 + dx
        scored.append((score, inp, value, rect))

    scored.sort(key=lambda x: x[0])
    best = scored[0]

    log("Bulunan tarih adayları:")
    for score, inp, value, rect in scored[:10]:
        log(
            f"  value={value} id={safe_attr(inp,'id') or '-'} "
            f"name={safe_attr(inp,'name') or '-'} "
            f"x={rect.get('x')} y={rect.get('y')} score={score:.1f}"
        )

    return best[1], best[2]

def choose_service_entry_date_input(driver, label):
    # "Cihaz Servise Giriş" satırında boş tarih inputunu seçmek için
    # label'a en yakın SAĞDAKİ boş/aktif text inputu bul.
    lrect = driver.execute_script("""
        const r = arguments[0].getBoundingClientRect();
        return {x:r.x, y:r.y, width:r.width, height:r.height};
    """, label)

    lx = float(lrect.get("x", 0))
    ly = float(lrect.get("y", 0))
    lright = lx + float(lrect.get("width", 0))
    lcenter_y = ly + float(lrect.get("height", 0)) / 2

    candidates = []

    for inp in driver.find_elements(By.XPATH, "//input"):
        try:
            itype = (safe_attr(inp, "type") or "text").lower()
            if itype in ("hidden", "button", "submit", "image", "checkbox", "radio"):
                continue

            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
            """, inp)

            ix = float(rect.get("x", 0))
            iy = float(rect.get("y", 0))
            icenter_y = iy + float(rect.get("height", 0)) / 2

            # Label'ın sağında olmayanları ele.
            if ix <= lright:
                continue

            dy = abs(icenter_y - lcenter_y)
            dx = ix - lright
            score = dy * 10 + dx

            value = norm(driver.execute_script("return arguments[0].value || '';", inp))
            candidates.append((score, inp, value, rect))
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])

    log("Cihaz Servise Giriş input adayları:")
    for score, inp, value, rect in candidates[:10]:
        log(
            f"  value={value or '(boş)'} id={safe_attr(inp,'id') or '-'} "
            f"name={safe_attr(inp,'name') or '-'} "
            f"x={rect.get('x')} y={rect.get('y')} score={score:.1f}"
        )

    return candidates[0][1]

def set_input_value(driver, el, value):
    # Normal input yazma
    try:
        el.click()
        el.clear()
        el.send_keys(value)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el
        )
        return True
    except Exception:
        pass

    # JS fallback
    try:
        driver.execute_script("""
            const el = arguments[0];
            const value = arguments[1];
            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            el.blur();
        """, el, value)
        return True
    except Exception:
        return False

def step7_read_and_write_date(driver):
    log("\n[ADIM 7] Ekrandaki Teknisyen Atandı tarihi okunuyor ve Cihaz Servise Giriş'e yazılıyor...")

    switch_right(driver)

    assigned_label = WebDriverWait(driver, 20).until(
        lambda d: find_label(d, "Teknisyen Atandı") or False
    )
    service_label = find_label(driver, "Cihaz Servise Giriş")

    if service_label is None:
        raise RuntimeError("'Cihaz Servise Giriş' etiketi bulunamadı.")

    src, src_value = choose_nearest_date_input(driver, assigned_label)
    if src is None or not src_value:
        raise RuntimeError("Teknisyen Atandı çevresinde okunabilir tarih bulunamadı.")

    log("Okunan Teknisyen Atandı tarihi: " + src_value)
    log("Kaynak input ID   : " + (safe_attr(src, "id") or "-"))
    log("Kaynak input Name : " + (safe_attr(src, "name") or "-"))

    dst = choose_service_entry_date_input(driver, service_label)
    if dst is None:
        raise RuntimeError("Cihaz Servise Giriş tarih inputu bulunamadı.")

    dst_value = norm(driver.execute_script("return arguments[0].value || '';", dst))
    disabled = bool(driver.execute_script("return !!arguments[0].disabled;", dst))
    readonly = bool(driver.execute_script("return !!arguments[0].readOnly;", dst))

    log("Hedef input ID    : " + (safe_attr(dst, "id") or "-"))
    log("Hedef input Name  : " + (safe_attr(dst, "name") or "-"))
    log("Hedef mevcut değer: " + (dst_value or "(boş)"))
    log("Hedef disabled    : " + str(disabled))
    log("Hedef readonly    : " + str(readonly))

    # Kullanıcı kuralı: dolu veya pasif ise atla.
    if dst_value:
        log("Cihaz Servise Giriş dolu. Atlandı.")
        return "SKIP_FILLED"

    if disabled or readonly or (not dst.is_enabled()):
        log("Cihaz Servise Giriş pasif/readonly. Atlandı.")
        return "SKIP_DISABLED"

    if not set_input_value(driver, dst, src_value):
        raise RuntimeError("Tarih hedef alana yazılamadı.")

    time.sleep(0.5)
    check = norm(driver.execute_script("return arguments[0].value || '';", dst))

    if check != src_value:
        raise RuntimeError(
            f"Tarih yazma doğrulanamadı. Beklenen={src_value}, Hedef={check}"
        )

    log("Tarih başarıyla yazıldı: " + check)
    return "COPIED"


def find_reason_select_near_status(driver, status_el):
    # Önce status ile aynı satırdaki select'leri dene.
    try:
        row = status_el.find_element(By.XPATH, "./ancestor::tr[1]")
        selects = row.find_elements(By.TAG_NAME, "select")
        for sel_el in selects:
            if sel_el == status_el:
                continue
            try:
                texts = [norm(o.text) for o in Select(sel_el).options]
                if any("HP080" in t or "Onarım fiyat onayı bekleniyor" in t for t in texts):
                    return sel_el
            except Exception:
                pass
    except Exception:
        pass

    # Son çare: sayfadaki tüm selectlerde HP080 / açıklama ara.
    for sel_el in driver.find_elements(By.TAG_NAME, "select"):
        if sel_el == status_el:
            continue
        try:
            texts = [norm(o.text) for o in Select(sel_el).options]
            if any("HP080" in t or "Onarım fiyat onayı bekleniyor" in t for t in texts):
                return sel_el
        except Exception:
            pass

    return None

def step8_status_reason(driver):
    log("\n[ADIM 8] Durum/Neden = Bekliyor / Onarım fiyat onayı bekleniyor [HP080]...")
    switch_right(driver)

    # Durum alanını mevcut edit ekranında seçenek içeriğinden bul.
    status_el = None

    # Önce olası ID/name'ler.
    for key in ["status", "status1", "STATUS", "STATUS1"]:
        try:
            els = driver.find_elements(By.ID, key)
            for el in els:
                if el.tag_name.lower() == "select" and el.is_displayed():
                    texts = [norm(o.text) for o in Select(el).options]
                    if any(t.casefold() == "bekliyor" for t in texts):
                        status_el = el
                        break
            if status_el is not None:
                break
        except Exception:
            pass

    # Son çare: tüm selectleri tara.
    if status_el is None:
        for el in driver.find_elements(By.TAG_NAME, "select"):
            try:
                texts = [norm(o.text) for o in Select(el).options]
                if any(t.casefold() == "bekliyor" for t in texts) and any(
                    "Teknisyen Atandı".casefold() in t.casefold() for t in texts
                ):
                    status_el = el
                    break
            except Exception:
                pass

    if status_el is None:
        raise RuntimeError("Edit ekranındaki Durum select alanı bulunamadı.")

    status_sel = Select(status_el)
    status_target = None
    for opt in status_sel.options:
        if norm(opt.text).casefold() == "bekliyor":
            status_target = opt
            break

    if status_target is None:
        raise RuntimeError("Durum seçeneklerinde 'Bekliyor' bulunamadı.")

    status_value = safe_attr(status_target, "value")
    if status_value:
        status_sel.select_by_value(status_value)
    else:
        status_sel.select_by_visible_text(status_target.text)

    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
        status_el
    )
    time.sleep(0.8)

    log("Durum seçildi: " + norm(Select(status_el).first_selected_option.text))
    log("Durum value : " + (status_value or "-"))

    reason_el = find_reason_select_near_status(driver, status_el)
    if reason_el is None:
        raise RuntimeError("Neden select alanı veya HP080 seçeneği bulunamadı.")

    reason_sel = Select(reason_el)
    reason_target = None

    for opt in reason_sel.options:
        text = norm(opt.text)
        if "HP080" in text:
            reason_target = opt
            break

    if reason_target is None:
        for opt in reason_sel.options:
            if "Onarım fiyat onayı bekleniyor" in norm(opt.text):
                reason_target = opt
                break

    if reason_target is None:
        raise RuntimeError("'Onarım fiyat onayı bekleniyor [HP080]' seçeneği bulunamadı.")

    reason_value = safe_attr(reason_target, "value")
    if reason_value:
        reason_sel.select_by_value(reason_value)
    else:
        reason_sel.select_by_visible_text(reason_target.text)

    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
        reason_el
    )
    time.sleep(0.5)

    log("Neden seçildi: " + norm(Select(reason_el).first_selected_option.text))
    log("Neden value : " + (reason_value or "-"))

    return "STATUS_REASON_SET"


def find_product_info_header(driver):
    # Önce tam metinle Ürün Bilgileri başlığını bul.
    candidates = []
    for xp in [
        "//*[normalize-space()='Ürün Bilgileri']",
        "//*[contains(normalize-space(.),'Ürün Bilgileri')]"
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        candidates.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        return None

    # En kısa metinli öğe genellikle gerçek başlık hücresidir.
    candidates.sort(key=lambda e: len(norm(e.text)) if norm(e.text) else 99999)
    return candidates[0]

def choose_product_info_toggle(driver, header):
    candidates = []

    # Başlığın kendisi tıklanabilir mi?
    if safe_attr(header, "onclick") or "pointer" in safe_attr(header, "style"):
        candidates.append(header)

    # Header içindeki / yakınındaki gerçek aç-kapa öğelerini ara.
    for xp in [
        ".//*[@onclick]",
        ".//*[contains(@style,'cursor') and contains(@style,'pointer')]",
        ".//img",
        ".//span",
        ".//a",
        "./preceding::*[1][@onclick]",
        "./following::*[1][@onclick]",
    ]:
        try:
            for el in header.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed() and el not in candidates:
                        candidates.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    # Aynı üst container içinde küçük ikon/onclick ara.
    for up in [1, 2, 3, 4]:
        try:
            container = header.find_element(By.XPATH, f"./ancestor::*[{up}]")
            for xp in [
                ".//*[@onclick]",
                ".//*[contains(@style,'cursor') and contains(@style,'pointer')]",
                ".//img",
                ".//span",
                ".//a",
            ]:
                for el in container.find_elements(By.XPATH, xp):
                    try:
                        if not el.is_displayed() or el in candidates:
                            continue
                        # Başlığa yakın ve küçük öğeleri tercih etmek için ekle.
                        hr = header.rect
                        er = el.rect
                        if abs(er.get("y", 0) - hr.get("y", 0)) <= 20:
                            candidates.append(el)
                    except Exception:
                        pass
        except Exception:
            pass

    if not candidates:
        return header

    def score(el):
        s = 0
        tag = el.tag_name.lower()
        onclick = safe_attr(el, "onclick")
        style = safe_attr(el, "style")
        src = safe_attr(el, "src")
        title = safe_attr(el, "title")
        alt = safe_attr(el, "alt")
        txt = norm(el.text)

        if onclick:
            s += 10
        if "pointer" in style:
            s += 5
        if tag in ("img", "span", "a"):
            s += 4
        if "open" in (src + title + alt).casefold() or "close" in (src + title + alt).casefold():
            s += 3
        if txt == "Ürün Bilgileri":
            s += 2

        # Küçük ikonlar daha olası.
        try:
            r = el.rect
            if r.get("width", 999) <= 40 and r.get("height", 999) <= 40:
                s += 4
        except Exception:
            pass

        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]

def step9_open_product_info(driver):
    log("\n[ADIM 9] Ürün Bilgileri bölümü açılıyor...")
    switch_right(driver)

    header = WebDriverWait(driver, 20).until(
        lambda d: find_product_info_header(d) or False
    )

    log("Ürün Bilgileri başlığı bulundu.")
    log("Header tag : " + header.tag_name)
    log("Header text: " + (norm(header.text) or "-"))

    toggle = choose_product_info_toggle(driver, header)

    log("Tıklanacak öğe:")
    log("  Tag     : " + toggle.tag_name)
    log("  Text    : " + (norm(toggle.text) or "-"))
    log("  ID      : " + (safe_attr(toggle, "id") or "-"))
    log("  Class   : " + (safe_attr(toggle, "class") or "-"))
    log("  OnClick : " + (safe_attr(toggle, "onclick") or "-"))
    log("  Src     : " + (safe_attr(toggle, "src") or "-"))

    # Tıkla.
    try:
        toggle.click()
    except Exception:
        driver.execute_script("arguments[0].click();", toggle)

    time.sleep(1)

    log("Ürün Bilgileri aç/kapa kontrolüne tıklandı.")
    return "PRODUCT_INFO_TOGGLED"


def step10_fill_dealer(driver):
    log("\n[ADIM 10] Bayi alanına 72000000000 yazılıyor...")
    switch_right(driver)

    # "Bayi" etiketini bul.
    labels = []
    for xp in [
        "//*[normalize-space()='Bayi']",
        "//*[contains(normalize-space(.),'Bayi')]"
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        labels.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not labels:
        raise RuntimeError("'Bayi' etiketi bulunamadı.")

    # En kısa metinli görünür öğe gerçek etikete en yakın adaydır.
    labels.sort(key=lambda e: len(norm(e.text)) if norm(e.text) else 99999)
    label = labels[0]

    lr = driver.execute_script("""
        const r = arguments[0].getBoundingClientRect();
        return {x:r.x, y:r.y, width:r.width, height:r.height};
    """, label)
    lright = float(lr["x"]) + float(lr["width"])
    lcy = float(lr["y"]) + float(lr["height"]) / 2

    candidates = []
    for inp in driver.find_elements(By.XPATH, "//input"):
        try:
            typ = (safe_attr(inp, "type") or "text").lower()
            if typ in ("hidden", "button", "submit", "image", "checkbox", "radio"):
                continue
            if not inp.is_displayed():
                continue

            r = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
            """, inp)
            x = float(r["x"])
            cy = float(r["y"]) + float(r["height"]) / 2

            if x <= lright:
                continue

            dy = abs(cy - lcy)
            dx = x - lright
            score = dy * 10 + dx
            candidates.append((score, inp))
        except Exception:
            pass

    if not candidates:
        raise RuntimeError("'Bayi' etiketinin yanındaki input bulunamadı.")

    candidates.sort(key=lambda x: x[0])
    field = candidates[0][1]

    log("Bayi inputu bulundu.")
    log("  ID   : " + (safe_attr(field, "id") or "-"))
    log("  Name : " + (safe_attr(field, "name") or "-"))

    if not field.is_enabled() or safe_attr(field, "disabled") or safe_attr(field, "readonly"):
        raise RuntimeError("Bayi alanı pasif/readonly.")

    value = "72000000000"

    try:
        field.click()
        field.clear()
        field.send_keys(value)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            field
        )
    except Exception:
        driver.execute_script("""
            const el=arguments[0], v=arguments[1];
            el.focus();
            el.value=v;
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
            el.blur();
        """, field, value)

    time.sleep(0.4)
    check = norm(driver.execute_script("return arguments[0].value || '';", field))
    if check != value:
        raise RuntimeError(f"Bayi değeri doğrulanamadı. Beklenen={value}, Alan={check}")

    log("Bayi alanına başarıyla yazıldı: " + check)
    return "DEALER_FILLED"


def find_label_exact_or_contains(driver, text):
    candidates = []
    for xp in [
        f"//*[normalize-space()='{text}']",
        f"//*[contains(normalize-space(.),'{text}')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        candidates.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda e: len(norm(e.text)) if norm(e.text) else 99999)
    return candidates[0]

def get_visible_text_inputs_near_label_row(driver, label, y_tolerance=18):
    lr = driver.execute_script("""
        const r = arguments[0].getBoundingClientRect();
        return {x:r.x, y:r.y, width:r.width, height:r.height};
    """, label)

    lright = float(lr["x"]) + float(lr["width"])
    lcy = float(lr["y"]) + float(lr["height"]) / 2
    candidates = []

    for inp in driver.find_elements(By.XPATH, "//input"):
        try:
            typ = (safe_attr(inp, "type") or "text").lower()
            if typ in ("hidden", "button", "submit", "image", "checkbox", "radio"):
                continue
            if not inp.is_displayed():
                continue

            r = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
            """, inp)

            x = float(r["x"])
            cy = float(r["y"]) + float(r["height"]) / 2

            if x <= lright or abs(cy - lcy) > y_tolerance:
                continue

            value = norm(driver.execute_script("return arguments[0].value || '';", inp))
            candidates.append((x, inp, value, r))
        except Exception:
            pass

    candidates.sort(key=lambda item: item[0])
    return candidates

def collect_visible_text_inputs(driver):
    items = []
    for inp in driver.find_elements(By.XPATH, "//input"):
        try:
            typ = (safe_attr(inp, "type") or "text").lower()
            if typ in ("hidden", "button", "submit", "image", "checkbox", "radio"):
                continue
            if not inp.is_displayed():
                continue

            value = norm(driver.execute_script("return arguments[0].value || '';", inp))
            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x:r.x, y:r.y, width:r.width, height:r.height};
            """, inp)

            items.append({
                "el": inp,
                "value": value,
                "x": float(rect.get("x", 0)),
                "y": float(rect.get("y", 0)),
                "w": float(rect.get("width", 0)),
                "h": float(rect.get("height", 0)),
                "id": safe_attr(inp, "id"),
                "name": safe_attr(inp, "name"),
            })
        except Exception:
            pass
    return items

def is_full_serial_value(value):
    v = (value or "").strip()
    if not v:
        return False
    if "*" in v or "." in v or ":" in v or "/" in v or " " in v:
        return False
    if len(v) < 8 or len(v) > 20:
        return False
    if "-" in v:
        return False
    return any(c.isalpha() for c in v) and any(c.isdigit() for c in v)

def is_masked_imei_value(value):
    v = (value or "").strip()
    return len(v) >= 8 and "*" in v and any(c.isdigit() for c in v)

def find_serial_source_and_target(driver):
    items = collect_visible_text_inputs(driver)

    log("Ürün Bilgileri alanındaki seri/IMEI adayları:")
    for item in items:
        v = item["value"]
        if is_full_serial_value(v) or is_masked_imei_value(v):
            log(
                f"  value={v or '(boş)'} "
                f"id={item['id'] or '-'} name={item['name'] or '-'} "
                f"x={item['x']} y={item['y']}"
            )

    serials = [i for i in items if is_full_serial_value(i["value"])]
    masked = [i for i in items if is_masked_imei_value(i["value"])]

    # Model/kod benzeri başka alfanümerik alanlar da olabilir.
    # Ürün bilgi bölümünde seri genelde masked IMEI ile aynı satıra en yakın olandır.
    source_item = None
    if masked and serials:
        best = None
        for s in serials:
            for m in masked:
                dy = abs(s["y"] - m["y"])
                dx = abs(s["x"] - m["x"])
                score = dy * 20 + dx
                if best is None or score < best[0]:
                    best = (score, s, m)
        if best:
            source_item = best[1]

    if source_item is None and serials:
        # En üstte görünen makul seri adayını seç.
        serials.sort(key=lambda i: (i["y"], i["x"]))
        source_item = serials[0]

    if source_item is None:
        raise RuntimeError("Alfanümerik Seri No kaynağı bulunamadı.")

    source = source_item["el"]
    source_value = source_item["value"]

    # Kullanıcının yeni kuralı:
    # Sağdaki seri/IMEI alanı zaten doluysa hiçbir şey yapmadan Save.
    # Maskeli IMEI değeri görünüyorsa bunu DOLU kabul et.
    if masked:
        # Kaynağa en yakın maskeli alanı hedef kabul et.
        masked.sort(
            key=lambda m: abs(m["y"] - source_item["y"]) * 20 + abs(m["x"] - source_item["x"])
        )
        target_item = masked[0]
        return source, source_value, target_item["el"], target_item["value"]

    # Maskeli alan yoksa, kaynağın aynı satırında ve sağında yer alan en yakın boş text inputu hedef kabul et.
    blanks = []
    source_right = source_item["x"] + source_item["w"]
    source_cy = source_item["y"] + source_item["h"] / 2

    for item in items:
        if item["el"] == source:
            continue
        if item["value"]:
            continue
        if item["x"] <= source_right:
            continue

        cy = item["y"] + item["h"] / 2
        dy = abs(cy - source_cy)
        dx = item["x"] - source_right

        # Aynı görsel satırdaki boş inputları güçlü biçimde tercih et.
        score = dy * 20 + dx
        blanks.append((score, item))

    if not blanks:
        raise RuntimeError("Seri No'nun sağındaki boş hedef alan bulunamadı.")

    blanks.sort(key=lambda t: t[0])
    target_item = blanks[0][1]

    log("Boş hedef Seri/IMEI alanı bulundu:")
    log(
        f"  id={target_item['id'] or '-'} name={target_item['name'] or '-'} "
        f"x={target_item['x']} y={target_item['y']}"
    )

    return source, source_value, target_item["el"], target_item["value"]

def set_text_value(driver, field, value):
    try:
        field.click()
        field.clear()
        field.send_keys(value)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            field
        )
    except Exception:
        driver.execute_script("""
            const el=arguments[0], v=arguments[1];
            el.focus();
            el.value=v;
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
            el.blur();
        """, field, value)

    time.sleep(0.4)
    return norm(driver.execute_script("return arguments[0].value || '';", field))

def find_button_by_text_or_value(driver, text):
    candidates = []
    for xp in [
        f"//input[@value='{text}']",
        f"//button[normalize-space()='{text}']",
        f"//*[self::a or self::span][normalize-space()='{text}']",
        f"//*[contains(@value,'{text}')]",
        f"//*[contains(normalize-space(.),'{text}') and (self::button or self::a or self::span)]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        candidates.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda e: (e.rect.get("y", 99999), -e.rect.get("x", 0)))
    return candidates[0]

def click_element(driver, el):
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)

def accept_optional_alerts(driver, first_timeout=10, second_timeout=5):
    accepted = 0

    end = time.time() + first_timeout
    while time.time() < end:
        try:
            alert = driver.switch_to.alert
            log("Popup 1: " + (alert.text or "(metin yok)"))
            alert.accept()
            accepted += 1
            log("Popup 1 -> Tamam")
            break
        except Exception:
            time.sleep(0.25)

    end = time.time() + second_timeout
    while time.time() < end:
        try:
            alert = driver.switch_to.alert
            log("Popup 2: " + (alert.text or "(metin yok)"))
            alert.accept()
            accepted += 1
            log("Popup 2 -> Tamam")
            break
        except Exception:
            time.sleep(0.25)

    return accepted

def click_save(driver):
    """
    SAVE DIRECT FIX v2.2.18

    Amaç:
    - Önce tüm frame/iframe contextlerinde sayfayı en üste al.
    - Exact "Save" butonunu DOM üzerinden tespit et.
    - Öncelik: input[value='Save'] / button text='Save'
    - Tıklama: native mouse event zinciri + JS .click() + Selenium click fallback.
    - Hangi frame/path'te tıklandığını logla.
    - Confirm Notice -> Save akışı korunur.
    """

    def switch_to_frame_path(path):
        driver.switch_to.default_content()
        for idx in path:
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            if idx >= len(frames):
                raise RuntimeError(f"Frame path geçersiz: {path}")
            driver.switch_to.frame(frames[idx])

    def scroll_top_here():
        try:
            driver.execute_script("""
                try { window.scrollTo(0, 0); } catch(e) {}
                try {
                    document.documentElement.scrollTop = 0;
                    document.body.scrollTop = 0;
                } catch(e) {}
            """)
        except Exception:
            pass

    def exact_save_elements():
        xpaths = [
            "//input[translate(normalize-space(@value),'SAVE','save')='save']",
            "//button[translate(normalize-space(.),'SAVE','save')='save']",
            "//a[translate(normalize-space(.),'SAVE','save')='save']",
        ]
        out = []
        seen = set()
        for xp in xpaths:
            try:
                for el in driver.find_elements(By.XPATH, xp):
                    try:
                        if el.id in seen:
                            continue
                        seen.add(el.id)
                        out.append(el)
                    except Exception:
                        pass
            except Exception:
                pass
        return out

    def rect(el):
        try:
            return driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {
                    x:r.x,y:r.y,width:r.width,height:r.height,
                    right:r.right,bottom:r.bottom
                };
            """, el)
        except Exception:
            return {"x":0,"y":99999,"width":0,"height":0,"right":0,"bottom":0}

    def collect_frame_paths(path=(), depth=0, max_depth=7):
        paths = [path]
        if depth >= max_depth:
            return paths
        try:
            switch_to_frame_path(path)
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            count = len(frames)
        except Exception:
            count = 0
        for i in range(count):
            paths.extend(collect_frame_paths(path + (i,), depth + 1, max_depth))
        return paths

    def collect_candidates():
        candidates = []
        paths = collect_frame_paths()
        for path in paths:
            try:
                switch_to_frame_path(path)
                scroll_top_here()
                time.sleep(0.08)

                try:
                    vw = float(driver.execute_script("return window.innerWidth || 1366;"))
                except Exception:
                    vw = 1366.0

                for el in exact_save_elements():
                    try:
                        r = rect(el)
                        tag = el.tag_name
                        value = safe_attr(el, "value") or ""
                        text = (el.text or "").strip()
                        onclick = safe_attr(el, "onclick") or ""
                        disabled = bool(safe_attr(el, "disabled"))
                        displayed = False
                        try:
                            displayed = el.is_displayed()
                        except Exception:
                            pass

                        # Üst araç çubuğundaki Save'i hedefle:
                        # - sayfayı en üste aldıktan sonra y küçük olmalı
                        # - mümkün olduğunca sağda olmalı
                        # - disabled olmamalı
                        y = float(r.get("y", 99999))
                        right_gap = max(0.0, vw - float(r.get("right", 0)))

                        score = abs(y) * 20.0 + right_gap
                        if tag.lower() == "input":
                            score -= 100.0
                        if value.strip().lower() == "save":
                            score -= 150.0
                        if displayed:
                            score -= 50.0
                        if disabled:
                            score += 10000.0

                        candidates.append({
                            "path": path,
                            "score": score,
                            "tag": tag,
                            "value": value,
                            "text": text,
                            "onclick": onclick,
                            "disabled": disabled,
                            "displayed": displayed,
                            "rect": r,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

        candidates.sort(key=lambda c: c["score"])
        return candidates

    def find_exact_element_in_current():
        els = exact_save_elements()
        if not els:
            return None

        # Aynı frame içinde en üst/sağ adayı seç.
        try:
            vw = float(driver.execute_script("return window.innerWidth || 1366;"))
        except Exception:
            vw = 1366.0

        ranked = []
        for el in els:
            try:
                r = rect(el)
                y = float(r.get("y", 99999))
                right_gap = max(0.0, vw - float(r.get("right", 0)))
                value = (safe_attr(el, "value") or "").strip().lower()
                score = abs(y) * 20.0 + right_gap
                if value == "save":
                    score -= 150.0
                ranked.append((score, el, r))
            except Exception:
                pass
        ranked.sort(key=lambda x: x[0])
        return ranked[0] if ranked else None

    def direct_dom_click(el, label):
        # Görünür alana al.
        try:
            driver.execute_script("""
                arguments[0].scrollIntoView({block:'center', inline:'center'});
            """, el)
            time.sleep(0.2)
        except Exception:
            pass

        # 1) Gerçek mouse event zinciri + click
        try:
            ok = driver.execute_script("""
                const el = arguments[0];
                if (!el) return false;
                try { el.focus(); } catch(e) {}
                const opts = {bubbles:true,cancelable:true,view:window,button:0};
                ['mouseover','mouseenter','mousemove','mousedown','mouseup','click']
                  .forEach(t => el.dispatchEvent(new MouseEvent(t, opts)));
                return true;
            """, el)
            if ok:
                log(label + " DOM MouseEvent zinciri ile tetiklendi.")
                return True
        except Exception as e:
            log(label + f" DOM MouseEvent başarısız: {e}")

        # 2) JS .click()
        try:
            driver.execute_script("arguments[0].click();", el)
            log(label + " JavaScript .click() ile tetiklendi.")
            return True
        except Exception as e:
            log(label + f" JS .click() başarısız: {e}")

        # 3) Selenium native
        try:
            el.click()
            log(label + " Selenium native click ile basıldı.")
            return True
        except Exception as e:
            log(label + f" Selenium click başarısız: {e}")

        # 4) ActionChains
        try:
            ActionChains(driver).move_to_element(el).pause(0.15).click(el).perform()
            log(label + " ActionChains ile basıldı.")
            return True
        except Exception as e:
            raise RuntimeError(f"{label} hiçbir yöntemle tıklanamadı: {e}")

    log("SAVE DIRECT FIX: tüm frame'lerde exact Save aranıyor...")

    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError("Hiçbir frame içinde exact 'Save' butonu bulunamadı.")

    log(f"Bulunan Save adayı sayısı: {len(candidates)}")
    for i, c in enumerate(candidates[:10], 1):
        r = c["rect"]
        log(
            f"  [{i}] path={c['path']} score={c['score']:.1f} "
            f"tag={c['tag']} value={c['value']!r} text={c['text']!r} "
            f"displayed={c['displayed']} disabled={c['disabled']} "
            f"x={r.get('x')} y={r.get('y')} w={r.get('width')} h={r.get('height')} "
            f"onclick={c['onclick']!r}"
        )

    chosen = candidates[0]
    switch_to_frame_path(chosen["path"])
    scroll_top_here()
    time.sleep(0.2)

    current = find_exact_element_in_current()
    if current is None:
        raise RuntimeError(
            f"Seçilen frame path'te Save yeniden bulunamadı: {chosen['path']}"
        )

    _, save_btn, save_rect = current

    log(
        "ANA SAVE SEÇİLDİ -> "
        f"path={chosen['path']} "
        f"x={save_rect.get('x')} y={save_rect.get('y')} "
        f"value={safe_attr(save_btn,'value')!r} "
        f"text={(save_btn.text or '').strip()!r} "
        f"onclick={safe_attr(save_btn,'onclick')!r}"
    )

    direct_dom_click(save_btn, "Ana Save")
    time.sleep(1.2)

    # Ana Save sonrası standart alert/confirm.
    for popup_no in range(1, 4):
        try:
            alert = driver.switch_to.alert
            log(f"Save sonrası JS popup {popup_no}: " + (alert.text or "(metin yok)"))
            alert.accept()
            log(f"JS popup {popup_no} -> Tamam/OK")
            time.sleep(0.5)
        except Exception:
            break

    # Confirm Notice için default_content'ten tüm frame'leri tekrar tara.
    popup_end = time.time() + 10
    popup_clicked = False

    while time.time() < popup_end and not popup_clicked:
        popup_candidates = collect_candidates()

        # Popup Save genellikle sayfanın ortalarındadır; üst toolbar Save'i ele.
        filtered = []
        for c in popup_candidates:
            y = float(c["rect"].get("y", 0))
            if y > 70 and c["displayed"] and not c["disabled"]:
                filtered.append(c)

        if filtered:
            filtered.sort(key=lambda c: c["score"])
            chosen_popup = filtered[0]
            switch_to_frame_path(chosen_popup["path"])

            # Aynı frame'deki exact Save'lerden y>70 olanı seç.
            popup_els = []
            for el in exact_save_elements():
                try:
                    rr = rect(el)
                    if float(rr.get("y", 0)) > 70:
                        popup_els.append((float(rr.get("y", 0)), el, rr))
                except Exception:
                    pass

            if popup_els:
                popup_els.sort(key=lambda x: x[0])
                _, popup_save, rr = popup_els[0]
                log(
                    "Confirm Notice Save seçildi -> "
                    f"path={chosen_popup['path']} x={rr.get('x')} y={rr.get('y')}"
                )
                direct_dom_click(popup_save, "Confirm Notice -> Save")
                popup_clicked = True
                time.sleep(1.0)
                break

        time.sleep(0.25)

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    if not popup_clicked:
        log("Confirm Notice görünmedi; ek popup Save gerekmemiş olabilir.")

    # Popup Save sonrası JS alert/confirm.
    for popup_no in range(1, 4):
        try:
            alert = driver.switch_to.alert
            log(
                f"Popup Save sonrası mesaj {popup_no}: " +
                (alert.text or "(metin yok)")
            )
            alert.accept()
            log(f"Popup Save sonrası mesaj {popup_no} -> Tamam")
            time.sleep(0.5)
        except Exception:
            break

    log("SAVE DIRECT FIX akışı tamamlandı.")

def step11_serial_warranty_and_save(driver):
    log("\n[ADIM 11] Seri/IMEI tamamla > Garanti Sorgula > Popup(lar) > Save...")
    switch_right(driver)

    source, source_value, target, target_value = find_serial_source_and_target(driver)

    log("Kaynak alan:")
    log("  ID    : " + (safe_attr(source, "id") or "-"))
    log("  Name  : " + (safe_attr(source, "name") or "-"))
    log("  Value : " + source_value)

    log("Hedef alan:")
    log("  ID    : " + (safe_attr(target, "id") or "-"))
    log("  Name  : " + (safe_attr(target, "name") or "-"))
    log("  Value : " + (target_value or "(boş)"))

    if target_value:
        log("Seri/IMEI hedef alanı DOLU.")
        log("Kopyalama ve Garanti Sorgula işlemleri YOK SAYILDI.")
        log("Doğrudan Save'e geçiliyor.")
    else:
        if (not target.is_enabled()) or safe_attr(target, "disabled") or safe_attr(target, "readonly"):
            log("Hedef Seri/IMEI alanı boş fakat pasif/readonly; alan atlanıyor ve doğrudan Save işlemine geçiliyor.")
            click_save(driver)
            return

        written = set_text_value(driver, target, source_value)
        if written != source_value:
            raise RuntimeError(
                f"Seri/IMEI kopyalama doğrulanamadı. Beklenen={source_value}, Alan={written}"
            )

        log("Seri/IMEI hedef alana kopyalandı: " + written)

        warranty_btn = find_button_by_text_or_value(driver, "Garanti Sorgula")
        if warranty_btn is None:
            raise RuntimeError("'Garanti Sorgula' butonu bulunamadı.")

        log("Garanti Sorgula butonuna basılıyor...")
        click_element(driver, warranty_btn)

        accepted = accept_optional_alerts(driver, first_timeout=10, second_timeout=5)
        log(f"Kabul edilen popup sayısı: {accepted}")
        time.sleep(1.5)

    click_save(driver)
    time.sleep(1)
    return "STEP11_DONE"


POLL_INTERVAL_SECONDS = 30

def return_to_work_order_list(driver):
    """
    Edit/Save sonrasında tekrar İş Emirlerini Listele Lite arama ekranına dön.
    Önce sağ üst 'Listele' butonunu kullanmayı dener.
    Olmazsa İş Emirlerini Listele Lite menüsüne tekrar tıklar.
    """
    log("\n[ADIM 12] Liste ekranına dönülüyor...")

    try:
        switch_right(driver)
        btn = find_button_by_text_or_value(driver, "Listele")
        if btn is not None:
            click_element(driver, btn)
            time.sleep(1.5)
            driver.switch_to.default_content()
            if wait_for_search_form(driver, timeout=10):
                driver.switch_to.default_content()
                log("Listele butonu ile arama ekranına dönüldü.")
                return True
    except Exception:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    log("Listele ile dönülemedi; İş Emirlerini Listele Lite menüsü kullanılacak.")
    driver.switch_to.default_content()

    target = None
    end = time.time() + 10
    while time.time() < end:
        driver.switch_to.default_content()
        target = recursive_find_text(driver, "İş Emirlerini Listele Lite")
        if target is not None:
            break
        time.sleep(0.5)

    if target is None:
        raise RuntimeError("Liste ekranına dönüş için İş Emirlerini Listele Lite bulunamadı.")

    smart_click_menu_item(driver, target)
    driver.switch_to.default_content()

    if not wait_for_search_form(driver, timeout=15):
        raise RuntimeError("Liste ekranına dönüldü fakat arama formu yüklenmedi.")

    driver.switch_to.default_content()
    log("İş Emirlerini Listele Lite ekranına dönüldü.")
    return True

def ensure_filters(driver):
    """
    Durum ve garanti seçimleri sayfada korunmuşsa dokunmaz.
    Bozulmuşsa yeniden uygular.
    """
    switch_right(driver)

    status = driver.find_element(By.ID, "status1")
    current_status = norm(Select(status).first_selected_option.text)

    if "ST025" not in current_status and "Teknisyen Atandı" not in current_status:
        Select(status).select_by_value("ST025")
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            status
        )
        log("Durum yeniden ST025 Teknisyen Atandı yapıldı.")
    else:
        log("Durum seçimi korunuyor: " + current_status)

    warranty = find_warranty_select(driver)
    if warranty is None:
        raise RuntimeError("G.Dahili/Harici alanı bulunamadı.")

    current_warranty = norm(Select(warranty).first_selected_option.text)

    if "Garanti Harici" not in current_warranty:
        sel = Select(warranty)
        target = None
        for opt in sel.options:
            if norm(opt.text).casefold() == "garanti harici":
                target = opt
                break
        if target is None:
            for opt in sel.options:
                if "garanti harici" in norm(opt.text).casefold():
                    target = opt
                    break
        if target is None:
            raise RuntimeError("Garanti Harici seçeneği bulunamadı.")

        value = safe_attr(target, "value")
        if value:
            sel.select_by_value(value)
        else:
            sel.select_by_visible_text(target.text)

        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            warranty
        )
        log("Garanti yeniden Garanti Harici yapıldı.")
    else:
        log("Garanti seçimi korunuyor: " + current_warranty)

    driver.switch_to.default_content()

def click_search_and_find_edit(driver):
    """
    Sadece Ara'ya basar ve ilk görünür Edit bağlantısını arar.
    Kayıt yoksa False döndürür.
    """
    switch_right(driver)

    search = find_search_button(driver)
    if search is None:
        raise RuntimeError("Ara butonu bulunamadı.")

    click_element(driver, search)
    log("Ara'ya basıldı.")

    # Sonuçların yüklenmesi için kısa bekleme.
    time.sleep(1.2)

    edits = []
    for xp in [
        "//a[normalize-space()='Edit']",
        "//*[normalize-space()='Edit' and (self::a or self::span or self::td)]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        edits.append(el)
                except Exception:
                    pass
        except Exception:
            pass

    if not edits:
        log("Kayıt bulunamadı. Edit yok.")
        driver.switch_to.default_content()
        return False

    edit = edits[0]
    log("Kayıt bulundu. İlk Edit'e basılıyor...")

    target = edit
    try:
        a = edit.find_element(By.XPATH, "./ancestor::a[1]")
        if a.is_displayed():
            target = a
    except Exception:
        pass

    click_element(driver, target)
    time.sleep(1.5)
    log("Edit'e basıldı.")
    return True

def process_current_record(driver):
    """
    ADIM 7-11 akışını uygular.
    """
    result7 = step7_read_and_write_date(driver)
    step8_status_reason(driver)
    step9_open_product_info(driver)
    step10_fill_dealer(driver)
    step11_serial_warranty_and_save(driver)

    log("Kayıt işlemi tamamlandı.")
    return result7

def continuous_loop(driver):
    """
    Yönetim ve İş Emirlerini Listele Lite yalnızca başlangıçta açılır.
    Sonra belirli aralıklarla Ara'ya basılır.
    Kayıt varsa ilk Edit işlenir; kayıt yoksa beklenir.
    """
    cycle = 0

    while True:
        cycle += 1
        print("\n" + "=" * 90)
        print(f"ADIM 12 DÖNGÜ #{cycle}")
        print("=" * 90)

        try:
            ensure_filters(driver)

            found = click_search_and_find_edit(driver)

            if found:
                process_current_record(driver)
                return_to_work_order_list(driver)
                ensure_filters(driver)
            else:
                # click_search_and_find_edit driver'ı default_content'a döndürür.
                pass

        except KeyboardInterrupt:
            raise

        except Exception as e:
            log("Döngü hatası: " + str(e))
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

            # Hata sonrası liste ekranına toparlanmayı dene.
            try:
                return_to_work_order_list(driver)
                ensure_filters(driver)
            except Exception as recovery_error:
                log("Toparlanma hatası: " + str(recovery_error))

        log(f"{POLL_INTERVAL_SECONDS} saniye bekleniyor...")
        time.sleep(POLL_INTERVAL_SECONDS)

def main():
    print("=" * 100)
    print("GSPN OTOMASYON - ADIM 12 / SÜREKLİ DÖNGÜ")
    print("=" * 100)
    print("Başlangıçta: Yönetim > İş Emirlerini Listele Lite > ST025 > Garanti Harici")
    print(f"Sonrasında her {POLL_INTERVAL_SECONDS} saniyede bir Ara yapılır.")
    print("Kayıt varsa ilk Edit açılır ve ADIM 7-11 işlemleri uygulanır.")
    print("Kayıt yoksa beklenir ve tekrar Ara yapılır.")
    print("Durdurmak için konsolda CTRL+C.")
    print()

    try:
        driver = connect()
        log("Chrome bağlantısı: BAŞARILI")

        # Yönetim sadece bir kez açılır.
        work = step2_management(driver)
        driver.switch_to.window(work)

        # İş Emirlerini Listele Lite sadece başlangıçta açılır.
        step3_work_order_lite(driver)

        # Filtreler başlangıçta bir kez uygulanır, sonrasında korunur/kontrol edilir.
        step4_status(driver)
        step5_warranty(driver)

        log("\nADIM 12 sürekli takip başladı.")
        continuous_loop(driver)

    except KeyboardInterrupt:
        print("\nADIM 12 kullanıcı tarafından durduruldu (CTRL+C).")

    except Exception as e:
        print("\nADIM 12 HATASI:")
        print(e)

    input("\nÇıkmak için ENTER...")

if __name__ == "__main__":
    main()
