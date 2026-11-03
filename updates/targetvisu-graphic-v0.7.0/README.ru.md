# TargetVisu Graphic View — изображения по переменной PLC (v0.7.0)

## Возможности

У примитива `Graphic View` теперь есть **Image selector variable** и до **16 состояний изображения**.
Каждое состояние содержит целое значение PLC и PNG-изображение. Редактор принимает PNG/JPEG,
встраивает результат в TargetVisu JSON как PNG, ограничивает каждый PNG до 1 МиБ
и размером до 1024×1024 пикселей. Общий лимит JSON: 4 МиБ.

Пример: `PumpState : INT`; `0` → «остановлен», `1` → «работает», `2` → «авария».
Можно выбрать и `BOOL`: FALSE → 0, TRUE → 1.

Список состояний задаётся напрямую в свойствах примитива:
- назначить для каждого изображения значение переменной;
- загрузить / заменить / удалить изображение;
- указать статическое **Default image** для неизвестного значения PLC;
- выбрать масштабирование `contain`, `cover` или `stretch`.

Если привязка отсутствует, показывается статическое изображение, либо первая картинка
из списка, если статическая не задана. Если привязка есть, но значение отсутствует или
не совпало ни с одним состоянием, показывается статическая картинка; если её нет —
нейтральная серая заглушка. При очередном опросе PLC изображение обновляется автоматически.

Подходящие типы: `BOOL`, `SINT`, `INT`, `DINT`, `USINT`, `UINT`, `UDINT`, `BYTE`,
`WORD`, `DWORD`. Числовые значения состояний: от -2147483648 до 4294967295.
Типы `REAL`, `LREAL`, `LINT`, `ULINT`, `LWORD` для селектора не поддерживаются.

Примитив остаётся **только для отображения**. Обратных записей в PLC нет.
Старый JSON с одиночным изображением `{ "data": "...", "fit": "contain" }` поддерживается.

## Runtime на Banana Pi

Сначала убедитесь, что текущие изменения на Banana Pi сохранены и оборудование
находится в безопасном состоянии перед перезапуском графики. Установщик не перезапускает
PLC или X-сессию автоматически.

```bash
cd /root/openplc-runtime-github
git status --short
git fetch origin feature/graphic-view-image-states
git switch feature/graphic-view-image-states
git pull --ff-only origin feature/graphic-view-image-states
python3 updates/targetvisu-graphic-v0.7.0/install_update.py --runtime /root/openplc-runtime --check
python3 updates/targetvisu-graphic-v0.7.0/install_update.py --runtime /root/openplc-runtime
```

Если `git status --short` не пуст, сохраните локальные изменения прежде чем
переключать ветку (не используйте `git reset --hard`). Если рабочая копия Git
совпадает с установленным Runtime, переключение ветки уже заменит исходники.

В безопасный момент перезапустите графический сеанс:

```bash
systemctl restart lightdm
```

Изменяются только три Python-файла `model.py`, `render.py`, `graphics.py`.
Пересборка `plc_main` не требуется. `viewer.py`, основное приложение PLC,
настройки RETAIN и текущий проект не изменяются.

Установщик предварительно проверяет синтаксис и файлы, создаёт резервную
копию `targetvisu-graphic-backup-...`, позволяет делать `--check`.
Для отката скопируйте сохранённые файлы обратно и перезапустите LightDM.

**Не применяйте затем старый установщик `targetvisu-v0.5.0` или `targetvisu-number-v0.6.0`**,
иначе он может перезаписать новые файлы.

## Editor на Windows

Из исходной Git-копии:

```powershell
cd "D:\Project_PLC\OpenPLC_Editor\editor-source"
git status --short
git fetch origin feature/graphic-view-image-states
git switch feature/graphic-view-image-states
git pull --ff-only origin feature/graphic-view-image-states
npm run package
```

Если `node_modules` нет — сначала `npm ci`. Нужны Node.js 22/23.
Готовый дистрибутив Editor появится в `dist`.
После установки Editor соберите и загрузите проект с новыми свойствами Graphic View.

## Проверки

Исходники развиваются в отдельной ветке `feature/graphic-view-image-states`,
зависящей от `feature/number-dynamic-colors`. Слияние в `main` выполняйте
только после успешной проверки Editor, Runtime и тестирования на Banana Pi.
