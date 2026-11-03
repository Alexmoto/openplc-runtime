# TargetVisu v1.0 — Number Output / Input + Output и цифровая клавиатура

## Новый режим Number

В OpenPLC Editor выделите примитив **Number**, затем выберите **Number mode**:

- **Output (display only)** — только отображает число из PLC; нажатие ничего не записывает;
- **Input + Output (touch keypad)** — отображает текущее число и позволяет изменять его нажатием.

Выберите **Value variable** — переменную PLC, которую нужно читать и изменять. В режиме
Input + Output параметр должен быть **записываемой числовой** переменной.
Редактор автоматически создаёт действие `write` на ту же переменную.
Разные переменные для отображения и записи в данном режиме не допускаются.

Для чисел используются существующие параметры `Minimum`, `Maximum`, `Decimals`
и привязка `Enabled when TRUE`. После нажатия Number на экране HMI появляется
модальная цифровая клавиатура:

- цифры 0–9, `C` (очистить), `⌫` (стереть), `±` (знак);
- точка для типов `REAL` и `LREAL`; для целочисленных типов точка недоступна;
- **Отмена** ничего не записывает;
- **Записать** проверяет диапазон Number и допустимость значения для типа PLC,
  затем отправляет его существующему механизму TargetVisu;
- при ошибке ввода клавиатура остаётся открытой и показывает причину.

Поддерживаются `SINT`, `USINT`, `INT`, `UINT`, `DINT`, `UDINT`,
`LINT`, `ULINT`, `BYTE`, `WORD`, `DWORD`, `LWORD`, `REAL`, `LREAL`.
`BOOL` в Number Input + Output не поддерживается. На Banana Pi ввод
64-битных целых использует целочисленную арифметику Python без потери точности.

Запись **невозможна**, если PLC отключён, экранный элемент скрыт или запрещён
через `Enabled when TRUE`, цель записи неизменяема, число не проходит проверку
диапазона либо подпись компилированной программы не совпадает.
Runtime повторно проверяет запись на стороне брокера после подтверждения пользователем.

Совместимость: старые проекты без `numberMode` читаются как прежде.
Старые Number с `action.kind = write` продолжают работать и открывают
новую цифровую клавиатуру.

## Runtime на Banana Pi

Сначала сохраните несохранённые локальные изменения, если они есть.
Рекомендуется использовать отдельную Git-копию, не ту, из которой в данный момент
запущен Runtime:

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/number-touch-keypad
git switch feature/number-touch-keypad
git pull --ff-only origin feature/number-touch-keypad
python3 updates/targetvisu-number-input-v1.0.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-number-input-v1.0.0/install_update.py --runtime /root/openplc-runtime
```

Скрипт резервирует прежние Python-файлы, обновляет `model.py` и `viewer.py`
и добавляет `keypad.py`. Если папка Git и рабочая папка Runtime совпадают, переключение
ветки изменяет код ещё до запуска установщика — в этом случае используйте резервную
копию Git-коммита для отката.

Затем в безопасный для оборудования момент:

```bash
systemctl restart lightdm
```

Эта команда прерывает локальный графический сеанс TargetVisu.
**Пересборка `plc_main` не нужна**. `RETAIN`, OPC DA, C++ и PLC-программа
не меняются. Сборка PLC-программы нужна, когда вы обновляете её HMI-настройки
и загружаете новый проект из Editor.

## Editor на Windows

Из рабочей Git-копии:

```powershell
cd "D:\Project_PLC\OpenPLC_Editor\editor-source"
git status --short
git fetch origin feature/number-touch-keypad
git switch feature/number-touch-keypad
git pull --ff-only origin feature/number-touch-keypad
npm run package
```

Если нет `node_modules`, сначала запустите `npm ci` (Node.js 22–23).
Установите результат из папки `dist`. В режиме Preview нажатие Number
открывает такую же цифровую клавиатуру; в Preview изменения остаются
**только локальными** и не посылаются контроллеру.

Новая ветка построена на `feature/transparent-button-number`, поэтому включает
предыдущие изменения: прозрачные Button/Number, фон-картинки, Graphic View по
переменной и цвета Number.

## Испытания

Перед вводом в эксплуатацию проверьте на тестовом PLC:
- ввод целого и дробного числа, положительного и отрицательного;
- выход за минимум/максимум и диапазон типа PLC;
- отмену без записи, подтверждение, исчезновение связи и `Enabled=FALSE`;
- прозрачный Number на фоне изображения;
- корректность обратного чтения установленного значения после очередного опроса PLC.

Пока PR открыт как draft, изменения на настоящей HMI-панели не подтверждены.
