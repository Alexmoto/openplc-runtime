# TargetVisu v1.1 — 12 цветных ламп Indicator

Разработка основана на присланном пользователем PNG `Lamp33x33Off.png` (33×33).
В состав Editor и Runtime встроен один PNG-атлас из 12 объёмных цветных ламп
(отдельные файлы на устройстве не нужны).

## Режимы примитива Indicator

В свойствах **Indicator style**:

- `Classic (BOOL)` — прежний эллипс, цвет `fill`/ `activeFill`,
  источник `BOOL`; старые проекты без `indicatorStyle` работают как прежде;
- `12-color lamp (0 = hidden)` — новые изображения 33×33; привязка к
  целочисленной переменной PLC (`SINT`, `USINT`, `BYTE`, `INT`, `UINT`,
  `WORD`, `DINT`, `UDINT`, `DWORD`). 64-битные, REAL/LREAL и BOOL
  в этом режиме не поддерживаются.

| Значение | Индикатор | Значение | Индикатор |
|---:|---|---:|---|
| 0 | **Скрыт** | 1 | Светло-серый |
| 2 | Тёмно-серый | 3 | Светло-зелёный |
| 4 | Тёмно-зелёный | 5 | Светло-красный |
| 6 | Тёмно-красный | 7 | Светло-жёлтый |
| 8 | Тёмно-жёлтый | 9 | Светло-оранжевый |
| 10 | Тёмно-оранжевый | 11 | Светло-синий |
| 12 | Тёмно-синий | | |

Значения вне диапазона 1–12, отрицательные числа и отсутствие
актуального PLC-значения ведут к скрытию изображения. Кнопок или действий записи
в PLC у такой лампы нет. Отдельная прежняя привязка `Visible when TRUE`
по-прежнему может дополнительно скрыть её.

Объёмные блики, металлическая окантовка и прозрачные края взяты из
присланной формы лампы, спрайт автоматически масштабируется без искажения
пропорций и центрируется в прямоугольнике элемента.

Пример ST:

```iecst
VAR_GLOBAL
    LampState : UINT := 0; // 0 = лампа скрыта, 1..12 = выбранный цвет
END_VAR
```

В Editor добавьте **Indicator**, выберите **Indicator style → 12-color lamp**,
затем **Value variable → LampState**. В Preview меняйте значение от 0 до 12.
На Runtime индикатор обновится после следующего опроса PLC.

## Runtime Banana Pi

При использовании отдельной Git-копии репозитория:

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/indicator-lamp12
git switch feature/indicator-lamp12
git pull --ff-only origin feature/indicator-lamp12

python3 updates/targetvisu-lamps-v1.1.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-lamps-v1.1.0/install_update.py --runtime /root/openplc-runtime
```

Если `git status --short` не пуст, сохраните изменения до переключения ветки.
Не используйте `git reset --hard` без резервной копии.

Установщик проверяет синтаксис и обновляет накопительно только Python-модули
TargetVisu: `model.py`, `render.py`, `graphics.py`, `viewer.py`,
`keypad.py` и `lamp_palette.py`; предварительно создаёт каталог
`targetvisu-lamps-backup-...` с прежними версиями. C++-ядро, RETAIN и
PLC-программа не изменяются. **Пересборка `plc_main` не нужна.**

В безопасный для оборудования момент перезапустите графический сеанс:

```bash
systemctl restart lightdm
```

Команда временно отключает локальный HMI.
Для отката восстановите модули из каталога резервной копии, а новый файл
`lamp_palette.py` при необходимости удалите.

Не запускайте после v1.1 старые установщики TargetVisu: они могут
перезаписать новые функции.

## Editor Windows

```cmd
cd /d D:\Project_PLC\OpenPLC_Editor\editor-source
git status --short
git fetch origin feature/indicator-lamp12
git switch feature/indicator-lamp12
git pull --ff-only origin feature/indicator-lamp12
npm run package
```

После установки нового Editor из `dist` соберите и загрузите PLC-проект,
чтобы новая привязка и стиль стали доступны Runtime.

Режим находится в тестовой ветке. До слияния PR в main сначала проверьте
на Banana Pi при корректной связи с PLC: невидимость при 0 и при потере
значения, все 12 цветов, масштабирование и совместимость старых BOOL-индикаторов.
