# OpenPLC TargetVisu Runtime 0.1.0 — GTK/Cairo, X11

Продолжение Editor TargetVisu 0.1.0/0.1.1. Это первая рабочая версия для Linux:
отдельное нативное окно GTK 3, без браузера и Electron. Python-сервис обмена
работает отдельно от окна и от потоков выполнения ПЛК.

Поддерживается: rectangle, ellipse, line, text, indicator, button, number;
видимость/доступность по BOOL, несколько экранов, стартовый экран, масштабирование
с сохранением пропорций, set/toggle/momentary, диалог числового ввода.
Привязки: BOOL и числовые IEC-типы от 8 до 64 бит, REAL/LREAL.
STRING/WSTRING и составные типы в этой версии отклоняются при проверке.
До 1000 разных привязанных скалярных переменных. Тексты элементов — UTF-8,
включая русский. Переход между экранами — через список в верхней панели.

## Сначала DEMO на Banana Pi, через существующее SSH/X11

Распакуйте архив в `/root/targetvisu_runtime` (внутри должны быть
`install_runtime.py` и каталог `targetvisu`). В Cygwin/X подключитесь, как раньше:

```sh
ssh -Y root@192.168.1.89
```

На плате:

```sh
apt update
apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
cd /root/targetvisu_runtime
python3 -m targetvisu check --document targetvisu/example.targetvisu.json --debug-map targetvisu/example.debug-map.json
python3 -m targetvisu serve --demo --document targetvisu/example.targetvisu.json --debug-map targetvisu/example.debug-map.json
```

Оставьте сервис работающим. Во втором SSH-сеансе с `ssh -Y`:

```sh
cd /root/targetvisu_runtime
python3 -m targetvisu view --demo --document targetvisu/example.targetvisu.json --debug-map targetvisu/example.debug-map.json
```

Откроется насосная станция: START/STOP переключают индикатор, щелчок по правому
числовому полю задаёт Setpoint, Pressure повторяет уставку. Надпись DEMO обязательна:
этот режим не подключается к ПЛК. Пересборка Runtime для DEMO не нужна.
Выйти из полноэкранного режима можно закрытием окна через менеджер окон;
первый запуск делайте без `--fullscreen`.

## Установка расширения в настоящий Runtime

Остановите демонстрационный сервис Ctrl+C перед запуском рабочего сервиса.

```sh
cd /root/targetvisu_runtime
python3 install_runtime.py --runtime /root/openplc-runtime --check
python3 install_runtime.py --runtime /root/openplc-runtime
```

Установщик проверяет все файлы до записи и сохраняет резервную копию.
Если исходники ядра отличаются, он ничего не меняет. Пришлите сообщение ошибки;
не удаляйте проверки и не применяйте патч вслепую. Изменение только первой строки
SPDX MIT/GPL-3.0 допускается с сохранением вашей строки лицензии.
Установщик не трогает Modbus diagnostics и настройки Runtime.

Для рабочего режима НУЖНА пересборка C/C++-ядра. Просто перезапустить Python
недостаточно. Модуль использует обычную запись, которой нет в старом протоколе.
После успешной проверки установщика, в период, когда можно остановить ПЛК:

```sh
systemctl stop openplc-runtime
cmake -S /root/openplc-runtime -B /root/openplc-runtime/build
cmake --build /root/openplc-runtime/build --target plc_main -j1
systemctl start openplc-runtime
```

`openplc-runtime` — имя службы из штатного install.sh. Если Runtime запущен другим способом,
останавливайте и запускайте его тем же способом. Не запускайте второй `plc_main`
параллельно штатному. На плате с 452 МБ RAM используйте `-j1`.
Если CMake сообщает о несовместимом старом build-кэше, используйте отдельный каталог
сборки и проверьте путь бинарника в вашем запускном скрипте; не стирайте настройки.

Проверка нового канала:

```sh
ls -l /run/runtime/targetvisu/core.sock
```

У ядра появляется отдельный локальный Unix-сокет. Штатный сокет вебсервера
`plc_runtime.socket` остаётся за вебсервером: его постоянное соединение не мешает
обмену TargetVisu. Новых TCP-портов и X-сервера на плате для SSH/X11 не требуется.

## Свой проект: связь Editor → Runtime

1. В Editor сохраните проект, экспортируйте `targetvisu.json` из TargetVisu.
2. Скомпилируйте проект для `OpenPLC Runtime v4` и загрузите его в Runtime.
3. Возьмите `debug-map.json` именно от этой компиляции. Для локального проекта он
   находится в `<проект>/build/<boardTarget>/src/debug-map.json`; найдите файл в
   каталоге build проекта. Для облачного проекта это build workspace Editor.
4. Передайте оба JSON на плату в `/root/targetvisu-project/`. Например, через `scp`
   из Cygwin. Карта из демонстрации не подходит к вашей программе.
5. Включите программу в RUN штатным способом.

Проверка и запуск сервиса на плате:

```sh
cd /root/openplc-runtime/tools
python3 -m targetvisu check --document /root/targetvisu-project/targetvisu.json --debug-map /root/targetvisu-project/debug-map.json
python3 -m targetvisu serve --document /root/targetvisu-project/targetvisu.json --debug-map /root/targetvisu-project/debug-map.json
```

Окно из другого SSH/X11-сеанса:

```sh
cd /root/openplc-runtime/tools
python3 -m targetvisu view --document /root/targetvisu-project/targetvisu.json --debug-map /root/targetvisu-project/debug-map.json
```

Для локального экрана используйте те же команды из графического сеанса платы,
при желании добавьте `--fullscreen` к `view`. Не задавайте DISPLAY вручную при
SSH-forwarding: значение `localhost:10.0` выставляет SSH.

Окно и сервис запускайте от одного пользователя. По умолчанию сокет брокера —
`/run/openplc-targetvisu/control.sock`, доступ только владельцу. Сокет ядра также
закрыт для других пользователей. Для запуска от другого пользователя настройте
права осознанно, не делайте сокеты общедоступными. Для DEMO от обычного пользователя
можно передать обоим процессам `--broker-socket /tmp/my-targetvisu/control.sock`.

После изменения ST или привязок остановите окно/сервис, заново экспортируйте JSON,
скомпилируйте и передайте согласованную пару файлов. Автоматическая передача
TargetVisu при Upload и автозапуск окна в этой версии ещё не реализованы.

## Семантика и ограничения

- Адреса берутся из compiler debug-map v2. Имена сопоставляются без учёта регистра,
  без поиска по суффиксу и без подстановки адресов. Например `Pump1.Pressure`,
  а не имя типа PROGRAM. Неизвестный символ — ошибка запуска.
- Идентификатор MD5 проверяется в ядре при каждом чтении и записи. Это идентификатор
  сборки, не механизм криптографической аутентификации. Клиенту нужен новый core.
- Запись обычная (`IECVar::set` / журнал образа), не FORCE. Подтверждение означает
  «поставлено в очередь», а не «программа подтвердила команду». Активный force
  сохраняет приоритет; ST может перезаписать значение своим следующим присваиванием.
  Для управления используйте отдельные Request-переменные, как в примере Editor.
- Входы %I запрещены ядром. Константы/readonly из карты также запрещены сервисом;
  обычная карта compiler v2 может не содержать этих флагов, поэтому используйте
  JSON, проверенный Editor. Сервис разрешает только действия объявленных элементов,
  произвольного API записи адреса у окна нет.
- Toggle использует свежее прочитанное значение. Это не атомарная IEC-операция
  read-modify-write относительно ST или других внешних клиентов.
- Чтение удерживает блокировку жизненного цикла программы. Это не единый атомарный
  снимок всех переменных параллельно работающих IEC-задач, как и штатный debugger.
- При STOP, смене проекта, потере связи значения скрыты, действия заблокированы.
  Запоздалые команды окна после разрыва не воспроизводятся при переподключении.
- Momentary: FALSE при отпускании, уходе указателя/фокуса, смене экрана, закрытии
  окна или разрыве его соединения. Сервис продлевает аренду удержания heartbeat-ом;
  без heartbeat она истекает через `max(1 секунды, 3 × refreshMs)`, плюс период
  опроса и задержки I/O. При недоступном ядре сброс повторяется после восстановления
  связи с той же сборкой. При аварии самого сервиса/ОС сброс гарантировать нельзя:
  если это существенно для управления механизмом, нужен таймаут команды в ST.
- В этой версии целевые Runtime — Linux little-endian, включая ARMv7/ARM64/x86_64.
  Проверена сборка x86_64; на Banana Pi и физическом оборудовании ещё не проверено.

## Проверки и откат

```sh
cd /root/openplc-runtime
PYTHONPATH=tools python3 -m unittest discover -s tools/targetvisu/tests -p 'test_*.py' -v
sh tools/targetvisu/tests/run_core_tests.sh
```

GTK-тест требует работающего DISPLAY и использует DEMO:

```sh
cd /root/openplc-runtime/tools
python3 targetvisu/tests/gtk_smoke.py /tmp/targetvisu-test.png
```

Для отката остановите Runtime, восстановите четыре файла ядра из каталога
`targetvisu.backup.<timestamp>/core/src/plc_app/`, пересоберите ядро, затем запустите
штатную службу. Каталог `tools/targetvisu` можно убрать отдельно.
