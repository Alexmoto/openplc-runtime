# SPDX-License-Identifier: GPL-3.0-only
"""Regression: repeated project uploads must not relocate MQTT's debug-map-bound config."""
from pathlib import Path

from webserver.plugin_config_model import PluginsConfiguration


def test_mqtt_remains_project_scoped_across_uploads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conf_dir = Path('core/generated/conf')
    conf_dir.mkdir(parents=True)
    (conf_dir / 'mqtt.json').write_text('{"version": 1}')
    (conf_dir / 'modbus_master.json').write_text('[]')

    Path('plugins.conf').write_text(
        'mqtt,./core/src/drivers/plugins/python/mqtt/mqtt_plugin.py,0,0,'
        './core/generated/conf/mqtt.json,./venvs/mqtt\n'
        'modbus_master,./core/src/drivers/plugins/python/modbus_master/modbus_master_plugin.py,'
        '0,0,./core/src/drivers/plugins/python/modbus_master/modbus_master.json,./venvs/modbus_master\n'
    )

    for version in (1, 2):
        (conf_dir / 'mqtt.json').write_text('{"version": ' + str(version) + '}')
        plugins = PluginsConfiguration.from_file()
        updated, messages = plugins.update_plugins_from_config_dir(
            str(conf_dir), copy_to_plugin_dirs=True
        )
        assert updated >= 0
        mqtt = plugins.get_plugin('mqtt')
        modbus = plugins.get_plugin('modbus_master')
        assert mqtt.enabled
        assert mqtt.config_path == 'core/generated/conf/mqtt.json'
        assert not Path('core/src/drivers/plugins/python/mqtt/mqtt.json').exists()
        assert modbus.enabled
        assert modbus.config_path == (
            'core/src/drivers/plugins/python/modbus_master/modbus_master.json'
        )
        assert Path(modbus.config_path).read_text() == '[]'
        assert plugins.to_file()

    # Disabling MQTT in Editor (config omitted) must disable its plugin.
    (conf_dir / 'mqtt.json').unlink()
    plugins = PluginsConfiguration.from_file()
    plugins.update_plugins_from_config_dir(str(conf_dir), copy_to_plugin_dirs=True)
    assert not plugins.get_plugin('mqtt').enabled
    assert plugins.get_plugin('modbus_master').enabled
