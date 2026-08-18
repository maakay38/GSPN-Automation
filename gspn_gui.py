import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
from dataclasses import dataclass

import gspn_engine as eng
import auto_update

APP_TITLE = "GSPN Otomasyon Merkezi"
APP_VERSION = "2.2.3"
DEFAULT_INTERVAL = 30


@dataclass
class SelectInfo:
    key: str
    label: str
    element_id: str
    element_name: str
    options: list
    values: list
    selected_text: str


class GSPNGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("1080x760")
        self.minsize(920, 650)

        self.driver = None
        self.work_handle = None

        self.stop_event = threading.Event()
        self.worker_thread = None
        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()

        self.select_infos = {}
        self.select_vars = {}
        self.combo_widgets = {}
        self._update_check_started = False

        self._configure_theme()
        self._build_ui()

        self.after(120, self._drain_queues)
        self.after(1200, self._check_update_on_start)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------------------- UI --------------------

    def _configure_theme(self):
        self.configure(bg="#0B1220")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "TFrame",
            background="#0B1220",
        )
        style.configure(
            "Card.TFrame",
            background="#111C2E",
            relief="flat",
        )
        style.configure(
            "Title.TLabel",
            background="#0B1220",
            foreground="#F8FAFC",
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#0B1220",
            foreground="#94A3B8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background="#111C2E",
            foreground="#E2E8F0",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Field.TLabel",
            background="#111C2E",
            foreground="#CBD5E1",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background="#111C2E",
            foreground="#93C5FD",
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "TCombobox",
            padding=6,
            fieldbackground="#F8FAFC",
            background="#F8FAFC",
            foreground="#0F172A",
        )
        style.configure(
            "TEntry",
            padding=6,
            fieldbackground="#F8FAFC",
            foreground="#0F172A",
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 9),
        )
        style.configure(
            "Danger.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 9),
        )

    def _build_ui(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))

        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)

        ttk.Label(left, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Şube • Durum • Neden • Teknisyen • Ürün • Garanti Durumu",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        self.connection_badge = tk.Label(
            header,
            text="● Bağlı değil",
            bg="#111C2E",
            fg="#FCA5A5",
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
        )
        self.connection_badge.pack(side="right")

        controls = ttk.Frame(outer, style="Card.TFrame", padding=14)
        controls.pack(fill="x", pady=(0, 12))

        ttk.Label(controls, text="Kontrol Paneli", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=8, sticky="w", pady=(0, 10)
        )

        ttk.Label(controls, text="Bekleme Süresi (sn)", style="Field.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )

        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL))
        ttk.Entry(controls, textvariable=self.interval_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(0, 18)
        )

        self.connect_btn = ttk.Button(
            controls,
            text="Bağlan & Alanları Yükle",
            style="Accent.TButton",
            command=self.on_connect,
        )
        self.connect_btn.grid(row=1, column=2, padx=(0, 8))

        self.refresh_btn = ttk.Button(
            controls,
            text="Dropdownları Yenile",
            command=self.on_refresh,
            state="disabled",
        )
        self.refresh_btn.grid(row=1, column=3, padx=(0, 18))

        self.start_btn = ttk.Button(
            controls,
            text="▶ Başlat",
            style="Accent.TButton",
            command=self.on_start,
            state="disabled",
        )
        self.start_btn.grid(row=1, column=4, padx=(0, 8))

        self.stop_btn = ttk.Button(
            controls,
            text="■ Durdur",
            style="Danger.TButton",
            command=self.on_stop,
            state="disabled",
        )
        self.stop_btn.grid(row=1, column=5, padx=(0, 8))

        self.status_label = ttk.Label(
            controls,
            text="Hazır",
            style="Status.TLabel",
        )
        self.status_label.grid(row=1, column=6, sticky="e", padx=(18, 0))

        for c in range(7):
            controls.columnconfigure(c, weight=1, uniform="controlcols")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="maincols")
        body.columnconfigure(1, weight=1, uniform="maincols")
        body.rowconfigure(0, weight=1)

        filter_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        filter_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ttk.Label(filter_card, text="Arama Filtreleri", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))

        self.filter_canvas = tk.Canvas(filter_card, bg="#111C2E", highlightthickness=0)
        self.filter_scroll = ttk.Scrollbar(filter_card, orient="vertical", command=self.filter_canvas.yview)
        self.filter_inner = ttk.Frame(self.filter_canvas, style="Card.TFrame")
        self.filter_inner.bind("<Configure>", lambda e: self.filter_canvas.configure(scrollregion=self.filter_canvas.bbox("all")))
        self.filter_window = self.filter_canvas.create_window((0, 0), window=self.filter_inner, anchor="nw")
        self.filter_canvas.configure(yscrollcommand=self.filter_scroll.set)
        self.filter_canvas.bind("<Configure>", lambda e: self.filter_canvas.itemconfigure(self.filter_window, width=e.width))
        self.filter_canvas.pack(side="left", fill="both", expand=True)
        self.filter_scroll.pack(side="right", fill="y")

        self.empty_filters = ttk.Label(self.filter_inner, text="GSPN'ye bağlanınca dropdown alanları burada otomatik listelenecek.", style="Field.TLabel")
        self.empty_filters.pack(anchor="w", pady=12)

        log_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        log_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(log_card, text="Canlı İşlem Günlüğü", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))

        self.log_text = tk.Text(log_card, bg="#08111F", fg="#CFE3FF", insertbackground="#FFFFFF", relief="flat", font=("Consolas", 9), wrap="word", padx=10, pady=10)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self._append_log("GUI hazır. Önce 'Bağlan & Alanları Yükle' butonuna basın.")

    def _append_log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log(self, text):
        self.log_queue.put(str(text))

    def _set_status(self, text, connected=None):
        self.status_queue.put((text, connected))

    def _drain_queues(self):
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass

        try:
            while True:
                text, connected = self.status_queue.get_nowait()
                self.status_label.configure(text=text)
                if connected is True:
                    self.connection_badge.configure(text="● GSPN bağlı", fg="#86EFAC")
                elif connected is False:
                    self.connection_badge.configure(text="● Bağlı değil", fg="#FCA5A5")
        except queue.Empty:
            pass

        self.after(120, self._drain_queues)

    def _connect_and_prepare(self):
        self._log("Chrome oturumuna bağlanılıyor...")
        driver = eng.connect()
        work = eng.step2_management(driver)
        driver.switch_to.window(work)
        eng.step3_work_order_lite(driver)
        self.driver = driver
        self.work_handle = work
        self._set_status("Bağlandı", True)
        self._log("GSPN İş Emirlerini Listele Lite ekranı hazır.")

    def _switch_right(self):
        if not self.driver:
            raise RuntimeError("GSPN bağlantısı yok.")
        self.driver.switch_to.window(self.work_handle)
        eng.switch_right(self.driver)

    def _discover_selects(self):
        self._switch_right()
        d = self.driver
        raw = d.execute_script(r"""
            const selects = Array.from(document.querySelectorAll('select'));
            function clean(s){ return (s || '').replace(/\s+/g,' ').trim(); }
            return selects.map((s, idx) => {
                const r = s.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return null;
                let label = '';
                const tr = s.closest('tr');
                if (tr) {
                    const cells = Array.from(tr.querySelectorAll('td,th'));
                    const sRect = s.getBoundingClientRect();
                    let best = null;
                    for (const c of cells) {
                        if (c.contains(s)) continue;
                        const cr = c.getBoundingClientRect();
                        const t = clean(c.innerText);
                        if (!t || t.length > 80) continue;
                        const sameRow = Math.abs((cr.y + cr.height/2) - (sRect.y + sRect.height/2)) < 18;
                        const left = cr.x < sRect.x;
                        if (sameRow && left) {
                            const dist = sRect.x - (cr.x + cr.width);
                            if (!best || dist < best.dist) best = {dist, text:t};
                        }
                    }
                    if (best) label = best.text;
                }
                if (!label) {
                    const parentText = clean(s.parentElement ? s.parentElement.innerText : '');
                    if (parentText && parentText.length <= 80) label = parentText;
                }
                const options = Array.from(s.options).map(o => ({text: clean(o.text), value: o.value}));
                return {idx, id: s.id || '', name: s.name || '', label: label || s.id || s.name || ('Select ' + (idx+1)), options, selectedText: s.options[s.selectedIndex] ? clean(s.options[s.selectedIndex].text) : ''};
            }).filter(Boolean);
        """)

        infos = []
        used_labels = {}
        for item in raw:
            label = item["label"].strip() or item["id"] or item["name"] or "Dropdown"
            used_labels[label] = used_labels.get(label, 0) + 1
            display_label = label if used_labels[label] == 1 else f"{label} ({used_labels[label]})"
            key = item["id"] or item["name"] or f"idx:{item['idx']}"
            infos.append(SelectInfo(key=key, label=display_label, element_id=item["id"], element_name=item["name"], options=[o["text"] for o in item["options"]], values=[o["value"] for o in item["options"]], selected_text=item["selectedText"]))
        self.driver.switch_to.default_content()
        return infos

    def _canonical_filter_name(self, label, info):
        text = (label or "").strip()
        low = text.casefold()
        if "şube" in low or "sube" in low: return "Şube"
        if low == "durum" or "status" in low: return "Durum"
        if "neden" in low or "reason" in low: return "Neden"
        if "teknisyen" in low or "technician" in low: return "Teknisyen"
        if low == "ürün" or low == "urun" or "product" in low: return "Ürün"
        if "g.dahili/harici" in low or "dahili/harici" in low or "garanti" in low or "warranty" in low: return "Garanti Durumu"
        key = f"{info.element_id} {info.element_name}".casefold()
        if "status" in key: return "Durum"
        if "reason" in key: return "Neden"
        if "tech" in key or "engineer" in key: return "Teknisyen"
        if "product" in key or "prd" in key: return "Ürün"
        if "warranty" in key or "garanti" in key: return "Garanti Durumu"
        if "branch" in key or "sube" in key: return "Şube"
        return None

    def _filter_requested_infos(self, infos):
        wanted_order = ["Şube", "Durum", "Neden", "Teknisyen", "Ürün", "Garanti Durumu"]
        selected = {}
        for info in infos:
            canonical = self._canonical_filter_name(info.label, info)
            if canonical and canonical not in selected:
                info.label = canonical
                selected[canonical] = info
        return [selected[name] for name in wanted_order if name in selected]

    def _render_selects(self, infos):
        infos = self._filter_requested_infos(infos)
        for child in self.filter_inner.winfo_children():
            child.destroy()
        self.select_infos.clear(); self.select_vars.clear(); self.combo_widgets.clear()
        for row, info in enumerate(infos):
            self.select_infos[info.key] = info
            ttk.Label(self.filter_inner, text=info.label, style="Field.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
            var = tk.StringVar(value=info.selected_text)
            combo = ttk.Combobox(self.filter_inner, textvariable=var, values=info.options, state="readonly", width=38)
            combo.grid(row=row, column=1, sticky="ew", pady=5)
            self.select_vars[info.key] = var; self.combo_widgets[info.key] = combo
        self.filter_inner.columnconfigure(1, weight=1)

    def _apply_gui_filters(self):
        self._switch_right(); d = self.driver
        for key, info in list(self.select_infos.items()):
            selected_text = self.select_vars[key].get().strip()
            if not selected_text: continue
            el = None
            if info.element_id:
                els = d.find_elements(eng.By.ID, info.element_id); el = els[0] if els else None
            if el is None and info.element_name:
                els = d.find_elements(eng.By.NAME, info.element_name); el = els[0] if els else None
            if el is None: continue
            sel = eng.Select(el); current = eng.norm(sel.first_selected_option.text)
            if current == selected_text: continue
            for opt in sel.options:
                if eng.norm(opt.text) == selected_text:
                    value = eng.safe_attr(opt, "value")
                    sel.select_by_value(value) if value else sel.select_by_visible_text(opt.text)
                    d.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)
                    self._log(f"Filtre uygulandı: {info.label} = {selected_text}")
                    time.sleep(0.15); break
        d.switch_to.default_content()

    def on_connect(self):
        if self.worker_thread and self.worker_thread.is_alive(): return
        self.connect_btn.configure(state="disabled"); self._set_status("Bağlanıyor...", None)
        def task():
            try:
                self._connect_and_prepare(); infos = self._discover_selects()
                self.after(0, lambda: self._render_selects(infos)); self.after(0, lambda: self.start_btn.configure(state="normal")); self.after(0, lambda: self.refresh_btn.configure(state="normal"))
                shown = len(self._filter_requested_infos(infos)); self._log(f"{shown} arama filtresi yüklendi.")
            except Exception as e:
                self._set_status("Bağlantı hatası", False); self._log(f"Bağlantı hatası: {e}")
            finally:
                self.after(0, lambda: self.connect_btn.configure(state="normal"))
        threading.Thread(target=task, daemon=True).start()

    def on_refresh(self):
        def task():
            try:
                infos = self._discover_selects(); self.after(0, lambda: self._render_selects(infos)); self._log("Arama filtreleri yenilendi.")
            except Exception as e: self._log(f"Dropdown yenileme hatası: {e}")
        threading.Thread(target=task, daemon=True).start()

    def on_start(self):
        if self.worker_thread and self.worker_thread.is_alive(): return
        try:
            interval = int(self.interval_var.get().strip())
            if interval < 3: raise ValueError
        except ValueError:
            messagebox.showwarning("Bekleme Süresi", "Bekleme süresi en az 3 saniye olan bir tam sayı olmalı."); return
        if not self.driver:
            messagebox.showwarning("Bağlantı", "Önce 'Bağlan & Alanları Yükle' butonuna basın."); return
        self.stop_event.clear(); self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.connect_btn.configure(state="disabled"); self.refresh_btn.configure(state="disabled")
        self.worker_thread = threading.Thread(target=self._automation_loop, args=(interval,), daemon=True); self.worker_thread.start()

    def on_stop(self):
        self.stop_event.set(); self._set_status("Durduruluyor...", True); self._log("Durdurma isteği gönderildi.")

    def _automation_loop(self, interval):
        self._set_status("Çalışıyor", True); self._log(f"Sürekli takip başladı. Arama aralığı: {interval} saniye.")
        cycle = 0
        try:
            while not self.stop_event.is_set():
                cycle += 1; self._log(f"──── Döngü #{cycle} ────")
                try:
                    self._apply_gui_filters(); found = eng.click_search_and_find_edit(self.driver)
                    if found:
                        self._log("Kayıt bulundu. Edit açıldı."); eng.process_current_record(self.driver); self._log("Kayıt işlemi ve Save tamamlandı."); eng.return_to_work_order_list(self.driver); self._log("Liste ekranına dönüldü.")
                    else: self._log("Kayıt bulunamadı.")
                except Exception as e:
                    self._log(f"Döngü hatası: {e}")
                    try: eng.return_to_work_order_list(self.driver); self._log("Hata sonrası liste ekranına dönüldü.")
                    except Exception as recovery_error: self._log(f"Toparlanma hatası: {recovery_error}")
                if self.stop_event.wait(interval): break
        finally:
            self._set_status("Durduruldu", True); self._log("Sürekli takip durduruldu.")
            self.after(0, lambda: self.start_btn.configure(state="normal")); self.after(0, lambda: self.stop_btn.configure(state="disabled")); self.after(0, lambda: self.connect_btn.configure(state="normal")); self.after(0, lambda: self.refresh_btn.configure(state="normal"))

    def _check_update_on_start(self):
        if self._update_check_started:
            return
        self._update_check_started = True

        try:
            result = auto_update.check_for_update(APP_VERSION)
            if not result:
                return
            remote_version, download_url, notes = result
            msg = f"Yeni sürüm bulundu: v{remote_version}\n\nMevcut sürüm: v{APP_VERSION}\nYeni sürüm: v{remote_version}\n"
            if notes: msg += f"\nNotlar:\n{notes}\n"
            if messagebox.askyesno("Güncelleme Bulundu", msg + "\nŞimdi güncellensin mi?"):
                self._append_log(f"Yeni sürüm indiriliyor: v{remote_version}")
                auto_update.download_and_install(root=self, download_url=download_url, current_exe_name="GSPN_Otomasyon.exe", new_version=remote_version)
        except Exception as e:
            self._append_log(f"Güncelleme kontrolü atlandı: {e}")

    def _on_close(self):
        self.stop_event.set(); self.destroy()


if __name__ == "__main__":
    app = GSPNGUI(); app.mainloop()
