# gui_gtk.py (Com Tela de Loading / Blur, Tray Corrigido e Assets Independentes do Usuário)
import os
import subprocess
from urllib.parse import unquote, urlparse
import threading
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, GLib

import pystray
from pystray import MenuItem as item
from PIL import Image

import config_manager

CACHE_FOLDER = os.path.expanduser("~/.cache/rewall")


class VideoPreviewCard(Gtk.EventBox):
    def __init__(self, filename, full_path, on_click_callback):
        super().__init__()
        self.full_path = full_path
        self.on_click_callback = on_click_callback
        self.preview_ready = False

        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK |
            Gdk.EventMask.LEAVE_NOTIFY_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK
        )

        self.card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.card_box.get_style_context().add_class("card")
        self.add(self.card_box)

        self.thumb_frame = Gtk.Box()
        self.thumb_frame.set_size_request(440, 220)
        self.thumb_frame.get_style_context().add_class("thumb-frame")
        self.card_box.pack_start(self.thumb_frame, True, True, 0)

        self.image_widget = Gtk.Image()
        self.thumb_frame.pack_start(self.image_widget, True, True, 0)

        label = Gtk.Label(label=filename)
        label.get_style_context().add_class("card-title")
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(40)
        label.set_property("margin-top", 10)
        self.card_box.pack_start(label, False, False, 0)

        self.static_thumb = os.path.join(CACHE_FOLDER, f"{filename}_static_2x.png")
        self.anim_thumb = os.path.join(CACHE_FOLDER, f"{filename}_anim_2x.gif")

        self.generate_resources()

        self.connect("button-press-event", self.on_clicked)
        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

        self.show_static()

    def generate_resources(self):
        os.makedirs(CACHE_FOLDER, exist_ok=True)

        if not os.path.exists(self.static_thumb):
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", self.full_path,
                        "-ss", "00:00:01",
                        "-vframes", "1",
                        "-vf", "scale=440:220",
                        self.static_thumb
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False
                )
            except Exception:
                pass

        if not os.path.exists(self.anim_thumb):
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", self.full_path,
                        "-ss", "00:00:01",
                        "-t", "3",
                        "-vf", "scale=440:220,fps=15",
                        self.anim_thumb
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False
                )
            except Exception:
                pass

        self.preview_ready = os.path.exists(self.anim_thumb)

    def show_static(self):
        if os.path.exists(self.static_thumb):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    self.static_thumb, 440, 220, True
                )
                self.image_widget.set_from_pixbuf(pixbuf)
            except Exception:
                pass

    def show_animated(self):
        if self.preview_ready and os.path.exists(self.anim_thumb):
            try:
                animation = GdkPixbuf.PixbufAnimation.new_from_file(self.anim_thumb)
                self.image_widget.set_from_animation(animation)
            except Exception:
                pass

    def on_mouse_enter(self, widget, event):
        self.card_box.get_style_context().add_class("hover")
        self.show_animated()

    def on_mouse_leave(self, widget, event):
        self.card_box.get_style_context().remove_class("hover")
        self.show_static()

    def on_clicked(self, widget, event):
        if callable(self.on_click_callback):
            self.on_click_callback(self.full_path)

    def set_selected(self, selected):
        context = self.card_box.get_style_context()
        if selected:
            context.add_class("selected")
        else:
            context.remove_class("selected")


class WallpaperConfigApp:
    def __init__(self, on_video_selected_callback, current_wallpaper_config=None):
        self.callback = on_video_selected_callback
        self.selected_path = None
        self.cards = {}
        self.current_wallpaper_config = current_wallpaper_config or {}
        self.config = config_manager.load_config()
        self._sync_local_config_with_plugin()
        self.wallpaper_folder = self.config.get(
            "wallpaper_folder", os.path.expanduser("~/Vídeos/Hidamari")
        )
        os.makedirs(self.wallpaper_folder, exist_ok=True)
        os.makedirs(CACHE_FOLDER, exist_ok=True)
        self._timer_id = None
        self._remote_loading = False
        self._ignore_toggle = False
        self.search_query = ""
        self.css_provider = None
        self.tray_icon = None

        self.load_css()
        self.build_ui()

        # Agenda o carregamento dos wallpapers logo após a janela aparecer com o loading visível
        GLib.idle_add(self.init_load_wallpapers)

        paused = self._as_bool(self.current_wallpaper_config.get(
            "manual_paused", self.config.get("manual_paused", False)
        ))
        self._ignore_toggle = True
        self.btn_pause.set_active(paused)
        self.btn_pause.set_label("Retomar" if paused else "Pausar")
        self._ignore_toggle = False

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in {
            "true", "1", "yes", "sim", "on", "enabled", "ativo"
        }

    @staticmethod
    def _normalise_path(path):
        if not path:
            return ""
        text = str(path)
        if text.startswith("file://"):
            text = unquote(urlparse(text).path)
        return os.path.normcase(os.path.realpath(os.path.abspath(
            os.path.expanduser(text)
        )))

    def _sync_local_config_with_plugin(self):
        """Adota o estado real do wallpaper sem perder preferências locais da GUI."""
        if not self._as_bool(self.current_wallpaper_config.get("found", False)):
            return

        for key in (
            "volume", "pause_fullscreen", "playback_rate", "target_fps",
            "manual_paused",
        ):
            if key in self.current_wallpaper_config:
                self.config[key] = self.current_wallpaper_config[key]
        config_manager.save_config(self.config)

    def load_css(self):
        if self.css_provider:
            Gtk.StyleContext.remove_provider_for_screen(
                Gdk.Screen.get_default(), self.css_provider
            )

        self.css_provider = Gtk.CssProvider()
        theme = self.config.get("theme", "neon")
        filename = "style_original.css" if theme == "original" else "style.css"
        css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(css_path):
            try:
                self.css_provider.load_from_path(css_path)
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(), self.css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception:
                pass

    def build_ui(self):
        self.window = Gtk.Window(title="Re:Wall")
        self.window.set_default_size(1080, 760)
        self.window.get_style_context().add_class("rewall-window")
        self.window.connect("delete-event", self.on_window_delete)

        # Overlay principal para cobrir a UI com a tela de loading
        self.overlay = Gtk.Overlay()
        self.window.add(self.overlay)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.overlay.add(main_box)

        # Caminho dinâmico para o ícone principal
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                self.window.set_icon(pixbuf)
            except Exception as e:
                print(f"Erro ao carregar o ícone: {e}")

        # Tela de Loading / Blur (Overlay)
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.loading_box.set_valign(Gtk.Align.CENTER)
        self.loading_box.set_halign(Gtk.Align.CENTER)
        self.loading_box.get_style_context().add_class("loading-overlay")

        spinner = Gtk.Spinner()
        spinner.set_size_request(64, 64)
        spinner.start()
        self.loading_box.pack_start(spinner, False, False, 0)

        lbl_loading = Gtk.Label(label="Carregando e otimizando wallpapers...")
        lbl_loading.get_style_context().add_class("loading-text")
        self.loading_box.pack_start(lbl_loading, False, False, 0)

        self.overlay.add_overlay(self.loading_box)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("RE:WALL")
        header.set_subtitle("VIDEO WALLPAPER ENGINE")
        self.window.set_titlebar(header)

        refresh = Gtk.Button(label="Atualizar")
        refresh.get_style_context().add_class("header-action")
        refresh.connect("clicked", lambda w: self.init_load_wallpapers())
        header.pack_start(refresh)

        notebook = Gtk.Notebook()
        main_box.pack_start(notebook, True, True, 0)

        gallery = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        gallery.get_style_context().add_class("gallery")
        folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        folder_box.set_border_width(12)
        folder_box.get_style_context().add_class("control-surface")
        folder_box.pack_start(Gtk.Label(label="Pasta de Origem:", xalign=0), False, False, 0)

        self.btn_selecionar_pasta = Gtk.FileChooserButton(
            title="Selecione o diretório dos wallpapers",
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        try:
            self.btn_selecionar_pasta.set_current_folder(self.wallpaper_folder)
        except Exception:
            pass
        self.btn_selecionar_pasta.connect("current-folder-changed", self.on_folder_changed)
        folder_box.pack_start(self.btn_selecionar_pasta, True, True, 0)
        gallery.pack_start(folder_box, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        search_box.set_border_width(12)
        search_box.get_style_context().add_class("search-row")
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Pesquisar wallpapers por nome...")
        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic"
        )
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self.on_search_changed)
        search_box.pack_start(self.search_entry, True, True, 0)
        gallery.pack_start(search_box, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        gallery.pack_start(scroll, True, True, 0)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_column_spacing(20)
        self.flowbox.set_row_spacing(20)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_filter_func(self._filter_wallpapers)
        scroll.add(self.flowbox)
        notebook.append_page(gallery, Gtk.Label(label="GALERIA"))

        config_scroll = Gtk.ScrolledWindow()
        config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        config_box.set_border_width(32)
        config_box.get_style_context().add_class("config-panel")
        config_scroll.add(config_box)

        self.check_fullscreen = Gtk.CheckButton(
            label="Pausar automaticamente em tela cheia"
        )
        self.check_fullscreen.set_active(bool(self.config.get("pause_fullscreen", True)))
        self.check_fullscreen.connect("toggled", self.on_config_changed)
        config_box.pack_start(self.check_fullscreen, False, False, 0)

        self.check_autostart = Gtk.CheckButton(
            label="Inicializar o Re:Wall junto com o KDE Plasma"
        )
        self.check_autostart.set_active(bool(self.config.get("autostart", False)))
        self.check_autostart.connect("toggled", self.on_config_changed)
        config_box.pack_start(self.check_autostart, False, False, 0)

        self.check_tray = Gtk.CheckButton(
            label="Minimizar para a bandeja (tray) ao fechar"
        )
        self.check_tray.set_active(bool(self.config.get("minimize_to_tray", True)))
        self.check_tray.connect("toggled", self.on_config_changed)
        config_box.pack_start(self.check_tray, False, False, 0)

        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        theme_row.pack_start(Gtk.Label(label="Tema", xalign=0), False, False, 0)
        self.theme_selector = Gtk.ComboBoxText()
        self.theme_selector.append("neon", "Neon")
        self.theme_selector.append("original", "Original")
        self.theme_selector.set_active_id(self.config.get("theme", "neon"))
        self.theme_selector.connect("changed", self.on_theme_changed)
        theme_row.pack_start(self.theme_selector, False, False, 0)
        config_box.pack_start(theme_row, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        row.pack_start(Gtk.Label(label="Volume", xalign=0), False, False, 0)
        self.slider_volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.slider_volume.set_value(float(self.config.get("volume", 0.0)) * 100)
        self.slider_volume.set_hexpand(True)
        self.slider_volume.set_draw_value(False)
        self.slider_volume.connect("value-changed", self.slider_changed)
        row.pack_start(self.slider_volume, True, True, 0)
        config_box.pack_start(row, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.pack_start(Gtk.Label(label="Velocidade", xalign=0), False, False, 0)
        self.spin_speed = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=float(self.config.get("playback_rate", 1.0)),
                lower=.05, upper=3, step_increment=.05
            ), digits=2
        )
        self.spin_speed.set_hexpand(True)
        self.spin_speed.connect("value-changed", self.params_changed)
        row.pack_start(self.spin_speed, True, True, 0)
        config_box.pack_start(row, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.pack_start(Gtk.Label(label="FPS alvo (0 = automático)", xalign=0), False, False, 0)
        self.spin_fps = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=int(self.config.get("target_fps", 0)),
                lower=0, upper=120, step_increment=1
            ), digits=0
        )
        self.spin_fps.set_hexpand(True)
        self.spin_fps.connect("value-changed", self.params_changed)
        row.pack_start(self.spin_fps, True, True, 0)
        config_box.pack_start(row, False, False, 0)
        notebook.append_page(config_scroll, Gtk.Label(label="CONFIGURAÇÕES"))

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.get_style_context().add_class("footer")
        main_box.pack_end(footer, False, False, 0)

        self.lbl_status = Gtk.Label(label="Status: escolha um wallpaper...")
        self.lbl_status.get_style_context().add_class("status")
        footer.pack_start(self.lbl_status, False, False, 0)

        self.btn_pause = Gtk.ToggleButton(label="Pausar")
        self.btn_pause.get_style_context().add_class("pause-action")
        self.btn_pause.connect("toggled", self.on_pause_toggled)
        footer.pack_end(self.btn_pause, False, False, 8)

        self.btn_apply = Gtk.Button(label="Aplicar Wallpaper")
        self.btn_apply.get_style_context().add_class("primary-action")
        self.btn_apply.set_sensitive(False)
        self.btn_apply.connect("clicked", self.on_apply_clicked)
        footer.pack_end(self.btn_apply, False, False, 0)

    def show(self):
        self.window.show_all()
        self.window.present()
        if self.check_tray.get_active():
            self.setup_tray_icon()

    def init_load_wallpapers(self):
        self.loading_box.show()
        self._loading_finished = False
        GLib.idle_add(self._run_load_sequence)
        return False

    def _run_load_sequence(self):
        self.load_wallpapers()
        self._loading_finished = True
        self.loading_box.hide()
        return False

    def _hide_loading_screen(self):
        if getattr(self, "_loading_finished", False):
            self.loading_box.hide()
        return False

    def on_folder_changed(self, widget):
        folder = widget.get_filename()
        if folder:
            self.wallpaper_folder = folder
            self.config["wallpaper_folder"] = folder
            config_manager.save_config(self.config)
            self.init_load_wallpapers()

    def _filter_wallpapers(self, child):
        card = child.get_child()
        if not card:
            return False
        return self.search_query in os.path.basename(card.full_path).casefold()

    def on_search_changed(self, widget):
        self.search_query = widget.get_text().strip().casefold()
        self.flowbox.invalidate_filter()

    def load_wallpapers(self):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)
        self.cards.clear()
        self.selected_path = None
        self.btn_apply.set_sensitive(False)

        try:
            files = [
                f for f in os.listdir(self.wallpaper_folder)
                if f.lower().endswith('.mp4')
            ]
        except Exception:
            files = []

        for filename in sorted(files, key=str.lower):
            path = os.path.abspath(os.path.join(self.wallpaper_folder, filename))
            card = VideoPreviewCard(filename, path, self.on_card_selected)
            self.cards[path] = card
            self.flowbox.insert(card, -1)

        self.flowbox.show_all()
        self.flowbox.invalidate_filter()
        self._select_current_wallpaper()

    def _select_current_wallpaper(self):
        active_path = self._normalise_path(
            self.current_wallpaper_config.get("original_file_path")
            or self.current_wallpaper_config.get("file_path", "")
        )
        if not active_path:
            return

        for path, card in self.cards.items():
            if self._normalise_path(path) == active_path:
                self.on_card_selected(path)
                paused = self._as_bool(
                    self.current_wallpaper_config.get("manual_paused", False)
                )
                auto_paused = (
                    self._as_bool(self.current_wallpaper_config.get(
                        "pause_fullscreen", False
                    ))
                    and self._as_bool(self.current_wallpaper_config.get(
                        "fullscreen_active", False
                    ))
                )
                state = (
                    "Pausado manualmente" if paused
                    else "Pausado em tela cheia" if auto_paused
                    else "Rodando"
                )
                self.lbl_status.set_text(
                    f"{state}: {os.path.basename(active_path)}"
                )
                return

        self.lbl_status.set_text(
            "Wallpaper ativo fora da pasta selecionada: "
            f"{os.path.basename(active_path)}"
        )

    def on_card_selected(self, path):
        self.selected_path = self._normalise_path(path)
        for p, card in self.cards.items():
            card.set_selected(self._normalise_path(p) == self.selected_path)
        self.btn_apply.set_sensitive(True)
        self.lbl_status.set_text(f"Selecionado: {os.path.basename(self.selected_path)}")

    def on_apply_clicked(self, widget):
        if not self.selected_path:
            return
        try:
            ok = self.callback(
                caminho_video=self.selected_path,
                volume=float(self.config.get("volume", 0.0)),
                pause_fullscreen=bool(self.config.get("pause_fullscreen", True)),
                playback_rate=float(self.config.get("playback_rate", 1.0)),
                target_fps=int(self.config.get("target_fps", 0))
            )
            if ok:
                self.config["manual_paused"] = False
                config_manager.save_config(self.config)
                self.current_wallpaper_config["file_path"] = self.selected_path
                self.current_wallpaper_config["original_file_path"] = self.selected_path
                self.current_wallpaper_config["manual_paused"] = False
                self._ignore_toggle = True
                self.btn_pause.set_active(False)
                self.btn_pause.set_label("Pausar")
                self._ignore_toggle = False
                self.lbl_status.set_text(f"Rodando: {os.path.basename(self.selected_path)}")
            else:
                self.lbl_status.set_text("Não foi possível aplicar o wallpaper")
        except Exception as exc:
            self.lbl_status.set_text(f"Erro ao aplicar: {exc}")

    def _send_params(self):
        try:
            from controller import atualizar_configuracao
            ok = atualizar_configuracao(
                volume=self.config["volume"],
                pause_fullscreen=self.config["pause_fullscreen"],
                playback_rate=self.config["playback_rate"],
                target_fps=self.config["target_fps"]
            )
            self.lbl_status.set_text(
                "Parâmetros atualizados" if ok else "Falha ao atualizar parâmetros"
            )
        except Exception as exc:
            self.lbl_status.set_text(f"Erro: {exc}")
        self._timer_id = None
        return False

    def slider_changed(self, widget):
        self.config["volume"] = widget.get_value() / 100.0
        config_manager.save_config(self.config)
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(250, self._send_params)

    def params_changed(self, widget):
        self.config["playback_rate"] = self.spin_speed.get_value()
        self.config["target_fps"] = int(self.spin_fps.get_value())
        config_manager.save_config(self.config)
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(200, self._send_params)

    def on_config_changed(self, widget):
        if self._ignore_toggle:
            return
        self.config["pause_fullscreen"] = self.check_fullscreen.get_active()
        self.config["autostart"] = self.check_autostart.get_active()
        self.config["minimize_to_tray"] = self.check_tray.get_active()
        config_manager.save_config(self.config)
        self._send_params()

        if not self.check_tray.get_active() and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

    def on_theme_changed(self, widget):
        theme = widget.get_active_id()
        if theme not in {"neon", "original"}:
            return
        self.config["theme"] = theme
        config_manager.save_config(self.config)
        self.load_css()

    def on_pause_toggled(self, widget):
        if self._ignore_toggle:
            return

        paused = widget.get_active()
        widget.set_label("Retomar" if paused else "Pausar")
        self.config["manual_paused"] = paused
        config_manager.save_config(self.config)
        try:
            from controller import set_manual_pause
            if set_manual_pause(paused):
                self.lbl_status.set_text("Pausado" if paused else "Reproduzindo")
            else:
                self.lbl_status.set_text("Falha ao alterar reprodução")
        except Exception as exc:
            self.lbl_status.set_text(f"Erro: {exc}")

    def select_and_play(self, path, params=None):
        self.on_card_selected(path)
        if params:
            self.config.update(params)
        self.on_apply_clicked(None)
        return True

    def on_window_delete(self, widget, event):
        if self.check_tray.get_active():
            self.window.hide()
            self.setup_tray_icon()
            return True

        self.quit_app_completely()
        return False

    def setup_tray_icon(self):
        if self.tray_icon is not None:
            return

        # Caminho dinâmico para o ícone do tray
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "tray_icon.png")
        try:
            image = Image.open(icon_path)
        except Exception:
            image = Image.new('RGB', (64, 64), color=(30, 30, 30))

        menu = (
            item('Abrir', self.show_window_from_tray, default=True),
            item('Sair', self.quit_app_completely)
        )

        self.tray_icon = pystray.Icon("ReWall", image, "Re:Wall", menu)

        def run_tray():
            try:
                self.tray_icon.run()
            except Exception:
                pass

        threading.Thread(target=run_tray, daemon=True).start()

    def show_window_from_tray(self, icon=None, item=None):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

        GLib.idle_add(self.window.show_all)
        GLib.idle_add(self.window.present)
        # Garante que a tela de loading não reapareça presa se já foi carregada antes
        GLib.idle_add(self._hide_loading_screen)

    def quit_app_completely(self, icon=None, item=None):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        GLib.idle_add(Gtk.main_quit)
