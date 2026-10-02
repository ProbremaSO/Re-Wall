
import os
import sys
import json
import shutil
import subprocess


# ============================================================
# RE:WALL ENGINE
# Main launcher / Plasma 6 + KWin integration
# ============================================================

PLUGIN_ID = "com.jonas.rewall"

PLUGIN_DIR = os.path.expanduser(
    f"~/.local/share/plasma/wallpapers/{PLUGIN_ID}"
)

UI_DIR = os.path.join(
    PLUGIN_DIR,
    "contents",
    "ui"
)

CONFIG_DIR = os.path.join(
    PLUGIN_DIR,
    "contents",
    "config"
)

KWIN_SCRIPT_ID = "com.jonas.rewall-monitor"

KWIN_SCRIPT_DIR = os.path.expanduser(
    f"~/.local/share/kwin/scripts/{KWIN_SCRIPT_ID}"
)

KWIN_CODE_DIR = os.path.join(
    KWIN_SCRIPT_DIR,
    "contents",
    "code"
)


# ============================================================
# UTILIDADES
# ============================================================

def escrever_arquivo(
    caminho,
    conteudo
):

    os.makedirs(
        os.path.dirname(caminho),
        exist_ok=True
    )

    with open(
        caminho,
        "w",
        encoding="utf-8"
    ) as arquivo:

        arquivo.write(
            conteudo
        )


def executar_comando(
    comando,
    check=False
):

    try:

        resultado = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=check
        )


        if resultado.stdout:

            print(
                resultado.stdout.strip()
            )


        return resultado.returncode


    except FileNotFoundError:

        print(
            f"[Re:Wall] Comando não encontrado: "
            f"{comando[0]}"
        )

        return 127


    except Exception as erro:

        print(
            f"[Re:Wall] Erro executando "
            f"{comando}: {erro}"
        )

        return 1


# ============================================================
# INSTALA PLUGIN PLASMA 6
# ============================================================

def instalar_plugin_plasma6():

    print(
        "[Re:Wall] Instalando/atualizando "
        "plugin Plasma 6..."
    )


    os.makedirs(
        UI_DIR,
        exist_ok=True
    )

    os.makedirs(
        CONFIG_DIR,
        exist_ok=True
    )


    # ========================================================
    # main.xml
    # ========================================================

    main_xml = """<?xml version="1.0" encoding="UTF-8"?>
<kcfg>
    <kcfgfile name=""/>

    <group name="General">

        <entry name="file_path" type="Path">
            <default></default>
        </entry>

        <entry name="original_file_path" type="Path">
            <default></default>
        </entry>

        <entry name="volume" type="Double">
            <default>0.5</default>
        </entry>

        <entry name="pause_fullscreen" type="Bool">
            <default>true</default>
        </entry>

        <entry name="fullscreen_active" type="Bool">
            <default>false</default>
        </entry>

        <entry name="manual_paused" type="Bool">
            <default>false</default>
        </entry>

        <entry name="playback_rate" type="Double">
            <default>1.0</default>
        </entry>

        <entry name="target_fps" type="Int">
            <default>0</default>
        </entry>

    </group>
</kcfg>
"""


    escrever_arquivo(
        os.path.join(
            CONFIG_DIR,
            "main.xml"
        ),
        main_xml
    )


    # ========================================================
    # main.qml
    # ========================================================

    main_qml = """import QtQuick
import QtMultimedia
import org.kde.plasma.plasmoid

WallpaperItem {

    id: main

    anchors.fill: parent

    property bool isLoading: true

    property bool pauseFullscreen:
        booleanoConfig(
            main.configuration.pause_fullscreen,
            true
        )

    property bool fullscreenActive:
        booleanoConfig(
            main.configuration.fullscreen_active,
            false
        )

    property bool manualPaused:
        booleanoConfig(
            main.configuration.manual_paused,
            false
        )

    property bool shouldPlay:
        !manualPaused &&
        !(pauseFullscreen && fullscreenActive)

    property bool playing:
        shouldPlay &&
        main.configuration.file_path !== ""

    property real playbackRate: {
        var rate = Number(
            main.configuration.playback_rate
        )

        if (isNaN(rate) || rate <= 0) {
            return 1.0
        }

        return rate
    }

    property real volume: {
        var value = Number(
            main.configuration.volume
        )

        if (isNaN(value)) {
            return 0.5
        }

        return Math.max(
            0.0,
            Math.min(1.0, value)
        )
    }

    property bool playerInitialized: false

    // ========================================================
    // FUNDO
    // ========================================================

    Rectangle {
        anchors.fill: parent
        color: "#0d0b11"
    }

    // ========================================================
    // CONVERSÃO BOOLEAN
    // ========================================================

    function booleanoConfig(valor, padrao) {

        if (valor === true) {
            return true
        }

        if (valor === false) {
            return false
        }

        var texto = String(valor).toLowerCase().trim()

        if (
            texto === "true" ||
            texto === "1" ||
            texto === "yes" ||
            texto === "sim" ||
            texto === "on"
        ) {
            return true
        }

        if (
            texto === "false" ||
            texto === "0" ||
            texto === "no" ||
            texto === "não" ||
            texto === "nao" ||
            texto === "off" ||
            texto === ""
        ) {
            return false
        }

        return padrao
    }

    // ========================================================
    // CONTROLE DE PLAYBACK
    // ========================================================

    onPlayingChanged: {

        if (main.isLoading) {
            return
        }

        if (main.playing) {
            main.play()
        } else {
            main.pause()
        }
    }

    function play() {

        pauseTimer.stop()
        playTimer.start()
    }

    function pause() {

        playTimer.stop()

        pauseTimer.start()
    }

    function updateState() {

        if (!main.playerInitialized) {
            return
        }

        if (main.playing) {

            main.pause()
            main.play()

        } else {

            main.play()
            main.pause()
        }
    }

    // ========================================================
    // PLAY TIMER
    // ========================================================

    Timer {

        id: playTimer

        interval: 10
        repeat: false

        onTriggered: {

            if (
                main.configuration.file_path === ""
            ) {
                return
            }

            console.log(
                "Re:Wall: player.play() | manual=",
                main.manualPaused,
                "fullscreen=",
                main.fullscreenActive,
                "pauseFullscreen=",
                main.pauseFullscreen,
                "state=",
                player.playbackState
            )

            player.play()
        }
    }

    // ========================================================
    // PAUSE TIMER
    // ========================================================

    Timer {

        id: pauseTimer

        interval: 10
        repeat: false

        onTriggered: {

            console.log(
                "Re:Wall: player.pause() | state=",
                player.playbackState
            )

            player.pause()
        }
    }

    Timer {

        id: startTimer

        interval: 100
        repeat: false

        onTriggered: {

            main.isLoading = false
            main.updateState()
        }
    }

    // ========================================================
    // MEDIA PLAYER
    // ========================================================

    MediaPlayer {

        id: player

        loops: MediaPlayer.Infinite

        source:
            main.configuration.file_path

        playbackRate:
            main.playbackRate

        videoOutput:
            videoOutput

        audioOutput: AudioOutput {

            id: audioOut

            volume:
                main.volume
        }

        onMediaStatusChanged: {

            console.log(
                "Re:Wall: mediaStatus =",
                mediaStatus
            )

            if (
                mediaStatus ===
                    MediaPlayer.LoadedMedia ||
                mediaStatus ===
                    MediaPlayer.BufferedMedia
            ) {

                Qt.callLater(
                    main.updateState
                )
            }
        }

        onPlaybackStateChanged: {

            console.log(
                "Re:Wall: playbackState =",
                playbackState
            )

            if (!main.isLoading) {
                Qt.callLater(
                    main.updateState
                )
            }
        }

        onErrorOccurred: {

            console.log(
                "Re:Wall MediaPlayer erro:",
                error,
                errorString
            )
        }

        Component.onCompleted: {

            main.playerInitialized = true

            console.log(
                "Re:Wall: MediaPlayer inicializado"
            )

            startTimer.start()
        }
    }

    // ========================================================
    // VIDEO OUTPUT
    // ========================================================

    VideoOutput {

        id: videoOutput

        anchors.fill: parent

        fillMode:
            VideoOutput.PreserveAspectCrop
    }

    // ========================================================
    // CONFIGURAÇÃO DO PLASMA
    // ========================================================

    Connections {

        target:
            main.configuration

        function onValueChanged(key, value) {

            console.log(
                "Re:Wall: configuração mudou:",
                key,
                value
            )

            if (
                key === "manual_paused" ||
                key === "pause_fullscreen" ||
                key === "fullscreen_active" ||
                key === "file_path"
            ) {

                Qt.callLater(
                    main.updateState
                )
            }
        }

        function onFile_pathChanged() {

            console.log(
                "Re:Wall: file_path mudou para:",
                main.configuration.file_path
            )

            player.stop()

            Qt.callLater(
                main.updateState
            )
        }

        function onVolumeChanged() {

            audioOut.volume =
                main.volume
        }

        function onPlayback_rateChanged() {

            player.playbackRate =
                main.playbackRate
        }

        function onPause_fullscreenChanged() {

            Qt.callLater(
                main.updateState
            )
        }

        function onFullscreen_activeChanged() {

            Qt.callLater(
                main.updateState
            )
        }

        function onManual_pausedChanged() {

            console.log(
                "Re:Wall: manual_paused mudou:",
                main.configuration.manual_paused
            )

            Qt.callLater(
                main.updateState
            )
        }
    }

    // ========================================================
    // INICIALIZAÇÃO
    // ========================================================

    Component.onCompleted: {

        console.log(
            "Re:Wall: WallpaperItem iniciado"
        )

        startTimer.start()
    }
}
"""

    escrever_arquivo(
        os.path.join(
            UI_DIR,
            "main.qml"
        ),
        main_qml
    )


    # ========================================================
    # config.qml
    # ========================================================

    config_qml = """import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ColumnLayout {

    id: root

    spacing: 12
    Layout.fillWidth: true
    Layout.margins: 16

    property alias cfg_file_path:
        file_path.text

    property alias cfg_volume:
        volume_slider.value

    property alias cfg_pause_fullscreen:
        pause_fullscreen.checked

    property real cfg_playback_rate: 1.0

    property alias cfg_target_fps:
        target_fps.value

    onCfg_playback_rateChanged: {
        if (
            Math.round(
                cfg_playback_rate * 100
            ) !== playback_rate.value
        ) {
            playback_rate.value = Math.round(
                cfg_playback_rate * 100
            )
        }
    }

    Controls.TextField {
        id: file_path
        Layout.fillWidth: true

        placeholderText:
            qsTr(
                "Caminho para o arquivo de vídeo"
            )
    }

    Controls.Button {
        text:
            qsTr(
                "Selecionar vídeo"
            )

        onClicked: {
            fileDialog.open()
        }
    }

    Controls.CheckBox {
        id: pause_fullscreen

        text:
            qsTr(
                "Pausar automaticamente em tela cheia"
            )

        checked: true
    }

    RowLayout {
        Layout.fillWidth: true

        Controls.Label {
            text:
                qsTr("Volume:")
        }

        Controls.Slider {
            id: volume_slider

            from: 0.0
            to: 1.0
            stepSize: 0.05
            Layout.fillWidth: true
        }
    }

    RowLayout {
        Layout.fillWidth: true

        Controls.Label {
            text:
                qsTr("Velocidade:")
        }

        Controls.SpinBox {
            id: playback_rate

            from: 25
            to: 300
            stepSize: 5
            value: 100

            textFromValue: function(value, locale) {
                return (value / 100).toFixed(2) + "x"
            }

            valueFromText: function(text, locale) {
                var numero = Number(
                    String(text)
                        .replace("x", "")
                        .trim()
                )

                if (isNaN(numero)) {
                    return value
                }

                return Math.round(
                    numero * 100
                )
            }

            onValueChanged: {
                cfg_playback_rate = value / 100.0
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true

        Controls.Label {
            text:
                qsTr("FPS alvo:")
        }

        Controls.SpinBox {
            id: target_fps

            from: 0
            to: 120
            stepSize: 1
            value: 0
        }
    }

    FileDialog {
        id: fileDialog

        title:
            qsTr(
                "Selecionar vídeo"
            )

        fileMode:
            FileDialog.OpenFile

        nameFilters: [
            qsTr(
                "Vídeos (*.mp4 *.webm *.mkv *.avi *.mov)"
            ),
            qsTr(
                "Todos os arquivos (*)"
            )
        ]

        onAccepted: {
            file_path.text =
                selectedFile
                    .toString()
                    .replace(
                        "file://",
                        ""
                    )
        }
    }
}
"""

    escrever_arquivo(
        os.path.join(
            UI_DIR,
            "config.qml"
        ),
        config_qml
    )


    # ========================================================
    # METADATA
    # ========================================================

    metadata = {

        "KPlugin": {

            "Name":
                "Re:Wall Engine",

            "Description":
                "Motor de vídeo wallpaper "
                "de alta performance para Plasma 6",

            "Icon":
                "video-display",

            "Id":
                PLUGIN_ID,

            "Category":
                "Wallpapers",

            "Version":
                "1.0",

            "Authors": [
                {
                    "Name":
                        "Jonas"
                }
            ],

            "License":
                "GPL-2.0+"
        },


        "KPackageStructure":
            "Plasma/Wallpaper"
    }


    escrever_arquivo(
        os.path.join(
            PLUGIN_DIR,
            "metadata.json"
        ),
        json.dumps(
            metadata,
            indent=4,
            ensure_ascii=False
        )
    )


    print(
        "[Re:Wall] Plugin Plasma 6 atualizado."
    )


# ============================================================
# INSTALA MONITOR KWIN
# ============================================================

def instalar_monitor_kwin():

    print(
        "[Re:Wall] Instalando monitor KWin..."
    )


    os.makedirs(
        KWIN_CODE_DIR,
        exist_ok=True
    )


    # ========================================================
    # METADATA
    # ========================================================

    metadata = {

        "KPlugin": {

            "Name":
                "Re:Wall Window Monitor",

            "Description":
                "Monitor de janelas fullscreen "
                "do Re:Wall",

            "Id":
                KWIN_SCRIPT_ID,

            "Version":
                "1.0",

            "License":
                "GPL-2.0+",

            "Authors": [
                {
                    "Name":
                        "Jonas"
                }
            ]
        },


        "X-Plasma-API":
            "javascript",


        "X-Plasma-MainScript":
            "code/main.js",


        "KPackageStructure":
            "KWin/Script"
    }


    escrever_arquivo(
        os.path.join(
            KWIN_SCRIPT_DIR,
            "metadata.json"
        ),
        json.dumps(
            metadata,
            indent=4,
            ensure_ascii=False
        )
    )


    # ========================================================
    # MAIN.JS
    # ========================================================

    main_js = r'''"use strict";

print("Re:Wall: monitor KWin iniciado");

var ultimoEstadoFullscreen = null;
var ultimaJanela = null;
var consultaAgendada = false;

var CONTROLLER_SERVICE = "com.jonas.rewall.Controller";
var CONTROLLER_PATH = "/com/jonas/rewall/Controller";
var CONTROLLER_INTERFACE = "com.jonas.rewall.Controller";

function janelaFullscreenAtual() {
    try {
        var janela = workspace.activeWindow;

        if (!janela) {
            return { active: false, fullscreen: false, caption: "(nenhuma)" };
        }

        var fullscreen = janela.fullScreen === true;
        var caption = String(janela.caption || "");

        print("Re:Wall: janela ativa = " + caption + " | fullscreen=" + fullscreen);

        return {
            active: true,
            fullscreen: fullscreen,
            caption: caption
        };
    } catch (e) {
        print("Re:Wall: erro lendo workspace.activeWindow: " + e);
        return null;
    }
}

function enviarFullscreenAoController(ativo) {
    ativo = ativo === true;

    if (ultimoEstadoFullscreen === ativo) {
        return;
    }

    ultimoEstadoFullscreen = ativo;

    print("Re:Wall: fullscreen mudou para " + ativo);

    try {
        callDBus(
            CONTROLLER_SERVICE,
            CONTROLLER_PATH,
            CONTROLLER_INTERFACE,
            "SetFullscreen",
            ativo,
            function() {
                print("Re:Wall: estado fullscreen enviado ao controller");
            }
        );
    } catch (e) {
        print("Re:Wall: erro no callDBus do controller: " + e);
    }
}

function verificarFullscreen() {
    if (consultaAgendada) {
        return;
    }

    consultaAgendada = true;

    try {
        var estado = janelaFullscreenAtual();
        consultaAgendada = false;

        if (!estado) {
            return;
        }

        if (estado.caption !== ultimaJanela) {
            ultimaJanela = estado.caption;
            print("Re:Wall: janela atual = " + estado.caption);
        }

        enviarFullscreenAoController(estado.fullscreen);
    } catch (e) {
        consultaAgendada = false;
        print("Re:Wall: erro verificando fullscreen: " + e);
    }
}

workspace.windowActivated.connect(function(window) {
    print("Re:Wall: windowActivated");
    verificarFullscreen();
});

workspace.windowAdded.connect(function(window) {
    try {
        if (window && window.fullScreenChanged) {
            window.fullScreenChanged.connect(function() {
                print("Re:Wall: fullScreenChanged -> " + window.fullScreen);
                verificarFullscreen();
            });
        }
    } catch (e) {
        print("Re:Wall: não foi possível conectar fullScreenChanged: " + e);
    }

    verificarFullscreen();
});

workspace.windowRemoved.connect(function(window) {
    verificarFullscreen();
});

workspace.currentDesktopChanged.connect(function() {
    verificarFullscreen();
});

var timer = new QTimer();
timer.interval = 1000;
timer.timeout.connect(function() {
    verificarFullscreen();
});
timer.start();

verificarFullscreen();

print("Re:Wall: monitor fullscreen pronto");
'''





    escrever_arquivo(
        os.path.join(
            KWIN_CODE_DIR,
            "main.js"
        ),
        main_js.lstrip()
    )


    print(
        "[Re:Wall] Script KWin atualizado."
    )


# ============================================================
# ATIVA MONITOR KWIN
# ============================================================

def ativar_monitor_kwin():

    print(
        "[Re:Wall] Registrando monitor KWin..."
    )


    pacote_tmp ="/tmp/rewall-kwin-monitor"


    try:

        if os.path.exists(
            pacote_tmp
        ):

            shutil.rmtree(
                pacote_tmp
            )


        shutil.copytree(
            KWIN_SCRIPT_DIR,
            pacote_tmp
        )


    except Exception as erro:

        print(
            "[Re:Wall] Erro criando "
            "pacote temporário:"
        )

        print(
            erro
        )

        return False


    metadata_path = os.path.join(
        pacote_tmp,
        "metadata.json"
    )


    main_js_path = os.path.join(
        pacote_tmp,
        "contents",
        "code",
        "main.js"
    )


    if not os.path.isfile(
        metadata_path
    ):

        print(
            "[Re:Wall] ERRO: metadata.json "
            "não encontrado."
        )

        return False


    if not os.path.isfile(
        main_js_path
    ):

        print(
            "[Re:Wall] ERRO: main.js "
            "não encontrado."
        )

        return False


    # ========================================================
    # UPDATE
    # ========================================================

    retorno = executar_comando(
        [
            "kpackagetool6",
            "--type",
            "KWin/Script",
            "-u",
            pacote_tmp
        ]
    )


    # ========================================================
    # INSTALL
    # ========================================================

    if retorno != 0:

        print(
            "[Re:Wall] Instalando novo "
            "pacote KWin..."
        )


        retorno = executar_comando(
            [
                "kpackagetool6",
                "--type",
                "KWin/Script",
                "-i",
                pacote_tmp
            ]
        )


    if retorno != 0:

        print(
            "[Re:Wall] ERRO: não foi possível "
            "instalar o script KWin."
        )

        return False


    # ========================================================
    # ATIVA
    # ========================================================

    retorno = executar_comando(
        [
            "kwriteconfig6",
            "--file",
            "kwinrc",
            "--group",
            "Plugins",
            "--key",
            f"{KWIN_SCRIPT_ID}Enabled",
            "true"
        ]
    )


    if retorno != 0:

        print(
            "[Re:Wall] ERRO ativando "
            "script KWin."
        )

        return False


    # ========================================================
    # RECONFIGURA
    # ========================================================

    retorno = executar_comando(
        [
            "qdbus6",
            "org.kde.KWin",
            "/KWin",
            "reconfigure"
        ]
    )


    if retorno == 0:

        print(
            "[Re:Wall] Monitor KWin "
            "ativado com sucesso!"
        )

    else:

        print(
            "[Re:Wall] AVISO: reconfigure "
            "do KWin falhou."
        )


    try:

        shutil.rmtree(
            pacote_tmp
        )

    except Exception:

        pass


    return True


# ============================================================
# INSTALAÇÃO COMPLETA
# ============================================================

def garantir_instalacao_completa():

    print()

    print(
        "=" * 60
    )

    print(
        " RE:WALL ENGINE"
    )

    print(
        " Plasma 6 + KWin fullscreen monitor"
    )

    print(
        "=" * 60
    )

    print()


    instalar_plugin_plasma6()

    instalar_monitor_kwin()

    ativar_monitor_kwin()


    print()

    print(
        "[Re:Wall] Instalação concluída."
    )

    print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    garantir_instalacao_completa()


    print(
        "Iniciando painel de controle "
        "Re:Wall (GTK3)..."
    )


    os.environ[
        "GDK_BACKEND"
    ] = "x11"


    try:

        import gi

        gi.require_version(
            "Gtk",
            "3.0"
        )

        from gi.repository import Gtk


    except Exception as erro:

        print(
            "[Re:Wall] Erro carregando GTK3:"
        )

        print(
            erro
        )

        sys.exit(1)


    try:

        from gui_gtk import (
            WallpaperConfigApp
        )


    except Exception as erro:

        print(
            "[Re:Wall] Erro importando "
            "gui_gtk:"
        )

        print(
            erro
        )

        sys.exit(1)


    try:

        from controller import (
            aplicar_wallpaper_no_plasma6,
            get_current_plugin_config,
            ensure_controller_service
        )

        ensure_controller_service()

    except Exception as erro:

        print(
            "[Re:Wall] Aviso: controller não pôde ser carregado:"
        )

        print(erro)

        aplicar_wallpaper_no_plasma6 = None
        get_current_plugin_config = None


    current_wallpaper_config = {}

    if callable(get_current_plugin_config):
        try:
            current_wallpaper_config = get_current_plugin_config() or {}
            print(
                "[Re:Wall] Wallpaper atual detectado: "
                + str(current_wallpaper_config.get("file_path", ""))
            )
        except Exception as erro:
            print(
                "[Re:Wall] Não foi possível detectar o wallpaper atual: "
                + str(erro)
            )
            current_wallpaper_config = {}


    app = WallpaperConfigApp(
        on_video_selected_callback=
            aplicar_wallpaper_no_plasma6,
        current_wallpaper_config=current_wallpaper_config
    )


    app.show()


    Gtk.main()
