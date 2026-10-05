import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

export default class MnemoShiftEmissionHudExtension extends Extension {
    enable() {
        this._prevCpuTotal = 0;
        this._prevCpuIdle = 0;
        this._timerId = null;
        this._widget = null;
        this._label = null;
        this._secondaryPanel = null;
        this._panelsCreatedId = null;
        this._cachedGpu = null;

        this._setupHud();

        if (global.zorinTaskbar) {
            this._panelsCreatedId = global.zorinTaskbar.connect('panels-created', () => {
                this._cleanupWidget();
                this._setupHud();
            });
        }
    }

    disable() {
        if (this._panelsCreatedId && global.zorinTaskbar) {
            global.zorinTaskbar.disconnect(this._panelsCreatedId);
            this._panelsCreatedId = null;
        }
        this._cleanupWidget();
    }

    _cleanupWidget() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = null;
        }
        if (this._widget) {
            let parent = this._widget.get_parent();
            if (parent) {
                parent.remove_child(this._widget);
            }
            this._widget.destroy();
            this._widget = null;
            this._label = null;
        }
        this._secondaryPanel = null;
    }

    _findSecondaryPanel() {
        if (!global.zorinTaskbar?.panels || global.zorinTaskbar.panels.length === 0) {
            return Main.panel || null;
        }

        // Jeśli jest tylko jeden monitor/panel (np. laptop), dołącz do tego panelu
        if (global.zorinTaskbar.panels.length === 1) {
            return global.zorinTaskbar.panels[0];
        }

        // W konfiguracji wielomonitorowej szukaj panelu emisyjnego (HDMI-0)
        for (const p of global.zorinTaskbar.panels) {
            if (!p.isPrimary || p.isStandalone || p.monitor?.width === 1920) {
                return p;
            }
        }
        return global.zorinTaskbar.panels[0] || null;
    }

    _setupHud() {
        const panelObj = this._findSecondaryPanel();
        if (!panelObj) {
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                if (!this._widget) {
                    this._setupHud();
                }
                return GLib.SOURCE_REMOVE;
            });
            return;
        }

        this._secondaryPanel = panelObj;

        // Container button for GNOME Shell top bar
        this._widget = new St.Button({
            style_class: 'panel-button mnemoshift-emission-hud-button',
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._label = new St.Label({
            style_class: 'mnemoshift-emission-hud-label',
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._label.clutter_text.set({
            ellipsize: Pango.EllipsizeMode.NONE,
            use_markup: true,
            x_align: Clutter.ActorAlign.CENTER,
        });

        this._widget.set_child(this._label);

        // Click to open system monitor
        this._widget.connect('clicked', () => {
            try {
                let app = Gio.AppInfo.create_from_commandline(
                    'gnome-system-monitor',
                    'System Monitor',
                    Gio.AppInfoCreateFlags.NONE
                );
                app.launch([], null);
            } catch (e) {
                console.error('[MnemoShift HUD] Launch error:', e);
            }
        });

        // Add to the centerBox of the secondary panel
        if (panelObj._centerBox) {
            panelObj._centerBox.add_child(this._widget);
            panelObj._centerBox.visible = true;
        } else if (panelObj.panel?._centerBox) {
            panelObj.panel._centerBox.add_child(this._widget);
            panelObj.panel._centerBox.visible = true;
        } else if (panelObj._rightBox) {
            panelObj._rightBox.insert_child_at_index(this._widget, 0);
            panelObj._rightBox.visible = true;
        }

        // Initial telemetry poll
        this._updateTelemetry();

        // Poll every 2 seconds
        this._timerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._updateTelemetry();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _readCpuUsage() {
        try {
            const [ok, bytes] = GLib.file_get_contents('/proc/stat');
            if (!ok || !bytes) return 0;
            const text = new TextDecoder().decode(bytes);
            const firstLine = text.split('\n')[0];
            const parts = firstLine.trim().split(/\s+/).slice(1).map(Number);
            const idle = parts[3] + (parts[4] || 0);
            const total = parts.reduce((a, b) => a + b, 0);

            if (this._prevCpuTotal === 0) {
                this._prevCpuTotal = total;
                this._prevCpuIdle = idle;
                return 0;
            }

            const deltaTotal = total - this._prevCpuTotal;
            const deltaIdle = idle - this._prevCpuIdle;
            this._prevCpuTotal = total;
            this._prevCpuIdle = idle;

            if (deltaTotal <= 0) return 0;

            const usage = Math.round(100 * (deltaTotal - deltaIdle) / deltaTotal);
            return Math.max(0, Math.min(100, usage));
        } catch (e) {
            return 0;
        }
    }

    _readRamUsage() {
        try {
            const [ok, bytes] = GLib.file_get_contents('/proc/meminfo');
            if (!ok || !bytes) return { usedGiB: '0.0', pct: 0 };
            const text = new TextDecoder().decode(bytes);
            let totalKb = 0;
            let availKb = 0;
            for (const line of text.split('\n')) {
                if (line.startsWith('MemTotal:')) {
                    totalKb = parseInt(line.replace(/[^0-9]/g, ''), 10);
                } else if (line.startsWith('MemAvailable:')) {
                    availKb = parseInt(line.replace(/[^0-9]/g, ''), 10);
                }
            }
            const usedKb = totalKb - availKb;
            const usedGiB = (usedKb / 1048576).toFixed(1);
            const pct = totalKb > 0 ? Math.round((usedKb / totalKb) * 100) : 0;
            return { usedGiB, pct };
        } catch (e) {
            return { usedGiB: '0.0', pct: 0 };
        }
    }

    _queryGpuAsync() {
        try {
            const proc = new Gio.Subprocess({
                argv: ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            });
            proc.init(null);
            proc.communicate_utf8_async(null, null, (p, res) => {
                try {
                    const [ok, stdout] = p.communicate_utf8_finish(res);
                    if (ok && stdout) {
                        const parts = stdout.trim().split(',').map(s => s.trim());
                        if (parts.length >= 3) {
                            const gpuUtil = parseInt(parts[0], 10) || 0;
                            const vramUsedMb = parseFloat(parts[1]) || 0;
                            const vramTotalMb = parseFloat(parts[2]) || 0;
                            const vramUsedGiB = (vramUsedMb / 1024).toFixed(1);
                            this._cachedGpu = {
                                gpuUtil,
                                vramUsedGiB,
                                vramPct: vramTotalMb > 0 ? Math.round((vramUsedMb / vramTotalMb) * 100) : 0,
                            };
                        }
                    }
                } catch (e) {
                    // Ignore subprocess errors
                }
            });
        } catch (e) {
            // Ignore spawn errors
        }
    }

    _updateTelemetry() {
        if (!this._label) return;

        const cpu = this._readCpuUsage();
        const ram = this._readRamUsage();
        this._queryGpuAsync();
        const gpu = this._cachedGpu;

        const cyan = '#29F0F7';
        const slate = '#E2E8F0';
        const amber = '#E5A958';
        const sepColor = '#3B4252';
        const sep = `<span color="${sepColor}"> │ </span>`;

        const cpuColor = cpu > 85 ? amber : slate;
        const ramColor = ram.pct > 85 ? amber : slate;
        const gpuColor = gpu ? (gpu.gpuUtil > 85 ? amber : slate) : slate;
        const vramColor = gpu ? (gpu.vramPct > 85 ? amber : slate) : slate;

        const cpuStr = `<span weight="bold" color="${cyan}">CPU</span> <span color="${cpuColor}">${cpu}%</span>`;
        const ramStr = `<span weight="bold" color="${cyan}">RAM</span> <span color="${ramColor}">${ram.usedGiB}G</span>`;
        const gpuStr = `<span weight="bold" color="${cyan}">GPU</span> <span color="${gpuColor}">${gpu ? gpu.gpuUtil + '%' : '--'}</span>`;
        const vramStr = `<span weight="bold" color="${cyan}">VRAM</span> <span color="${vramColor}">${gpu ? gpu.vramUsedGiB + 'G' : '--'}</span>`;

        this._label.clutter_text.set_markup(
            `<span font_family="JetBrains Mono, monospace" font_size="9.5pt">${cpuStr}${sep}${ramStr}${sep}${gpuStr}${sep}${vramStr}</span>`
        );
    }
}
