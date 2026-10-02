import json
import hashlib
import os
import re
import subprocess
import sys
from typing import Any

PLUGIN_ID = "com.jonas.rewall"
LOG_PATH = os.path.expanduser("~/.cache/rewall/rewall.log")
RENDER_CACHE_DIR = os.path.expanduser("~/.cache/rewall/rendered")

DBUS_SERVICE = "com.jonas.rewall.Controller"
DBUS_PATH = "/com/jonas/rewall/Controller"
DBUS_INTERFACE = "com.jonas.rewall.Controller"


# ============================================================
# LOG
# ============================================================

def _log(message: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass
    print(f"[Re:Wall] {message}", flush=True)


# ============================================================
# UTILIDADES
# ============================================================

def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "sim", "on", "enabled", "ativo"}:
        return True
    if text in {"false", "0", "no", "não", "nao", "off", "disabled", "desativado"}:
        return False
    return default


def _js_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _evaluate_plasma_script(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "qdbus6",
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell.evaluateScript",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )


def _normalise_video_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(str(path).removeprefix("file://")))


def _render_for_target_fps(source_path: str, target_fps: int) -> str | None:
    """Retorna um vídeo no FPS escolhido, reutilizando a cópia em cache quando possível."""
    source_path = _normalise_video_path(source_path)
    if not os.path.isfile(source_path):
        _log(f"Vídeo não encontrado: {source_path}")
        return None

    if target_fps <= 0:
        return source_path

    try:
        stat = os.stat(source_path)
        identity = f"{source_path}|{stat.st_size}|{stat.st_mtime_ns}|{target_fps}"
        name = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        os.makedirs(RENDER_CACHE_DIR, exist_ok=True)
        output_path = os.path.join(RENDER_CACHE_DIR, f"{name}_{target_fps}fps.mp4")
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return output_path

        temporary_path = output_path + ".part.mp4"
        _log(f"Otimizando '{os.path.basename(source_path)}' para {target_fps} FPS...")
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", source_path,
                "-map", "0:v:0", "-map", "0:a?",
                "-vf", f"fps=fps={target_fps}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
                temporary_path,
            ],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode != 0 or not os.path.isfile(temporary_path):
            _log("Não foi possível otimizar o vídeo para o FPS escolhido: " +
                 (result.stderr.strip().splitlines()[-1] if result.stderr else "ffmpeg falhou"))
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            return None

        os.replace(temporary_path, output_path)
        _log(f"Vídeo otimizado pronto: {os.path.basename(output_path)}")
        return output_path
    except Exception as exc:
        _log(f"Falha preparando vídeo para {target_fps} FPS: {exc}")
        return None


# ============================================================
# CONFIGURAÇÃO DO PLUGIN
# ============================================================

def _write_plugin_config(
    updates: dict[str, Any],
    reload_config: bool = True,
) -> bool:
    if not updates:
        return False

    lines = [
        f'd.writeConfig("{key}", {_js_value(value)});'
        for key, value in updates.items()
    ]
    reload_line = "d.reloadConfig();" if reload_config else ""

    script = f"""
var result = {{found:false, count:0}};
var ds = desktops();
for (var i = 0; i < ds.length; i++) {{
    var d = ds[i];
    if (d.wallpaperPlugin === "{PLUGIN_ID}") {{
        result.found = true;
        result.count++;
        d.currentConfigGroup = ["Wallpaper", "{PLUGIN_ID}", "General"];
        {chr(10).join(lines)}
        {reload_line}
    }}
}}
print(JSON.stringify(result));
"""

    try:
        result = _evaluate_plasma_script(script)
        if result.returncode != 0:
            _log(result.stderr.strip() or result.stdout.strip())
            return False

        match = re.search(r"\{.*\}", result.stdout, re.S)
        if not match:
            _log("Resposta inválida do PlasmaShell ao escrever configuração.")
            return False

        data = json.loads(match.group(0))
        if not data.get("found"):
            _log("Re:Wall não está ativo em nenhum desktop.")
            return False
        return True

    except Exception as exc:
        _log(f"Falha comunicando com Plasma: {exc}")
        return False


def aplicar_wallpaper_no_plasma6(
    caminho_video: str | None,
    volume: float = 0.0,
    pause_fullscreen: bool = True,
    playback_rate: float = 1.0,
    target_fps: int = 0,
) -> bool:
    updates: dict[str, Any] = {}

    if caminho_video:
        source_path = _normalise_video_path(caminho_video)
        try:
            fps = max(0, int(target_fps))
        except (TypeError, ValueError):
            _log("FPS alvo inválido.")
            return False
        playback_path = _render_for_target_fps(source_path, fps)
        if not playback_path:
            return False
        updates["file_path"] = playback_path
        updates["original_file_path"] = source_path
        updates["manual_paused"] = False

    try:
        updates.update(
            {
                "volume": max(0.0, min(1.0, float(volume))),
                "pause_fullscreen": _to_bool(pause_fullscreen, True),
                "playback_rate": max(0.05, float(playback_rate)),
                "target_fps": max(0, int(target_fps)),
            }
        )
    except Exception as exc:
        _log(f"Parâmetro inválido: {exc}")
        return False

    return _write_plugin_config(updates)


def atualizar_configuracao(**kwargs: Any) -> bool:
    allowed = {
        "file_path",
        "original_file_path",
        "volume",
        "pause_fullscreen",
        "fullscreen_active",
        "manual_paused",
        "playback_rate",
        "target_fps",
    }

    updates: dict[str, Any] = {}

    requested_fps = kwargs.get("target_fps")
    if requested_fps is not None:
        try:
            requested_fps = max(0, int(requested_fps))
        except (TypeError, ValueError):
            _log("FPS alvo inválido.")
            return False

        current = _read_config()
        current_fps = max(0, int(current.get("target_fps", 0) or 0))
        source_path = current.get("original_file_path") or current.get("file_path")
        if source_path and requested_fps != current_fps:
            playback_path = _render_for_target_fps(source_path, requested_fps)
            if not playback_path:
                return False
            updates["file_path"] = playback_path
            updates["original_file_path"] = _normalise_video_path(source_path)

    for key, value in kwargs.items():
        if key not in allowed:
            continue

        if key == "file_path":
            if not value:
                continue
            value = _normalise_video_path(value)
            if not os.path.isfile(value):
                _log(f"Arquivo não encontrado: {value}")
                return False

        elif key == "volume":
            value = max(0.0, min(1.0, float(value)))

        elif key in {"pause_fullscreen", "fullscreen_active", "manual_paused"}:
            value = _to_bool(value)

        elif key == "playback_rate":
            value = max(0.05, float(value))

        elif key == "target_fps":
            value = max(0, int(value))

        updates[key] = value

    return _write_plugin_config(updates) if updates else False


def set_manual_pause(flag: bool) -> bool:
    return atualizar_configuracao(manual_paused=_to_bool(flag))


def set_pause_fullscreen(flag: bool) -> bool:
    return atualizar_configuracao(pause_fullscreen=_to_bool(flag))


# ============================================================
# LEITURA DA CONFIGURAÇÃO
# ============================================================

def _read_config() -> dict[str, Any]:
    script = f"""
var result={{found:false}};
var ds=desktops();
for(var i=0;i<ds.length;i++){{
 var d=ds[i];
 if(d.wallpaperPlugin==="{PLUGIN_ID}"){{
  d.currentConfigGroup=["Wallpaper","{PLUGIN_ID}","General"];
  result.found=true;
  result.file_path=d.readConfig("file_path","");
  result.original_file_path=d.readConfig("original_file_path","");
  result.volume=d.readConfig("volume",0.0);
  result.pause_fullscreen=d.readConfig("pause_fullscreen",true);
  result.fullscreen_active=d.readConfig("fullscreen_active",false);
  result.manual_paused=d.readConfig("manual_paused",false);
  result.playback_rate=d.readConfig("playback_rate",1.0);
  result.target_fps=d.readConfig("target_fps",0);
  break;
 }}
}}
print(JSON.stringify(result));
"""

    try:
        result = _evaluate_plasma_script(script)
        match = re.search(r"\{.*\}", result.stdout, re.S)
        return json.loads(match.group(0)) if match else {}
    except Exception as exc:
        _log(f"Erro lendo configuração: {exc}")
        return {}


def get_manual_pause_state() -> bool:
    return _to_bool(_read_config().get("manual_paused", False))


def get_current_plugin_config() -> dict[str, Any]:
    return _read_config()


def persist_file_path_in_config_qml(caminho_video: str | None) -> bool:
    return bool(caminho_video)


def persist_plugin_defaults(*args: Any, **kwargs: Any) -> bool:
    return True


# ============================================================
# ESTADO FULLSCREEN — ÚNICA RESPONSABILIDADE DO CONTROLLER
# ============================================================

def set_fullscreen_state(flag: bool) -> bool:
    """Recebe o estado bruto do KWin e o entrega ao wallpaper.

    O KWin NÃO escreve mais no PlasmaShell. Ele apenas chama este método.
    A decisão de tocar/pausar continua no QML através de:

        !manual_paused && !(pause_fullscreen && fullscreen_active)
    """
    flag = _to_bool(flag)

    current = _read_config()
    if not current:
        _log(
            f"Fullscreen recebido={flag}, mas o wallpaper Re:Wall não foi encontrado."
        )
        return False

    old = _to_bool(current.get("fullscreen_active", False))
    if old == flag:
        return True

    _log(f"KWin informou fullscreen={flag}; atualizando Re:Wall.")
    return _write_plugin_config({"fullscreen_active": flag}, reload_config=True)


# ============================================================
# D-BUS CONTROLLER SERVICE
# ============================================================

_DBUS_XML = f"""
<node>
  <interface name="{DBUS_INTERFACE}">
    <method name="SetFullscreen">
      <arg name="fullscreen" type="b" direction="in"/>
    </method>
  </interface>
</node>
"""


def _run_dbus_service() -> int:
    try:
        import gi
        gi.require_version("Gio", "2.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gio, GLib
    except Exception as exc:
        _log(f"Não foi possível iniciar o serviço D-Bus do controller: {exc}")
        return 1

    loop = GLib.MainLoop()
    interface_info = Gio.DBusNodeInfo.new_for_xml(_DBUS_XML).interfaces[0]

    def method_call(
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation,
    ):
        if method_name == "SetFullscreen":
            try:
                fullscreen = bool(parameters.unpack()[0])
                ok = set_fullscreen_state(fullscreen)
                invocation.return_value(GLib.Variant("()"))
                _log(
                    f"D-Bus SetFullscreen({fullscreen}) recebido "
                    f"({'ok' if ok else 'falhou'})."
                )
            except Exception as exc:
                _log(f"Erro processando SetFullscreen: {exc}")
                invocation.return_dbus_error(
                    "com.jonas.rewall.Error",
                    str(exc),
                )
            return

        invocation.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod",
            f"Método desconhecido: {method_name}",
        )

    def on_bus_acquired(connection, name):
        try:
            connection.register_object(
                DBUS_PATH,
                interface_info,
                method_call,
                None,
                None,
            )
            _log("Controller D-Bus registrado e aguardando eventos do KWin.")
        except Exception as exc:
            _log(f"Erro registrando objeto D-Bus: {exc}")
            loop.quit()

    def on_name_acquired(connection, name):
        _log(f"Serviço D-Bus ativo: {name}")

    def on_name_lost(connection, name):
        _log(
            "Serviço D-Bus não pôde assumir o nome "
            f"{name}; provavelmente já existe outro controller ativo."
        )
        loop.quit()

    owner_id = Gio.bus_own_name(
        Gio.BusType.SESSION,
        DBUS_SERVICE,
        Gio.BusNameOwnerFlags.NONE,
        on_bus_acquired,
        on_name_acquired,
        on_name_lost,
    )

    try:
        loop.run()
    finally:
        Gio.bus_unown_name(owner_id)

    return 0


def ensure_controller_service() -> bool:
    """Garante que exista um controller D-Bus em segundo plano."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            Gio.Variant("(s)", (DBUS_SERVICE,)),
            Gio.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )

        if bool(result.unpack()[0]):
            _log("Controller D-Bus já está em execução.")
            return True

    except Exception as exc:
        _log(f"Não foi possível verificar o controller D-Bus: {exc}")

    try:
        command = [sys.executable, os.path.abspath(__file__), "--service"]
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        _log("Controller D-Bus iniciado em segundo plano.")
        return True
    except Exception as exc:
        _log(f"Falha iniciando controller D-Bus: {exc}")
        return False


# ============================================================
# API PÚBLICA
# ============================================================

__all__ = [
    "aplicar_wallpaper_no_plasma6",
    "atualizar_configuracao",
    "set_manual_pause",
    "set_pause_fullscreen",
    "set_fullscreen_state",
    "get_manual_pause_state",
    "get_current_plugin_config",
    "persist_file_path_in_config_qml",
    "persist_plugin_defaults",
    "ensure_controller_service",
]


if __name__ == "__main__":
    if "--service" in sys.argv:
        raise SystemExit(_run_dbus_service())
