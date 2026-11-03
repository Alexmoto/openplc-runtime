# TargetVisu Number — цвета PLC и скругление рамки (v0.6.0)

Эта версия добавляет к примитиву Number:
- три независимые привязки к PLC-переменным целочисленного типа: цвет фона (`fill`), цвет рамки (`stroke`), цвет текста (`textColor`);
- статические цвета по умолчанию при пустой привязке или отсутствующем значении;
- `Border width` (существующее свойство `strokeWidth`, 0–20 px);
- `Border radius` (новое свойство `borderRadius`, 0–100 px).

Значение цвета: `DWORD := 16#RRGGBB` (например, `16#00FF00` для зелёного).
При обновлении Runtime значение маскируется по младшим 24 битам, т.е. `0xRRGGBB`.
Для цвета используются целочисленные IEC-типы, включая `WORD` и `DWORD`. Тип `BOOL`, `REAL`, `LREAL` не поддерживается.

## Обязательная последовательность

Обновить исходники Editor и Runtime, затем **пересобрать Editor** и **повторно скомпилировать/загрузить проект PLC**, чтобы его опубликованный TargetVisu JSON содержал новые поля и привязки.

Не запускайте старый Runtime с проектом, использующим новые цветовые привязки: он не умеет их отрисовывать.

## Runtime на Banana Pi

В каталоге git-копии `openplc-runtime` (не обязательно в работающем каталоге):

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/number-dynamic-colors
git switch feature/number-dynamic-colors
git pull --ff-only origin feature/number-dynamic-colors
python3 updates/targetvisu-number-v0.6.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-number-v0.6.0/install_update.py --runtime /root/openplc-runtime
```

**Если `git status --short` показывает изменения**, не переключайте ветку, пока не сохраните их отдельным коммитом или в резервную копию. Если работающий каталог и git-копия совпадают, файлы будут обновлены при переключении ветки, а установщик увидит их как актуальные.

После проверки и при допустимой остановке графики:

```bash
systemctl restart lightdm
```

Это завершит текущий графический сеанс, поэтому команда отключит локальный интерфейс HMI на время перезапуска. Выполнять только при безопасном состоянии оборудования.

Скрипт обновляет лишь `tools/targetvisu/model.py` и `tools/targetvisu/render.py`; `plc_main`, параметры RETAIN, данные проекта, сервисы и `viewer.py` не меняет. При установке сохраняет резервную копию `targetvisu-number-backup-...` внутри целевого каталога. Для отката скопируйте из неё два файла обратно и перезапустите графический сеанс.

**Не применяйте повторно старый установщик `updates/targetvisu-v0.5.0/install_update.py`**: он содержит предыдущие копии Python-файлов.

## Editor на Windows

В git-копии `openplc-targetvisu`:

```powershell
git status --short
git fetch origin feature/number-dynamic-colors
git switch feature/number-dynamic-colors
git pull --ff-only origin feature/number-dynamic-colors
npm run package
```

Если нет `node_modules`, сначала `npm ci`. Требуются Node.js 22/23 и npm 10+. После сборки установите сгенерированную версию Editor на Windows.

## Совместимость

Старые документы TargetVisu без свойств `borderRadius` и `bindings.fill/stroke/textColor` принимаются: используется радиус 0 и неизменные цвета. Новые файлы создаются сразу с тремя пустыми привязками. Важные переменные PLC не должны иметь некорректные типы: компилятор Editor проверяет их до загрузки.

## Тестирование

Тесты и проверка GitHub Actions запускаются отдельно. До подтверждения на аппаратной Banana Pi и в установленном Windows Editor обновление считать тестовым. Если возникнет проблема, восстановить файлы из резервной копии и вернуться на предыдущий Editor.
