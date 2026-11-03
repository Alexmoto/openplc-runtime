# Обновления TargetVisu

[TargetVisu 0.4.0 — переключение экранов кнопками](targetvisu-v0.4.0/README.ru.md)

Здесь опубликован пакет обновления для уже установленного OpenPLC Runtime с TargetVisu Autostart v0.3.0. Это не полные исходники Runtime и не самостоятельная сборка. C++-ядро и RETAIN пакет не изменяет.

Скачайте репозиторий, перейдите в `updates/targetvisu-v0.4.0`, затем выполните на плате:

```sh
python3 install_update.py --runtime /root/openplc-runtime --check
python3 install_update.py --runtime /root/openplc-runtime
```

Editor: https://github.com/Alexmoto/openplc-targetvisu
